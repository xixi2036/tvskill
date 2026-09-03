#!/usr/bin/env python3
"""Read-only audit of live TVMao video-generator nodes and ordered inputs."""

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared_patterns import (  # noqa: E402
    CLASSROOM_RE,
    DIALOGUE_RE,
    EMPTY_SCENE_RE,
    EXACT_SHOT_BLOCK_RE,
    EXACT_SHOT_RE,
    FRONT_BOARD_RE,
    LOWER_BODY_LOCK_RE,
    OS_VO_RE,
    PLANNING_RE,
    SEAT_BOARD_RE,
)
from _shot_budget import shot_budget_messages  # noqa: E402
from _fast_drama_contract import prompt_quality_messages  # noqa: E402


TVMAO_BINDING_RE = re.compile(
    r"(?<![A-Za-z0-9_@\]])@?(?P<kind>图片|视频|音频)\s*(?P<number>\d+)"
    r"(?:（(?P<label>[^）\n]+)）)?"
)
CANVAS_MENTION_RE = re.compile(
    r"@\[(?P<kind>图片|视频|音频):(?P<node_id>[^\]\s]+)\]"
    r"(?:（(?P<label>[^）\n]+)）)?"
)
LEGACY_MIXED_RE = re.compile(
    r"\{\{(?:Mixed|Image|Portrait)\s+\d+\}\}|"
    r"(?<![A-Za-z0-9_@])Mixed\s+\d+(?![A-Za-z0-9_])"
)
SYNC_CUE_RE = re.compile(r"(?:他说|她说|开口说|说出).{0,12}\{")
CHINESE_SHOT_RE = re.compile(r"^镜头\s*(\d+)\s*：", re.M)
CONTINUOUS_RE = re.compile(
    r"单一连续镜头[，,、 ]*无剪切|single continuous take,\s*no cuts", re.I
)
LONG_TAKE_INTENT_RE = re.compile(r"长镜头叙事意图\s*[：:]\s*\S+")
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
# 身份锚定句：把某张图声明为某个主体的身份来源。
# 兼容画布 canonical（@[图片:nodeId]（语义））与运行时序列化（图片N（语义））两种形态，
# 因为审计既可能拿到存储 prompt，也可能拿到 history 里的实际提交内容。
IDENTITY_ANCHOR_RE = re.compile(
    r"(?P<ref>@?\[?图片[:：]?[^\]）]{0,24}\]?（[^）]*）|图片\d+（[^）]*）)"
    r"[^。；\n]{0,60}?定义为\s*(?P<subject><主体\d+>)"
)
VOICE_BOOTSTRAP_RE = re.compile(r"一次性(?:周妍画外)?音色采样预览")
DEFAULT_MODEL_ID = "doubao-seedance-2-0-fast-260128"
SUPPORTED_MODEL_PREFIXES = ("doubao-seedance-2-0-", "cm-seedance-2.0-")
GENERIC_TOKENS = {
    "角色", "人物", "独立人物图", "场景", "场景状态", "构图", "位置", "道具",
    "音色", "逐句音频", "首帧", "续接帧", "参考", "无身份", "新版表演",
}


def parse_json_output(text: str, label: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} 未返回 JSON：{exc}") from exc


def run_tvmao(tvmao: str, args: list[str]) -> Any:
    result = subprocess.run(
        [tvmao, *args], text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"TVMao 命令失败：{message}")
    return parse_json_output(result.stdout, "TVMao")


def normalized(value: str) -> str:
    return re.sub(r"[\s_·（）()【】\[\]-]+", "", value).lower()


def media_kind(value: str) -> str:
    value = value.lower()
    if "audio" in value or "音频" in value or "音色" in value:
        return "音频"
    if "video" in value or "视频" in value:
        return "视频"
    return "图片"


def category(value: str, kind: str = "") -> str:
    if PLANNING_RE.search(value):
        return "planning"
    if kind == "音频" or re.search(r"音色|音频|声音|配音", value):
        return "audio"
    if CLEAN_FRAME_RE.search(value):
        return "frame"
    if re.search(r"场景状态|人群状态|群演状态|占座", value):
        return "population"
    if re.search(r"场景|教室|房间|走廊|餐厅|街道|地点", value):
        return "scene"
    if re.search(
        r"道具|报告|钢笔|手机|钥匙|杂志|手袋|皮包|鞋|文件|纸张|杯|门|车",
        value,
    ):
        return "prop"
    return "character"


