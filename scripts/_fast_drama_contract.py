"""Shared Seedance fast-drama prompt gates for Markdown and live canvas audits."""

from __future__ import annotations

import collections
import re

from _shared_patterns import DIALOGUE_RE, EXACT_SHOT_BLOCK_RE, EXACT_SHOT_RE, OS_VO_RE
from _shot_budget import shot_budget_messages


GENERIC_DIALOGUE_TRIGGER_RE = re.compile(r"听见前一句结束后才开口")
GENERIC_EYE_TARGET_RE = re.compile(r"视线落在画面内真实对象的眼睛")
CHARACTER_REFERENCE_EXCLUSION_RE = re.compile(
    r"人物图.{0,80}(?:不继承|忽略).{0,80}(?:原背景|白底|多视图|分格|原姿势|直视镜头|原视线)"
    r"|(?:不继承|忽略).{0,80}(?:白底|多视图|分格|中性站姿|直视镜头)"
)
GENERIC_SOUND_DESIGN_RE = re.compile(
    r"保留场景连续底噪、衣料摩擦、脚步或道具接触的自然声"
)
GENERIC_PERFORMANCE_RE = re.compile(
    r"说完恢复鼻息并继续倾听，?保持自然活状态"
    r"|保持自然呼吸和连续动作，?不增加其它剧情动作"
)
PLANNING_SCENE_CLEANSE_RE = re.compile(
    r"定义为\s*<场景\d+>.{0,220}(?:不继承|忽略).{0,120}"
    r"(?:多视图|分格|文字标签|灰色占位)",
    re.S,
)
SEATED_BLOCK_RE = re.compile(r"坐在|保持坐姿|就座")
SCREEN_POSITION_RE = re.compile(
    r"画面(?:左|右)|屏幕(?:左|右)|左侧|右侧|对侧|前景|后景"
)
VISIBLE_TEXT_RE = re.compile(
    r"纸张抬头|加粗大字|(?:屏幕|手机|通知|协议).{0,28}[「“（]"
    r"|(?:清晰)?(?:显示|写着).{0,24}[「“（]"
)
ROUGH_SHOT_SECONDS_RE = re.compile(r"^Shot\s+\d+:.*?约\s*(\d+(?:\.\d+)?)\s*秒", re.M)
OFFSCREEN_SPATIAL_RE = re.compile(
    r"(?:电话|门外|走廊|画面外|左侧|右侧|远处|近处|前方|后方).{0,80}"
    r"(?:声场|方位|距离|混响|回声|带宽|听筒|扬声器)"
    r"|(?:声场|方位|距离|混响|回声|带宽|听筒|扬声器).{0,80}"
    r"(?:电话|门外|走廊|画面外|左侧|右侧|远处|近处|前方|后方)"
)
UNBOUND_SHOT_SUBJECT_RE = re.compile(r"^Shot\s+\d+:.*画外对话方", re.M)
BRIDGE_END_RE = re.compile(r"声连画断贯穿至 Shot\s+(\d+)")
CAMERA_COVERAGE_RE = re.compile(
    r"听者反应|双人关系镜|说话人侧面|说话人落句|动作细节特写|物证插入|画外声插切"
)
THIRD_ANGLE_RE = re.compile(r"双人关系镜|说话人侧面|动作细节特写|物证插入|侧后方中景")


