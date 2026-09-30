#!/usr/bin/env python3
"""Build a Markdown reference-video test report from a manifest and task results."""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--results", type=Path)
    parser.add_argument(
        "--suite-case",
        action="append",
        nargs=3,
        metavar=("NAME", "MANIFEST", "RESULTS"),
        help="Add one named script/case to a combined same-model report; may be repeated.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title", default="参考生视频模型测试报告")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def table_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def elapsed_seconds(start: Any, end: Any) -> float | None:
    start_time = parse_time(start)
    end_time = parse_time(end)
    if start_time is None or end_time is None:
        return None
    return (end_time - start_time).total_seconds()


def format_seconds(value: float | None) -> str:
    return "—" if value is None else f"{value:,.3f}s"


def format_audio(value: Any) -> str:
    if value is True:
        return "`true`"
    if value is False:
        return "`false`"
    return "省略（使用模型默认值）"


def scene_lookup(manifest: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(scene["scene_index"]): scene for scene in manifest.get("scenes", [])}


def prompt_signature(manifest: dict[str, Any]) -> str:
    """Identify reusable script details independently from output configuration."""
    scenes = [
        {
            "scene_index": scene.get("scene_index"),
            "scene_video_prompt": scene.get("scene_video_prompt"),
            "request_prompt_preview": scene.get("request_prompt_preview"),
            "references": scene.get("references") or [],
        }
        for scene in manifest.get("scenes", [])
    ]
    return json.dumps(scenes, ensure_ascii=False, sort_keys=True)


def script_display_name(case_name: str, manifest: dict[str, Any]) -> str:
    asset_dir = str((manifest.get("source") or {}).get("asset_dir") or "").strip()
    if asset_dir:
        return PureWindowsPath(asset_dir).name or case_name
    return case_name


