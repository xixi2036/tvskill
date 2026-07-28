#!/usr/bin/env python3
"""Validate LibTV Markdown using Seedance 2.0 official prompt rules."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _shared_patterns import (  # noqa: E402
    OS_VO_RE,
    DIALOGUE_RE,
    EXACT_SHOT_RE,
    EXACT_SHOT_BLOCK_RE,
    VOICE_SLOT_RE,
    CLASSROOM_RE,
    FRONT_BOARD_RE,
    SEAT_BOARD_RE,
    LOWER_BODY_LOCK_RE,
    EMPTY_SCENE_RE,
)


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
LEGACY_SHOT_RE = re.compile(r"^镜头\s*(\d+)\s*：", re.M)
LEGACY_SHOT_BLOCK_RE = re.compile(
    r"^镜头\s*\d+\s*：.*?(?=^镜头\s*\d+\s*：|\Z)", re.M | re.S
)
CONTINUOUS_TAKE_RE = re.compile(
    r"单一连续镜头[，,、 ]*无剪切|single continuous take,\s*no cuts", re.I
)
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
    "## 资产清单",
    "## 全剧连续性声明",
    "## 全剧连续性母版",
    "## 段间衔接总表",
    "## 语音对账",
    "## 画面对账",
)
COVERAGE_ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|$",
    re.M,
)
ASSET_ROW_RE = re.compile(
    r"^\|\s*(人物|场景|道具|色卡)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|$",
    re.M,
)
LANDING_RE = re.compile(r"V(\d{2})-Shot(\d+)")
DISPOSITION_KINDS = ("已落实", "合并", "转后期叠字", "舍弃")
EXACT_TEXT_PROP_RE = re.compile(r"含精确文字|精确可见文字")
# 多镜节点里，单个 Shot 塞进 3 条及以上原剧本画面指令即判定为把该切的镜合并了。
MAX_UNITS_PER_SHOT = 2
# 连续单镜本就是"一镜演完一串动作"，天然承载更多画面指令，放宽且只提示不拦截。
MAX_UNITS_PER_CONTINUOUS_TAKE = 4
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
    (re.compile(r"【空间锚点"), "旧式空间锚点字段"),
)
BRACKET_RE = re.compile(r"【[^】]*】")
ALLOWED_BRACKETS_RE = re.compile(r"^【(?:阶段\d+[^】]*|声音设计|关键约束)】$")
SOUND_DESIGN_BLOCK_RE = re.compile(r"【声音设计】.*?(?=\n\s*\n|\n\s*【|\Z)", re.S)
STYLE_LOCK_RE = re.compile(r"^[^\n]*(?:美学|质感|色调|film|grain|aesthetics)[^\n]*$", re.I)
ASSET_ANCHOR_RE = re.compile(r"严格按此图渲染|视觉锚定.{0,24}不可改造")
# 同样不能用 \b：#7A4FBD暗紫 这种紧贴中文的写法才是真实语料里的常态。
INLINE_HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}(?![0-9A-Fa-f])")
NAMED_IRON_RULE_RE = re.compile(r"[^\s，。；：]{2,12}铁律")
# NOT 后面未必有空格：中文语料里普遍写成 NOT卡通渲染+NOT三维动画。
NOT_CHAIN_RE = re.compile(r"NOT\s*\S+.{0,80}?NOT\s*\S+", re.S | re.I)
VOICE_PENDING_STATUS_RE = re.compile(r"待关联")
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
WIDE_SHOT_RE = re.compile(r"大全景|中全景|全景")
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
    # 自然光与灯具
    r"窗光|日光|阳光|月光|月色|自然光|晨光|暮光|夕阳|天光|逆光|侧光|顶光"
    r"|顶灯|台灯|壁灯|走廊灯|路灯|车灯|霓虹|烛光|荧光灯|屏幕光|射灯|吊灯"
    # 自发光体：虚空、意识空间等非写实场景没有窗和灯，但光束/电弧/辉光同样是
    # 可识别的具体光源，与"光影柔和"这类空泛画质词有本质区别
    r"|光束|电弧|辉光|自发光|火光|爆炸光|冷光源|环境光带|粒子光"
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
    if "色卡" in name:
        return "colorcard"
    if name.startswith("场景-") or name.startswith("场景状态-") or name.startswith("人群状态-"):
        return "scene"
    if name.startswith("首帧-") or name.startswith("续接帧-"):
        return "frame"
    if name.startswith("构图-") or name.startswith("位置-") or name.startswith("轨迹-"):
        return "planning"
    if name.startswith("道具-"):
        return "prop"
    return "character"


def trailing_speaker_note(prompt: str, end: int) -> str:
    """取台词右侧紧跟的括注，例如 {台词}(系统VO,使用Mixed 3音色)。"""
    tail = prompt[end:end + 40]
    match = re.match(r"\s*[（(]([^）)]*)[）)]", tail)
    return match.group(1) if match else ""


def has_synchronous_dialogue(prompt: str) -> bool:
    for match in DIALOGUE_RE.finditer(prompt):
        # 台词左右任一侧标了 OS/VO/旁白/内心，就是非同步声音，
        # 不该套用同步对白的开口触发、眼神目标与首帧眼神锚规则。
        if OS_VO_RE.search(trailing_speaker_note(prompt, match.end())):
            continue
        context = prompt[max(0, match.start() - 80):match.start()]
        immediate = context[-32:]
        if re.search(r"(?:他说|她说|开口说|说出|对白)\s*$", immediate):
            return True
        if not OS_VO_RE.search(immediate):
            return True
    return False


def synchronous_dialogue_blocks(prompt: str) -> list[str]:
    blocks = EXACT_SHOT_BLOCK_RE.findall(prompt)
    if not blocks:
        blocks = LEGACY_SHOT_BLOCK_RE.findall(prompt)
    if not blocks:
        blocks = [prompt]
    return [block for block in blocks if has_synchronous_dialogue(block)]


VOICE_SOURCE_RE = re.compile(r"<主体\d+>|[^\s，。；：,、（()）]{0,8}(?:VO|OS|旁白)")


def text_voice_subjects(prompt: str) -> set[str]:
    """台词的说话人：优先取右侧括注里显式写的声源，否则取左侧最近的 <主体N>。"""
    subjects: set[str] = set()
    for match in DIALOGUE_RE.finditer(prompt):
        note = trailing_speaker_note(prompt, match.end())
        noted = VOICE_SOURCE_RE.search(note) if note else None
        if noted:
            subjects.add(noted.group(0).strip())
            continue
        context = prompt[max(0, match.start() - 140):match.start()]
        found = re.findall(r"<主体\d+>", context)
        if found:
            subjects.add(found[-1])
    return subjects


def audio_control_subjects(prompt: str) -> set[str]:
    return {
        found.strip()
        for found in re.findall(
            r"\{\{Mixed \d+\}\}.{0,40}?只控制\s*"
            r"(<主体\d+>|[^\s，。；：,、]{0,10}(?:VO|OS|旁白))"
            r".{0,24}?音色",
            prompt,
        )
    }


def normalized_source(text: str) -> str:
    return re.sub(r"[\s　“”\"'‘’|｜]", "", text)


def check_coverage_against_script(
    coverage_rows: list[tuple[int, str, str, str, str]],
    script: Path,
    episode: int | None,
) -> list[str]:
    """用抽取器重新解析原剧本，逐行核对对账表——不信任表里自报的任何数字。"""
    errors: list[str] = []
    try:
        import extract_script_units
    except ImportError:
        return ["无法加载 extract_script_units，覆盖度对源校验未执行"]
    try:
        paragraphs = extract_script_units.read_paragraphs(script)
    except (OSError, KeyError, UnicodeError) as exc:
        return [f"无法读取原剧本 {script}：{exc}"]
    units = extract_script_units.extract(paragraphs, episode)
    if not units:
        return [f"原剧本 {script} 中没有抽到画面单元，请确认集号"]
    if len(units) != len(coverage_rows):
        errors.append(
            f"画面对账行数 {len(coverage_rows)} 与原剧本实际画面单元数 {len(units)} 不一致；"
            "缺行即为画面丢失，必须逐条补齐"
        )
    for unit, row in zip(units, coverage_rows):
        expected = normalized_source(str(unit["text"]))
        actual = normalized_source(row[2])
        if expected != actual:
            errors.append(
                f"画面对账第 {row[0]} 行原文与剧本不符：\n"
                f"    剧本：{unit['text']}\n"
                f"    对账：{row[2]}"
            )
    return errors


def check_pipeline_state(path: Path) -> tuple[list[str], list[str]]:
    """交付校验必须有流程凭据：不跑状态机就直接跑本脚本，等于绕过整条流程锁。

    交付物名形如 `<集号>-LibTV视频节点提示词.md`，对应 `<集号>-run_state.json`。
    """
    import json

    errors: list[str] = []
    warnings: list[str] = []
    episode = path.name.split("-")[0]
    state_file = path.parent / f"{episode}-run_state.json"
    if not state_file.exists():
        errors.append(
            f"缺少流程凭据 {state_file.name}：本脚本的通过结论只在走完 pipeline_state.py "
            "的前提下才算数。若只是单独检查一个文件，请显式加 --standalone"
        )
        return errors, warnings
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        errors.append(f"流程凭据无法解析：{exc}")
        return errors, warnings
    steps = state.get("steps", {})
    required = ("script_units", "entities", "assets", "segments", "coverage")
    missing = [step for step in required if steps.get(step) != "done"]
    if missing:
        errors.append(
            f"流程凭据显示这些前置步骤尚未完成：{missing}；"
            "请回到 pipeline_state.py 依次过闸，不要跳步"
        )
    recorded = state.get("deliveryHash", "")
    if recorded:
        import hashlib

        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != recorded:
            warnings.append(
                "交付 Markdown 自上次记录后已改动，流程凭据已过期；"
                "本次校验通过后需重新 complete 相关步骤"
            )
    return errors, warnings


def validate(
    path: Path,
    script: Path | None = None,
    episode: int | None = None,
    standalone: bool = True,
) -> tuple[list[str], list[str], dict[str, int]]:
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
    shots_by_segment: dict[str, int] = {}
    continuous_take_segments: dict[str, bool] = {}
    segments_with_color_card: dict[str, bool] = {}
    text_strategy_by_segment: dict[str, str] = {}
    segment_asset_names: dict[str, list[str]] = {}
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
        shots_by_segment[actual] = len(shots) if shots else 1
        continuous_take_segments[actual] = not shots
        color_card_rows = [
            row for row in rows if "色卡" in f"{row[1]} {row[3]}"
        ]
        segments_with_color_card[actual] = bool(color_card_rows)
        text_strategy_by_segment[actual] = text_strategy
        segment_asset_names[actual] = [row[1] for row in rows]
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
        bad_brackets = sorted({
            token for token in BRACKET_RE.findall(prompt)
            if not ALLOWED_BRACKETS_RE.match(token)
        })
        if bad_brackets:
            errors.append(
                f"{label} 提示词含禁用的【】画面文字语法：{bad_brackets}；"
                "只允许【阶段N…】【声音设计】【关键约束】三类结构标记"
            )
        if ABSOLUTE_TIME_RE.search(SOUND_DESIGN_BLOCK_RE.sub("", prompt)):
            errors.append(f"{label} 提示词含禁用内容：绝对时间码")

        if grade == "正式":
            first_line = prompt.splitlines()[0] if prompt.splitlines() else ""
            for present, missing_desc in (
                (bool(STYLE_LOCK_RE.match(first_line)), "开篇风格锁定行"),
                (bool(ASSET_ANCHOR_RE.search(prompt)), "逐资产视觉锚定语"),
                (bool(INLINE_HEX_RE.search(prompt)), "inline HEX 色值"),
                ("【声音设计】" in prompt, "独立【声音设计】分层段"),
                (
                    "【关键约束】" in prompt and bool(NAMED_IRON_RULE_RE.search(prompt)),
                    "【关键约束】具名铁律",
                ),
                (bool(NOT_CHAIN_RE.search(prompt)), "结尾 NOT 链"),
            ):
                if not present:
                    warnings.append(f"{label} 正式段缺少万物生结构六件套：{missing_desc}")

        if "：“" in prompt or "：\"" in prompt:
            errors.append(f"{label} 台词必须使用 {{精确原文}}，不能使用引号台词")
        if "真人实拍" not in prompt:
            errors.append(f"{label} 缺少真人实拍媒介说明")
        if not PHYSICAL_LIGHT_RE.search(prompt):
            errors.append(f"{label} 缺少可识别的物理光源")
        slop_count = sum(term in prompt for term in SLOP_TERMS)
        if slop_count >= 4:
            errors.append(f"{label} 空泛画质词过多，应改为机位、物理光源、动作或声音")
        no_subtitle = any(
            term in prompt for term in ("无字幕", "NOT字幕", "NOT 字幕", "不出现字幕")
        )
        if not (no_subtitle and "水印" in prompt and "Logo" in prompt):
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
                errors.append(
                    f"{label} 有台词/OS/VO/旁白时必须为每名说话人绑定独立音色音频，"
                    "或声明明确的音色占位槽"
                )
            slot_rows = [
                row for row in audio_rows
                if VOICE_SLOT_RE.search(f"{row[1]} {row[2]}")
            ]
            status_text = voice_status.group(1) if voice_status else ""
            status_pending = bool(VOICE_PENDING_STATUS_RE.search(status_text))
            if slot_rows:
                slots = [row[1] for row in slot_rows]
                if not status_pending:
                    errors.append(
                        f"{label} 存在音色占位槽 {slots}，音色状态必须写明“待关联”"
                    )
                if run_status != "阻塞":
                    errors.append(
                        f"{label} 音色占位槽未关联真实音频前，运行状态必须为阻塞"
                    )
                warnings.append(
                    f"{label} 音色占位槽待人工上传后关联：{slots}"
                )
            elif status_pending:
                errors.append(
                    f"{label} 音色状态标为待关联，但 Mixed 表中没有对应的音色占位槽"
                )
            if sound != "开启":
                errors.append(f"{label} 有台词/OS/VO/旁白时必须开启声音并原生声画同出")
            spoken = text_voice_subjects(prompt)
            controlled = audio_control_subjects(prompt)
            if audio_rows and not controlled:
                errors.append(
                    f"{label} 音频 Mixed 未声明只控制指定说话人的音色"
                    "（写成「只控制 <主体N> 的音色」或「只控制系统VO的音色」）"
                )
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

    asset_rows = [
        (kind.strip(), name.strip(), form.strip(), note.strip())
        for kind, name, form, note in ASSET_ROW_RE.findall(
            subsection(text, "## 资产清单")
        )
    ]
    if not asset_rows:
        errors.append("资产清单没有有效资产行")
    prop_rows = [row for row in asset_rows if row[0] == "道具"]
    color_card_rows = [row for row in asset_rows if row[0] == "色卡"]
    if not prop_rows:
        warnings.append(
            "资产清单没有登记任何道具；若本集确无承担叙事功能的道具请忽略，"
            "否则按实体提取合同补登记（精确文字道具必须走定版道具图）"
        )
    for _, name, _, note in prop_rows:
        if not EXACT_TEXT_PROP_RE.search(note):
            continue
        holders = [
            number for number, assets in segment_asset_names.items()
            if any(name in asset for asset in assets)
        ]
        if not holders:
            errors.append(
                f"道具「{name}」标注含精确文字，必须有定版道具图并绑进对应段的 Mixed，"
                "当前没有任何段绑定它"
            )
            continue
        for number in holders:
            if text_strategy_by_segment.get(number) != "定版道具图":
                errors.append(
                    f"V{number} 绑定了含精确文字的道具「{name}」，文字策略必须为定版道具图"
                )
    if color_card_rows:
        missing_color_card = sorted(
            number for number, bound in segments_with_color_card.items() if not bound
        )
        if missing_color_card:
            errors.append(
                "资产清单已登记色卡，以下段却未绑定任何色卡资产："
                f"{['V' + number for number in missing_color_card]}；"
                "色卡必须作为视觉锚定绑进 Mixed，只在提示词里写 HEX 不成立"
            )

    coverage_rows = [
        (int(index_text), kind.strip(), source.strip(), landing.strip(), disposition.strip())
        for index_text, kind, source, landing, disposition in COVERAGE_ROW_RE.findall(
            subsection(text, "## 画面对账")
        )
    ]
    if not coverage_rows:
        errors.append("画面对账没有有效对账行")
    else:
        expected_indexes = list(range(1, len(coverage_rows) + 1))
        if [row[0] for row in coverage_rows] != expected_indexes:
            errors.append("画面对账序号必须从 1 连续递增，且与原剧本抽取顺序一致")
        units_per_shot: dict[str, int] = {}
        for row_index, _, source, landing, disposition in coverage_rows:
            kind_match = next(
                (kind for kind in DISPOSITION_KINDS if disposition.startswith(kind)),
                "",
            )
            if not kind_match:
                errors.append(
                    f"画面对账第 {row_index} 行处置非法：{disposition or '（空）'}；"
                    f"只能是 {'／'.join(DISPOSITION_KINDS)}"
                )
                continue
            if kind_match == "舍弃":
                reason = disposition[len("舍弃"):].strip(" ：:")
                if not reason:
                    errors.append(f"画面对账第 {row_index} 行标为舍弃但没有写理由")
                continue
            if kind_match == "转后期叠字":
                # 后期叠字不落在视频节点里，没有 Shot 落点是正常的。
                continue
            landings = LANDING_RE.findall(landing)
            if not landings:
                errors.append(
                    f"画面对账第 {row_index} 行处置为{kind_match}，"
                    "落点必须写成 V01-Shot2 这样的具体位置"
                )
                continue
            for segment_number, shot_text in landings:
                if segment_number not in shots_by_segment:
                    errors.append(
                        f"画面对账第 {row_index} 行落点 V{segment_number} 不存在"
                    )
                elif int(shot_text) > shots_by_segment[segment_number]:
                    errors.append(
                        f"画面对账第 {row_index} 行落点 V{segment_number}-Shot{shot_text} "
                        f"超出该段实际 Shot 数 {shots_by_segment[segment_number]}"
                    )
                else:
                    key = f"V{segment_number}-Shot{shot_text}"
                    units_per_shot[key] = units_per_shot.get(key, 0) + 1
        crowded: list[str] = []
        crowded_takes: list[str] = []
        for key, count in sorted(units_per_shot.items()):
            segment_number = key[1:3]
            if continuous_take_segments.get(segment_number):
                if count > MAX_UNITS_PER_CONTINUOUS_TAKE:
                    crowded_takes.append(f"{key}({count}条)")
            elif count > MAX_UNITS_PER_SHOT:
                crowded.append(f"{key}({count}条)")
        if crowded:
            errors.append(
                f"以下 Shot 各自承载了超过 {MAX_UNITS_PER_SHOT} 条原剧本画面指令：{crowded}；"
                "该切的镜被合并了，画面指令密集时必须拆节点，不允许合并画面"
            )
        if crowded_takes:
            warnings.append(
                f"以下连续单镜承载了超过 {MAX_UNITS_PER_CONTINUOUS_TAKE} 条画面指令："
                f"{crowded_takes}；连续单镜可以一镜演完多个动作，但请确认不是把该切的镜省掉了"
            )
        if script is None:
            warnings.append(
                "画面对账未对源校验：本次没有传 --script <原剧本>，"
                "只检查了表格自身格式，无法证明原剧本的画面指令没有被整行漏掉"
            )
        else:
            errors.extend(check_coverage_against_script(coverage_rows, script, episode))

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

    if not standalone:
        state_errors, state_warnings = check_pipeline_state(path)
        errors.extend(state_errors)
        warnings.extend(state_warnings)

    return errors, warnings, {
        "videoSegments": len(matches),
        "totalDurationSeconds": sum(durations),
        "errorCount": len(errors),
        "warningCount": len(warnings),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path)
    parser.add_argument(
        "--script",
        type=Path,
        help="原剧本（.docx/.txt/.md）；传入后逐条核对画面对账是否漏行、是否被改写",
    )
    parser.add_argument("--episode", type=int, help="原剧本中的集号")
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="只单独检查这一个文件，不作为交付凭据（跳过流程状态机检查）",
    )
    args = parser.parse_args()
    try:
        errors, warnings, summary = validate(
            args.markdown, args.script, args.episode, standalone=args.standalone
        )
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
