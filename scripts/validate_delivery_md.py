#!/usr/bin/env python3
"""Validate LibTV Markdown using Seedance 2.0 official prompt rules."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SEGMENT_HEADING_RE = re.compile(r"^## 生成段 V(\d{2})｜(.+)$", re.M)
PROMPT_BLOCK_RE = re.compile(
    r"### LibTV 完成提示词（整块复制）\s*\n\s*```text\s*\n(.*?)\n```",
    re.S,
)
MIXED_ROW_RE = re.compile(
    r"^\| Mixed (\d+) \|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$",
    re.M,
)
MIXED_TOKEN_RE = re.compile(r"\{\{Mixed (\d+)\}\}")
SEMANTIC_BINDING_RE = re.compile(r"@\[([^\]]+)\]\s*\{\{Mixed (\d+)\}\}")
SEMANTIC_NAME_RE = re.compile(r"@\[([^\]]+)\]")
EXACT_SHOT_RE = re.compile(r"^Shot\s+(\d+):", re.M)
EXACT_SHOT_BLOCK_RE = re.compile(
    r"^Shot\s+\d+:.*?(?=^Shot\s+\d+:|\Z)", re.M | re.S
)
LEGACY_SHOT_RE = re.compile(r"^镜头\s*(\d+)\s*：", re.M)
LEGACY_SHOT_BLOCK_RE = re.compile(
    r"^镜头\s*\d+\s*：.*?(?=^镜头\s*\d+\s*：|\Z)", re.M | re.S
)
CONTINUOUS_TAKE_RE = re.compile(
    r"单一连续镜头[，,、 ]*无剪切|single continuous take,\s*no cuts", re.I
)
DIALOGUE_RE = re.compile(r"(?<!\{)\{([^{}\n]+)\}(?!\})")
DURATION_RE = re.compile(r"^- 时长：(\d+)秒$", re.M)
VOICE_STATUS_RE = re.compile(r"^- 音色状态：(.+)$", re.M)
DELIVERY_GRADE_RE = re.compile(r"^- 交付等级：(预览|正式)$", re.M)
PRODUCTION_ROUTE_RE = re.compile(r"^- 制作路线：(.+)$", re.M)
RISK_TAGS_RE = re.compile(r"^- 风险标签：(.+)$", re.M)
RUN_STATUS_RE = re.compile(r"^- 运行状态：(可运行|等待上段验收|阻塞)$", re.M)
CONTINUITY_MODE_RE = re.compile(
    r"^- 连续性模式：(场景母版|独立重置|等待上段验收末帧|已绑定上段验收末帧)$", re.M
)
SOUND_RE = re.compile(r"^- 声音：(开启|关闭)$", re.M)
TEXT_STRATEGY_RE = re.compile(r"^- 文字策略：(无画面文字|定版道具图|后期叠字)$", re.M)
SERIES_NAME_RE = re.compile(r"^- 剧名：(.+)$", re.M)
AUDIT_SCOPE_RE = re.compile(r"^- 审核范围：(全剧|截至EP\d+|单集)$", re.M)
SERIES_COUNT_RE = re.compile(r"^- 全剧集数：(\d+|未知)$", re.M)
TIMELINE_ANCHOR_RE = re.compile(r"^- 剧情时间锚：(.+)$", re.M)
PREVIOUS_EPISODE_RE = re.compile(r"^- 前集承接：(.+)$", re.M)
EPISODE_ENDPOINT_RE = re.compile(r"^- 本集最终出点：(.+)$", re.M)
SERIES_REVIEW_RE = re.compile(r"^- 全剧二审：已通过$", re.M)
CONTINUITY_GROUP_RE = re.compile(r"^- 连续组：(.+)$", re.M)
PREDECESSOR_SEGMENT_RE = re.compile(r"^- 前置段：(.+)$", re.M)
PROMPT_REVIEW_RE = re.compile(r"^- 提示词二审：已通过$", re.M)
TOTAL_DURATION_RE = re.compile(r"^- 总时长：(\d+)秒$", re.M)
SEGMENT_COUNT_RE = re.compile(r"^- 生成段：(\d+)个$", re.M)
MODEL_RE = re.compile(r"^- 模型：(.+)$", re.M)
ASPECT_RATIO_RE = re.compile(r"^- 画幅：(.+)$", re.M)
RESOLUTION_RE = re.compile(r"^- 分辨率：(.+)$", re.M)
ABSOLUTE_TIME_RE = re.compile(
    r"(?:\d{2}:\d{2}\.\d{2}|第\s*\d+(?:\.\d+)?\s*秒|\d+(?:\.\d+)?\s*[–—~-]\s*\d+(?:\.\d+)?\s*秒)"
)

REQUIRED_SECTIONS = (
    "## 使用方法",
    "## 公共素材清单",
    "## 全剧连续性声明",
    "## 全剧连续性母版",
    "## 段间衔接总表",
    "## 语音对账",
)
BANNED_DELIVERY = (
    "candidate.json",
    "asset-plan.json",
    "movement-ledger.json",
    "reference-manifest.json",
    "```json",
)
BANNED_PROMPT_PATTERNS = (
    (re.compile(r"@(?:图片|视频|音频)\d+"), "旧式 @图片N/@视频N/@音频N"),
    (re.compile(r"\b(?:TODO|TBD|DURATION_SEC)\b", re.I), "待办或内部变量"),
    (ABSOLUTE_TIME_RE, "绝对时间码"),
    (re.compile(r"【[^】]+】"), "零文字任务中禁用的【】画面文字语法"),
    (re.compile(r"【空间锚点"), "旧式空间锚点字段"),
)
EYE_TARGET_RE = re.compile(
    r"(?:视线|目光)(?:始终)?(?:落在|落向|锁在|锁定|停在|停向|投向|移向|固定在)"
    r"|看向|盯住|余光"
)
PRELINE_TRIGGER_RE = re.compile(
    r"开口前|说话前|听见.{0,18}(?:后|时)|看见.{0,18}(?:后|时)|"
    r"等不到|先.{0,22}(?:再|随后|然后|后)"
)
VOICE_DIRECTION_RE = re.compile(
    r"语速|重音|停顿|尾音|音量|气声|"
    r"加快|放慢|加重|压低|抬高|短促|一字一顿|拖长"
)
POSTLINE_ENDPOINT_RE = re.compile(
    r"(?:说完|台词结束|话音落下|尾音(?:落下|收住|结束)|闭口).{0,42}"
    r"(?:呼吸|鼻息|倾听|听着|继续|自然眨眼|恢复|视线|目光)"
)
STABLE_DIALOGUE_CAMERA_RE = re.compile(
    r"固定机位|稳定机位|锁定机位|稳定近景|固定近景|稳定三分之四侧|稳定过肩"
)
FROZEN_ENDPOINT_RE = re.compile(
    r"(?:说完|闭口).{0,24}(?:立即|马上)?.{0,20}(?:僵住|冻结|不动|完全静止)"
)
SHORT_LINE_STRETCH_RE = re.compile(r"放慢|慢说|停半拍|一字一顿|拖长|拉长")
PLANNING_ASSET_RE = re.compile(
    r"位置图|轨迹图|构图图|平面图|俯视图|机位图|箭头|虚线|假人|色块|网格|文字标注"
)
CLEAN_FRAME_BINDING_RE = re.compile(r"@\[(?:首帧|续接帧)-[^\]]+\]\s*\{\{Mixed \d+\}\}")
CROWD_STATE_BINDING_RE = re.compile(
    r"@\[(?:场景状态|人群状态|群演状态|占座)-[^\]]+\]\s*\{\{Mixed \d+\}\}"
)
EMPTY_SCENE_RE = re.compile(r"空教室|空场景|空房间|无人物(?:教室|场景|空间)")
WIDE_SHOT_RE = re.compile(r"大全景|中全景|全景")
CLASSROOM_RE = re.compile(r"教室|课堂|黑板|讲台")
FRONT_BOARD_RE = re.compile(
    r"(?:黑板.{0,16}(?:前墙|教室前方)|(?:前墙|教室前方).{0,16}黑板)"
)
SEAT_BOARD_RE = re.compile(
    r"(?:课桌|座椅|骨盆|髋部|膝盖|双脚|学生.{0,8}(?:身体|下半身))"
    r".{0,36}(?:面向|朝向|朝着).{0,12}(?:黑板|讲台|前墙)"
)
LOWER_BODY_LOCK_RE = re.compile(
    r"(?:(?:骨盆|髋部|膝盖|双脚|坐姿).{0,32}(?:保持|固定|仍|始终).{0,16}"
    r"(?:黑板|前方|不变)|(?:只让|仅让|只移动|仅移动|只转动|仅转动)"
    r".{0,4}(?:眼睛|视线|头部|侧头))"
)
OS_VO_RE = re.compile(r"\b(?:OS|VO)\b|内心|画外音|旁白", re.I)
COMPETING_DIALOGUE_ACTION_RE = re.compile(
    r"走入|走向|行走|转身|递给|递出|推向|飞出|飞向|撞上|扎入|掠过|"
    r"全班.{0,12}(?:转头|安静|反应)|众人.{0,12}(?:转头|安静|反应)|"
    r"群演.{0,12}(?:转头|起身|反应)|爆炸|特效"
)
EXACT_TEXT_GENERATION_RE = re.compile(
    r"文字以本提示词指定|清晰显示且只显示|必须(?:生成|出现|显示).{0,18}文字|精确生成.{0,12}文字"
)
HANDOFF_ROW_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", re.M
)
FACT_ROW_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$",
    re.M,
)
CROWD_TERM_RE = re.compile(r"学生|众人|人群|群演|群众|全班|全场")
CROWD_REACTION_RE = re.compile(r"转头|看向|盯住|僵住|后退|起身|鼓掌|欢呼|安静")
CROWD_HIERARCHY_RE = re.compile(
    r"(?:只有|仅有|最多).{0,12}(?:一名|一个)|"
    r"其余.{0,28}(?:呼吸|眨眼|微动|视线漂移|保持)|"
    r"(?:反应|动作).{0,12}错开"
)
PHYSICAL_LIGHT_RE = re.compile(
    r"窗光|日光|阳光|月光|顶灯|台灯|壁灯|走廊灯|路灯|霓虹|烛光|荧光灯|屏幕光"
)
SLOP_TERMS = (
    "高清",
    "8K",
    "超高清",
    "细节丰富",
    "电影质感",
    "色彩自然",
    "光影柔和",
    "高级感",
    "大师级",
    "杰作",
)


def section_end(matches: list[re.Match[str]], index: int, text: str) -> int:
    return matches[index + 1].start() if index + 1 < len(matches) else len(text)


def subsection(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    body_start = start + len(heading)
    next_heading = re.search(r"^#{1,3}\s+", text[body_start:], re.M)
    end = body_start + next_heading.start() if next_heading else len(text)
    return text[body_start:end]


def binding_category(name: str) -> str:
    if "音色" in name or "声音" in name or "台词音频" in name:
        return "audio"
    if name.startswith("场景-") or name.startswith("场景状态-") or name.startswith("人群状态-"):
        return "scene"
    if name.startswith("首帧-") or name.startswith("续接帧-"):
        return "frame"
    if name.startswith("构图-") or name.startswith("位置-") or name.startswith("轨迹-"):
        return "planning"
    if name.startswith("道具-"):
        return "prop"
    return "character"


def has_synchronous_dialogue(prompt: str) -> bool:
    for match in DIALOGUE_RE.finditer(prompt):
        context = prompt[max(0, match.start() - 80):match.start()]
        immediate = context[-32:]
        if re.search(r"(?:他说|她说|开口说|说出|对白)\s*$", immediate):
            return True
        if not re.search(r"内心|OS|画外音|旁白|VO", immediate, re.I):
            return True
    return False


def synchronous_dialogue_blocks(prompt: str) -> list[str]:
    blocks = EXACT_SHOT_BLOCK_RE.findall(prompt)
    if not blocks:
        blocks = LEGACY_SHOT_BLOCK_RE.findall(prompt)
    if not blocks:
        blocks = [prompt]
    return [block for block in blocks if has_synchronous_dialogue(block)]


def text_voice_subjects(prompt: str) -> set[str]:
    subjects: set[str] = set()
    for match in DIALOGUE_RE.finditer(prompt):
        context = prompt[max(0, match.start() - 140):match.start()]
        found = re.findall(r"<主体\d+>", context)
        if found:
            subjects.add(found[-1])
    return subjects


def audio_control_subjects(prompt: str) -> set[str]:
    return set(re.findall(
        r"\{\{Mixed \d+\}\}.{0,40}?只控制\s*(<主体\d+>).{0,24}?音色",
        prompt,
    ))


def validate(path: Path) -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    warnings: list[str] = []
    text = path.read_text(encoding="utf-8")

    if path.suffix.lower() != ".md":
        errors.append("交付物必须是 .md 文件")
    if not re.search(r"^# .+｜LibTV 完成提示词$", text, re.M):
        errors.append("缺少固定 H1：# <集号>｜LibTV 完成提示词")
    for heading in REQUIRED_SECTIONS:
        if heading not in text:
            errors.append(f"缺少章节：{heading}")
    for token in BANNED_DELIVERY:
        if token in text:
            errors.append(f"交付 Markdown 含禁用内容：{token}")
    for field_name, pattern in (
        ("剧名", SERIES_NAME_RE),
        ("审核范围", AUDIT_SCOPE_RE),
        ("全剧集数", SERIES_COUNT_RE),
        ("剧情时间锚", TIMELINE_ANCHOR_RE),
        ("前集承接", PREVIOUS_EPISODE_RE),
        ("本集最终出点", EPISODE_ENDPOINT_RE),
        ("全剧二审：已通过", SERIES_REVIEW_RE),
    ):
        if not pattern.search(text):
            errors.append(f"全剧连续性声明缺少或错误：{field_name}")
    if "| 连续键 | 类型 | 锁定版本 | 本集允许变化 | 变更依据 |" not in text:
        errors.append("全剧连续性母版缺少固定表头")

    model_match = MODEL_RE.search(text)
    if not model_match:
        errors.append("缺少节点默认模型")
    elif model_match.group(1).strip() not in {
        "Seedance 2.0 VIP",
        "Seedance 2.0 Fast VIP",
    }:
        errors.append("节点模型必须为 Seedance 2.0 VIP 或 Seedance 2.0 Fast VIP")
    aspect_match = ASPECT_RATIO_RE.search(text)
    if not aspect_match:
        errors.append("缺少节点默认画幅")
    elif aspect_match.group(1).strip() != "9:16":
        errors.append("节点默认画幅必须为 9:16")
    resolution_match = RESOLUTION_RE.search(text)
    if not resolution_match:
        errors.append("缺少节点默认分辨率")
    elif resolution_match.group(1).strip() != "480P":
        errors.append("节点默认分辨率必须为 480P")

    matches = list(SEGMENT_HEADING_RE.finditer(text))
    if not matches:
        errors.append("没有找到生成段章节")

    durations: list[int] = []
    for index, match in enumerate(matches, start=1):
        expected = f"{index:02d}"
        actual = match.group(1)
        label = f"V{actual}"
        if actual != expected:
            errors.append(f"{label} 编号不连续，应为 V{expected}")
        section = text[match.start():section_end(matches, index - 1, text)]

        duration = 0
        duration_match = DURATION_RE.search(section)
        if not duration_match:
            errors.append(f"{label} 缺少时长")
        else:
            duration = int(duration_match.group(1))
            durations.append(duration)
            if not 4 <= duration <= 15:
                errors.append(f"{label} 时长 {duration} 秒不在默认 4–15 秒范围内")

        grade_match = DELIVERY_GRADE_RE.search(section)
        route_match = PRODUCTION_ROUTE_RE.search(section)
        risk_match = RISK_TAGS_RE.search(section)
        run_match = RUN_STATUS_RE.search(section)
        continuity_match = CONTINUITY_MODE_RE.search(section)
        sound_match = SOUND_RE.search(section)
        text_strategy_match = TEXT_STRATEGY_RE.search(section)
        for field_name, field_match in (
            ("交付等级", grade_match),
            ("制作路线", route_match),
            ("风险标签", risk_match),
            ("运行状态", run_match),
            ("连续性模式", continuity_match),
            ("声音", sound_match),
            ("文字策略", text_strategy_match),
        ):
            if not field_match:
                errors.append(f"{label} 缺少或错误的{field_name}")
        if not CONTINUITY_GROUP_RE.search(section):
            errors.append(f"{label} 缺少连续组")
        if not PREDECESSOR_SEGMENT_RE.search(section):
            errors.append(f"{label} 缺少前置段")
        if not PROMPT_REVIEW_RE.search(section):
            errors.append(f"{label} 提示词二审未标记为已通过")
        if "### 状态交接" not in section:
            errors.append(f"{label} 缺少状态交接")
        elif "| 连续键 | 入点状态 | 出点状态 |" not in section:
            errors.append(f"{label} 状态交接缺少固定表头")
        else:
            handoff_rows = [
                row for row in HANDOFF_ROW_RE.findall(subsection(section, "### 状态交接"))
                if row[0].strip() not in {"连续键", "---"}
            ]
            if not handoff_rows:
                errors.append(f"{label} 状态交接没有有效状态行")
        if "### 剧本事实对账" not in section:
            errors.append(f"{label} 缺少剧本事实对账")
        elif "| 类型 | 原剧本事实 | 提示词落实 | 结果 |" not in section:
            errors.append(f"{label} 剧本事实对账缺少固定表头")
        else:
            fact_rows = [
                row for row in FACT_ROW_RE.findall(subsection(section, "### 剧本事实对账"))
                if row[0].strip() not in {"类型", "---"}
            ]
            if not fact_rows:
                errors.append(f"{label} 剧本事实对账没有有效事实行")
            elif any(row[3].strip() != "通过" for row in fact_rows):
                errors.append(f"{label} 剧本事实对账存在未通过项目")
        grade = grade_match.group(1) if grade_match else ""
        route = route_match.group(1).strip() if route_match else ""
        run_status = run_match.group(1) if run_match else ""
        continuity_mode = continuity_match.group(1) if continuity_match else ""
        sound = sound_match.group(1) if sound_match else ""
        text_strategy = text_strategy_match.group(1) if text_strategy_match else ""
        if run_status == "等待上段验收" and continuity_mode != "等待上段验收末帧":
            errors.append(f"{label} 等待段必须使用“等待上段验收末帧”")
        if run_status == "可运行" and continuity_mode == "等待上段验收末帧":
            errors.append(f"{label} 未绑定验收末帧前不能标为可运行")

        prompt_blocks = PROMPT_BLOCK_RE.findall(section)
        if len(prompt_blocks) != 1:
            errors.append(f"{label} 必须恰有一个 LibTV 完成提示词代码块")
            continue
        prompt = prompt_blocks[0].strip()

        rows = [
            (int(number), asset.strip(), media_type.strip(), semantic.strip())
            for number, asset, media_type, semantic in MIXED_ROW_RE.findall(section)
        ]
        if not rows:
            errors.append(f"{label} Mixed 上传表为空")
        for _, asset, _, semantic in rows:
            if PLANNING_ASSET_RE.search(f"{asset} {semantic}"):
                errors.append(f"{label} Mixed 含规划用资产，禁止上传给视频模型：{asset}")
        row_numbers = [number for number, _, _, _ in rows]
        if row_numbers != list(range(1, len(rows) + 1)):
            errors.append(f"{label} Mixed 上传表必须从 1 连续递增")

        prompt_numbers = {int(number) for number in MIXED_TOKEN_RE.findall(prompt)}
        row_number_set = set(row_numbers)
        missing = sorted(row_number_set - prompt_numbers)
        unknown = sorted(prompt_numbers - row_number_set)
        if missing:
            errors.append(f"{label} 上传表中 Mixed 未被提示词使用：{missing}")
        if unknown:
            errors.append(f"{label} 提示词引用了上传表不存在的 Mixed：{unknown}")
        if prompt_numbers and prompt_numbers != set(range(1, max(prompt_numbers) + 1)):
            errors.append(f"{label} 提示词中的 Mixed 编号不连续")

        bindings: dict[int, set[str]] = {}
        for semantic, number_text in SEMANTIC_BINDING_RE.findall(prompt):
            bindings.setdefault(int(number_text), set()).add(semantic)
        for number, semantics in sorted(bindings.items()):
            if len(semantics) > 1:
                errors.append(
                    f"{label} Mixed {number} 被多个独立语义共用：{sorted(semantics)}"
                )

        categories_by_number: dict[int, set[str]] = {}
        for semantic, number_text in SEMANTIC_BINDING_RE.findall(prompt):
            categories_by_number.setdefault(int(number_text), set()).add(binding_category(semantic))
        for number, categories in sorted(categories_by_number.items()):
            if len(categories) > 1:
                errors.append(f"{label} Mixed {number} 混用了人物/帧/场景/道具资产")

        for number, _, _, semantic_cell in rows:
            semantic_match = SEMANTIC_NAME_RE.search(semantic_cell)
            if semantic_match and semantic_match.group(1) not in bindings.get(number, set()):
                errors.append(
                    f"{label} Mixed {number} 上传表语义 @{semantic_match.group(1)} "
                    f"与提示词绑定 {sorted(bindings.get(number, set()))} 不一致"
                )

        character_bindings = [
            (semantic, int(number))
            for semantic, number in SEMANTIC_BINDING_RE.findall(prompt)
            if binding_category(semantic) == "character"
        ]
        if not character_bindings:
            warnings.append(f"{label} 未找到人物独立 Mixed 绑定")
        elif not re.search(r"定义为\s*<主体\d+>", prompt):
            errors.append(f"{label} 人物素材未定义为 <主体N>")
        if not re.search(r"定义为\s*<场景\d+>", prompt):
            errors.append(f"{label} 场景素材未定义为 <场景N>")
        if PLANNING_ASSET_RE.search(prompt):
            errors.append(f"{label} 提示词引用了规划图、标记图或位置示意资产")

        shots = [int(number) for number in EXACT_SHOT_RE.findall(prompt)]
        legacy_shots = [int(number) for number in LEGACY_SHOT_RE.findall(prompt)]
        continuous_take = bool(CONTINUOUS_TAKE_RE.search(prompt))
        if legacy_shots:
            errors.append(f"{label} LibTV 禁止旧“镜头N：”标签，多镜必须使用精确“Shot N:”")
        if shots:
            if shots != list(range(1, len(shots) + 1)):
                errors.append(f"{label} Shot N 编号必须从 1 连续递增")
            if continuous_take:
                errors.append(f"{label} 不能同时声明连续镜头和 Shot N 剪切")
            if duration <= 15 and len(shots) > 3:
                errors.append(
                    f"{label} {duration} 秒包含 {len(shots)} 个生成 Shot；"
                    "10–15 秒原生生成通常最多承载 2–3 个清楚事件"
                )
            elif duration and len(shots) > 1 and duration / len(shots) < 3:
                warnings.append(
                    f"{label} {duration} 秒包含 {len(shots)} 镜，平均不足 3 秒；"
                    "请确认没有把 v3 内部剪辑节拍误当成模型 Shot"
                )
        elif not continuous_take:
            errors.append(f"{label} 必须声明“单一连续镜头，无剪切”或使用精确 Shot N:")

        for pattern, description in BANNED_PROMPT_PATTERNS:
            if pattern.search(prompt):
                errors.append(f"{label} 提示词含禁用内容：{description}")

        if "：“" in prompt or "：\"" in prompt:
            errors.append(f"{label} 台词必须使用 {{精确原文}}，不能使用引号台词")
        if "真人实拍" not in prompt:
            errors.append(f"{label} 缺少真人实拍媒介说明")
        if not PHYSICAL_LIGHT_RE.search(prompt):
            errors.append(f"{label} 缺少可识别的物理光源")
        slop_count = sum(term in prompt for term in SLOP_TERMS)
        if slop_count >= 4:
            errors.append(f"{label} 空泛画质词过多，应改为机位、物理光源、动作或声音")
        if not all(term in prompt for term in ("无字幕", "水印", "Logo")):
            errors.append(f"{label} 缺少字幕/水印/Logo 兜底")
        if EXACT_TEXT_GENERATION_RE.search(prompt):
            errors.append(f"{label} 把精确文字交给视频模型生成；应使用定版道具图或后期叠字")
        if text_strategy == "定版道具图" and not any(
            "定版" in asset or "带字" in asset for _, asset, _, _ in rows
        ):
            errors.append(f"{label} 文字策略为定版道具图，但 Mixed 中没有定版带字资产")
        if len({name for name, _ in character_bindings}) > 1 and not any(
            term in prompt
            for term in ("分身", "双胞胎", "人物重复", "各只出现一人", "各出现一人")
        ):
            errors.append(f"{label} 多人物提示词缺少单一身份数量锁")

        dialogue_matches = list(DIALOGUE_RE.finditer(prompt))
        audio_rows: list[tuple[int, str, str, str]] = []
        has_text_voice = bool(dialogue_matches or OS_VO_RE.search(prompt))
        if has_text_voice:
            voice_status = VOICE_STATUS_RE.search(section)
            if not voice_status:
                errors.append(f"{label} 有文本声音但缺少音色状态")
            audio_rows = [row for row in rows if "音频" in row[2]]
            if not audio_rows:
                errors.append(f"{label} 有台词/OS/VO/旁白时必须绑定每名说话人的独立音色音频")
            if sound != "开启":
                errors.append(f"{label} 有台词/OS/VO/旁白时必须开启声音并原生声画同出")
            if audio_rows and not re.search(
                r"\{\{Mixed \d+\}\}.{0,40}?只控制\s*<主体\d+>.{0,24}?音色",
                prompt,
            ):
                errors.append(f"{label} 音频 Mixed 未声明只控制指定主体音色")
            spoken = text_voice_subjects(prompt)
            controlled = audio_control_subjects(prompt)
            missing = sorted(spoken - controlled)
            if missing:
                errors.append(
                    f"{label} 说话主体缺少对应独立音色绑定：{', '.join(missing)}"
                )

        sync_blocks = synchronous_dialogue_blocks(prompt)
        if sync_blocks:
            if any(
                len(DIALOGUE_RE.findall(block)) != 1 for block in sync_blocks
            ):
                errors.append(f"{label} 每个对白镜头必须只有一位说话人一个自然意群")
            if any(OS_VO_RE.search(block) for block in sync_blocks):
                errors.append(f"{label} 同一 Shot 内不能混合口型对白与 OS/VO/旁白")
            if any(COMPETING_DIALOGUE_ACTION_RE.search(block) for block in sync_blocks):
                errors.append(f"{label} 同步对白混入走位、道具、群体反应或特效竞争动作")
            if grade == "正式" and not CLEAN_FRAME_BINDING_RE.search(prompt):
                errors.append(f"{label} 正式同步对白缺少干净首帧或已验收续接帧眼神锚")
            if any(not PRELINE_TRIGGER_RE.search(block) for block in sync_blocks):
                errors.append(f"{label} 同步对白缺少开口触发")
            if any(not EYE_TARGET_RE.search(block) for block in sync_blocks):
                errors.append(f"{label} 同步对白缺少具体眼神对象或落点")
            if any(not POSTLINE_ENDPOINT_RE.search(block) for block in sync_blocks):
                errors.append(f"{label} 同步对白缺少说完后的可剪辑落点")
            if any(not STABLE_DIALOGUE_CAMERA_RE.search(block) for block in sync_blocks):
                errors.append(f"{label} 同步对白缺少固定或稳定机位")
            if any(FROZEN_ENDPOINT_RE.search(block) for block in sync_blocks):
                errors.append(f"{label} 同步对白使用冻结式说完落点，应改为呼吸、倾听或继续原动作")
            for block in sync_blocks:
                control_clauses = [
                    clause for clause in re.split(r"[，；。]", block)
                    if VOICE_DIRECTION_RE.search(clause)
                ]
                if len(control_clauses) > 1:
                    errors.append(f"{label} 同步对白声音控制超过一个，容易产生机械朗读")
                for dialogue in DIALOGUE_RE.findall(block):
                    chinese_chars = re.findall(r"[\u4e00-\u9fff]", dialogue)
                    if len(chinese_chars) <= 6 and SHORT_LINE_STRETCH_RE.search(block):
                        errors.append(f"{label} 六字以内短句不得放慢、停半拍、一字一顿或拖长")

        if CROWD_TERM_RE.search(prompt) and CROWD_REACTION_RE.search(prompt):
            if not CROWD_HIERARCHY_RE.search(prompt):
                errors.append(f"{label} 群体反应缺少一个焦点反应与其余人物持续微动")
        if CROWD_TERM_RE.search(prompt) and WIDE_SHOT_RE.search(prompt):
            if EMPTY_SCENE_RE.search(prompt):
                errors.append(f"{label} 全景可见人群却绑定空场景，空间状态冲突")
            if not CROWD_STATE_BINDING_RE.search(prompt) and not CLEAN_FRAME_BINDING_RE.search(prompt):
                errors.append(f"{label} 全景可见人群缺少已占位场景状态或干净首帧")
            if CLASSROOM_RE.search(prompt):
                if not FRONT_BOARD_RE.search(prompt) or not SEAT_BOARD_RE.search(prompt):
                    errors.append(
                        f"{label} 教室群像未锁定黑板前墙以及课桌、座椅和学生下半身的教学朝向"
                    )
                if CROWD_REACTION_RE.search(prompt) and not LOWER_BODY_LOCK_RE.search(prompt):
                    errors.append(
                        f"{label} 教室群像反应未声明只转眼/头/肩并保持骨盆、膝盖和坐姿朝向"
                    )

    count_match = SEGMENT_COUNT_RE.search(text)
    if not count_match:
        errors.append("缺少生成段总数")
    elif int(count_match.group(1)) != len(matches):
        errors.append(f"生成段总数应为 {len(matches)}")

    total_match = TOTAL_DURATION_RE.search(text)
    if not total_match:
        errors.append("缺少总时长")
    elif durations and int(total_match.group(1)) != sum(durations):
        errors.append(f"总时长应为 {sum(durations)} 秒")

    return errors, warnings, {
        "videoSegments": len(matches),
        "totalDurationSeconds": sum(durations),
        "errorCount": len(errors),
        "warningCount": len(warnings),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path)
    args = parser.parse_args()
    try:
        errors, warnings, summary = validate(args.markdown)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    for error in errors:
        print(f"ERROR: {error}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    print(
        "SUMMARY: "
        f"segments={summary['videoSegments']} "
        f"duration={summary['totalDurationSeconds']}s "
        f"errors={summary['errorCount']} warnings={summary['warningCount']}"
    )
    if errors:
        return 1
    print("OK: LibTV Seedance 2.0 Markdown delivery is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
