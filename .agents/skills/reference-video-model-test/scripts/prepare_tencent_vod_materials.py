#!/usr/bin/env python3
"""Prepare Tencent VOD reviewed materials for reference-video model tests."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clients.factory import get_aigc_client  # noqa: E402
from config.secrets_loader import load_and_validate_secrets  # noqa: E402
from utils.oss.uploader import upload_from_local  # noqa: E402


REQUIRED_CREDENTIALS = [
    "SECRET_ID_TENCENT_VOD",
    "SECRET_KEY_TENCENT_VOD",
    "SUB_APP_ID_TENCENT_VOD",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def new_state() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": f"rvmt-material-{uuid.uuid4().hex[:12]}",
        "created_at": utc_now(),
        "liveness": {},
        "materials": {},
    }


def load_state(path: Path) -> dict[str, Any]:
    return read_json(path) if path.exists() else new_state()


def response_value(response: dict[str, Any], *parts: str) -> Any:
    current: Any = response
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            raise KeyError("response path not found: " + ".".join(parts))
        current = current[part]
    return current


def collect_referenced_assets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    asset_by_name = {str(item["name"]): item for item in manifest.get("assets") or []}
    ordered_names: list[str] = []
    seen: set[str] = set()
    for scene in manifest.get("scenes") or []:
        for reference in scene.get("references") or []:
            name = str(reference["name"])
            if name not in seen:
                seen.add(name)
                ordered_names.append(name)
    missing = [name for name in ordered_names if name not in asset_by_name]
    if missing:
        raise ValueError(f"manifest references unknown assets: {missing}")
    return [asset_by_name[name] for name in ordered_names]


def resolve_group_id(
    state: dict[str, Any],
    *,
    is_real_person: bool,
    explicit_group_id: str | None,
) -> str:
    """Resolve the provider group without silently bypassing real-person liveness."""
    if is_real_person:
        group_id = str(state.get("group_id") or "").strip()
        if not group_id:
            raise ValueError("liveness is not complete; GroupId is unavailable")
        return group_id
    group_id = str(explicit_group_id or state.get("non_real_group_id") or "").strip()
    if not group_id:
        raise ValueError("--group-id is required when --is-real-person=false")
    return group_id


class TencentVodTestProtocol:
    """Skill-local access to signed Tencent VOD actions through the existing client."""

    def __init__(self) -> None:
        self.client = get_aigc_client(provider="hunyuan", task_type="video")

    async def call(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.client._request(action, payload)  # noqa: SLF001 - test protocol adapter
        if not isinstance(result, dict):
            raise RuntimeError(f"Tencent VOD {action} response must be an object")
        return result

    async def close(self) -> None:
        http = getattr(self.client, "_client", None)
        if http is not None and hasattr(http, "aclose"):
            await http.aclose()


async def start_liveness(
    state_path: Path,
    callback_url: str | None = None,
    renew: bool = False,
) -> dict[str, Any]:
    state = load_state(state_path)
    existing = state.get("liveness") or {}
    if existing.get("token") and existing.get("h5_link") and not renew:
        return {
            "status": "DONE" if state.get("group_id") else "PENDING_USER_ACTION",
            "h5_link": existing["h5_link"],
            "group_id": state.get("group_id"),
            "reused": True,
        }
    if renew and existing:
        state.setdefault("liveness_history", []).append(
            {
                "status": "EXPIRED",
                "request_id": existing.get("request_id"),
                "created_at": existing.get("created_at"),
                "expired_at": utc_now(),
            }
        )
        state["liveness"] = {}
        state.pop("group_id", None)
        write_json(state_path, state)

    load_and_validate_secrets(required_keys=REQUIRED_CREDENTIALS)
    protocol = TencentVodTestProtocol()
    payload = {"CallbackUrl": callback_url} if callback_url else {}
    try:
        try:
            response = await protocol.call("CreateAigcLivenessValidate", payload)
        except Exception as exc:
            state["liveness"] = {
                "status": "CREATE_UNKNOWN",
                "updated_at": utc_now(),
                "error_type": type(exc).__name__,
            }
            write_json(state_path, state)
            raise RuntimeError("liveness create result is unknown; do not resubmit automatically") from exc
        h5_link = str(response_value(response, "Response", "H5Link")).strip()
        token = str(response_value(response, "Response", "LivenessToken")).strip()
        if not h5_link or not token:
            raise RuntimeError("liveness create response contains an empty H5Link or LivenessToken")
        state["liveness"] = {
            "status": "PENDING_USER_ACTION",
            "h5_link": h5_link,
            "token": token,
            "request_id": response.get("Response", {}).get("RequestId"),
            "created_at": utc_now(),
        }
        write_json(state_path, state)
        return {"status": "PENDING_USER_ACTION", "h5_link": h5_link, "group_id": None, "reused": False}
    finally:
        await protocol.close()


async def check_liveness(state_path: Path) -> dict[str, Any]:
    state = load_state(state_path)
    if state.get("group_id"):
        return {"status": "DONE", "group_id": state["group_id"]}
    liveness = state.get("liveness") or {}
    token = str(liveness.get("token") or "")
    if not token:
        raise ValueError("liveness has not been started")
    if liveness.get("status") == "CREATE_UNKNOWN":
        raise RuntimeError("liveness create result is unknown; inspect provider before continuing")

    load_and_validate_secrets(required_keys=REQUIRED_CREDENTIALS)
    protocol = TencentVodTestProtocol()
    try:
        response = await protocol.call(
            "DescribeAigcLivenessValidateResult",
            {"LivenessToken": token},
        )
    finally:
        await protocol.close()
    result = response.get("Response") or {}
    status = str(result.get("Status") or "").upper()
    liveness.update(
        {
            "status": status or "UNKNOWN",
            "message": str(result.get("Message") or "")[:300],
            "request_id": result.get("RequestId"),
            "updated_at": utc_now(),
        }
    )
    state["liveness"] = liveness
    if status == "DONE":
        group_id = str(result.get("GroupId") or "").strip()
        if not group_id:
            raise RuntimeError("completed liveness response contains an empty GroupId")
        state["group_id"] = group_id
    write_json(state_path, state)
    return {"status": status or "UNKNOWN", "group_id": state.get("group_id")}


async def prepare_materials(
    state_path: Path,
    manifest_path: Path,
    registry_path: Path,
    concurrency: int,
    poll_timeout: int,
    poll_interval: float,
    group_name: str,
    group_description: str,
    is_real_person: bool,
    explicit_group_id: str | None,
) -> dict[str, Any]:
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    state = load_state(state_path)
    group_id = resolve_group_id(
        state,
        is_real_person=is_real_person,
        explicit_group_id=explicit_group_id,
    )
    if not is_real_person:
        state["non_real_group_id"] = group_id
        write_json(state_path, state)
    manifest = read_json(manifest_path)
    assets = collect_referenced_assets(manifest)
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(concurrency)
    load_and_validate_secrets(required_keys=REQUIRED_CREDENTIALS)
    protocol = TencentVodTestProtocol()

    async def save_material(key: str, **values: Any) -> dict[str, Any]:
        async with lock:
            item = state.setdefault("materials", {}).setdefault(key, {})
            item.update(values)
            write_json(state_path, state)
            return dict(item)

    async def prepare_one(asset: dict[str, Any]) -> dict[str, Any]:
        source = Path(str(asset["path"])).resolve()
        digest = sha256_file(source)
        key = f"{group_id}:{digest}"
        current = state.setdefault("materials", {}).get(key) or {}
        if current.get("asset_uri"):
            return current
        if current.get("status") == "CREATE_UNKNOWN" and not current.get("task_id"):
            raise RuntimeError(f"material {asset['name']} has an ambiguous create attempt")

        async with semaphore:
            upload_url = str(current.get("upload_url") or "")
            if not upload_url:
                upload_started = time.time()
                upload_url = await asyncio.to_thread(
                    upload_from_local,
                    str(source),
                    state["run_id"],
                    source.suffix.lower(),
                )
                current = await save_material(
                    key,
                    name=asset["name"],
                    file=asset["file"],
                    path=str(source),
                    sha256=digest,
                    group_id=group_id,
                    is_real_person=is_real_person,
                    upload_url=upload_url,
                    upload_seconds=round(time.time() - upload_started, 3),
                    status="UPLOADED",
                )

            task_id = str(current.get("task_id") or "")
            if not task_id:
                payload = {
                    "FileInfo": {"Type": "Url", "Url": upload_url},
                    "AssetType": "Image",
                    "GroupId": group_id,
                    "AssetName": str(asset["name"]),
                    "IsRealPerson": "True" if is_real_person else "False",
                    "GroupName": group_name,
                    "GroupDescription": group_description,
                }
                try:
                    response = await protocol.call("CreateAigcMaterial", payload)
                except Exception as exc:
                    await save_material(
                        key,
                        status="CREATE_UNKNOWN",
                        error_type=type(exc).__name__,
                        updated_at=utc_now(),
                    )
                    raise RuntimeError(
                        f"material {asset['name']} create result is unknown; do not resubmit automatically"
                    ) from exc
                task_id = str(response_value(response, "Response", "TaskId")).strip()
                if not task_id:
                    raise RuntimeError(f"material {asset['name']} create response contains an empty TaskId")
                current = await save_material(
                    key,
                    task_id=task_id,
                    status="SUBMITTED",
                    submitted_at=utc_now(),
                )

            deadline = time.time() + poll_timeout
            final: dict[str, Any] | None = None
            while time.time() < deadline:
                response = await protocol.call("DescribeTaskDetail", {"TaskId": task_id})
                top_status = str(response_value(response, "Response", "Status")).upper()
                nested = (response.get("Response") or {}).get("CreateAigcMaterialTask") or {}
                nested_status = str(nested.get("Status") or top_status).upper()
                await save_material(key, status=nested_status, last_polled_at=utc_now())
                if top_status == "FINISH" or nested_status == "FINISH":
                    final = response
                    break
                if top_status == "ABORTED" or nested_status == "ABORTED":
                    raise RuntimeError(f"material {asset['name']} task ended with status ABORTED")
                await asyncio.sleep(poll_interval)
            if final is None:
                raise TimeoutError(f"material {asset['name']} polling exceeded {poll_timeout} seconds")
            material_task = (final.get("Response") or {}).get("CreateAigcMaterialTask") or {}
            error_code = int(material_task.get("ErrCode") or 0)
            if error_code != 0:
                raise RuntimeError(
                    f"material {asset['name']} failed with provider error code {error_code}"
                )
            asset_id = str((material_task.get("Output") or {}).get("AssetId") or "").strip()
            if not asset_id:
                raise RuntimeError(f"material {asset['name']} completed without AssetId")
            return await save_material(
                key,
                status="SUCCEEDED",
                asset_id=asset_id,
                asset_uri=f"asset://{asset_id}",
                completed_at=utc_now(),
                provider_create_time=(final.get("Response") or {}).get("CreateTime"),
                provider_finish_time=(final.get("Response") or {}).get("FinishTime"),
            )

    try:
        prepared = await asyncio.gather(*[prepare_one(asset) for asset in assets])
    finally:
        await protocol.close()
    registry = {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "group_id": group_id,
        "is_real_person": is_real_person,
        "manifest": str(manifest_path.resolve()),
        "assets": [
            {
                "name": item["name"],
                "file": item["file"],
                "path": item["path"],
                "sha256": item["sha256"],
                "asset_id": item["asset_id"],
                "asset_uri": item["asset_uri"],
                "upload_url": item.get("upload_url"),
                "material_task_id": item["task_id"],
                "upload_seconds": item.get("upload_seconds"),
                "provider_create_time": item.get("provider_create_time"),
                "provider_finish_time": item.get("provider_finish_time"),
            }
            for item in prepared
        ],
    }
    write_json(registry_path, registry)
    return {
        "status": "SUCCEEDED",
        "group_id": group_id,
        "asset_count": len(registry["assets"]),
        "registry": str(registry_path.resolve()),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start-liveness")
    start.add_argument("--state", required=True, type=Path)
    start.add_argument("--callback-url")
    start.add_argument("--renew", action="store_true")
    check = subparsers.add_parser("check-liveness")
    check.add_argument("--state", required=True, type=Path)
    materials = subparsers.add_parser("prepare-materials")
    materials.add_argument("--state", required=True, type=Path)
    materials.add_argument("--manifest", required=True, type=Path)
    materials.add_argument("--registry", required=True, type=Path)
    materials.add_argument("--concurrency", type=int, default=4)
    materials.add_argument("--poll-timeout", type=int, default=1800)
    materials.add_argument("--poll-interval", type=float, default=10.0)
    materials.add_argument("--group-name", default="reference-video-model-test")
    materials.add_argument("--group-description", default="WAND-Vega 1.0-pro test materials")
    materials.add_argument("--group-id")
    materials.add_argument("--is-real-person", choices=("true", "false"), default="true")
    return parser.parse_args()


async def execute(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "start-liveness":
        return await start_liveness(args.state.resolve(), args.callback_url, args.renew)
    if args.command == "check-liveness":
        return await check_liveness(args.state.resolve())
    return await prepare_materials(
        args.state.resolve(),
        args.manifest.resolve(),
        args.registry.resolve(),
        args.concurrency,
        args.poll_timeout,
        args.poll_interval,
        args.group_name,
        args.group_description,
        args.is_real_person == "true",
        args.group_id,
    )


def main() -> int:
    args = parse_args()
    try:
        result = asyncio.run(execute(args))
    except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"Tencent VOD material preparation failed: {type(exc).__name__}: {exc}\n")
        return 2
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
