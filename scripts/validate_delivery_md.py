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
from _shared_patterns import (
    NARRATION_RE,
    TIMESTAMP_BLOCK_RE,
    TIMESTAMP_BLOCK_SPLIT_RE,  # noqa: E402
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
    SUPPORTED_RATIOS,
    SUPPORTED_RESOLUTIONS,
    SUPPORTED_MODELS,
)
from _shot_budget import shot_budget_messages  # noqa: E402
import _storyboard_grammar as SG  # noqa: E402
from _fast_drama_contract import prompt_quality_messages  # noqa: E402


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
REFERENCE_LIMITS = {"总计": 12, "图片": 9, "视频": 3, "音频": 3}
SEMANTIC_BINDING_RE = re.compile(r"@\[([^\]]+)\]\s*\{\{Mixed (\d+)\}\}")
SEMANTIC_NAME_RE = re.compile(r"@\[([^\]]+)\]")
LEGACY_SHOT_RE = re.compile(r"^镜头\s*(\d+)\s*：", re.M)
LEGACY_SHOT_BLOCK_RE = re.compile(
    r"^镜头\s*\d+\s*：.*?(?=^镜头\s*\d+\s*：|\Z)", re.M | re.S
)
CONTINUOUS_TAKE_RE = re.compile(
    r"单一连续镜头[，,、 ]*无剪切|single continuous take,\s*no cuts", re.I
)
LONG_TAKE_INTENT_RE = re.compile(r"长镜头叙事意图\s*[：:]\s*\S+")
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
# 二审字段取值域必须含「待二审」：确定性校验若要求文档先自称"已通过"才肯给 0，
# 而规则又规定"校验通过后才能这么写"，就成了逻辑死循环，逼所有人先写假状态。
# 正确的次序是：机器闸先过 → 人做二审 → 再改成已通过。
SERIES_REVIEW_RE = re.compile(r"^- 全剧二审：(已通过|待二审)$", re.M)
CONTINUITY_GROUP_RE = re.compile(r"^- 连续组：(.+)$", re.M)
PREDECESSOR_SEGMENT_RE = re.compile(r"^- 前置段：(.+)$", re.M)
PROMPT_REVIEW_RE = re.compile(r"^- 提示词二审：(已通过|待二审)$", re.M)
TOTAL_DURATION_RE = re.compile(r"^- 总时长：(\d+)秒$", re.M)
SEGMENT_COUNT_RE = re.compile(r"^- 生成段：(\d+)个$", re.M)
MODEL_RE = re.compile(r"^- 模型：(.+)$", re.M)
ASPECT_RATIO_RE = re.compile(r"^- 画幅：(.+)$", re.M)
RESOLUTION_RE = re.compile(r"^- 分辨率：(.+)$", re.M)
ABSOLUTE_TIME_RE = re.compile(
    r"(?:\d{2}:\d{2}\.\d{2}|第\s*\d+(?:\.\d+)?\s*秒)"
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
VOICE_ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|$",
    re.M,
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
    # 同样不能用 \b：「时长DURATION_SEC秒」两侧都是中文，边界不成立。
    (re.compile(r"(?<![A-Za-z])(?:TODO|TBD|DURATION_SEC)(?![A-Za-z])", re.I),
     "待办或内部变量"),
    (re.compile(r"【空间锚点"), "旧式空间锚点字段"),
    # 无状态读：模型拿到的只有这一段 prompt,不知道对话历史、不知道上一版长什么样。
    # 指向"另一次生成"的措辞在模型那里无法解析,只会被当成普通文字消耗权重。
    #
    # 词表经真实语料核对后收窄——以下三类**不能**入闸,会误杀合法写法：
    #   「上一段」 assets 模板里是声音连续性正文：「室内低频底噪延续上一段」
    #   「本段」   _fast_drama_contract 强制要求：「本段仅使用 <主体N>」「本段共 N 个…镜头」
    #   「之前」   可指镜内叙事先后：「他之前放下的杯子」
    # 只保留在全库零出现、且只可能指向另一次生成的措辞。
    (re.compile(r"不要像上次|前面那版|上一版|上个版本|刚才那版|之前那版|上次生成"),
     "会话依赖措辞（模型看不到上一次生成）"),
)
BRACKET_RE = re.compile(r"【[^】]*】")
ALLOWED_BRACKETS_RE = re.compile(r"^【(?:阶段\d+[^】]*|声音设计|关键约束)】$")
SOUND_DESIGN_BLOCK_RE = re.compile(r"【声音设计】.*?(?=\n\s*\n|\n\s*【|\Z)", re.S)
# 风格锁定行：除既有的美学/质感/色调类描述外，也接受**可指认的对标**——
# 导演／摄影师／影片名或标准类型词。对标 doubao-creative-drama：
# 风格字段应写「某某风格的电影」或「3D 玄幻风格」这类模型见过的锚点，
# 自造描述词（如「高端东方玄幻 3D 低饱和废土战场美学」）模型无从对齐。
STYLE_LOCK_RE = re.compile(
    r"^[^\n]*(?:美学|质感|色调|film|grain|aesthetics|"
    r"风格的电影|风格化|对标|掌镜|执导|赛璐璐|水墨|皮克斯)[^\n]*$",
    re.I,
)
ASSET_ANCHOR_RE = re.compile(r"严格按此图渲染|视觉锚定.{0,24}不可改造")
# 同样不能用 \b：#7A4FBD暗紫 这种紧贴中文的写法才是真实语料里的常态。
INLINE_HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}(?![0-9A-Fa-f])")
# 色卡「本段调用」的自然语言写法，取自万物生·问心真实语料的高频措辞。
COLOR_CALLOUT_RE = re.compile(
    r"重点调用|重点呈现|本段光的颜色|主色|环境底色|色调主色|色板中的"
)
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
    r"固定机位|稳定机位|锁定机位|稳定近景|固定近景|固定过肩机位|稳定三分之四侧|稳定过肩"
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
# 媒介四选一。此前写死"真人实拍"，导致 skill 自己 description 里承诺的
# 2D 动漫 / 3D CG 剧集没有任何合法路径通过校验——除非在动漫提示词里硬塞
# "真人实拍"四个字，那又违反"媒介与资产图一致"。
MEDIUM_RE = re.compile(r"真人实拍|2D\s*动漫|二维动漫|3D\s*CG|三维动画|定格动画")
PHYSICAL_LIGHT_RE = re.compile(
    # 自然光与灯具
    r"窗光|日光|阳光|月光|月色|自然光|晨光|暮光|夕阳|天光|逆光|侧光|顶光"
    r"|顶灯|台灯|落地灯|壁灯|走廊灯|路灯|车灯|霓虹|烛光|荧光灯|屏幕光|射灯|吊灯"
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
        shot_start = prompt.rfind("Shot ", 0, match.start())
        context = prompt[max(0, shot_start if shot_start >= 0 else match.start() - 180):match.start()]
        immediate = context[-32:]
        if OS_VO_RE.search(immediate):
            continue
        if re.search(r"(?:他说|她说|开口说|说出|对白)\s*$", immediate):
            return True
        return True
    return False


def synchronous_dialogue_blocks(prompt: str) -> list[str]:
    # 时间戳动作规划优先：万物生语料与豆包官方 skill 都用它替代镜头标签。
    blocks = TIMESTAMP_BLOCK_SPLIT_RE.findall(prompt)
    if not blocks:
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
        shot_start = prompt.rfind("Shot ", 0, match.start())
        context = prompt[max(0, shot_start if shot_start >= 0 else match.start() - 180):match.start()]
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


def check_voice_against_script(
    voice_rows: list[tuple[int, str, str, str]],
    script: Path,
    episode: int | None,
) -> list[str]:
    """语音对账同样必须对源。

    此前这张表只是个必需章节，没有任何行级检查——空表头也能通过。
    所谓"台词零丢失是因为有对账表"其实不成立：那张表和当年的画面一样只活在自觉里。
    """
    errors: list[str] = []
    try:
        import extract_script_units
    except ImportError:
        return ["无法加载 extract_script_units，语音对账对源校验未执行"]
    try:
        paragraphs = extract_script_units.read_paragraphs(script)
    except (OSError, KeyError, UnicodeError) as exc:
        return [f"无法读取原剧本 {script}：{exc}"]
    units = extract_script_units.extract(
        paragraphs, episode, extract_script_units.VOICE_KINDS
    )
    if not units:
        return [f"原剧本 {script} 中没有抽到任何台词，请确认集号"]
    if len(units) != len(voice_rows):
        errors.append(
            f"语音对账行数 {len(voice_rows)} 与原剧本实际台词数 {len(units)} 不一致；"
            "缺行即为台词丢失，必须逐句补齐"
        )
    for unit, row in zip(units, voice_rows):
        if normalized_source(str(unit["text"])) != normalized_source(row[1]):
            errors.append(
                f"语音对账第 {row[0]} 行原文与剧本不符：\n"
                f"    剧本：{unit['text']}\n"
                f"    对账：{row[1]}"
            )
    return errors


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



VOICE_LANDING_RE = re.compile(r"(V\d{2})-Shot\d+")


def check_voice_lines_reach_prompt(
    voice_rows: list[tuple[int, str, str, str]], text: str
) -> list[str]:
    """语音对账里的台词必须真的以 {原文} 落进它自己那段的提示词。

    此前只校验「有台词就要绑音色」，从不校验台词**文本**是否进了提示词。
    结果是整套同步对白规则（开口触发、眼神落点、固定机位、声连画断）全部静默
    失效——因为它们都以 `{}` 里的台词为触发条件，而提示词里根本没有 `{}`。

    2026-09-04 实证：《万妖图录传》EP01 的 V01 只在【声音设计】里写了
    「完成第一句内心独白」，未给原文；成片生成出剧本中不存在的
    「我还活着／那是虎妖王」。台词被静默替换，对账表却全绿。

    契约本就规定台词用 `{}`（libtv-completed-prompt-format.md:101，
    真值写法「他说 {精确原文台词}，一口自然说完」）——本函数把它落成闸。
    """
    errors: list[str] = []
    prompts: dict[str, str] = {}
    heads = list(SEGMENT_HEADING_RE.finditer(text))
    for i, match in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        block = re.search(r"```text\n(.*?)```", text[match.start():end], re.S)
        if block:
            prompts[f"V{match.group(1)}"] = block.group(1)
    for index, source, landing, _result in voice_rows:
        landing_match = VOICE_LANDING_RE.search(landing)
        if not landing_match:
            continue
        segment_id = landing_match.group(1)
        prompt = prompts.get(segment_id)
        if prompt is None:
            continue
        line = source.split("]", 1)[1].strip() if "]" in source else source
        line = normalized_source(line)
        if not line:
            continue
        # 内心独白／旁白用 『』，同步对白用 {}。
        # 豆包官方符号表五个符号，tvskill 此前漏了旁白 —— 结果内心独白与同步对白
        # 同符号，模型无从区分谁该有口型、谁该出字幕。
        narration = bool(OS_VO_RE.search(source.split("]", 1)[0] if "]" in source else source))
        braced = {normalized_source(m) for m in DIALOGUE_RE.findall(prompt)}
        quoted = {normalized_source(m) for m in NARRATION_RE.findall(prompt)}
        want, want_sym = (quoted, "『原文』") if narration else (braced, "{原文}")
        other, other_sym = (braced, "{}") if narration else (quoted, "『』")
        if line in want:
            continue
        if line in other:
            errors.append(
                f"语音对账第 {index} 行在 {segment_id} 里用错了符号："
                f"{'内心独白/旁白' if narration else '同步对白'}应写 {want_sym}，"
                f"现在写成了 {other_sym}；两者同符号会让模型分不清谁该有口型、谁该出字幕"
            )
        else:
            errors.append(
                f"语音对账第 {index} 行的台词没有以 {want_sym} 进入 {segment_id} 的提示词："
                f"{source[:40]}；只描述「完成一句独白」不算，模型会自己编台词"
            )
    return errors



# 跨段锁定的体位词：状态交接表里出现它们，就意味着这一段该角色的体位是锁死的。
POSTURE_WORDS = ("坐姿", "跌坐", "半跪", "跪", "站姿", "站立", "俯卧", "仰卧", "躺")
# 角色语义 → <主体N> 的定义句。
SUBJECT_DEF_RE = re.compile(
    r"@\[(?P<sem>[^\]]+)\][^。；\n]{0,80}?定义为\s*(?P<subject><主体\d+>)"
)


def check_posture_restated_per_shot(
    label: str, section: str, handoff_rows: list[tuple[str, str, str]],
) -> list[str]:
    """状态交接表锁了体位，就要在该角色在场的每一个 Shot 正文里复述。

    状态交接表是交付侧台账，**不进模型**。只写在表里，模型看不到，体位就会漂。

    2026-09-04 实证两处：
    - V02 Shot 4：姜月初该保持坐姿，成片里站了起来。同段 Shot 1／5 都写了
      「保持坐姿」，Shot 2／3 是闪回人物不在场——唯一在场却漏写的那一镜就是断裂点。
    - V07 Shot 2：裴长青该保持半跪，成片里站了起来。

    段内合法的体位变化（起身、被拉起）会让本检查误报，故只作警告并点名镜号，
    由人判断这一镜是「漏写」还是「本就该变」。
    """
    warnings: list[str] = []
    block = re.search(r"```text\n(.*?)```", section, re.S)
    if not block:
        return warnings
    prompt = block.group(1)
    postures: dict[str, str] = {}
    for key, entry, exit_state in handoff_rows:
        if not key.strip().startswith("character:"):
            continue
        name = key.split(":", 1)[1].strip()
        # 入点与出点合起来只出现一个体位词，才算「本段锁死」。
        # 出现两个不同的（如「半跪」→「站立」）说明段内本就要变，跳过。
        # 只有一侧写了体位（如入点「半跪开口」、出点「捂胸施压」）仍算锁死——
        # V07 的裴长青正是这个形状，早期版本因为要求两侧完全一致而漏掉了它。
        found = {w for w in POSTURE_WORDS if w in entry or w in exit_state}
        # 「跪」是「半跪」的子串，去掉被包含的粗粒度词，避免自我冲突。
        found = {w for w in found if not any(w != o and w in o for o in found)}
        if len(found) == 1:
            postures[name] = found.pop()

    if not postures:
        return warnings

    subjects = {
        match.group("sem"): match.group("subject")
        for match in SUBJECT_DEF_RE.finditer(prompt)
    }
    shots = EXACT_SHOT_BLOCK_RE.findall(prompt)
    for name, word in postures.items():
        subject = next(
            (tag for sem, tag in subjects.items() if name in sem), None
        )
        if not subject:
            continue
        missing = [
            index
            for index, shot in enumerate(shots, 1)
            if subject in shot and word not in shot
        ]
        if missing:
            warnings.append(
                f"{label} 状态交接把 {name} 锁为「{word}」，但 Shot "
                f"{'、'.join(str(i) for i in missing)} 里出现了 {subject} 却没复述体位；"
                "状态交接表不进模型，漏写的那一镜体位就会漂"
            )
    return warnings




def check_no_duplicate_lines(text: str) -> list[str]:
    """同一句台词不得在同一个镜头里出现两次。

    2026-09-04 实证：手写镜头文本里已写了台词，自动注入又追加了一遍，
    同一行里出现两份「内心独白 『我……穿越了。』」。模型会当成要说两遍。
    交付校验此前只查「台词有没有进提示词」，不查「进了几次」——反例测试暴露的洞。
    """
    errors: list[str] = []
    for index, line in enumerate(text.split("\n"), 1):
        spoken = [
            s for s in NARRATION_RE.findall(line) + DIALOGUE_RE.findall(line)
            if "Mixed" not in s
        ]
        seen: dict[str, int] = {}
        for item in spoken:
            key = normalized_source(item)
            seen[key] = seen.get(key, 0) + 1
        repeated = [k for k, v in seen.items() if v > 1]
        if repeated:
            errors.append(
                f"第 {index} 行同一句台词出现多次：{repeated[:2]}；"
                "同镜重复会让模型把一句说成两遍"
            )
    return errors



def check_storyboard_grammar(text: str) -> tuple[list[str], list[str]]:
    """分镜语法闸：四要素头、转场、受控词表、POV 规则、写作纪律。

    对标 doubao-creative-drama 的 storyboard.md（用户 2026-09-04 指定为主要基准）。
    tvskill 此前的镜头是散文式的，最严重的是**完全没有「视角类型」这个维度**——
    整条产线从没区分过镜头是「从外面看」还是「从角色眼睛里看」。
    """
    errors: list[str] = []
    warnings: list[str] = []
    heads = list(SEGMENT_HEADING_RE.finditer(text))
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        section_text = text[head.start():end]
        block = re.search(r"```text\n(.*?)```", section_text, re.S)
        if not block:
            continue
        label = f"V{head.group(1)}"
        prompt = block.group(1)
        # 分镜语法只对**时间戳新形态**强制。旧的 Shot N 形态是既有产线在用的
        # 交付形式，一刀切会打断在途项目；它保留原有规则，不受本闸约束。
        blocks = TIMESTAMP_BLOCK_SPLIT_RE.findall(prompt)
        if not blocks:
            continue
        for order, shot in enumerate(blocks, 1):
            first = shot.split("\n", 1)[0]
            parts = SG.parse_shot_head(first)
            if parts is None:
                errors.append(
                    f"{label} 第 {order} 个时间段缺少四要素头："
                    "应写 `[景别｜视角类型｜机位状态｜角度与朝向]`，四项齐全"
                )
                continue
            size, viewpoint, move, angle = parts
            if not SG.in_vocabulary(size, SG.SHOT_SIZES):
                errors.append(f"{label} 第 {order} 段景别「{size}」不在受控词表内")
            if not (
                SG.VIEWPOINT_OBJECTIVE in viewpoint
                or SG.is_pov(viewpoint)
                or SG.VIEWPOINT_SWITCH in viewpoint
            ):
                errors.append(
                    f"{label} 第 {order} 段视角类型「{viewpoint}」不合规："
                    "必须是第三人称客观视角／某角色 POV 第一人称视角／POV 与第三视角切换"
                )
            if not SG.in_vocabulary(move, SG.CAMERA_MOVES):
                errors.append(f"{label} 第 {order} 段机位状态「{move}」不在受控词表内")
            if not SG.in_vocabulary(angle, SG.CAMERA_ANGLES):
                errors.append(f"{label} 第 {order} 段角度与朝向「{angle}」不在受控词表内")

            if SG.is_pov(viewpoint):
                who = SG.VIEWPOINT_POV_RE.sub("", viewpoint).strip()
                if not who:
                    errors.append(
                        f"{label} 第 {order} 段 POV 没写明所属角色；"
                        "只写「第一人称」不算，必须写成「某某 POV 第一人称视角」"
                    )
                if not SG.POV_EYE_LEVEL_RE.search(shot):
                    errors.append(
                        f"{label} 第 {order} 段是 POV，正文必须写明从该角色眼睛高度出发"
                    )
                if SG.POV_FACE_BAN_RE.search(shot):
                    errors.append(
                        f"{label} 第 {order} 段是 POV，画面里不能出现该角色的完整正脸"
                    )
                if SG.POV_SELFIE_BAN_RE.search(shot):
                    errors.append(
                        f"{label} 第 {order} 段把 POV 写成了自拍／监控／无人机视角；"
                        "需要过肩效果请直接写「过肩镜头」"
                    )

            if not SG.TRANSITION_RE.search(shot):
                errors.append(
                    f"{label} 第 {order} 段末尾缺少转场标注："
                    "须写 [硬切]／[叠化]／[视线跟随切] 之一"
                )

        if SG.VAGUE_QUALITY_RE.search(prompt):
            hit = SG.VAGUE_QUALITY_RE.search(prompt).group(0)
            errors.append(
                f"{label} 使用了模糊质量词「{hit}」；必须替换为具体的构图、光影、"
                "色彩、材质或空间描述——风格词不能冒充实质"
            )
        if SG.ABSTRACT_EMOTION_RE.search(prompt):
            hit = SG.ABSTRACT_EMOTION_RE.search(prompt).group(0)
            errors.append(
                f"{label} 使用了抽象情绪词「{hit}」；情绪必须外化为具体身体细节"
                "（低头／肩膀颤抖／指节攥紧衣角／下颌线绷紧）"
            )
        if SG.CROWD_QUANTIFIER_RE.search(prompt):
            hit = SG.CROWD_QUANTIFIER_RE.search(prompt).group(0)
            errors.append(
                f"{label} 使用了群体量词「{hit}」；必须写全当前镜头内每个角色的名字"
            )
        if SG.PRONOUN_REF_RE.search(prompt):
            hit = SG.PRONOUN_REF_RE.search(prompt).group(0)
            errors.append(
                f"{label} 用「{hit}」指代已命名角色；同一角色全程必须同名"
            )
    return errors, warnings



# 留白式风格写法：模型无从对齐，必须换成可指认的锚点。
VAGUE_STYLE_RE = re.compile(
    r"^(?:电影风格|影视级布光|高级感|大片感|电影感|质感风格)$"
)
# 可指认的风格锚点：真人路径写「某某风格的电影」，非真人路径写类型词。
NAMED_STYLE_RE = re.compile(r"风格的电影|3D\s*\S+风格|2D\s*\S+风格|赛璐璐|水墨|皮克斯")
STYLE_FIELD_RE = re.compile(r"^- 风格：(.+)$", re.M)


def check_style_anchor(text: str) -> tuple[list[str], list[str]]:
    """全剧风格锚点：一个来源、一字不差、可指认。

    对标 doubao-creative-drama：剧本头 `风格` 字段是全链路唯一锚点，
    下游所有资产、关键帧、视频提示词的首句风格限定词必须**一字不差**沿用；
    读到「电影风格」「影视级布光」这类留白写法应停下回填，不得继续生成。

    tvskill 此前各段自己写风格行、无统一来源，本集用的是自造描述词
    「高端东方玄幻 3D 低饱和废土战场美学」——模型没见过这种词，无从对齐。
    """
    errors: list[str] = []
    warnings: list[str] = []
    field = STYLE_FIELD_RE.search(text)
    if not field:
        # 向后兼容：没声明 `风格` 字段的旧交付不触发本闸，不打断在途项目。
        # 声明了才走全套检查——这是新标准的自愿加入方式。
        return errors, warnings
    style = field.group(1).strip()
    if VAGUE_STYLE_RE.match(style):
        errors.append(
            f"风格字段「{style}」是留白写法，模型无从对齐；"
            "真人路径写「某某风格的电影」（可带代表作），非真人路径写「3D 玄幻风格」等类型词"
        )
    elif not NAMED_STYLE_RE.search(style):
        warnings.append(
            f"风格字段「{style}」不是可指认的锚点；"
            "建议改为导演／影片对标（「王家卫《花样年华》风格的电影」）或标准类型词"
        )
    # 各段提示词首句必须含该锚点
    heads = list(SEGMENT_HEADING_RE.finditer(text))
    missing = []
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        block = re.search(r"```text\n(.*?)```", text[head.start():end], re.S)
        if block and style not in block.group(1):
            missing.append(f"V{head.group(1)}")
    if missing:
        errors.append(
            f"这些段的提示词没有一字不差沿用风格锚点「{style}」：{missing}；"
            "全项目风格限定词必须同源同字，不得各段自写"
        )
    return errors, warnings


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
    # keyframe 也在内：经状态机不可达（requires 链强制它先于 coverage），
    # 但这个元组存在的意义正是拦手工篡改的状态文件，漏一步就是留一个后门。
    required = (
        "intake", "script_units", "entities", "assets",
        "segments", "keyframe", "coverage",
    )
    missing = [step for step in required if steps.get(step) != "done"]
    if missing:
        errors.append(
            f"流程凭据显示这些前置步骤尚未完成：{missing}；"
            "请回到 pipeline_state.py 依次过闸，不要跳步"
        )
    # 空 goal 不是"无需对账"，是硬错：契约被清空或字段被删后若在这里跳过，
    # 漂移的模型/画幅/分辨率会被静默放行，而 intake 仍写着 done。
    import goal_contract

    errors.extend(
        goal_contract.reconcile(path.read_text(encoding="utf-8"), state.get("goal") or {})
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
        ("全剧二审（已通过／待二审）", SERIES_REVIEW_RE),
    ):
        if not pattern.search(text):
            errors.append(f"全剧连续性声明缺少或错误：{field_name}")
    if "| 连续键 | 类型 | 锁定版本 | 本集允许变化 | 变更依据 |" not in text:
        errors.append("全剧连续性母版缺少固定表头")

    model_match = MODEL_RE.search(text)
    if not model_match:
        errors.append("缺少节点默认模型")
    elif model_match.group(1).strip() not in SUPPORTED_MODELS:
        errors.append(
            "节点模型不在支持集合内："
            + "、".join(sorted(SUPPORTED_MODELS))
        )
    aspect_match = ASPECT_RATIO_RE.search(text)
    if not aspect_match:
        errors.append("缺少节点默认画幅")
    elif aspect_match.group(1).strip() not in SUPPORTED_RATIOS:
        errors.append(
            "节点默认画幅不在平台支持集合内：" + "、".join(sorted(SUPPORTED_RATIOS))
        )
    resolution_match = RESOLUTION_RE.search(text)
    if not resolution_match:
        errors.append("缺少节点默认分辨率")
    elif resolution_match.group(1).strip().lower() not in SUPPORTED_RESOLUTIONS:
        errors.append(
            "节点默认分辨率不在平台支持集合内："
            + "、".join(sorted(SUPPORTED_RESOLUTIONS))
        )

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
            errors.append(f"{label} 缺少提示词二审字段（已通过／待二审）")
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
            else:
                warnings.extend(
                    check_posture_restated_per_shot(label, section, handoff_rows)
                )
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
        if "主体标签锁定：" not in prompt:
            errors.append(f"{label} 缺少稳定主体标签锁定行")

        rows = [
            (int(number), asset.strip(), media_type.strip(), semantic.strip())
            for number, asset, media_type, semantic in MIXED_ROW_RE.findall(section)
        ]
        if not rows:
            errors.append(f"{label} Mixed 上传表为空")
        counts = {
            "图片": sum("图片" in media_type for _, _, media_type, _ in rows),
            "视频": sum("视频" in media_type for _, _, media_type, _ in rows),
            "音频": sum("音频" in media_type for _, _, media_type, _ in rows),
        }
        counts["总计"] = sum(counts.values())
        for kind, limit in REFERENCE_LIMITS.items():
            if counts[kind] > limit:
                errors.append(
                    f"{label} 超过 Seedance 2.0 Rule of 12：{kind}={counts[kind]}>{limit}；"
                    "请拆段或移除非核心道具/背景资产"
                )
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
        # 起手帧已承载空间、构图、光影，可替代 <场景N> 定义。
        # 新架构下场景锚不再直接进视频节点（keyframe-composition-contract.md）。
        if not re.search(r"定义为\s*<场景\d+>", prompt) and not re.search(
            r"@\[?起手帧", prompt
        ):
            errors.append(
                f"{label} 既没有把场景素材定义为 <场景N>，也没有绑定起手帧；"
                "二者必居其一——空间信息总要有个来源"
            )
        if PLANNING_ASSET_RE.search(prompt):
            errors.append(f"{label} 提示词引用了规划图、标记图或位置示意资产")

        shots = [int(number) for number in EXACT_SHOT_RE.findall(prompt)]
        # 时间戳动作规划形态下，第 N 个时间段即对账表里的 Shot N 落点。
        # 两种形态共用同一套落点编号，对账表不必区分。
        spans = TIMESTAMP_BLOCK_RE.findall(prompt)
        shots_by_segment[actual] = len(shots) or len(spans) or 1
        continuous_take_segments[actual] = not shots and not spans
        color_card_rows = [
            row for row in rows if "色卡" in f"{row[1]} {row[3]}"
        ]
        segments_with_color_card[actual] = bool(color_card_rows)
        # 绑了色卡 ≠ 用了色卡。万物生·问心 113 条含色卡的真实提示词里，
        # 49% 在锚定句之后还点名了本段实际调用的颜色及其落点，例如：
        #   「本段光的颜色为烈日烤白的暖光 #F4E6C8 铸在沙地上，极短硬阴影 #6B5A47」
        #   「重点调用石窟冷蓝 #3A4A5C 作为夜空冷调主色 + 岩崖砂岩 #C9A678 的环境底色」
        # 只写「严格按此色板执行、不可偏离」而不点名落点，色卡对模型近乎无约束力——
        # 这是「为满足规则而绑、绑完丢在一边」的典型形状。
        if color_card_rows and not (
            INLINE_HEX_RE.search(prompt) or COLOR_CALLOUT_RE.search(prompt)
        ):
            warnings.append(
                f"V{actual} 绑定了色卡但未点名本段调用的颜色及其落点；"
                "锚定句之后应写明重点调用哪几个色、分别落在哪个物件或光上"
                "（真实语料 49% 如此写，只写「按色板执行」对模型约束力很弱）"
            )
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
        elif TIMESTAMP_BLOCK_RE.search(prompt):
            # 时间戳动作规划：万物生语料与豆包官方 skill 的一致写法，
            # 段内不用镜头标签，改为把段时长切成连续时间段。
            # 连续性与总时长由 _fast_drama_contract 校验。
            pass
        elif not continuous_take:
            errors.append(
                f"{label} 必须使用时间戳动作规划（`0-3 秒：`）、"
                "精确 Shot N: 或声明“单一连续镜头，无剪切”"
            )
        else:
            budget_errors, budget_warnings = shot_budget_messages(
                duration,
                1,
                continuous_take=True,
                has_long_take_intent=bool(LONG_TAKE_INTENT_RE.search(prompt)),
            )
            errors.extend(f"{label} {message}" for message in budget_errors)
            warnings.extend(f"{label} {message}" for message in budget_warnings)

        quality_errors, quality_warnings = prompt_quality_messages(
            prompt,
            duration,
            has_character_references=bool(character_bindings),
            text_strategy=text_strategy,
        )
        errors.extend(f"{label} {message}" for message in quality_errors)
        warnings.extend(f"{label} {message}" for message in quality_warnings)

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
            prompt_lines = prompt.splitlines()
            first_line = prompt_lines[0] if prompt_lines else ""
            # The mandatory subject-lock line may precede the style spine;
            # accept the following line as the style lock in that layout.
            style_line = (
                prompt_lines[1]
                if first_line.startswith("主体标签锁定：") and len(prompt_lines) > 1
                else first_line
            )
            for present, missing_desc in (
                (bool(STYLE_LOCK_RE.match(style_line)), "开篇风格锁定行"),
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
        if not MEDIUM_RE.search(prompt):
            errors.append(
                f"{label} 缺少媒介声明（真人实拍／2D 动漫／3D CG／定格动画／其它，"
                "全剧统一且中途不更换）"
            )
        if not PHYSICAL_LIGHT_RE.search(prompt):
            errors.append(f"{label} 缺少可识别的物理光源")
        slop_count = sum(term in prompt for term in SLOP_TERMS)
        if slop_count >= 4:
            errors.append(f"{label} 空泛画质词过多，应改为机位、物理光源、动作或声音")
        no_subtitle = any(
            term in prompt for term in ("无字幕", "NOT字幕", "NOT 字幕", "不出现字幕", "不新增字幕")
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
            if any(
                COMPETING_DIALOGUE_ACTION_RE.search(block)
                and not re.search(r"开口前完成.{0,36}停稳后", block)
                for block in sync_blocks
            ):
                errors.append(f"{label} 同步对白混入走位、道具、群体反应或特效竞争动作")
            if (grade == "正式" or run_status == "可运行") and not CLEAN_FRAME_BINDING_RE.search(prompt):
                errors.append(
                    f"{label} 可运行同步对白缺少干净首帧或已验收续接帧眼神锚；"
                    "预览标签不能绕过"
                )
            if any(not PRELINE_TRIGGER_RE.search(block) for block in sync_blocks):
                errors.append(f"{label} 同步对白缺少开口触发")
            if any(not EYE_TARGET_RE.search(block) for block in sync_blocks):
                errors.append(f"{label} 同步对白缺少具体眼神对象或落点")
            if any(
                not POSTLINE_ENDPOINT_RE.search(block) and "声连画断贯穿" not in block
                for block in sync_blocks
            ):
                errors.append(f"{label} 同步对白缺少说完后的可剪辑落点")
            if any(not STABLE_DIALOGUE_CAMERA_RE.search(block) for block in sync_blocks):
                errors.append(f"{label} 同步对白缺少固定或稳定机位")
            if any(FROZEN_ENDPOINT_RE.search(block) for block in sync_blocks):
                errors.append(f"{label} 同步对白使用冻结式说完落点，应改为呼吸、倾听或继续原动作")
            for block in sync_blocks:
                control_clauses = [
                    # 真实提示词压倒性使用半角逗号，且是多行文本块；
                    # 只按全角标点切分会让整块 800 字返回成一个子句，
                    # 这条规则在真实语料上等于死代码。
                    clause for clause in re.split(r"[，；。,;\n、]", block)
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

    voice_rows = [
        (int(index_text), source.strip(), segment_text.strip(), result.strip())
        for index_text, source, segment_text, result in VOICE_ROW_RE.findall(
            subsection(text, "## 语音对账")
        )
    ]
    if not voice_rows:
        errors.append(
            "语音对账没有有效对账行：原剧本每句台词/OS/VO/旁白都要有一行，"
            "空表头不构成对账"
        )
    else:
        if [row[0] for row in voice_rows] != list(range(1, len(voice_rows) + 1)):
            errors.append("语音对账序号必须从 1 连续递增，且与原剧本顺序一致")
        for row_index, _, segment_text, result in voice_rows:
            if not segment_text:
                errors.append(f"语音对账第 {row_index} 行没有写所在段")
            if not result:
                errors.append(f"语音对账第 {row_index} 行没有写对账结果")
        if script is not None:
            errors.extend(check_voice_against_script(voice_rows, script, episode))
        errors.extend(check_voice_lines_reach_prompt(voice_rows, text))
        errors.extend(check_no_duplicate_lines(text))
        style_errors, style_warnings = check_style_anchor(text)
        errors.extend(style_errors)
        warnings.extend(style_warnings)
        grammar_errors, grammar_warnings = check_storyboard_grammar(text)
        errors.extend(grammar_errors)
        warnings.extend(grammar_warnings)

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