def normalize_results(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        data = data.get("results")
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError("results must be an array or an object containing a results array")
    return data


def reviewed_material_label(results: list[dict[str, Any]]) -> str | None:
    """Describe the audited material type without assuming every registry is real-person."""
    material_types: set[bool] = set()
    has_registry = False
    for result in results:
        registry_path = str(result.get("asset_registry") or "").strip()
        if not registry_path:
            continue
        has_registry = True
        declared = result.get("asset_registry_is_real_person")
        if isinstance(declared, bool):
            material_types.add(declared)
            continue
        path = Path(registry_path)
        if path.is_file():
            registry = read_json(path)
            registry_value = registry.get("is_real_person") if isinstance(registry, dict) else None
            if isinstance(registry_value, bool):
                material_types.add(registry_value)
    if not has_registry:
        return None
    if material_types == {True}:
        return "已审核为真人素材并以 asset:// 输入"
    if material_types == {False}:
        return "已审核为非真人素材并以 asset:// 输入"
    return "已审核并以 asset:// 输入"


def read_json_object(path_value: Any) -> dict[str, Any] | None:
    path_text = str(path_value or "").strip()
    if not path_text:
        return None
    path = Path(path_text)
    if not path.is_file():
        return None
    try:
        value = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def asset_url_lookup(results: list[dict[str, Any]]) -> dict[str, str]:
    """Recover stable uploaded URLs from request snapshots and material state."""
    urls: dict[str, str] = {}
    registry_assets: list[dict[str, Any]] = []
    material_state_dirs: set[Path] = set()

    def remember(name: Any, url: Any) -> None:
        name_text = str(name or "").strip()
        url_text = str(url or "").strip()
        if name_text and url_text.startswith(("http://", "https://")):
            urls.setdefault(name_text, url_text)

    for result in results:
        snapshot = read_json_object(result.get("request_snapshot"))
        if snapshot:
            for item in snapshot.get("asset_order") or []:
                if isinstance(item, dict):
                    remember(item.get("name"), item.get("url"))

        registry_path_text = str(result.get("asset_registry") or "").strip()
        if not registry_path_text:
            continue
        registry_path = Path(registry_path_text)
        material_state_dirs.add(registry_path.parent)
        registry = read_json_object(registry_path)
        if not registry:
            continue
        for item in registry.get("assets") or []:
            if not isinstance(item, dict):
                continue
            registry_assets.append(item)
            remember(item.get("name"), item.get("upload_url"))

    if registry_assets:
        state_assets: list[dict[str, Any]] = []
        for directory in material_state_dirs:
            for state_path in directory.glob("*material_state.json"):
                state = read_json_object(state_path)
                materials = (state or {}).get("materials")
                if isinstance(materials, dict):
                    state_assets.extend(item for item in materials.values() if isinstance(item, dict))
        by_sha = {
            str(item.get("sha256")): item
            for item in state_assets
            if item.get("sha256") and item.get("upload_url")
        }
        by_name = {
            str(item.get("name")): item
            for item in state_assets
            if item.get("name") and item.get("upload_url")
        }
        for item in registry_assets:
            state_item = by_sha.get(str(item.get("sha256") or "")) or by_name.get(
                str(item.get("name") or "")
            )
            if state_item:
                remember(item.get("name"), state_item.get("upload_url"))
    return urls


def prompt_video_lines(scene_results: list[dict[str, Any]]) -> list[str]:
    """Render stable video URLs directly above one scene's Prompt details."""
    if not scene_results:
        return ["生成视频：—"]

    def video_link(result: dict[str, Any]) -> str:
        url = str(result.get("video_url") or "").strip()
        return f"[{url}]({url})" if url else "—"

    if len(scene_results) == 1:
        return [f"生成视频：{video_link(scene_results[0])}"]

    lines: list[str] = []
    for result in scene_results:
        test_id = str(result.get("test_id") or "未编号变体")
        variant = str(result.get("variant") or "").strip()
        resolution = str(result.get("_report_resolution") or "").strip()
        qualifiers = " / ".join(value for value in (resolution, variant) if value)
        label = test_id + (f"（{qualifiers}）" if qualifiers else "")
        lines.append(f"生成视频（{label}）：{video_link(result)}")
    return lines


def build_report(
    title: str,
    manifest: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    include_timing_summary: bool = True,
) -> str:
    config = manifest.get("test_config") or {}
    source = manifest.get("source") or {}
    scenes = scene_lookup(manifest)
    referenced_names = {
        str(reference.get("name") or "")
        for scene in scenes.values()
        for reference in scene.get("references", [])
    }
    material_label = reviewed_material_label(results)
    asset_urls = asset_url_lookup(results)
    lines = [
        f"# {title}",
        "",
        "## 1. 测试概览",
        "",
        f"- 厂商：`{table_text(config.get('provider'))}`",
        f"- 模型：`{table_text(config.get('model'))}`",
        f"- 分辨率：`{table_text(config.get('resolution'))}`",
        f"- ratio：`{table_text(config.get('ratio'))}`",
        f"- 预检生成时间：`{table_text(manifest.get('generated_at'))}`",
        f"- Prompt 文件：`{table_text(source.get('prompt_file'))}`",
        f"- 资产目录：`{table_text(source.get('asset_dir'))}`",
        "- 耗时口径：排队=`scheduled_time-submit_time`，执行=`end_time-scheduled_time`，总耗时=`end_time-submit_time`。",
        "",
        "## 2. 参考资产",
        "",
        "| 资产名 | 文件 | OSS 链接 | 引用状态与输入方式 |",
        "|---|---|---|---|",
    ]
    for asset in manifest.get("assets", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    table_text(asset.get("name")),
                    f"`{table_text(asset.get('file'))}`",
                    (
                        f"[{asset_urls[asset['name']]}]({asset_urls[asset['name']]})"
                        if asset.get("name") in asset_urls
                        else "—"
                    ),
                    (
                        f"已引用；{material_label}"
                        if asset.get("name") in referenced_names and material_label
                        else "已引用"
                        if asset.get("name") in referenced_names
                        else "未引用"
                    ),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 3. 任务结果",
            "",
            "| 测试编号 | 分镜/变体 | 输出时长 | 参考资产顺序 | 排队 / 执行 / 总耗时 | Task ID | 视频 | 视频存在的问题（待补充） |",
            "|---|---|---:|---|---|---|---|---|",
        ]
    )
    totals: list[tuple[str, float]] = []
    for ordinal, result in enumerate(results, start=1):
        scene_index = int(result["scene_index"])
        scene = scenes.get(scene_index)
        if scene is None:
            raise ValueError(f"result refers to unknown scene_index {scene_index}")
        test_id = str(result.get("test_id") or f"T-{ordinal:03d}")
        variant = str(result.get("variant") or "").strip()
        resolution = str(result.get("_report_resolution") or "").strip()
        scene_qualifiers = " / ".join(value for value in (resolution, variant) if value)
        scene_label = str(scene_index) + (f" / {scene_qualifiers}" if scene_qualifiers else "")
        usage = result.get("usage") or {}
        output_duration = usage.get("output_video_duration", usage.get("duration", scene.get("duration")))
        output_duration_text = "" if output_duration is None else f"{output_duration}s"
        reference_text = "；".join(
            f"图 {reference['index']} {reference['name']}" for reference in scene.get("references", [])
        )
        queue = elapsed_seconds(result.get("submit_time"), result.get("scheduled_time"))
        execution = elapsed_seconds(result.get("scheduled_time"), result.get("end_time"))
        total = elapsed_seconds(result.get("submit_time"), result.get("end_time"))
        if total is not None and str(result.get("status") or "").upper() == "SUCCEEDED":
            totals.append((test_id, total))
        timing = f"{format_seconds(queue)} / {format_seconds(execution)} / **{format_seconds(total)}**"
        video_url = str(result.get("video_url") or "").strip()
        video = f"[视频]({video_url})" if video_url else "—"
        lines.append(
            "| "
            + " | ".join(
                [
                    table_text(test_id),
                    table_text(scene_label),
                    table_text(output_duration_text),
                    table_text(reference_text),
                    timing,
                    f"`{table_text(result.get('task_id'))}`" if result.get("task_id") else "—",
                    video,
                    table_text(result.get("issues") or ""),
                ]
            )
            + " |"
        )

    results_by_scene: dict[int, list[dict[str, Any]]] = {}
    for result in results:
        results_by_scene.setdefault(int(result["scene_index"]), []).append(result)

    lines.extend(["", "## 4. scene_video_prompt 转换前后对照", ""])
    for scene_index in sorted(scenes):
        scene = scenes[scene_index]
        mapping = "；".join(
            f"<<<{reference['name']}>>> → 图{reference['index']}"
            for reference in scene.get("references", [])
        )
        lines.append(f"### 分镜 {scene_index}")
        lines.extend(prompt_video_lines(results_by_scene.get(scene_index, [])))
        lines.extend(
            [
                f"- 资产转换：{mapping or '—'}",
                "#### 转换前：scene_video_prompt 原值",
                "```text",
                str(scene.get("scene_video_prompt") or ""),
                "```",
                "#### 转换后：实际提交 Prompt",
                "```text",
                str(scene.get("request_prompt_preview") or scene.get("scene_video_prompt") or ""),
                "```",
                "",
            ]
        )

    if include_timing_summary:
        lines.extend(["## 5. 耗时统计", ""])
        succeeded_count = sum(str(item.get("status") or "").upper() == "SUCCEEDED" for item in results)
        lines.extend(
            [
                f"- 总任务数：{len(results)}",
                f"- 成功任务数：{succeeded_count}",
                f"- 成功率：{(succeeded_count / len(results) * 100):.2f}%" if results else "- 成功率：—",
            ]
        )
        if totals:
            values = [value for _, value in totals]
            shortest = min(totals, key=lambda item: item[1])
            longest = max(totals, key=lambda item: item[1])
            lines.extend(
                [
                    f"- 成功且具有完整时间字段的任务数：{len(values)}",
                    f"- 平均总耗时：{format_seconds(statistics.fmean(values))}",
                    f"- 最短总耗时：{format_seconds(shortest[1])}（{shortest[0]}）",
                    f"- 最长总耗时：{format_seconds(longest[1])}（{longest[0]}）",
                ]
            )
        else:
            lines.append("没有足够的厂商时间字段，无法计算提交到完成耗时。")
    lines.append("")
    return "\n".join(lines)