def meaningful_tokens(value: str) -> list[str]:
    parts = re.split(r"[-_/·\s]+", value)
    tokens: list[str] = []
    for part in parts:
        part = part.strip("@[]（）()")
        part = re.sub(r"^(?:TVSkill|EP\d+)$", "", part, flags=re.I)
        for generic in sorted(GENERIC_TOKENS, key=len, reverse=True):
            part = part.replace(generic, "")
        if not part or part in GENERIC_TOKENS:
            continue
        tokens.append(normalized(part))
    return tokens


def binding_matches_asset(semantic: str, item: dict[str, Any], kind: str) -> bool:
    actual = str(item.get("label") or item.get("name") or item.get("nodeId") or "")
    if category(semantic, kind) != category(actual, kind):
        return False
    tokens = meaningful_tokens(semantic)
    if not tokens:
        return False
    actual_norm = normalized(actual)
    return any(token in actual_norm for token in tokens)


def node_id(detail: dict[str, Any]) -> str:
    return str(detail.get("id") or detail.get("nodeId") or detail.get("nodeKey") or "")


def node_status(detail: dict[str, Any]) -> str:
    value = detail.get("status") or detail.get("runStatus") or ""
    return str(value).lower()


def node_run_count(detail: dict[str, Any]) -> int:
    """Conservatively infer whether a video node has consumed its one-shot budget."""
    for key in ("runCount", "generationCount", "attemptCount"):
        value = detail.get(key)
        if isinstance(value, int) and value >= 0:
            return value
    history = detail.get("history")
    if isinstance(history, list) and history:
        return len(history)
    if detail.get("content") or detail.get("media"):
        return 1
    if node_status(detail) and node_status(detail) != "idle":
        return 1
    return 0


def node_params(detail: dict[str, Any]) -> dict[str, Any]:
    value = detail.get("params")
    return value if isinstance(value, dict) else {}


def node_model(detail: dict[str, Any]) -> str:
    params = node_params(detail)
    return str(
        detail.get("modelId")
        or detail.get("model")
        or params.get("modelId")
        or params.get("model")
        or ""
    )


def ordered_inputs(detail: dict[str, Any]) -> list[dict[str, Any]]:
    values = detail.get("_tvskillInputs") or detail.get("inputs") or []
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, dict)]


