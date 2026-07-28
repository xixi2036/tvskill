#!/usr/bin/env python3
"""Create/update unrun LibTV video nodes directly from a TVSkill Markdown delivery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

import audit_canvas_nodes


SEGMENT_RE = re.compile(r"^## 生成段 V(\d{2})｜(.+)$", re.M)
PROMPT_RE = re.compile(
    r"### LibTV 完成提示词（整块复制）\s*\n```text\n(.*?)\n```", re.S
)
MIXED_RE = re.compile(
    r"^\| Mixed (\d+) \|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$",
    re.M,
)
TEXT_VOICE_RE = re.compile(r"(?<!\{)\{[^{}\n]+\}(?!\})|\b(?:OS|VO)\b|内心|画外音|旁白", re.I)
VOICE_SLOT_RE = re.compile(r"待上传|占位")
PLANNING_RE = re.compile(
    r"位置图|轨迹图|构图图|动线图|平面图|俯视图|机位图|箭头|虚线|假人|色块|网格|文字标注"
)


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def run(command: list[str], *, cwd: Path) -> dict[str, Any]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"命令失败：{message}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"命令未返回 JSON：{result.stdout[:300]}") from exc
    if not isinstance(value, dict):
        raise ValueError("命令返回的顶层不是 object")
    return value


def scalar(text: str, key: str) -> str:
    match = re.search(rf"^- {re.escape(key)}：(.+)$", text, re.M)
    if not match:
        raise ValueError(f"缺少元数据：{key}")
    return match.group(1).strip()


def normalized(value: str) -> str:
    value = re.sub(r"^TVSkill-EP\d+-", "", value, flags=re.I)
    return re.sub(r"[\s_·（）()【】\[\]-]+", "", value).lower()


def media_key(media_type: str) -> str:
    if "音频" in media_type:
        return "audioList"
    if "视频" in media_type:
        return "videoList"
    return "imageList"


def parse_markdown(path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    text = path.read_text(encoding="utf-8")
    headings = list(SEGMENT_RE.finditer(text))
    segments: list[dict[str, Any]] = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        block = text[match.start():end]
        prompt_match = PROMPT_RE.search(block)
        if not prompt_match:
            raise ValueError(f"V{match.group(1)} 缺少完成提示词代码块")
        rows = [
            {
                "number": int(number),
                "asset": asset.strip(),
                "mediaType": media_type.strip(),
                "semantic": semantic.strip(),
            }
            for number, asset, media_type, semantic in MIXED_RE.findall(block)
        ]
        if [row["number"] for row in rows] != list(range(1, len(rows) + 1)):
            raise ValueError(f"V{match.group(1)} Mixed 必须从 1 连续递增")
        sound = scalar(block, "声音")
        run_status = scalar(block, "运行状态")
        audio_rows = [row for row in rows if "音频" in row["mediaType"]]
        planning_rows = [row["asset"] for row in rows if PLANNING_RE.search(row["asset"])]
        has_text_voice = bool(TEXT_VOICE_RE.search(prompt_match.group(1)))
        voice_slots = [
            row["asset"] for row in audio_rows
            if VOICE_SLOT_RE.search(f"{row['asset']} {row['mediaType']}")
        ]
        blocked: list[str] = []
        if voice_slots:
            blocked.append(
                f"音色仍是占位槽 {voice_slots}；"
                "请先由人工上传音色素材到画布，再执行音色关联"
                "（回读 audioList/mixedListOrder → 回填素材名与 Mixed 顺序 → 重跑校验）后同步"
            )
        if run_status == "阻塞":
            blocked.append("运行状态为阻塞，禁止同步到可生成节点")
        if planning_rows:
            blocked.append(f"规划资产禁止进入 Mixed：{planning_rows}")
        if has_text_voice and (sound != "开启" or not audio_rows):
            blocked.append("含台词/OS/VO/旁白，必须开启声音并绑定独立音色音频")
        segments.append(
            {
                "number": match.group(1),
                "title": match.group(2).strip(),
                "duration": int(scalar(block, "时长").removesuffix("秒")),
                "sound": "on" if sound == "开启" else "off",
                "prompt": prompt_match.group(1).strip(),
                "mixed": rows,
                "blocked": blocked,
            }
        )
    if not segments:
        raise ValueError("Markdown 中没有生成段")
    return {
        "model": scalar(text, "模型"),
        "ratio": scalar(text, "画幅"),
        "resolution": scalar(text, "分辨率").lower(),
    }, segments


def item_id(item: dict[str, Any]) -> str:
    return str(item.get("nodeId") or item.get("nodeKey") or "")


def data_of(detail: dict[str, Any]) -> dict[str, Any]:
    data = detail.get("data")
    return data if isinstance(data, dict) else detail


def params_of(detail: dict[str, Any]) -> dict[str, Any]:
    params = data_of(detail).get("params")
    return params if isinstance(params, dict) else {}


def resolve_assets(
    listed: list[dict[str, Any]], segments: list[dict[str, Any]]
) -> None:
    images = [item for item in listed if item.get("type") in {"image", "audio", "video"}]
    for segment in segments:
        for row in segment["mixed"]:
            wanted = normalized(row["asset"])
            candidates = [
                item for item in images
                if normalized(str(item.get("name") or "")) == wanted
            ]
            if len(candidates) != 1:
                raise ValueError(
                    f"V{segment['number']} 素材“{row['asset']}”匹配到 {len(candidates)} 个节点"
                )
            row["nodeId"] = str(candidates[0]["id"])
            row["nodeName"] = str(candidates[0]["name"])


def read_node(libtv: str, project: str, target: str, cwd: Path) -> dict[str, Any]:
    return run([libtv, "node", target, "-p", project], cwd=cwd)


def add_live_labels(detail: dict[str, Any], names_by_id: dict[str, str]) -> None:
    params = params_of(detail)
    for key in ("imageList", "videoList", "audioList", "mixedList"):
        values = params.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict) or item.get("label"):
                continue
            actual_id = item_id(item)
            if actual_id in names_by_id:
                item["label"] = names_by_id[actual_id]


def update_cached_order(
    libtv: str,
    project: str,
    node_id: str,
    segment: dict[str, Any],
    cwd: Path,
) -> None:
    detail = read_node(libtv, project, node_id, cwd)
    params = params_of(detail)
    by_id: dict[str, dict[str, Any]] = {}
    for key in ("imageList", "videoList", "audioList", "mixedList"):
        values = params.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict) and item_id(item):
                by_id[item_id(item)] = dict(item)
    desired_ids = [row["nodeId"] for row in segment["mixed"]]
    missing = [node_id for node_id in desired_ids if node_id not in by_id]
    if missing:
        raise ValueError(f"V{segment['number']} 连接后媒体缓存缺少节点：{missing}")

    lists: dict[str, list[dict[str, Any]]] = {
        "imageList": [], "videoList": [], "audioList": []
    }
    mixed: list[dict[str, Any]] = []
    for row in segment["mixed"]:
        item = dict(by_id[row["nodeId"]])
        key = media_key(row["mediaType"])
        lists[key].append(item)
        mixed_item = dict(item)
        mixed_item["mediaType"] = {
            "imageList": "image", "videoList": "video", "audioList": "audio"
        }[key]
        mixed.append(mixed_item)

    command = [libtv, "node", node_id, "-p", project]
    for key, values in lists.items():
        command += ["-s", f"{key}={compact(values)}"]
        command += ["-s", f"{key}Order={compact([item_id(item) for item in values])}"]
    command += ["-s", f"mixedList={compact(mixed)}"]
    command += ["-s", f"mixedListOrder={compact(desired_ids)}"]
    command += ["--prompt", segment["prompt"]]
    run(command, cwd=cwd)


def verify(
    detail: dict[str, Any],
    segment: dict[str, Any],
    settings: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    data = data_of(detail)
    params = params_of(detail)
    if params.get("prompt") != segment["prompt"]:
        errors.append("prompt 回读不一致")
    if params.get("model") != settings["model"]:
        errors.append("model 回读不一致")
    actual_settings = params.get("settings")
    if not isinstance(actual_settings, dict):
        errors.append("settings 缺失")
    else:
        for key in ("ratio", "resolution", "duration", "enableSound"):
            if actual_settings.get(key) != settings[key]:
                errors.append(f"settings.{key} 回读不一致")
    desired = [row["nodeId"] for row in segment["mixed"]]
    if params.get("mixedListOrder") != desired:
        errors.append("mixedListOrder 回读不一致")
    if [item_id(item) for item in params.get("mixedList", [])] != desired:
        errors.append("mixedList 回读不一致")
    task_info = data.get("taskInfo")
    if isinstance(task_info, dict) and task_info.get("status") == 2:
        errors.append("目标节点已有旧生成结果，不是未运行节点")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--node-prefix", default="TVSkill-EP03-")
    parser.add_argument("--node-suffix", default="-v3提示词")
    parser.add_argument("--only", help="仅同步指定段号，逗号分隔，例如 1,2,15")
    parser.add_argument("--libtv")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    cwd = Path.cwd()
    libtv = args.libtv or shutil.which("libtv") or str(Path.home() / ".libtv" / "libtv")
    try:
        defaults, segments = parse_markdown(args.markdown)
        if args.only:
            selected = {f"{int(value):02d}" for value in args.only.split(",") if value.strip()}
            segments = [segment for segment in segments if segment["number"] in selected]
            if not segments:
                raise ValueError("--only 没有匹配任何生成段")
        blocked_segments = [segment for segment in segments if segment["blocked"]]
        if blocked_segments:
            detail = "；".join(
                f"V{segment['number']} {'／'.join(segment['blocked'])}"
                for segment in blocked_segments
            )
            ready = [
                segment["number"] for segment in segments if not segment["blocked"]
            ]
            hint = (
                f"；其余已就绪段可用 --only {','.join(ready)} 先行同步" if ready else ""
            )
            raise ValueError(f"{detail}{hint}")
        listing = run([libtv, "node", "list", "-p", args.project], cwd=cwd)
        listed = listing.get("nodes")
        if not isinstance(listed, list):
            raise ValueError("node list 缺少 nodes")
        resolve_assets(listed, segments)
        by_name = {
            str(item.get("name")): item
            for item in listed if isinstance(item, dict) and item.get("name")
        }
        names_by_id = {
            str(item.get("id")): str(item.get("name") or item.get("id"))
            for item in listed if isinstance(item, dict) and item.get("id")
        }
        plan: list[dict[str, Any]] = []
        for segment in segments:
            name = f"{args.node_prefix}V{segment['number']}{args.node_suffix}"
            plan.append(
                {
                    "nodeName": name,
                    "action": "update" if name in by_name else "create",
                    "duration": segment["duration"],
                    "sound": segment["sound"],
                    "mixed": [
                        {
                            "number": row["number"],
                            "asset": row["nodeName"],
                            "nodeId": row["nodeId"],
                        }
                        for row in segment["mixed"]
                    ],
                }
            )
        if not args.apply:
            print(compact({"mode": "dry-run", "nodes": plan}))
            return 0

        results: list[dict[str, Any]] = []
        for segment, item_plan in zip(segments, plan):
            name = item_plan["nodeName"]
            settings = {
                "model": defaults["model"],
                "ratio": defaults["ratio"],
                "resolution": defaults["resolution"],
                "duration": segment["duration"],
                "enableSound": segment["sound"],
            }
            existing = by_name.get(name)
            if existing:
                node_id = str(existing["id"])
                detail = read_node(libtv, args.project, node_id, cwd)
                task_info = data_of(detail).get("taskInfo")
                if isinstance(task_info, dict) and task_info.get("status") == 2:
                    raise ValueError(
                        f"{name} 已有成功生成结果，禁止在改边或改参数后才拦截；"
                        "请新建版本节点"
                    )
                old_ids = [
                    item_id(item)
                    for item in params_of(detail).get("mixedList", [])
                    if isinstance(item, dict) and item_id(item)
                ]
                if old_ids:
                    command = [libtv, "node", node_id, "-p", args.project]
                    for old_id in old_ids:
                        command += ["--left-rm", old_id]
                    run(command, cwd=cwd)
                command = [libtv, "node", node_id, "-p", args.project]
            else:
                command = [
                    libtv, "node", "create", name, "-t", "video",
                    "-p", args.project,
                ]
            command += ["--prompt", segment["prompt"]]
            command += ["-s", f"model={settings['model']}"]
            command += ["-s", "modeType=mixed2video"]
            command += ["-s", f"settings={compact({k: settings[k] for k in ('ratio', 'resolution', 'duration', 'enableSound')})}"]
            for row in segment["mixed"]:
                command += ["--left-add", row["nodeId"]]
            response = run(command, cwd=cwd)
            node_id = str(
                response.get("nodeKey")
                or response.get("id")
                or data_of(response).get("nodeKey")
                or data_of(response).get("id")
                or (existing or {}).get("id")
                or ""
            )
            if not node_id:
                refreshed = run([libtv, "node", "list", "-p", args.project], cwd=cwd)
                matches = [
                    item for item in refreshed.get("nodes", [])
                    if isinstance(item, dict) and item.get("name") == name
                ]
                if len(matches) != 1:
                    raise ValueError(f"无法解析新节点 ID：{name}")
                node_id = str(matches[0]["id"])
            update_cached_order(libtv, args.project, node_id, segment, cwd)
            detail = read_node(libtv, args.project, node_id, cwd)
            add_live_labels(detail, names_by_id)
            errors = verify(detail, segment, settings)
            canvas_errors, _, _ = audit_canvas_nodes.audit_node(detail)
            errors.extend(f"实时门禁：{error}" for error in canvas_errors)
            if errors:
                raise ValueError(f"{name} 回读失败：{errors}")
            results.append({"nodeName": name, "nodeId": node_id, "errors": 0})
        print(compact({"mode": "applied", "nodes": results}))
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