def prompt_quality_messages(
    prompt: str,
    duration: int,
    *,
    has_character_references: bool,
    text_strategy: str = "",
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    shots = [int(number) for number in EXACT_SHOT_RE.findall(prompt)]

    if shots:
        # 只有**同步对白**才约束刀长：口型要对上，就必须停在说话人脸上。
        # 内心独白与画外音不需要口型，压在快切蒙太奇上完全成立——参考成片的
        # 回忆段正是「快切画面 + 连续独白」。把独白也算进念白时长会误判，
        # 2026-09-04 首版就把三个纯独白段（V05/V08/V10）错报成长对话段。
        spoken_chars = sum(
            len(re.findall(r"[\u4e00-\u9fff]", line))
            for block in EXACT_SHOT_BLOCK_RE.findall(prompt) or [prompt]
            if not OS_VO_RE.search(block)
            for line in DIALOGUE_RE.findall(block)
        )
        budget_errors, budget_warnings = shot_budget_messages(
            duration, len(shots), spoken_chars=spoken_chars
        )
        errors.extend(budget_errors)
        warnings.extend(budget_warnings)

    if has_character_references and not CHARACTER_REFERENCE_EXCLUSION_RE.search(prompt):
        errors.append(
            "人物参考缺少传递边界；必须声明只锁身份/服装，不继承白底、多视图分格、"
            "中性站姿或原视线"
        )
    if shots:
        rough_seconds = [float(value) for value in ROUGH_SHOT_SECONDS_RE.findall(prompt)]
        if rough_seconds and len(rough_seconds) != len(shots):
            errors.append("只有部分 Shot 写了约时长；必须全写或全不写")
        elif rough_seconds:
            if any(value < 1 or value > 4 for value in rough_seconds):
                errors.append("子镜头约时长必须以 2–3 秒为主，单镜只允许 1–4 秒")
            if abs(sum(rough_seconds) - duration) > 0.5:
                errors.append(
                    f"Shot 约时长合计 {sum(rough_seconds):g} 秒不等于段时长 {duration} 秒"
                )
        else:
            warnings.append("未显式写 Shot 约时长，无法核对爆款短剧约 2.1 秒刀长")
        if len(shots) >= 4 and not re.search(r"本段共\s*\d+\s*个.{0,24}硬切镜头", prompt):
            errors.append("四镜以上缺少硬切结构声明，总镜数与镜间关系不明确")

    if GENERIC_DIALOGUE_TRIGGER_RE.search(prompt):
        errors.append("使用了无指向的“听见前一句结束后才开口”模板")
    if GENERIC_EYE_TARGET_RE.search(prompt):
        errors.append("使用了无指向的“画面内真实对象”眼神模板")
    if UNBOUND_SHOT_SUBJECT_RE.search(prompt):
        errors.append("Shot 使用未绑定的“画外对话方”作为人物；可识别人物必须统一写 <主体N>")
    if GENERIC_SOUND_DESIGN_RE.search(prompt):
        errors.append("声音设计是全剧通用占位句，必须写本段底噪和逐拍声音事件")
    if GENERIC_PERFORMANCE_RE.search(prompt):
        errors.append(
            "使用了机械表演通用句；必须写角色目标、可见触发、一次具体身体动作和变化后的落点"
        )
    if PLANNING_SCENE_CLEANSE_RE.search(prompt):
        errors.append(
            "场景引用需要排除多视图/文字/灰色占位，说明它仍是规划板；"
            "负向提示不能把规划资产洗成视频素材，必须换干净单视图场景锚或干净首帧"
        )
    if re.search(r"^Shot\s+\d+:.*?：?转场[。；\s]", prompt, re.M):
        errors.append("存在只有“转场”而没有画面、机位和落点的空 Shot")
    if "。。" in prompt:
        errors.append("提示词含重复句号，属于机械编译残留")
    prompt_lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    duplicate_bindings = sorted({
        line for line, count in collections.Counter(prompt_lines).items()
        if count > 1 and "@[" in line and ("{{Mixed" in line or "@[图片:" in line or "@[音频:" in line)
    })
    if duplicate_bindings:
        errors.append(f"重复定义同一参考或音色：{duplicate_bindings}")
    if "无画面文字" in prompt and VISIBLE_TEXT_RE.search(prompt):
        errors.append("一边要求显示手机/屏幕/文件文字，一边声明无画面文字")
    if text_strategy == "定版道具图" and "无画面文字" in prompt:
        errors.append("文字策略为定版道具图时不能写“无画面文字”；应写只保留定版图文字")
    if "画外音" in prompt and not OFFSCREEN_SPATIAL_RE.search(prompt):
        errors.append("画外音缺少声场方位、距离或电话/空间混响说明")

    shot_region = prompt.split("【声音设计】", 1)[0]
    visible_subjects = set(re.findall(r"<主体\d+>", shot_region))
    if len(visible_subjects) >= 2 and SEATED_BLOCK_RE.search(shot_region):
        if not SCREEN_POSITION_RE.search(shot_region):
            errors.append(
                "多人坐姿段缺少屏幕左右、对侧或前后景位置锁；"
                "必须把每名人物绑定到具体座位和人物关系轴"
            )

    dialogue_matches = list(DIALOGUE_RE.finditer(prompt))
    dialogue_chars = sum(
        len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", match.group(1)))
        for match in dialogue_matches
    )
    if dialogue_chars > duration * 5:
        errors.append(
            f"台词约 {dialogue_chars} 字超过 {duration} 秒节点的快口容量 {duration * 5} 字；"
            "必须在自然意群处拆生成段"
        )
    long_dialogues = [
        match for match in dialogue_matches
        if len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", match.group(1))) > 18
    ]
    if long_dialogues and (len(shots) < 2 or "声连画断" not in prompt):
        errors.append(
            "存在超过 18 字的长对白，但没有用多机位声连画断承载；"
            "应在说话人、听者反应、关系镜或物证插入之间连续切换"
        )
    shot_blocks = [
        (int(EXACT_SHOT_RE.search(match.group(0)).group(1)), match.group(0), match.start(), match.end())
        for match in EXACT_SHOT_BLOCK_RE.finditer(prompt)
    ]
    for dialogue in long_dialogues:
        owner = next(
            (item for item in shot_blocks if item[2] <= dialogue.start() < item[3]),
            None,
        )
        if owner is None:
            continue
        start_number, owner_text, _, _ = owner
        bridge = BRIDGE_END_RE.search(owner_text)
        if bridge is None:
            errors.append("长对白所在 Shot 没有声明声连画断的结束镜号")
            continue
        end_number = int(bridge.group(1))
        span = [text for number, text, _, _ in shot_blocks if start_number <= number <= end_number]
        joined_span = "\n".join(span)
        if len(span) >= 2 and not CAMERA_COVERAGE_RE.search(joined_span):
            errors.append("长对白虽声明声连画断，但没有说话人/听者/关系/细节机位变化")
        if len(span) >= 4 and not THIRD_ANGLE_RE.search(joined_span):
            errors.append("跨四镜以上的长对白只有正反打重复，必须加入关系镜、侧面机位或有剧情依据的细节镜")
        reaction_run = 0
        max_reaction_run = 0
        for text in span:
            if "听者反应" in text:
                reaction_run += 1
                max_reaction_run = max(max_reaction_run, reaction_run)
            else:
                reaction_run = 0
        if max_reaction_run >= 3:
            errors.append("长对白连续重复三次以上同类听者反应镜，必须改变机位功能")
    return errors, warnings