def node_fingerprint(detail: dict[str, Any]) -> str:
    payload = {
        "nodeId": node_id(detail),
        "modelId": node_model(detail),
        "params": node_params(detail),
        "inputs": [
            {
                "nodeId": str(item.get("nodeId") or item.get("id") or ""),
                "kind": media_kind(str(item.get("mediaType") or item.get("type") or "")),
                "compliance": item.get("compliance"),
            }
            for item in ordered_inputs(detail)
        ],
        "status": node_status(detail),
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_bindings(prompt: str) -> list[tuple[str, int, str]]:
    bindings: list[tuple[str, int, str]] = []
    for match in TVMAO_BINDING_RE.finditer(prompt):
        bindings.append(
            (
                match.group("kind"),
                int(match.group("number")),
                (match.group("label") or "").strip(),
            )
        )
    return bindings


def serialize_canvas_prompt(
    prompt: str, inputs: list[dict[str, Any]]
) -> tuple[str, list[str], int]:
    """Validate canvas mentions and mirror the web editor's model-facing serialization."""
    errors: list[str] = []
    counters = {"图片": 0, "视频": 0, "音频": 0}
    refs: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    for item in inputs:
        kind = media_kind(str(item.get("mediaType") or item.get("type") or ""))
        counters[kind] += 1
        item_id = str(item.get("nodeId") or item.get("id") or "")
        refs[(kind, item_id)] = (counters[kind], item)

    seen: set[tuple[str, str]] = set()
    mention_count = 0

    def replacement(match: re.Match[str]) -> str:
        nonlocal mention_count
        mention_count += 1
        kind = match.group("kind")
        node = match.group("node_id")
        semantic = (match.group("label") or "").strip()
        hit = refs.get((kind, node))
        if hit is None:
            errors.append(f"画布引用 {match.group(0)} 没有同类型入边")
            # 网页端正则只吃 `@[类型:节点ID]`，紧随其后的 `（语义名）` 是普通正文。
            # 无对应入边时网页把 mention 换成空串、把括号文本原样留下，成为孤儿括号。
            # 这里必须还原同样的残留，否则预测出的模型输入与实际不符。
            return f"（{semantic}）" if semantic else ""
        index, item = hit
        seen.add((kind, node))
        if not semantic:
            errors.append(f"画布引用 @[{kind}:{node}] 缺少括号语义标签")
            return f"{kind}{index}"
        if not binding_matches_asset(semantic, item, kind):
            actual = item.get("label") or node
            if meaningful_tokens(semantic):
                errors.append(f"画布引用 @[{kind}:{node}] 语义“{semantic}”与实际素材“{actual}”不一致")
            else:
                errors.append(f"画布引用 @[{kind}:{node}] 语义“{semantic}”无可校验标识，无法确认对应“{actual}”")
        return f"{kind}{index}（{semantic}）"

    serialized = CANVAS_MENTION_RE.sub(replacement, prompt)
    unreferenced = [
        str(item.get("label") or item.get("nodeId") or item.get("id") or "")
        for item in inputs
        if (
            media_kind(str(item.get("mediaType") or item.get("type") or "")),
            str(item.get("nodeId") or item.get("id") or ""),
        ) not in seen
    ]
    if unreferenced:
        errors.append(f"TVMao 入边未被画布 mention 绑定：{unreferenced}")
    plain_remainder = CANVAS_MENTION_RE.sub("", prompt)
    if parse_bindings(plain_remainder):
        errors.append("提示词含普通 图片N/视频N/音频N 文本；网页不会显示素材关联 chip，必须写 node-id mention")
    return serialized, errors, mention_count


def audit_node(
    detail: dict[str, Any], *, require_compliance: bool = False,
    require_one_shot: bool = False,
) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    params = node_params(detail)
    name = str(detail.get("name") or node_id(detail) or "未命名节点")
    stored_prompt = str(params.get("prompt") or "")
    if not stored_prompt:
        errors.append("缺少提示词")
    if LEGACY_MIXED_RE.search(stored_prompt):
        errors.append("节点提示词仍含 LibTV Mixed/Image/Portrait token，尚未编译为 TVMao node-id mention")

    inputs = ordered_inputs(detail)
    prompt, mention_errors, mention_count = serialize_canvas_prompt(stored_prompt, inputs)
    errors.extend(mention_errors)
    buckets: dict[str, list[dict[str, Any]]] = {"图片": [], "视频": [], "音频": []}
    for item in inputs:
        buckets[media_kind(str(item.get("mediaType") or item.get("type") or ""))].append(item)
    reference_counts = {kind: len(bucket) for kind, bucket in buckets.items()}
    reference_counts["总计"] = sum(reference_counts.values())
    for kind, limit in {"总计": 12, "图片": 9, "视频": 3, "音频": 3}.items():
        if reference_counts[kind] > limit:
            errors.append(
                f"超过 Seedance 2.0 Rule of 12：{kind}={reference_counts[kind]}>{limit}；"
                "请拆段或移除非核心道具/背景资产"
            )
    bindings = parse_bindings(prompt)
    seen: set[tuple[str, int]] = set()
    for kind, number, semantic in bindings:
        bucket = buckets[kind]
        if number < 1 or number > len(bucket):
            errors.append(f"@{kind}{number} 越界，实际只有 {len(bucket)} 个{kind}输入")
            continue
        key = (kind, number)
        seen.add(key)
        if not semantic:
            errors.append(f"@{kind}{number} 缺少括号语义标签")
            continue
        if not binding_matches_asset(semantic, bucket[number - 1], kind):
            actual = bucket[number - 1].get("label") or bucket[number - 1].get("nodeId")
            if meaningful_tokens(semantic):
                errors.append(f"@{kind}{number} 语义“{semantic}”与实际素材“{actual}”不一致")
            else:
                errors.append(f"@{kind}{number} 语义“{semantic}”无可校验标识，无法确认对应“{actual}”")
    unreferenced = [
        f"{kind}{index}"
        for kind, bucket in buckets.items()
        for index in range(1, len(bucket) + 1)
        if (kind, index) not in seen
    ]
    if unreferenced:
        errors.append(f"TVMao 入边未被提示词绑定：{unreferenced}")

    planning_assets = [
        str(item.get("label") or item.get("nodeId") or "")
        for item in inputs
        if PLANNING_RE.search(str(item.get("label") or ""))
    ]
    if planning_assets:
        errors.append(f"规划图进入 TVMao 输入边：{planning_assets}")

    duration = int(params.get("duration") or 0)
    exact_shots = [int(value) for value in EXACT_SHOT_RE.findall(prompt)]
    chinese_shots = [int(value) for value in CHINESE_SHOT_RE.findall(prompt)]
    if chinese_shots:
        errors.append("TVMao 多镜提示词使用了旧“镜头N：”标签，应改为精确“Shot N:”")
    if exact_shots:
        if exact_shots != list(range(1, len(exact_shots) + 1)):
            errors.append("Shot N 编号不连续")
        if CONTINUOUS_RE.search(prompt):
            errors.append("同一提示词同时声明连续镜头和 Shot N 剪切")
    elif not chinese_shots and not CONTINUOUS_RE.search(prompt):
        errors.append("未声明“单一连续镜头，无剪切”，也没有精确 Shot N: 多镜结构")
    elif not chinese_shots:
        budget_errors, budget_warnings = shot_budget_messages(
            duration,
            1,
            continuous_take=True,
            has_long_take_intent=bool(LONG_TAKE_INTENT_RE.search(prompt)),
        )
        errors.extend(budget_errors)
        warnings.extend(budget_warnings)

    quality_errors, quality_warnings = prompt_quality_messages(
        prompt,
        duration,
        has_character_references=bool(re.search(r"（角色[-：]", prompt)),
    )
    errors.extend(quality_errors)
    warnings.extend(quality_warnings)

    dialogue_matches = list(DIALOGUE_RE.finditer(prompt))
    dialogue = [match.group(1) for match in dialogue_matches]

    def is_offscreen_voice(match: re.Match[str]) -> bool:
        context = prompt[max(0, match.start() - 100):match.start()]
        return bool(re.search(r"(?:画外|电话)?\s*(?:VO|OS|旁白).{0,36}$", context, re.I))

    on_screen_dialogue = [match for match in dialogue_matches if not is_offscreen_voice(match)]
    has_sync = bool(on_screen_dialogue and SYNC_CUE_RE.search(prompt))
    has_os_vo = bool(OS_VO_RE.search(prompt))
    voice_bootstrap = bool(VOICE_BOOTSTRAP_RE.search(prompt))
    audio_inputs = buckets["音频"]
    if dialogue or has_os_vo:
        if not audio_inputs and not voice_bootstrap:
            errors.append("存在对白/OS/VO，但没有 audio-input 入边")
        if voice_bootstrap:
            if audio_inputs:
                errors.append("音色采样预览不得绑定 audio-input；它只用于建立首条角色音色")
            if len(dialogue) != 1:
                errors.append("音色采样预览必须只含一段原剧本台词")
            if "不作为正式成片或续接来源" not in prompt:
                errors.append("音色采样预览必须声明不作为正式成片或续接来源")
            if not re.search(r"不要\s*(?:bgm|BGM|音乐)|无音乐", prompt):
                errors.append("音色采样预览必须明确禁用音乐")
        spoken_subjects: set[str] = set()
        for match in on_screen_dialogue:
            context = prompt[max(0, match.start() - 140):match.start()]
            found = re.findall(r"<主体\d+>", context)
            if found:
                spoken_subjects.add(found[-1])
        controlled_subjects = set(re.findall(
            r"@?音频\d+（[^）]+）.{0,50}?只控制\s*(<主体\d+>|[^\s，。；：,、]{0,10}(?:VO|OS|旁白)).{0,24}?音色",
            prompt,
        ))
        missing = [] if voice_bootstrap else sorted(spoken_subjects - controlled_subjects)
        if missing:
            errors.append(f"说话主体缺少对应独立音色绑定：{', '.join(missing)}")

        short_dialogue = any(len(re.sub(r"\W", "", line)) <= 6 for line in dialogue)
        if short_dialogue and ROBOTIC_PROSODY_RE.search(prompt):
            errors.append("六字以内短台词使用了放慢、停顿、逐字或匀速控制，存在机器人节奏风险")

    # ── 职责主权：每个出场 <主体N> 必须有且只有一份身份锚 ──────────────
    # 现有 Rule of 12 只卡参考图**数量**，不卡**职责**。真实踩过两种形状：
    #   ① 覆盖缺口：正文用了 <主体1> 却一张角色图都没绑，人物脸每段随机、跨段无法一致
    #   ② 双 Primary：两张图都声明锚定同一个 <主体N>，参考竞争直接导致身份漂移
    # 后者正是十轴审计里「参考污染／身份漂移 → 减少竞争参考」记录过的失败形状，
    # 此前只能事后返工才发现，这里把它前移成事前拦截。
    identity_owner: dict[str, list[str]] = {}
    for match in IDENTITY_ANCHOR_RE.finditer(prompt):
        identity_owner.setdefault(match.group("subject"), []).append(match.group("ref"))
    for subject, refs in sorted(identity_owner.items()):
        if len(set(refs)) > 1:
            errors.append(
                f"{subject} 同时被 {'、'.join(sorted(set(refs)))} 声明为身份锚定："
                "同一职责只能有一个主权来源，多张竞争会导致身份漂移"
            )
    unowned = sorted(set(re.findall(r"<主体\d+>", prompt)) - set(identity_owner))
    if unowned:
        errors.append(
            f"以下主体在正文出场但没有任何身份锚定：{', '.join(unowned)}；"
            "每个可识别人物必须有一份角色图声明「定义为 <主体N>…严格按此图渲染」，"
            "否则该人物的五官与服装每次生成都是随机的，跨段无法一致"
        )

    # Stop at the structured tail. Otherwise the last Shot block absorbs the
    # global SOUND/CONSTRAINTS/NOT sections and false-matches words such as
    # "群体反应" as if they were part of a synchronized action.
    shot_region = prompt.split("【声音设计】", 1)[0]
    shot_blocks = EXACT_SHOT_BLOCK_RE.findall(shot_region) or [shot_region]
    sync_blocks = [block for block in shot_blocks if SYNC_CUE_RE.search(block)]
    if any(len(DIALOGUE_RE.findall(block)) != 1 for block in sync_blocks):
        errors.append("每个同步对白 Shot 必须只有一位说话人和一个自然意群")
    if any(COMPLEX_ACTION_RE.search(block) for block in sync_blocks):
        errors.append("同步对白 Shot 同时承担走位、道具、群演或特效竞争动作")
    if has_sync and not any(CLEAN_FRAME_RE.search(str(item.get("label") or "")) for item in inputs):
        errors.append("同步对白缺少干净首帧或已验收续接帧")

    if EXACT_TEXT_RE.search(prompt):
        errors.append("把精确画面文字交给视频模型生成")
    labels = " ".join(str(item.get("label") or "") for item in inputs)
    if CROWD_RE.search(prompt) and WIDE_RE.search(prompt):
        if EMPTY_SCENE_RE.search(labels) and not re.search(r"占座|人群状态|群演状态", labels):
            errors.append("全景要求可见人群，但输入边只有空场景")
        if CLASSROOM_RE.search(f"{prompt} {labels}"):
            if not OCCUPIED_SCENE_RE.search(labels):
                errors.append("教室群像全景缺少已验收的占座＋教学朝向场景状态图")
            if not FRONT_BOARD_RE.search(prompt) or not SEAT_BOARD_RE.search(prompt):
                errors.append("教室群像未锁定黑板前墙以及课桌、座椅和学生下半身的教学朝向")
            if GROUP_REACTION_RE.search(prompt) and not LOWER_BODY_LOCK_RE.search(prompt):
                errors.append("教室群像反应未声明只转眼/头/肩并保持骨盆、膝盖和坐姿朝向")

    model = node_model(detail)
    if not model.startswith(SUPPORTED_MODEL_PREFIXES):
        warnings.append(f"模型不是 TVSkill 支持的 Seedance 2.0 modelId：{model}")
    elif model != DEFAULT_MODEL_ID:
        warnings.append(f"模型不是默认 {DEFAULT_MODEL_ID}：{model}")
    if params.get("ratio") != "9:16":
        warnings.append(f"画幅不是 9:16：{params.get('ratio')}")
    if str(params.get("resolution") or "").lower() != "480p":
        warnings.append(f"分辨率不是 480p：{params.get('resolution')}")

    non_active = [
        str(item.get("label") or item.get("nodeId") or "")
        for item in inputs
        if str(item.get("compliance") or "").lower() not in {"", "active"}
    ]
    unknown_compliance = [
        str(item.get("label") or item.get("nodeId") or "")
        for item in inputs if not item.get("compliance")
    ]
    if require_compliance and (non_active or unknown_compliance):
        errors.append(f"Seedance 运行前素材合规状态未全部 active：{non_active + unknown_compliance}")
    elif non_active:
        warnings.append(f"素材合规状态尚未 active：{non_active}")

    status = node_status(detail)
    run_count = node_run_count(detail)
    if require_one_shot and run_count > 0:
        errors.append(
            f"一次性视频预算已消耗：runCount={run_count}；禁止同节点或同提示词重新生成"
        )
    if status in {"succeeded", "generating"}:
        warnings.append(f"节点状态为 {status}；修改输入时应新建版本节点")

    return errors, warnings, {
        "nodeId": node_id(detail),
        "name": name,
        "inputs": len(inputs),
        "bindings": mention_count,
        "duration": duration,
        "shots": len(exact_shots) or len(chinese_shots) or 1,
        "fingerprint": node_fingerprint(detail),
        "status": status,
        "runCount": run_count,
    }


def find_tvmao(explicit: str | None) -> str:
    candidates = [explicit, shutil.which("tvmao"), str(Path.home() / ".tvmao" / "tvmao")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise ValueError("找不到 tvmao；请用 --tvmao 指定")


def object_id(value: dict[str, Any]) -> str:
    return str(value.get("id") or value.get("nodeId") or value.get("nodeKey") or "")


def edge_from(value: dict[str, Any]) -> str:
    source = value.get("from") or value.get("fromNodeId") or value.get("source")
    if isinstance(source, dict):
        return object_id(source)
    return str(source or "")


def parse_mapping(values: list[str], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{label} 必须使用 左值=节点ID：{value}")
        key, node = value.split("=", 1)
        if not key.strip() or not node.strip():
            raise ValueError(f"{label} 映射不能为空：{value}")
        result[key.strip()] = node.strip()
    return result


def collect_live_details(
    tvmao: str,
    project: int,
    targets: list[str],
    *,
    audit_all: bool,
    asset_labels: dict[str, str],
) -> list[dict[str, Any]]:
    listed = run_tvmao(tvmao, ["node", "list", "--project", str(project)])
    if not isinstance(listed, list):
        raise ValueError("tvmao node list 顶层必须是数组")
    by_id = {object_id(item): item for item in listed if isinstance(item, dict) and object_id(item)}
    if audit_all:
        targets = [
            node for node, item in by_id.items()
            if str(item.get("type") or "") == "video-generator"
        ]
    if not targets:
        if audit_all:
            raise ValueError(
                "项目内没有 video-generator 节点；Markdown 中写出的参考名不构成画布关联，"
                "必须先创建节点、连接真实入边并再次运行 --all/--pre-run 审计"
            )
        raise ValueError("必须用 --node 指定 video-generator 节点，或显式使用 --all")

    compliance_payload = run_tvmao(tvmao, ["compliance", "status", "--project", str(project)])
    compliance: dict[str, str] = {}
    if isinstance(compliance_payload, list):
        for item in compliance_payload:
            if isinstance(item, dict) and object_id(item):
                compliance[object_id(item)] = str(item.get("status") or "")

    details: list[dict[str, Any]] = []
    for target in targets:
        detail = run_tvmao(tvmao, ["node", "get", target, "--project", str(project)])
        if not isinstance(detail, dict):
            raise ValueError(f"tvmao node get {target} 顶层必须是 object")
        if isinstance(detail.get("node"), dict):
            detail = dict(detail["node"])
        edges = run_tvmao(tvmao, ["edge", "list", "--to", target, "--project", str(project)])
        if not isinstance(edges, list):
            raise ValueError(f"tvmao edge list --to {target} 顶层必须是数组")
        inputs: list[dict[str, Any]] = []
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            upstream_id = edge_from(edge)
            upstream = by_id.get(upstream_id, {})
            inputs.append(
                {
                    "nodeId": upstream_id,
                    "type": upstream.get("type"),
                    "mediaType": upstream.get("type"),
                    "label": asset_labels.get(upstream_id) or upstream.get("name") or upstream_id,
                    "compliance": compliance.get(upstream_id),
                    "edgeId": object_id(edge),
                }
            )
        detail["_tvskillInputs"] = inputs
        details.append(detail)
    return details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--project", type=int)
    source.add_argument("--detail-json", nargs="+", type=Path)
    parser.add_argument("--node", action="append", default=[])
    parser.add_argument("--all", action="store_true", help="审计项目内全部 video-generator 节点")
    parser.add_argument("--asset", action="append", default=[], help="素材语义=节点ID，可重复")
    parser.add_argument("--tvmao")
    parser.add_argument(
        "--pre-run", action="store_true",
        help="要求 idle、runCount=0 且全部素材合规状态为 active；CLI 2.0.0 节点须从网页运行",
    )
    parser.add_argument("--receipt", type=Path, help="零硬错误时写出 Markdown 节点指纹凭证")
    args = parser.parse_args()
    try:
        semantic_to_id = parse_mapping(args.asset, "--asset")
        labels_by_id = {node: semantic for semantic, node in semantic_to_id.items()}
        if args.detail_json:
            details = []
            for path in args.detail_json:
                value = parse_json_output(path.read_text(encoding="utf-8"), str(path))
                if not isinstance(value, dict):
                    raise ValueError(f"{path} 顶层必须是 object")
                details.append(value)
        else:
            details = collect_live_details(
                find_tvmao(args.tvmao), args.project, args.node,
                audit_all=args.all, asset_labels=labels_by_id,
            )
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    total_errors = 0
    total_warnings = 0
    receipt_rows: list[dict[str, Any]] = []
    for detail in details:
        errors, warnings, summary = audit_node(
            detail,
            require_compliance=args.pre_run,
            require_one_shot=args.pre_run,
        )
        if args.pre_run and summary["status"] != "idle":
            errors.append(f"运行前门禁要求 idle；当前状态为 {summary['status'] or 'unknown'}")
        total_errors += len(errors)
        total_warnings += len(warnings)
        receipt_rows.append({
            "nodeId": summary["nodeId"], "name": summary["name"],
            "fingerprint": summary["fingerprint"], "warnings": len(warnings),
            "runCount": summary["runCount"],
        })
        print(f"NODE: {summary['name']}")
        for error in errors:
            print(f"ERROR: {error}")
        for warning in warnings:
            print(f"WARNING: {warning}")
        print(
            f"NODE_SUMMARY: inputs={summary['inputs']} bindings={summary['bindings']} "
            f"duration={summary['duration']}s shots={summary['shots']} "
            f"errors={len(errors)} warnings={len(warnings)}"
        )
    print(f"SUMMARY: nodes={len(details)} errors={total_errors} warnings={total_warnings}")
    if total_errors:
        return 1
    if args.receipt:
        lines = [
            "# TVSkill TVMao 运行前审计凭证", "",
            f"- 生成时间（UTC）：{datetime.now(timezone.utc).isoformat()}",
            f"- 项目：`{args.project or 'detail-json'}`",
            f"- 节点数：{len(receipt_rows)}",
            f"- 运行前模式：{'是' if args.pre_run else '否'}",
            "- 安全运行入口：TVMao 网页（CLI 2.0.0 未序列化 node-id mention）",
            "- 硬错误：0", "",
            "| 节点 ID | 节点名 | 输入指纹 SHA-256 | runCount | 警告 |",
            "|---|---|---|---:|---:|",
        ]
        for row in receipt_rows:
            lines.append(
                f"| `{row['nodeId']}` | {row['name']} | `{row['fingerprint']}` | "
                f"{row['runCount']} | {row['warnings']} |"
            )
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"RECEIPT: {args.receipt}")
    print("OK: live TVMao canvas mention and ordered-input preflight passed")
    if args.pre_run:
        print("RUN_GATE: use TVMao web; CLI 2.0.0 node run does not serialize node-id mentions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
