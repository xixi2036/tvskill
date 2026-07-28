#!/usr/bin/env python3
"""Read-only audit of live LibTV video prompts, Mixed order, and readiness."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _shared_patterns import (  # noqa: E402
    OS_VO_RE,
    DIALOGUE_RE,
    EXACT_SHOT_RE,
    EXACT_SHOT_BLOCK_RE,
    PLANNING_RE,
    CLASSROOM_RE,
    FRONT_BOARD_RE,
    SEAT_BOARD_RE,
    LOWER_BODY_LOCK_RE,
    EMPTY_SCENE_RE,
)


BRACKET_BINDING_RE = re.compile(
    r"@\[(?P<label>[^\]]+)\]\s*\{\{Mixed\s+(?P<number>\d+)\}\}"
)
PAREN_BINDING_RE = re.compile(
    r"@(?P<label>[^@\n(){}]{1,80})\(\{\{Mixed\s+(?P<number>\d+)\}\}\)"
)
SYNC_CUE_RE = re.compile(r"(?:他说|她说|开口说|说出).{0,12}\{")
CHINESE_SHOT_RE = re.compile(r"^镜头\s*(\d+)\s*：", re.M)
CONTINUOUS_RE = re.compile(r"单一连续镜头[，,、 ]*无剪切|single continuous take,\s*no cuts", re.I)
CLEAN_FRAME_RE = re.compile(r"首帧|续接帧|验收末帧|稳定末帧")
CROWD_RE = re.compile(r"学生|众人|人群|群演|全班|全场")
WIDE_RE = re.compile(r"大全景|中全景|全景")
OCCUPIED_SCENE_RE = re.compile(r"占座|人群状态|群演状态|教学朝向")
GROUP_REACTION_RE = re.compile(r"转头|侧头|回看|看向|视线|安静|停笔")
EXACT_TEXT_RE = re.compile(
    r"文字以本提示词指定|清晰显示且只显示|必须(?:生成|出现|显示).{0,18}文字|"
    r"纸面.{0,12}(?:显示|写出).{0,30}[“\"]"
)
COMPLEX_ACTION_RE = re.compile(
    r"走入|走向|沿.{0,12}走|转身|递给|递入|推向|飞出|飞向|撞上|扎入|"
    r"掠过|群体反应|全班.{0,12}(?:转头|安静)|爆炸|特效"
)
ROBOTIC_PROSODY_RE = re.compile(r"放慢|停半拍|一字一顿|拖长|逐字|匀速|均匀")
GENERIC_TOKENS = {
    "角色", "人物", "独立人物图", "场景", "场景状态", "构图", "位置", "道具",
    "音色", "逐句音频", "首帧", "续接帧", "参考", "无身份", "新版表演",
}


def data_of(detail: dict[str, Any]) -> dict[str, Any]:
    return detail.get("data") if isinstance(detail.get("data"), dict) else detail


def params_of(detail: dict[str, Any]) -> dict[str, Any]:
    data = data_of(detail)
    return data.get("params") if isinstance(data.get("params"), dict) else {}


def task_status(detail: dict[str, Any]) -> int | None:
    task_info = data_of(detail).get("taskInfo")
    if not isinstance(task_info, dict):
        return None
    value = task_info.get("status")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def node_id(detail: dict[str, Any]) -> str:
    data = data_of(detail)
    return str(
        detail.get("nodeKey")
        or detail.get("id")
        or data.get("nodeKey")
        or data.get("id")
        or ""
    )


def node_fingerprint(detail: dict[str, Any]) -> str:
    """Fingerprint every live input that can change a generation result."""
    params = params_of(detail)
    payload = {
        "nodeId": node_id(detail),
        "prompt": params.get("prompt"),
        "model": params.get("model"),
        "settings": params.get("settings"),
        "mixedList": [
            {
                "id": item_id(item),
                "mediaType": item.get("mediaType"),
            }
            for item in params.get("mixedList", [])
            if isinstance(item, dict)
        ],
        "mixedListOrder": params.get("mixedListOrder"),
        "imageListOrder": params.get("imageListOrder"),
        "videoListOrder": params.get("videoListOrder"),
        "audioListOrder": params.get("audioListOrder"),
        "taskStatus": task_status(detail),
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_json_output(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} 未返回 JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} 顶层必须是 object")
    return value


def run_libtv(libtv: str, args: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        [libtv, *args], text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"LibTV 命令失败：{message}")
    return parse_json_output(result.stdout, "LibTV")


def normalized(value: str) -> str:
    return re.sub(r"[\s_·（）()【】\[\]-]+", "", value).lower()


def category(value: str, media_type: str = "") -> str:
    if PLANNING_RE.search(value):
        return "planning"
    if media_type == "audio" or re.search(r"音色|音频|声音|配音", value):
        return "audio"
    if CLEAN_FRAME_RE.search(value):
        return "frame"
    if re.search(r"场景状态|人群状态|群演状态|占座", value):
        return "population"
    if re.search(r"场景|教室|房间|走廊|餐厅|街道|地点", value):
        return "scene"
    if re.search(r"道具|报告|钢笔|手机|文件|纸张|杯|门|车", value):
        return "prop"
    if re.search(r"人物|角色", value):
        return "character"
    return "character"


def meaningful_tokens(value: str) -> list[str]:
    parts = re.split(r"[-_/·\s]+", value)
    tokens: list[str] = []
    for part in parts:
        part = part.strip("@[]（）()")
        part = re.sub(r"^(?:TVSkill|EP\d+)$", "", part, flags=re.I)
        for generic in sorted(GENERIC_TOKENS, key=len, reverse=True):
            part = part.replace(generic, "")
        if not part or part in GENERIC_TOKENS or len(part) < 2:
            continue
        tokens.append(normalized(part))
    return tokens


def binding_matches_asset(semantic: str, item: dict[str, Any]) -> bool:
    actual = str(item.get("label") or item.get("name") or "")
    expected_category = category(semantic)
    actual_category = category(actual, str(item.get("mediaType") or ""))
    if expected_category != actual_category:
        return False
    tokens = meaningful_tokens(semantic)
    if not tokens:
        return True
    actual_norm = normalized(actual)
    return any(token in actual_norm for token in tokens)


def parse_bindings(prompt: str) -> list[tuple[str, int]]:
    found: list[tuple[int, str, int]] = []
    for pattern in (BRACKET_BINDING_RE, PAREN_BINDING_RE):
        for match in pattern.finditer(prompt):
            found.append((match.start(), match.group("label").strip(), int(match.group("number"))))
    return [(label, number) for _, label, number in sorted(found)]


def ordered_mixed(params: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    mixed = params.get("mixedList")
    if not isinstance(mixed, list):
        mixed = []
    by_id = {
        str(item.get("nodeId") or item.get("nodeKey")): item
        for item in mixed if isinstance(item, dict)
    }
    order = params.get("mixedListOrder")
    if not isinstance(order, list) or not order:
        order = [str(item.get("nodeId") or item.get("nodeKey")) for item in mixed]
    order = [str(node_id) for node_id in order]
    if len(order) != len(set(order)):
        errors.append("mixedListOrder 存在重复节点")
    ordered: list[dict[str, Any]] = []
    for node_id in order:
        item = by_id.get(node_id)
        if item is None:
            errors.append(f"mixedListOrder 中的节点 {node_id} 不在 mixedList")
            continue
        ordered.append(item)
    if len(ordered) != len(mixed):
        errors.append("mixedList 与 mixedListOrder 数量不一致")
    return ordered, errors


def item_id(item: dict[str, Any]) -> str:
    return str(item.get("nodeId") or item.get("nodeKey") or "")


def audit_media_orders(params: dict[str, Any], mixed: list[dict[str, Any]]) -> list[str]:
    """Require each cached media array to agree with its explicit Order field."""
    errors: list[str] = []
    union: list[str] = []
    for list_key in ("imageList", "videoList", "audioList"):
        order_key = f"{list_key}Order"
        items = params.get(list_key)
        order = params.get(order_key)
        if (items is None or items == []) and (order is None or order == []):
            continue
        if not isinstance(items, list) or not isinstance(order, list):
            errors.append(f"{list_key} 与 {order_key} 必须同时存在且为数组")
            continue
        actual = [item_id(item) for item in items if isinstance(item, dict)]
        expected = [str(value) for value in order]
        if not all(actual):
            errors.append(f"{list_key} 存在缺少 nodeId/nodeKey 的素材")
        if actual != expected:
            errors.append(f"{list_key} 与 {order_key} 顺序不一致")
        if len(expected) != len(set(expected)):
            errors.append(f"{order_key} 存在重复节点")
        union.extend(expected)
    mixed_ids = [item_id(item) for item in mixed]
    if union and (len(union) != len(set(union)) or set(union) != set(mixed_ids)):
        errors.append("分媒体列表与 mixedList 的节点集合不一致")
    return errors


def audit_node(detail: dict[str, Any]) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    data = data_of(detail)
    params = params_of(detail)
    name = str(data.get("name") or detail.get("name") or detail.get("nodeKey") or "未命名节点")
    prompt = str(params.get("prompt") or "")
    if not prompt:
        errors.append("缺少提示词")
    ordered, order_errors = ordered_mixed(params)
    errors.extend(order_errors)
    errors.extend(audit_media_orders(params, ordered))
    bindings = parse_bindings(prompt)
    seen_numbers: dict[int, str] = {}
    for semantic, number in bindings:
        if number < 1 or number > len(ordered):
            errors.append(f"@[{semantic}] 引用 Mixed {number}，实际只有 {len(ordered)} 个素材")
            continue
        if number in seen_numbers and seen_numbers[number] != semantic:
            errors.append(
                f"Mixed {number} 同时绑定 {seen_numbers[number]} 与 {semantic}"
            )
        seen_numbers[number] = semantic
        item = ordered[number - 1]
        if not binding_matches_asset(semantic, item):
            actual = item.get("label") or item.get("name") or item.get("nodeId")
            errors.append(f"Mixed {number} 语义“{semantic}”与实际素材“{actual}”不一致")
    unreferenced = [
        index for index in range(1, len(ordered) + 1) if index not in seen_numbers
    ]
    if unreferenced:
        errors.append(f"画布 Mixed 未被提示词绑定：{unreferenced}")

    planning_assets = [
        str(item.get("label") or item.get("name") or item.get("nodeId"))
        for item in ordered
        if PLANNING_RE.search(str(item.get("label") or item.get("name") or ""))
    ]
    if planning_assets:
        errors.append(f"规划图进入 Mixed：{planning_assets}")

    settings = params.get("settings") if isinstance(params.get("settings"), dict) else {}
    duration = int(settings.get("duration") or 0)
    exact_shots = [int(value) for value in EXACT_SHOT_RE.findall(prompt)]
    chinese_shots = [int(value) for value in CHINESE_SHOT_RE.findall(prompt)]
    if chinese_shots:
        errors.append("LibTV 多镜提示词使用了旧“镜头N：”标签，应改为精确“Shot N:”")
    if exact_shots:
        if exact_shots != list(range(1, len(exact_shots) + 1)):
            errors.append("Shot N 编号不连续")
        if CONTINUOUS_RE.search(prompt):
            errors.append("同一提示词同时声明连续镜头和 Shot N 剪切")
        if duration <= 15 and len(exact_shots) > 3:
            errors.append(
                f"{duration} 秒包含 {len(exact_shots)} 个生成 Shot；"
                "10–15 秒原生生成通常最多承载 2–3 个清楚事件"
            )
        elif duration and len(exact_shots) > 1 and duration / len(exact_shots) < 3:
            warnings.append(
                f"{duration} 秒包含 {len(exact_shots)} 镜，平均不足 3 秒；"
                "请确认没有把 v3 内部剪辑节拍误当成模型 Shot"
            )
    elif not chinese_shots and not CONTINUOUS_RE.search(prompt):
        errors.append("未声明“单一连续镜头，无剪切”，也没有精确 Shot N: 多镜结构")

    dialogue = DIALOGUE_RE.findall(prompt)
    has_sync = bool(SYNC_CUE_RE.search(prompt))
    has_os_vo = bool(OS_VO_RE.search(prompt))
    audio = params.get("audioList") if isinstance(params.get("audioList"), list) else []
    sound_value = settings.get("enableSound")
    sound_on = sound_value is True or str(sound_value or "").lower() in {"on", "true", "1"}
    if dialogue or has_os_vo:
        if not sound_on:
            errors.append("存在对白/OS/VO，但节点声音未开启")
        if not audio:
            errors.append("存在对白/OS/VO，但 audioList 为空")
        spoken_subjects: set[str] = set()
        for match in DIALOGUE_RE.finditer(prompt):
            context = prompt[max(0, match.start() - 140):match.start()]
            found = re.findall(r"<主体\d+>", context)
            if found:
                spoken_subjects.add(found[-1])
        controlled_subjects = set(re.findall(
            r"\{\{Mixed\s+\d+\}\}.{0,40}?只控制\s*(<主体\d+>).{0,24}?音色",
            prompt,
        ))
        missing = sorted(spoken_subjects - controlled_subjects)
        if missing:
            errors.append(f"说话主体缺少对应独立音色绑定：{', '.join(missing)}")
        short_dialogue = any(len(re.sub(r"\W", "", line)) <= 6 for line in dialogue)
        if short_dialogue and ROBOTIC_PROSODY_RE.search(prompt):
            errors.append("六字以内短台词使用了放慢、停顿、逐字或匀速控制，存在机器人节奏风险")
    shot_blocks = EXACT_SHOT_BLOCK_RE.findall(prompt) or [prompt]
    sync_blocks = [block for block in shot_blocks if SYNC_CUE_RE.search(block)]
    if any(len(DIALOGUE_RE.findall(block)) != 1 for block in sync_blocks):
        errors.append("每个同步对白 Shot 必须只有一位说话人和一个自然意群")
    if any(COMPLEX_ACTION_RE.search(block) for block in sync_blocks):
        errors.append("同步对白 Shot 同时承担走位、道具、群演或特效竞争动作")
    if has_sync and not any(CLEAN_FRAME_RE.search(
        str(item.get("label") or item.get("name") or "")
    ) for item in ordered) and "原生声画同出预览" not in prompt:
        errors.append("同步对白缺少干净首帧或已验收续接帧")

    if EXACT_TEXT_RE.search(prompt):
        errors.append("把精确画面文字交给视频模型生成")
    if CROWD_RE.search(prompt) and WIDE_RE.search(prompt):
        labels = " ".join(str(item.get("label") or item.get("name") or "") for item in ordered)
        if EMPTY_SCENE_RE.search(labels) and not re.search(r"占座|人群状态|群演状态", labels):
            errors.append("全景要求可见人群，但 Mixed 只有空场景")
        if CLASSROOM_RE.search(f"{prompt} {labels}"):
            if not OCCUPIED_SCENE_RE.search(labels):
                errors.append("教室群像全景缺少已验收的占座＋教学朝向场景状态图")
            if not FRONT_BOARD_RE.search(prompt) or not SEAT_BOARD_RE.search(prompt):
                errors.append(
                    "教室群像未锁定黑板前墙以及课桌、座椅和学生下半身的教学朝向"
                )
            if GROUP_REACTION_RE.search(prompt) and not LOWER_BODY_LOCK_RE.search(prompt):
                errors.append(
                    "教室群像反应未声明只转眼/头/肩并保持骨盆、膝盖和坐姿朝向"
                )

    if params.get("model") not in {
        "Seedance 2.0 VIP",
        "Seedance 2.0 Fast VIP",
    }:
        warnings.append(f"模型不是受支持的 Seedance 2.0 VIP/Fast VIP 档位：{params.get('model')}")
    if settings.get("ratio") != "9:16":
        warnings.append(f"画幅不是 9:16：{settings.get('ratio')}")
    if str(settings.get("resolution") or "").lower() != "480p":
        warnings.append(f"分辨率不是 480P：{settings.get('resolution')}")
    task_info = data.get("taskInfo")
    if isinstance(task_info, dict) and task_info.get("status") == 2:
        warnings.append("节点已有生成结果；修复提示词后不能沿用旧成片作为连续性来源")

    return errors, warnings, {
        "nodeId": node_id(detail),
        "name": name,
        "mixed": len(ordered),
        "bindings": len(bindings),
        "duration": duration,
        "shots": len(exact_shots) or len(chinese_shots) or 1,
        "fingerprint": node_fingerprint(detail),
    }


def find_libtv(explicit: str | None) -> str:
    candidates = [
        explicit,
        shutil.which("libtv"),
        str(Path.home() / ".libtv" / "libtv"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise ValueError("找不到 libtv；请用 --libtv 指定")


def collect_live_details(
    libtv: str, project: str, nodes: list[str], name_prefix: str
) -> list[dict[str, Any]]:
    listing = run_libtv(libtv, ["node", "list", "-p", project])
    listed = listing.get("nodes")
    if not isinstance(listed, list):
        raise ValueError("node list 未返回 nodes 数组")
    targets: list[str] = []
    if nodes:
        targets = nodes
    else:
        for item in listed:
            if not isinstance(item, dict) or item.get("type") != "video":
                continue
            name = str(item.get("name") or "")
            if name.startswith(name_prefix):
                targets.append(str(item.get("id") or name))
    if not targets:
        raise ValueError("没有找到目标 video 节点")
    names_by_id = {
        str(item.get("id")): str(item.get("name") or item.get("id"))
        for item in listed if isinstance(item, dict) and item.get("id")
    }
    details = [run_libtv(libtv, ["node", target, "-p", project]) for target in targets]
    for detail in details:
        data = detail.get("data") if isinstance(detail.get("data"), dict) else detail
        params = data.get("params") if isinstance(data.get("params"), dict) else {}
        for key in ("imageList", "videoList", "audioList", "mixedList"):
            items = params.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or item.get("label"):
                    continue
                node_id = str(item.get("nodeId") or item.get("nodeKey") or "")
                if node_id in names_by_id:
                    item["label"] = names_by_id[node_id]
    return details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--project")
    source.add_argument("--detail-json", nargs="+", type=Path)
    parser.add_argument("--node", action="append", default=[])
    parser.add_argument("--name-prefix", default="TVSkill-")
    parser.add_argument("--libtv")
    parser.add_argument(
        "--pre-run",
        action="store_true",
        help="按运行前门禁审计；已有成功生成结果也视为硬错误",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        help="审计零硬错误时写出 Markdown 节点指纹凭证",
    )
    args = parser.parse_args()
    try:
        if args.detail_json:
            details = [
                parse_json_output(path.read_text(encoding="utf-8"), str(path))
                for path in args.detail_json
            ]
        else:
            details = collect_live_details(
                find_libtv(args.libtv), args.project, args.node, args.name_prefix
            )
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    total_errors = 0
    total_warnings = 0
    receipt_rows: list[dict[str, Any]] = []
    for detail in details:
        errors, warnings, summary = audit_node(detail)
        if args.pre_run and task_status(detail) == 2:
            errors.append("运行前门禁要求未运行节点；当前节点已有成功生成结果")
        total_errors += len(errors)
        total_warnings += len(warnings)
        receipt_rows.append(
            {
                "nodeId": summary["nodeId"],
                "name": summary["name"],
                "fingerprint": summary["fingerprint"],
                "warnings": len(warnings),
            }
        )
        print(f"NODE: {summary['name']}")
        for error in errors:
            print(f"ERROR: {error}")
        for warning in warnings:
            print(f"WARNING: {warning}")
        print(
            f"NODE_SUMMARY: mixed={summary['mixed']} bindings={summary['bindings']} "
            f"duration={summary['duration']}s shots={summary['shots']} "
            f"errors={len(errors)} warnings={len(warnings)}"
        )
    print(
        f"SUMMARY: nodes={len(details)} errors={total_errors} warnings={total_warnings}"
    )
    if total_errors:
        return 1
    if args.receipt:
        lines = [
            "# TVSkill LibTV 运行前审计凭证",
            "",
            f"- 生成时间（UTC）：{datetime.now(timezone.utc).isoformat()}",
            f"- 项目：`{args.project or 'detail-json'}`",
            f"- 节点数：{len(receipt_rows)}",
            f"- 运行前模式：{'是' if args.pre_run else '否'}",
            "- 硬错误：0",
            "",
            "| 节点 ID | 节点名 | 输入指纹 SHA-256 | 警告 |",
            "|---|---|---|---:|",
        ]
        for row in receipt_rows:
            lines.append(
                f"| `{row['nodeId']}` | {row['name']} | "
                f"`{row['fingerprint']}` | {row['warnings']} |"
            )
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"RECEIPT: {args.receipt}")
    print("OK: live LibTV prompt and Mixed preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
