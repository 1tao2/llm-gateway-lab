#!/usr/bin/env python3
"""Run a preflighted reference-video test from a declarative call spec."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.secrets_loader import load_and_validate_secrets  # noqa: E402
from clients.factory import get_aigc_client  # noqa: E402
from utils.oss.uploader import upload_from_bytes, upload_from_local, upload_from_url_stream  # noqa: E402


TOKEN_RE = re.compile(r"<<<(.*?)>>>")
TEMPLATE_RE = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
SECRET_HEADER_NAMES = {"authorization", "x-api-key", "api-key", "x-auth-token"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--call-spec", required=True, type=Path)
    parser.add_argument("--asset-registry", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--poll-timeout", type=int, default=1800)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--variant", default="首次生成")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_path(value: Any, path: str, *, required: bool = True) -> Any:
    current = value
    for part in (path or "").split("."):
        if not part:
            continue
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        elif required:
            raise KeyError(f"response path not found: {path}")
        else:
            return None
    return current


def render_template(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: render_template(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_template(item, context) for item in value]
    if not isinstance(value, str):
        return value
    exact = TEMPLATE_RE.fullmatch(value)
    if exact:
        key = exact.group(1)
        if key not in context:
            raise KeyError(f"unknown template variable: {key}")
        return context[key]

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise KeyError(f"unknown template variable: {key}")
        return str(context[key])

    return TEMPLATE_RE.sub(replace, value)


def validate_public_https_url(url: str, allowed_hosts: set[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"API URL must be credential-free HTTPS: {url}")
    host = parsed.hostname.lower()
    if host not in allowed_hosts:
        raise ValueError(f"API host {host!r} is not listed in transport.allowed_hosts")
    if host in {"localhost", "localhost.localdomain"}:
        raise ValueError("localhost API endpoints are not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("private, loopback, and link-local API addresses are not allowed")


def validate_call_spec(spec: dict[str, Any]) -> None:
    if spec.get("schema_version") != "1.0":
        raise ValueError("call spec schema_version must be 1.0")
    transport = spec.get("transport") or {}
    kind = transport.get("kind")
    if kind not in {"http", "project_client"}:
        raise ValueError("transport.kind must be http or project_client")
    if kind == "http":
        allowed_hosts = {str(item).strip().lower() for item in transport.get("allowed_hosts") or [] if str(item).strip()}
        if not allowed_hosts:
            raise ValueError("transport.allowed_hosts must not be empty")
        for section_name in ("create", "query"):
            section = spec.get(section_name) or {}
            method = str(section.get("method") or "").upper()
            if method not in {"GET", "POST"}:
                raise ValueError(f"{section_name}.method must be GET or POST")
            validate_public_https_url(str(section.get("url") or ""), allowed_hosts)
        static_headers = transport.get("headers") or {}
        for name in static_headers:
            if str(name).strip().lower() in SECRET_HEADER_NAMES:
                raise ValueError(f"secret header {name!r} must be configured through transport.auth, not stored in call spec")
        auth = transport.get("auth") or {"type": "none"}
        auth_type = auth.get("type")
        if auth_type not in {"none", "bearer_env", "header_env"}:
            raise ValueError("transport.auth.type must be none, bearer_env, or header_env")
        if auth_type != "none":
            env_name = str(auth.get("env") or "")
            if not ENV_NAME_RE.fullmatch(env_name):
                raise ValueError("transport.auth.env must be an uppercase environment variable name")
        if auth_type == "header_env" and not str(auth.get("header") or "").strip():
            raise ValueError("transport.auth.header is required for header_env")
    else:
        if not str(transport.get("provider") or "").strip():
            raise ValueError("transport.provider is required for project_client")
        if not str(transport.get("task_type") or "").strip():
            raise ValueError("transport.task_type is required for project_client")
        factory_provider = str(transport.get("factory_provider") or transport.get("provider") or "")
        if not factory_provider.strip():
            raise ValueError("transport.factory_provider must not be empty when provided")
        for env_name in transport.get("credential_envs") or []:
            if not ENV_NAME_RE.fullmatch(str(env_name)):
                raise ValueError("transport.credential_envs must contain uppercase environment variable names")
        for section_name in ("create", "query"):
            method = str((spec.get(section_name) or {}).get("method") or "")
            if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", method) or method.startswith("_"):
                raise ValueError(f"{section_name}.method must be a public client method name")
    query = spec.get("query") or {}
    for field in ("status_path", "task_id_path", "video_url_path"):
        owner = spec.get("create") if field == "task_id_path" else query
        if not str((owner or {}).get(field) or "").strip():
            raise ValueError(f"missing required call spec field: {field}")
    if not query.get("success_values") or not query.get("failure_values"):
        raise ValueError("query.success_values and query.failure_values must not be empty")
    media = spec.get("media") or {}
    if not isinstance(media.get("item_template"), dict):
        raise ValueError("media.item_template must be an object")
    alpha_policy = str((spec.get("assets") or {}).get("alpha_policy") or "flatten_white_jpeg")
    if alpha_policy not in {"preserve", "flatten_white_jpeg"}:
        raise ValueError("assets.alpha_policy must be preserve or flatten_white_jpeg")


def build_auth_headers(spec: dict[str, Any]) -> dict[str, str]:
    transport = spec["transport"]
    headers = {str(key): str(value) for key, value in (transport.get("headers") or {}).items()}
    auth = transport.get("auth") or {"type": "none"}
    auth_type = auth.get("type")
    if auth_type == "none":
        return headers
    env_name = str(auth["env"])
    secret = os.getenv(env_name)
    if not secret:
        raise RuntimeError(f"required credential environment variable is not configured: {env_name}")
    if auth_type == "bearer_env":
        headers["Authorization"] = f"Bearer {secret}"
    else:
        headers[str(auth["header"])] = secret
    return headers


def transform_prompt(prompt: str, references: list[dict[str, Any]], spec: dict[str, Any]) -> str:
    prompt_config = spec.get("prompt") or {}
    label_template = str(prompt_config.get("image_reference_template") or "图 {index}")
    name_to_label = {
        str(reference["name"]): label_template.format(index=reference["index"], name=reference["name"])
        for reference in references
    }

    def replace(match: re.Match[str]) -> str:
        name = (match.group(1) or "").strip()
        if name not in name_to_label:
            raise ValueError(f"Prompt contains an unresolved asset placeholder: {name!r}")
        return name_to_label[name]

    return TOKEN_RE.sub(replace, prompt)


def build_media(references: list[dict[str, Any]], urls: list[str], spec: dict[str, Any]) -> list[Any]:
    item_template = spec["media"]["item_template"]
    return [
        render_template(
            item_template,
            {"url": url, "name": reference["name"], "index": reference["index"]},
        )
        for reference, url in zip(references, urls)
    ]


def build_create_request(scene: dict[str, Any], config: dict[str, Any], urls: list[str], spec: dict[str, Any]) -> dict[str, Any]:
    references = scene.get("references") or []
    prompt = transform_prompt(str(scene.get("scene_video_prompt") or ""), references, spec)
    media = build_media(references, urls, spec)
    context = {
        "model": config.get("model"),
        "provider": config.get("provider"),
        "scene_index": scene.get("scene_index"),
        "prompt": prompt,
        "media": media,
        "resolution": config.get("resolution"),
        "ratio": config.get("ratio"),
        "duration": scene.get("duration"),
        "audio": scene.get("audio"),
        "prompt_extend": config.get("prompt_extend"),
        "watermark": config.get("watermark"),
    }
    create = spec["create"]
    if spec["transport"]["kind"] == "http":
        return {
            "method": str(create["method"]).upper(),
            "url": render_template(create["url"], context),
            "body": render_template(create.get("body"), context) if "body" in create else None,
            "prompt": prompt,
            "media": media,
        }
    return {
        "method": str(create["method"]),
        "kwargs": render_template(create.get("kwargs") or {}, context),
        "prompt": prompt,
        "media": media,
    }


def upload_reference(
    reference: dict[str, Any],
    asset_by_name: dict[str, dict[str, Any]],
    run_id: str,
    alpha_policy: str = "flatten_white_jpeg",
) -> str:
    asset = asset_by_name[reference["name"]]
    source = Path(reference["path"])
    if asset.get("has_alpha") and alpha_policy == "flatten_white_jpeg":
        with Image.open(source) as image:
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            background.alpha_composite(rgba)
            output = BytesIO()
            background.convert("RGB").save(output, format="JPEG", quality=95)
            output.seek(0)
            return upload_from_bytes(output, task_id=run_id, file_extension=".jpg")
    return upload_from_local(str(source), task_id=run_id, file_extension=source.suffix.lower())


def load_asset_registry(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    data = load_json(path.resolve())
    assets = data.get("assets") if isinstance(data, dict) else None
    if not isinstance(assets, list):
        raise ValueError("asset registry must contain an assets array")
    by_name: dict[str, dict[str, Any]] = {}
    for item in assets:
        if not isinstance(item, dict):
            raise ValueError("asset registry entries must be objects")
        name = str(item.get("name") or "").strip()
        asset_uri = str(item.get("asset_uri") or "").strip()
        if not name or name in by_name:
            raise ValueError(f"asset registry contains an empty or duplicate name: {name!r}")
        if not asset_uri.startswith("asset://"):
            raise ValueError(f"asset registry entry {name!r} has an invalid asset_uri")
        by_name[name] = item
    return by_name


def resolve_registry_urls(
    references: list[dict[str, Any]],
    registry: dict[str, dict[str, Any]],
) -> list[str]:
    urls: list[str] = []
    for reference in references:
        name = str(reference["name"])
        item = registry.get(name)
        if item is None:
            raise ValueError(f"asset registry is missing reference {name!r}")
        source = Path(str(reference["path"])).resolve()
        expected_hash = str(item.get("sha256") or "")
        if not expected_hash or sha256_file(source) != expected_hash:
            raise ValueError(f"asset registry hash does not match local reference {name!r}")
        urls.append(str(item["asset_uri"]))
    return urls


class Runtime:
    def __init__(self, args: argparse.Namespace, manifest: dict[str, Any], spec: dict[str, Any]):
        self.args = args
        self.manifest = manifest
        self.spec = spec
        self.output_dir = args.output_dir.resolve()
        self.state_path = self.output_dir / "state.json"
        self.results_path = self.output_dir / "results.json"
        self.state_lock = asyncio.Lock()
        self.state = load_json(self.state_path) if self.state_path.exists() else {
            "run_id": f"rvmt-{uuid.uuid4().hex[:12]}",
            "status": "INITIALIZED",
            "created_at": utc_now(),
            "inputs": {
                "manifest": str(args.manifest.resolve()),
                "manifest_sha256": sha256_file(args.manifest.resolve()),
                "call_spec": str(args.call_spec.resolve()),
                "call_spec_sha256": sha256_file(args.call_spec.resolve()),
            },
            "tasks": {},
        }
        self.asset_by_name = {item["name"]: item for item in manifest.get("assets") or []}
        self.asset_registry = load_asset_registry(args.asset_registry)
        self.asset_registry_is_real_person: bool | None = None
        if args.asset_registry:
            registry_document = load_json(args.asset_registry.resolve())
            registry_flag = registry_document.get("is_real_person") if isinstance(registry_document, dict) else None
            if isinstance(registry_flag, bool):
                self.asset_registry_is_real_person = registry_flag
        transport = spec["transport"]
        self.transport_kind = transport["kind"]
        self.headers = build_auth_headers(spec) if self.transport_kind == "http" else {}
        timeout = float(transport.get("timeout_seconds") or 120)
        self.http = httpx.AsyncClient(timeout=timeout, follow_redirects=False) if self.transport_kind == "http" else None
        self.project_client = (
            get_aigc_client(
                provider=str(transport.get("factory_provider") or transport["provider"]),
                task_type=str(transport["task_type"]),
            )
            if self.transport_kind == "project_client"
            else None
        )
        if self.transport_kind == "project_client" and self.project_client is None:
            raise RuntimeError("configured project client is unavailable")

    async def update_task(self, scene_index: int, **values: Any) -> dict[str, Any]:
        async with self.state_lock:
            task = self.state.setdefault("tasks", {}).setdefault(str(scene_index), {})
            task.update(values)
            write_json(self.state_path, self.state)
            return dict(task)

    async def request_json(self, method: str, url: str, body: Any, *, retry_query: bool = False) -> dict[str, Any]:
        if self.http is None:
            raise RuntimeError("HTTP transport is not initialized")
        attempts = 3 if retry_query else 1
        for attempt in range(1, attempts + 1):
            try:
                response = await self.http.request(method, url, headers=self.headers, json=body)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise RuntimeError("provider response must be a JSON object")
                return data
            except (httpx.ConnectError, httpx.TimeoutException):
                if attempt == attempts:
                    raise
                await asyncio.sleep(attempt * 2)
        raise AssertionError("unreachable")

    async def call_create(self, request: dict[str, Any]) -> dict[str, Any]:
        if self.transport_kind == "http":
            return await self.request_json(request["method"], request["url"], request["body"])
        method = getattr(self.project_client, request["method"])
        result = await method(**request["kwargs"])
        if not isinstance(result, dict):
            raise RuntimeError("project client create response must be a JSON object")
        return result

    async def call_query(self, task_id: str) -> dict[str, Any]:
        query = self.spec["query"]
        context = {"task_id": task_id, "model": self.manifest["test_config"].get("model")}
        if self.transport_kind == "http":
            query_url = render_template(query["url"], context)
            query_body = render_template(query.get("body"), context) if "body" in query else None
            return await self.request_json(str(query["method"]).upper(), query_url, query_body, retry_query=True)
        kwargs = render_template(query.get("kwargs") or {}, context)
        method = getattr(self.project_client, str(query["method"]))
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                result = await method(**kwargs)
                if not isinstance(result, dict):
                    raise RuntimeError("project client query response must be a JSON object")
                return result
            except Exception as exc:
                last_error = exc
                if attempt == 3:
                    raise
                await asyncio.sleep(attempt * 2)
        raise last_error or AssertionError("unreachable")

    async def run_scene(self, scene: dict[str, Any]) -> dict[str, Any]:
        scene_index = int(scene["scene_index"])
        task_state = self.state.get("tasks", {}).get(str(scene_index), {})
        if task_state.get("status") == "SUCCEEDED" and task_state.get("result"):
            return task_state["result"]
        if task_state.get("status") == "CREATE_UNKNOWN" and not task_state.get("task_id"):
            raise RuntimeError(f"scene {scene_index} has an ambiguous prior create attempt; inspect provider before rerunning")

        references = scene.get("references") or []
        urls = task_state.get("asset_urls")
        if not urls:
            upload_started = time.time()
            if self.asset_registry:
                urls = resolve_registry_urls(references, self.asset_registry)
            else:
                alpha_policy = str((self.spec.get("assets") or {}).get("alpha_policy") or "flatten_white_jpeg")
                urls = await asyncio.gather(*[
                    asyncio.to_thread(
                        upload_reference,
                        reference,
                        self.asset_by_name,
                        self.state["run_id"],
                        alpha_policy,
                    )
                    for reference in references
                ])
            await self.update_task(
                scene_index,
                status="ASSETS_UPLOADED",
                asset_urls=list(urls),
                asset_upload_seconds=round(time.time() - upload_started, 3),
            )
            task_state = self.state["tasks"][str(scene_index)]

        request = build_create_request(scene, self.manifest["test_config"], list(urls), self.spec)
        snapshot_path = self.output_dir / "requests" / f"scene_{scene_index}.json"
        write_json(snapshot_path, {
            "model": self.manifest["test_config"].get("model"),
            "provider": self.manifest["test_config"].get("provider"),
            "method": request["method"],
            "url": request.get("url"),
            "body": request.get("body"),
            "kwargs": request.get("kwargs"),
            "asset_order": [
                {"index": reference["index"], "name": reference["name"], "url": url}
                for reference, url in zip(references, urls)
            ],
        })

        task_id = task_state.get("task_id")
        if not task_id:
            try:
                create_response = await self.call_create(request)
            except Exception as exc:
                ambiguous = self.transport_kind == "project_client" or isinstance(
                    exc, (httpx.ConnectError, httpx.TimeoutException)
                )
                if ambiguous:
                    await self.update_task(scene_index, status="CREATE_UNKNOWN", error_type=type(exc).__name__)
                    raise RuntimeError(
                        f"scene {scene_index} create result is unknown; do not resubmit automatically"
                    ) from exc
                raise
            task_id = str(get_path(create_response, self.spec["create"]["task_id_path"])).strip()
            if not task_id:
                raise RuntimeError(f"scene {scene_index} create response contains an empty task ID")
            await self.update_task(
                scene_index,
                status="SUBMITTED",
                task_id=task_id,
                submitted_at=utc_now(),
                request_snapshot=str(snapshot_path),
            )

        query = self.spec["query"]
        success = {str(item).upper() for item in query["success_values"]}
        failure = {str(item).upper() for item in query["failure_values"]}
        interval = float(query.get("poll_interval_seconds") or 10)
        poll_started = time.time()
        deadline = poll_started + self.args.poll_timeout
        final_response: dict[str, Any] | None = None
        while time.time() < deadline:
            response = await self.call_query(task_id)
            status = str(get_path(response, query["status_path"])).upper()
            await self.update_task(scene_index, status=status, last_polled_at=utc_now())
            if status in success:
                final_response = response
                break
            if status in failure:
                raise RuntimeError(f"scene {scene_index} provider task ended with status {status}")
            await asyncio.sleep(interval)
        if final_response is None:
            raise TimeoutError(f"scene {scene_index} polling exceeded {self.args.poll_timeout} seconds")

        provider_url = str(get_path(final_response, query["video_url_path"])).strip()
        stable_url = await asyncio.to_thread(upload_from_url_stream, provider_url, task_id, ".mp4")
        time_paths = query.get("time_paths") or {}
        usage_path = str(query.get("usage_path") or "").strip()

        def optional_response_path(name: str) -> Any:
            path = str(time_paths.get(name) or "").strip()
            return get_path(final_response, path, required=False) if path else None

        result = {
            "test_id": f"SCENE-{scene_index}",
            "scene_index": scene_index,
            "variant": self.args.variant,
            "task_id": task_id,
            "status": "SUCCEEDED",
            "audio": scene.get("audio"),
            "audio_policy": "explicit per-scene decision" if scene.get("audio") is not None else "omitted; provider default",
            "video_url": stable_url,
            "submit_time": optional_response_path("submit_time"),
            "scheduled_time": optional_response_path("scheduled_time"),
            "end_time": optional_response_path("end_time"),
            "wall_poll_seconds": round(time.time() - poll_started, 3),
            "asset_upload_seconds": self.state["tasks"][str(scene_index)].get("asset_upload_seconds"),
            "asset_registry": str(self.args.asset_registry.resolve()) if self.args.asset_registry else None,
            "asset_registry_is_real_person": self.asset_registry_is_real_person,
            "usage": get_path(final_response, usage_path, required=False) if usage_path else {},
            "issues": "",
            "request_snapshot": str(snapshot_path),
        }
        await self.update_task(scene_index, status="SUCCEEDED", completed_at=utc_now(), result=result)
        return result

    async def close(self) -> None:
        if self.http is not None:
            await self.http.aclose()
        project_http = getattr(self.project_client, "_client", None)
        if project_http is not None and hasattr(project_http, "aclose"):
            await project_http.aclose()


async def execute(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest.resolve())
    spec = load_json(args.call_spec.resolve())
    validate_call_spec(spec)
    if not (manifest.get("preflight") or {}).get("passed"):
        raise ValueError("manifest preflight did not pass")
    if not manifest.get("scenes"):
        raise ValueError("manifest contains no scenes")
    if args.concurrency < 1:
        raise ValueError("--concurrency must be at least 1")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "manifest.snapshot.json", manifest)
    write_json(output_dir / "call_spec.snapshot.json", spec)
    if args.validate_only:
        for scene in manifest["scenes"]:
            urls = [f"https://assets.invalid/reference-{item['index']}.jpg" for item in scene.get("references") or []]
            request = build_create_request(scene, manifest["test_config"], urls, spec)
            write_json(output_dir / "requests" / f"scene_{scene['scene_index']}.json", {
                "method": request["method"],
                "url": request.get("url"),
                "body": request.get("body"),
                "kwargs": request.get("kwargs"),
                "asset_order": scene.get("references") or [],
            })
        print(json.dumps({"status": "VALID", "scenes": len(manifest["scenes"])}, ensure_ascii=False))
        return 0

    transport = spec["transport"]
    if transport["kind"] == "http":
        auth = transport.get("auth") or {"type": "none"}
        required_keys = [auth["env"]] if auth.get("type") != "none" else []
    else:
        required_keys = list(transport.get("credential_envs") or [])
    if required_keys:
        load_and_validate_secrets(required_keys=required_keys)
    runtime = Runtime(args, manifest, spec)
    semaphore = asyncio.Semaphore(args.concurrency)

    async def guarded(scene: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            try:
                return await runtime.run_scene(scene)
            except Exception as exc:
                scene_index = int(scene["scene_index"])
                task = runtime.state.get("tasks", {}).get(str(scene_index), {})
                final_status = "CREATE_UNKNOWN" if task.get("status") == "CREATE_UNKNOWN" else "FAILED"
                await runtime.update_task(
                    scene_index,
                    status=final_status,
                    failed_at=utc_now(),
                    error_type=type(exc).__name__,
                    error=str(exc)[:1000],
                )
                return {
                    "test_id": f"SCENE-{scene_index}",
                    "scene_index": scene_index,
                    "variant": args.variant,
                    "task_id": task.get("task_id"),
                    "status": final_status,
                    "audio": scene.get("audio"),
                    "video_url": "",
                    "issues": str(exc),
                }

    try:
        results = await asyncio.gather(*[guarded(scene) for scene in manifest["scenes"]])
    finally:
        await runtime.close()
    write_json(runtime.results_path, {"results": results})
    runtime.state["status"] = "SUCCEEDED" if all(item["status"] == "SUCCEEDED" for item in results) else "PARTIAL_OR_FAILED"
    runtime.state["completed_at"] = utc_now()
    write_json(runtime.state_path, runtime.state)
    print(json.dumps({"status": runtime.state["status"], "results": results}, ensure_ascii=False))
    return 0 if runtime.state["status"] == "SUCCEEDED" else 2


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(execute(args))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"reference-video runner failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
