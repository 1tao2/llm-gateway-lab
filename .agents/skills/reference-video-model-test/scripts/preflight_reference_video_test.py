#!/usr/bin/env python3
"""Build a deterministic manifest for a local reference-video model test."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - environment failure
    raise SystemExit("Pillow is required; run this script in the repository's kino environment") from exc


SCHEMA_VERSION = "1.0"
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
TOKEN_RE = re.compile(r"<<<(.*?)>>>")
DURATION_RE = re.compile(r"电影感\s*(\d+(?:\.\d+)?)\s*秒")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--asset-dir", required=True, type=Path)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--resolution", required=True)
    parser.add_argument("--ratio", required=True)
    parser.add_argument(
        "--scene-index",
        action="append",
        type=int,
        default=[],
        help="Only preflight this scene_index; may be repeated. Defaults to all scenes.",
    )
    parser.add_argument(
        "--default-audio",
        choices=("true", "false", "omit"),
        default="omit",
        help="Default per-scene audio decision; omit means do not send the field.",
    )
    parser.add_argument(
        "--scene-audio",
        action="append",
        default=[],
        metavar="SCENE_INDEX=true|false|omit",
        help="Override audio for one scene; may be repeated.",
    )
    parser.add_argument("--prompt-extend", choices=("true", "false"), default="false")
    parser.add_argument("--watermark", choices=("true", "false"), default="false")
    parser.add_argument("--max-reference-images", type=int)
    parser.add_argument("--max-prompt-chars", type=int)
    parser.add_argument("--max-image-bytes", type=int)
    parser.add_argument(
        "--call-spec",
        type=Path,
        help="Optional declarative call spec used to preview provider-specific asset labels.",
    )
    parser.add_argument("--output", type=Path, help="Write JSON here; stdout when omitted.")
    return parser.parse_args()


def parse_tristate(value: str) -> bool | None:
    return {"true": True, "false": False, "omit": None}[value]


def parse_scene_audio(values: list[str]) -> dict[int, bool | None]:
    result: dict[int, bool | None] = {}
    for value in values:
        try:
            index_text, setting = value.split("=", 1)
            index = int(index_text)
            parsed = parse_tristate(setting.lower())
        except (ValueError, KeyError) as exc:
            raise ValueError(f"invalid --scene-audio value: {value!r}") from exc
        if index in result:
            raise ValueError(f"duplicate --scene-audio for scene {index}")
        result[index] = parsed
    return result


def load_scenes(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    raw = path.read_text(encoding="utf-8")
    warnings: list[str] = []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            data = json.loads(raw.strip().rstrip(","), strict=False)
            warnings.append("Prompt file is JSON-like but not strict JSON; tolerant parsing was used.")
        except json.JSONDecodeError as exc:
            raise ValueError(f"cannot parse prompt file: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("scenes")
    if not isinstance(data, list):
        raise ValueError("prompt file must contain a scene list or an object with a scenes list")
    if not all(isinstance(item, dict) for item in data):
        raise ValueError("every scene must be an object")
    return data, warnings


def unique_tokens(prompt: str) -> list[str]:
    return list(dict.fromkeys(match.group(1).strip() for match in TOKEN_RE.finditer(prompt)))


def build_request_prompt_preview(
    prompt: str,
    references: list[dict[str, Any]],
    *,
    provider: str,
    model: str,
    call_spec: dict[str, Any] | None = None,
) -> str:
    """Apply deterministic placeholder conversion needed for limit checks.

    Hailuo H3 reference images are numbered in their frozen media order as 图1、图2…….
    Other providers retain the source prompt until their conversion contract is added here.
    """
    if call_spec is not None:
        label_template = str((call_spec.get("prompt") or {}).get("image_reference_template") or "图 {index}")
        converted = prompt
        for reference in references:
            name = str(reference.get("name") or "").strip()
            index = reference.get("index")
            if name and index is not None:
                converted = converted.replace(
                    f"<<<{name}>>>",
                    label_template.format(index=index, name=name),
                )
        return converted
    if provider.strip().lower() != "hailuo" or model.strip().lower() != "hailuo-h3":
        return prompt
    converted = prompt
    for reference in references:
        name = str(reference.get("name") or "").strip()
        index = reference.get("index")
        if name and index is not None:
            converted = converted.replace(f"<<<{name}>>>", f"图{index}")
    return converted


def extract_duration(scene: dict[str, Any], prompt: str) -> tuple[int | float | None, str | None]:
    for key in ("duration", "scene_duration", "total_duration"):
        value = scene.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return value, key
        if isinstance(value, str):
            try:
                parsed = float(value)
            except ValueError:
                continue
            if parsed > 0:
                return int(parsed) if parsed.is_integer() else parsed, key
    match = DURATION_RE.search(prompt)
    if not match:
        return None, None
    parsed = float(match.group(1))
    return (int(parsed) if parsed.is_integer() else parsed), "scene_video_prompt"


def inspect_assets(asset_dir: Path) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    assets: list[dict[str, Any]] = []
    by_name: dict[str, list[dict[str, Any]]] = {}
    candidates = sorted(
        (
            path
            for path in asset_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
        ),
        key=lambda path: path.name,
    )
    for path in candidates:
        record: dict[str, Any] = {
            "name": path.stem,
            "file": path.name,
            "path": str(path.resolve()),
            "bytes": path.stat().st_size,
        }
        try:
            with Image.open(path) as image:
                record.update(
                    {
                        "format": image.format,
                        "mode": image.mode,
                        "width": image.width,
                        "height": image.height,
                        "has_alpha": image.mode in {"RGBA", "LA"} or "transparency" in image.info,
                    }
                )
        except Exception as exc:  # Pillow exposes provider-specific decode exceptions
            record["inspection_error"] = str(exc)
        assets.append(record)
        by_name.setdefault(path.stem, []).append(record)
    return assets, by_name


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    prompt_file = args.prompt_file.resolve()
    asset_dir = args.asset_dir.resolve()
    if not prompt_file.is_file():
        raise ValueError(f"prompt file does not exist: {prompt_file}")
    if not asset_dir.is_dir():
        raise ValueError(f"asset directory does not exist: {asset_dir}")
    call_spec = None
    alpha_policy = "flatten_white_jpeg"
    if args.call_spec:
        call_spec_path = args.call_spec.resolve()
        if not call_spec_path.is_file():
            raise ValueError(f"call spec does not exist: {call_spec_path}")
        call_spec = json.loads(call_spec_path.read_text(encoding="utf-8"))
        if not isinstance(call_spec, dict):
            raise ValueError("call spec must contain a JSON object")
        alpha_policy = str((call_spec.get("assets") or {}).get("alpha_policy") or alpha_policy)

    scenes_raw, parser_warnings = load_scenes(prompt_file)
    requested_scene_indexes = set(args.scene_index)
    available_scene_indexes: set[int] = set()
    for scene in scenes_raw:
        try:
            available_scene_indexes.add(int(scene.get("scene_index")))
        except (TypeError, ValueError):
            continue
    unknown_requested_scenes = sorted(requested_scene_indexes - available_scene_indexes)
    if unknown_requested_scenes:
        raise ValueError(f"--scene-index refers to unknown scenes: {unknown_requested_scenes}")
    if requested_scene_indexes:
        scenes_raw = [
            scene
            for scene in scenes_raw
            if int(scene.get("scene_index")) in requested_scene_indexes
        ]
    assets, assets_by_name = inspect_assets(asset_dir)
    scene_audio = parse_scene_audio(args.scene_audio)
    default_audio = parse_tristate(args.default_audio)
    errors: list[str] = []
    warnings = list(parser_warnings)
    seen_indexes: set[int] = set()
    referenced_names: set[str] = set()
    scenes: list[dict[str, Any]] = []

    for position, scene in enumerate(scenes_raw, start=1):
        raw_index = scene.get("scene_index")
        try:
            scene_index = int(raw_index)
        except (TypeError, ValueError):
            errors.append(f"scene at position {position} has invalid scene_index: {raw_index!r}")
            continue
        if scene_index in seen_indexes:
            errors.append(f"duplicate scene_index: {scene_index}")
        seen_indexes.add(scene_index)

        prompt = scene.get("scene_video_prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            errors.append(f"scene {scene_index} has empty scene_video_prompt")
            prompt = "" if prompt is None else str(prompt)
        prompt_chars = len(prompt)
        names = unique_tokens(prompt)
        referenced_names.update(names)
        duration, duration_source = extract_duration(scene, prompt)
        if duration is None:
            errors.append(f"scene {scene_index} has no unambiguous duration")

        references: list[dict[str, Any]] = []
        missing_assets: list[str] = []
        for reference_index, name in enumerate(names, start=1):
            matches = assets_by_name.get(name, [])
            if len(matches) == 0:
                missing_assets.append(name)
                errors.append(f"scene {scene_index} is missing asset {name!r}")
                references.append({"index": reference_index, "name": name, "file": None})
            elif len(matches) > 1:
                errors.append(f"scene {scene_index} asset {name!r} matches multiple files")
                references.append({"index": reference_index, "name": name, "file": None})
            else:
                if (
                    args.max_image_bytes is not None
                    and matches[0]["bytes"] > args.max_image_bytes
                ):
                    errors.append(
                        f"scene {scene_index} asset {name!r} is {matches[0]['bytes']} bytes, "
                        f"exceeding configured limit {args.max_image_bytes}"
                    )
                references.append(
                    {
                        "index": reference_index,
                        "name": name,
                        "file": matches[0]["file"],
                        "path": matches[0]["path"],
                    }
                )
        if args.max_reference_images is not None and len(references) > args.max_reference_images:
            errors.append(
                f"scene {scene_index} has {len(references)} references, exceeding configured limit "
                f"{args.max_reference_images}"
            )

        request_prompt_preview = build_request_prompt_preview(
            prompt,
            references,
            provider=args.provider,
            model=args.model,
            call_spec=call_spec,
        )
        request_prompt_chars = len(request_prompt_preview)
        if args.max_prompt_chars is not None and request_prompt_chars > args.max_prompt_chars:
            errors.append(
                f"scene {scene_index} request prompt has {request_prompt_chars} characters, "
                f"exceeding configured limit {args.max_prompt_chars}"
            )

        scenes.append(
            {
                "scene_index": scene_index,
                "scene_title": scene.get("scene_title") or "",
                "scene_video_prompt": prompt,
                "prompt_chars": prompt_chars,
                "request_prompt_preview": request_prompt_preview,
                "request_prompt_chars": request_prompt_chars,
                "duration": duration,
                "duration_source": duration_source,
                "audio": scene_audio.get(scene_index, default_audio),
                "references": references,
                "missing_assets": missing_assets,
            }
        )

    unknown_audio_scenes = sorted(set(scene_audio) - seen_indexes)
    if unknown_audio_scenes:
        errors.append(f"--scene-audio refers to unknown scenes: {unknown_audio_scenes}")
    for name, matches in assets_by_name.items():
        if len(matches) > 1:
            errors.append(f"asset stem {name!r} is ambiguous: {[item['file'] for item in matches]}")
    for asset in assets:
        if asset.get("inspection_error"):
            errors.append(f"cannot inspect asset {asset['file']}: {asset['inspection_error']}")
        if asset.get("has_alpha"):
            if alpha_policy == "preserve":
                warnings.append(f"asset {asset['file']} has an alpha channel; preserve the original format for upload")
            else:
                warnings.append(f"asset {asset['file']} has an alpha channel; convert without overwriting the source")
    unused_assets = sorted(set(assets_by_name) - referenced_names)
    if unused_assets:
        warnings.append(f"unused assets: {unused_assets}")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"prompt_file": str(prompt_file), "asset_dir": str(asset_dir)},
        "test_config": {
            "provider": args.provider,
            "model": args.model,
            "resolution": args.resolution,
            "ratio": args.ratio,
            "scene_indexes": sorted(requested_scene_indexes),
            "default_audio": default_audio,
            "prompt_extend": args.prompt_extend == "true",
            "watermark": args.watermark == "true",
            "max_reference_images": args.max_reference_images,
            "max_prompt_chars": args.max_prompt_chars,
            "max_image_bytes": args.max_image_bytes,
            "alpha_policy": alpha_policy,
        },
        "preflight": {"passed": not errors, "errors": errors, "warnings": warnings},
        "assets": assets,
        "unused_assets": unused_assets,
        "scenes": scenes,
    }


def main() -> int:
    args = parse_args()
    try:
        manifest = build_manifest(args)
    except (OSError, ValueError) as exc:
        print(f"preflight failed: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0 if manifest["preflight"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