def build_suite_report(
    title: str,
    cases: list[tuple[str, dict[str, Any], list[dict[str, Any]]]],
) -> str:
    if not cases:
        raise ValueError("suite report requires at least one case")
    consolidated: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = []
    positions: dict[tuple[Any, ...], int] = {}
    for name, manifest, results in cases:
        config = manifest.get("test_config") or {}
        source = manifest.get("source") or {}
        case_key = (
            name,
            source.get("prompt_file"),
            config.get("provider"),
            config.get("model"),
            config.get("resolution"),
            config.get("ratio"),
        )
        if case_key not in positions:
            positions[case_key] = len(consolidated)
            consolidated.append((name, manifest, list(results)))
            continue
        position = positions[case_key]
        _, _, existing_results = consolidated[position]
        existing_results.extend(results)
    cases = consolidated
    first_config = cases[0][1].get("test_config") or {}
    shared_fields = ("provider", "model")
    for name, manifest, _ in cases[1:]:
        config = manifest.get("test_config") or {}
        for field in shared_fields:
            if config.get(field) != first_config.get(field):
                raise ValueError(f"suite case {name!r} has a different {field}")

    all_results = [
        (case_name, manifest, result)
        for case_name, manifest, results in cases
        for result in results
    ]
    resolutions = list(dict.fromkeys(str((manifest.get("test_config") or {}).get("resolution") or "") for _, manifest, _ in cases))
    ratios = list(dict.fromkeys(str((manifest.get("test_config") or {}).get("ratio") or "") for _, manifest, _ in cases))
    prompt_files = {
        str((manifest.get("source") or {}).get("prompt_file") or "")
        for _, manifest, _ in cases
    }
    lines = [
        f"# {title}",
        "",
        "## 1. 综合测试概览",
        "",
        f"- 厂商：`{table_text(first_config.get('provider'))}`",
        f"- 模型：`{table_text(first_config.get('model'))}`",
        "- 分辨率：" + "、".join(f"`{table_text(value)}`" for value in resolutions),
        "- ratio：" + "、".join(f"`{table_text(value)}`" for value in ratios),
        f"- 剧本数：{len(prompt_files)}",
        f"- 测试配置组数：{len(cases)}",
        f"- 总任务数：{len(all_results)}",
        "- 测试组：" + "、".join(table_text(name) for name, _, _ in cases),
        "- 耗时口径：总耗时=`end_time-submit_time`；厂商未返回排队时间时不拆分排队与执行耗时。",
        "",
        "## 2. 综合任务结果",
        "",
        "| 剧本 | 分镜/变体 | 输出时长 | 参考资产顺序 | 总耗时 | Task ID | 视频 | 视频存在的问题（待补充） |",
        "|---|---|---:|---|---:|---|---|---|",
    ]
    totals: list[tuple[str, float]] = []
    for case_name, manifest, result in all_results:
        scenes = scene_lookup(manifest)
        scene_index = int(result["scene_index"])
        scene = scenes.get(scene_index)
        if scene is None:
            raise ValueError(f"suite case {case_name!r} result refers to unknown scene_index {scene_index}")
        variant = str(result.get("variant") or "").strip()
        scene_label = str(scene_index) + (f" / {variant}" if variant else "")
        usage = result.get("usage") or {}
        duration = usage.get("output_video_duration", usage.get("duration", scene.get("duration")))
        references = "；".join(
            f"图 {reference['index']} {reference['name']}" for reference in scene.get("references", [])
        )
        total = elapsed_seconds(result.get("submit_time"), result.get("end_time"))
        label = f"{case_name}/分镜{scene_index}"
        if total is not None and str(result.get("status") or "").upper() == "SUCCEEDED":
            totals.append((label, total))
        video_url = str(result.get("video_url") or "").strip()
        lines.append(
            "| "
            + " | ".join(
                [
                    table_text(case_name),
                    table_text(scene_label),
                    table_text("" if duration is None else f"{duration}s"),
                    table_text(references),
                    f"**{format_seconds(total)}**",
                    f"`{table_text(result.get('task_id'))}`" if result.get("task_id") else "—",
                    f"[视频]({video_url})" if video_url else "—",
                    table_text(result.get("issues") or ""),
                ]
            )
            + " |"
        )

    detail_groups: list[dict[str, Any]] = []
    detail_positions: dict[tuple[str, str], int] = {}
    for case_name, manifest, results in cases:
        source = manifest.get("source") or {}
        detail_key = (str(source.get("prompt_file") or case_name), prompt_signature(manifest))
        config = manifest.get("test_config") or {}
        resolution = str(config.get("resolution") or "").strip()
        ratio = str(config.get("ratio") or "").strip()
        decorated_results = [
            dict(result, _report_resolution=resolution, _report_case_name=case_name)
            for result in results
        ]
        if detail_key not in detail_positions:
            detail_positions[detail_key] = len(detail_groups)
            detail_groups.append(
                {
                    "name": script_display_name(case_name, manifest),
                    "manifest": manifest,
                    "results": decorated_results,
                    "resolutions": [resolution] if resolution else [],
                    "ratios": [ratio] if ratio else [],
                }
            )
            continue
        group = detail_groups[detail_positions[detail_key]]
        group["results"].extend(decorated_results)
        if resolution and resolution not in group["resolutions"]:
            group["resolutions"].append(resolution)
        if ratio and ratio not in group["ratios"]:
            group["ratios"].append(ratio)

    lines.extend(["", "## 3. 分剧本测试明细", ""])
    for index, group in enumerate(detail_groups, start=1):
        detail_manifest = dict(group["manifest"])
        detail_manifest["test_config"] = dict(detail_manifest.get("test_config") or {})
        detail_manifest["test_config"]["resolution"] = "、".join(group["resolutions"])
        detail_manifest["test_config"]["ratio"] = "、".join(group["ratios"])
        lines.extend([f"### 3.{index} {group['name']}", ""])
        case_lines = build_report(
            f"{group['name']}测试明细",
            detail_manifest,
            group["results"],
            include_timing_summary=False,
        ).splitlines()[1:]
        while case_lines and not case_lines[0].strip():
            case_lines.pop(0)
        for line in case_lines:
            lines.append("##" + line if line.startswith("##") else line)
        if lines[-1] != "":
            lines.append("")

    succeeded = sum(
        str(result.get("status") or "").upper() == "SUCCEEDED"
        for _, _, result in all_results
    )
    lines.extend(
        [
            "## 4. 综合耗时统计",
            "",
            f"- 总任务数：{len(all_results)}",
            f"- 成功任务数：{succeeded}",
            f"- 成功率：{(succeeded / len(all_results) * 100):.2f}%" if all_results else "- 成功率：—",
        ]
    )
    if totals:
        values = [value for _, value in totals]
        shortest = min(totals, key=lambda item: item[1])
        longest = max(totals, key=lambda item: item[1])
        lines.extend(
            [
                f"- 具有完整厂商时间字段的成功任务数：{len(values)}",
                f"- 平均总耗时：{format_seconds(statistics.fmean(values))}",
                f"- 最短总耗时：{format_seconds(shortest[1])}（{shortest[0]}）",
                f"- 最长总耗时：{format_seconds(longest[1])}（{longest[0]}）",
            ]
        )
    else:
        lines.append("没有足够的厂商时间字段，无法计算提交到完成耗时。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        if args.suite_case:
            if args.manifest or args.results:
                raise ValueError("--suite-case cannot be combined with --manifest or --results")
            cases = [
                (name, read_json(Path(manifest_path)), normalize_results(read_json(Path(results_path))))
                for name, manifest_path, results_path in args.suite_case
            ]
            report = build_suite_report(args.title, cases)
        else:
            if args.manifest is None or args.results is None:
                raise ValueError("--manifest and --results are required unless --suite-case is used")
            manifest = read_json(args.manifest)
            results = normalize_results(read_json(args.results))
            report = build_report(args.title, manifest, results)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"cannot build report: {exc}") from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
