#!/usr/bin/env python3
"""目标契约：开工前与用户对齐的全剧级决策，落盘为不可漂移的契约。

设计依据见 docs/superpowers/specs/2026-09-04-tvskill-目标契约-design.md。

母契约是人读人改的 Markdown（`<项目根>/目标契约.md`）。本模块是它的
**唯一**解析与校验实现——pipeline_state.py 与 validate_delivery_md.py
都从这里导入，不各自重新解析，避免"规则散在多处"。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


class GoalContractError(ValueError):
    """母契约结构不合法：缺小节或缺字段。"""


# 小标题 → 字段名。顺序即模板顺序，字段名必须与 spec §5 逐字一致。
SECTIONS: dict[str, list[str]] = {
    "媒介与风格": ["媒介", "3D 子风格", "STYLE-ID", "保真取向", "成像基底"],
    "技术口径": ["模型展示名", "画幅", "分辨率", "视频预算路线"],
    "交付边界": ["交付到哪一步", "集数范围"],
    "资产策略": ["资产来源", "跨集身份根归属"],
    "声音路线": ["音色来源", "音色采样预览例外", "BGM"],
    "质量目标": ["对标成片", "验收严格度"],
}

ALL_FIELDS: list[str] = [name for names in SECTIONS.values() for name in names]

TEMPLATE = "# <项目名> 目标契约\n\n" + "\n\n".join(
    f"## {section}\n" + "\n".join(f"- {name}：" for name in names)
    for section, names in SECTIONS.items()
) + "\n"


def parse(text: str) -> tuple[dict[str, str], dict[str, int]]:
    """解析母契约。返回 (字段→值, 字段→行号)。行号从 1 起。"""
    lines = text.splitlines()
    missing_sections = [
        section for section in SECTIONS
        if not any(line.strip() == f"## {section}" for line in lines)
    ]
    if missing_sections:
        raise GoalContractError(
            f"母契约缺少这些小节：{missing_sections}；"
            "小标题必须与模板逐字一致，不能改写或增删"
        )

    goal: dict[str, str] = {}
    linenos: dict[str, int] = {}
    for index, line in enumerate(lines, 1):
        match = re.match(r"^-\s*(.+?)：(.*)$", line)
        if not match:
            continue
        name = match.group(1).strip()
        if name in ALL_FIELDS and name not in goal:
            goal[name] = match.group(2).strip()
            linenos[name] = index

    missing_fields = [name for name in ALL_FIELDS if name not in goal]
    if missing_fields:
        raise GoalContractError(
            f"母契约缺少这些字段：{missing_fields}；"
            "字段名必须与模板逐字一致"
        )
    return goal, linenos


def structure_errors(goal: dict[str, str], linenos: dict[str, int]) -> list[str]:
    """检查未决状态：空值、「待定」、以及未被用户确认掉的「[推断]」标记。"""
    errors: list[str] = []
    for name in ALL_FIELDS:
        value = goal[name]
        line = linenos[name]
        if not value or value == "待定":
            errors.append(
                f"第 {line} 行 {name} 仍为空或「待定」；"
                "开工前必须由用户裁定，不能带着未决项进入生产"
            )
        elif "[推断]" in value:
            errors.append(
                f"第 {line} 行 {name} 仍带「[推断]」标记：{value}；"
                "助手推断值必须经用户确认后去掉该标记"
            )
    return errors


# 成像基底取自 references/libtv/optical-substrate-library.md §1 的五种基底。
SUBSTRATES = (
    "35mm 发行拷贝",
    "16mm 电视转播转录",
    "长焦胶片压缩",
    "早期数字 / 小传感器",
    "监控 / CRT 翻拍",
)

ENUMS: dict[str, tuple[str, ...]] = {
    "媒介": ("真人实拍", "2D 动漫", "3D CG", "定格动画", "其它"),
    "3D 子风格": (
        "影视级国漫风格化3D", "高端日韩风格化3D", "仿真人数字人", "不适用",
    ),
    "保真取向": ("电影感", "低保真"),
    "成像基底": SUBSTRATES + ("不适用",),
    "交付到哪一步": ("仅 Markdown", "同步画布", "跑生成", "出成片"),
    "资产来源": ("复用既有 canonical", "全新生成", "混合"),
    "音色采样预览例外": ("是", "否"),
    "BGM": ("有", "无"),
}


def available_choices() -> dict[str, list[str]]:
    """弹窗候选集。只列真正跑得通的值。

    模型必须**同时**在校验白名单与 sync 别名表里：
    `_shared_patterns.SUPPORTED_MODELS` 含 `Seedance 2.5`，但
    `sync_delivery_markdown.MODEL_ALIASES` 没有它，而后者是
    `.get(requested, requested)`——未知名原样透传，到 TVMao schema 才炸。
    把这种值摆进候选集，比写死更糟。
    """
    from _shared_patterns import (  # noqa: E402
        SUPPORTED_MODELS, SUPPORTED_RATIOS, SUPPORTED_RESOLUTIONS,
    )
    from sync_delivery_markdown import MODEL_ALIASES  # noqa: E402

    return {
        "模型展示名": sorted(set(SUPPORTED_MODELS) & set(MODEL_ALIASES)),
        "画幅": sorted(SUPPORTED_RATIOS),
        "分辨率": sorted(SUPPORTED_RESOLUTIONS),
    }


def value_errors(goal: dict[str, str], linenos: dict[str, int]) -> list[str]:
    """枚举校验 + 四条联动必填规则（spec §5）。"""
    errors: list[str] = []

    for name, allowed in ENUMS.items():
        value = goal[name]
        if value and value not in allowed:
            errors.append(
                f"第 {linenos[name]} 行 {name} 取值非法：{value}；"
                f"合法取值为 {'／'.join(allowed)}"
            )

    for name, choices in available_choices().items():
        value = goal[name]
        if value and value not in choices:
            errors.append(
                f"第 {linenos[name]} 行 {name} 不在当前可用集合内：{value}；"
                f"可用值为 {'／'.join(choices)}"
            )

    if goal["媒介"] == "3D CG" and goal["3D 子风格"] == "不适用":
        errors.append(
            f"第 {linenos['3D 子风格']} 行 3D 子风格：媒介为 3D CG 时必须选定子风格。"
            "「3D CG」不是完整画风选择，它同时兼容仿真人数字人、风格化动画和潮玩卡通"
        )
    if goal["媒介"] != "3D CG" and goal["3D 子风格"] != "不适用":
        errors.append(
            f"第 {linenos['3D 子风格']} 行 3D 子风格：媒介不是 3D CG 时，3D 子风格必须填「不适用」"
        )
    if goal["保真取向"] == "电影感" and goal["成像基底"] == "不适用":
        errors.append(
            f"第 {linenos['成像基底']} 行 成像基底：保真取向为电影感时必须选定成像基底，"
            f"可选 {'／'.join(SUBSTRATES)}"
        )
    if goal["保真取向"] == "低保真" and goal["成像基底"] != "不适用":
        errors.append(
            f"第 {linenos['成像基底']} 行 成像基底：保真取向为低保真时，成像基底必须填「不适用」；"
            "光学缺陷库对低保真不适用"
        )
    return errors


# 只对账有现成解析锚点的四项：媒介、模型展示名、画幅、分辨率（spec §10）。
# BGM、音色采样预览例外、视频预算路线在交付 Markdown 中没有锚点，硬校验需
# 新写三个解析器，按 YAGNI 不做；质量目标组是自然语言，无法等值比对（决策四）。
# 「集数范围」仅记录，不参与校验。
_DELIVERY_ANCHORS = {
    "模型展示名": re.compile(r"^- 模型：(.+)$", re.M),
    "画幅": re.compile(r"^- 画幅：(.+)$", re.M),
    "分辨率": re.compile(r"^- 分辨率：(.+)$", re.M),
}

# 与 validate_delivery_md.py:215 的 MEDIUM_RE 保持同一套词。
_MEDIUM_RE = re.compile(r"真人实拍|2D\s*动漫|二维动漫|3D\s*CG|三维动画|定格动画")
_MEDIUM_CANONICAL = {
    "二维动漫": "2D 动漫",
    "三维动画": "3D CG",
}


def _canonical_medium(token: str) -> str:
    token = re.sub(r"\s+", " ", token).strip()
    return _MEDIUM_CANONICAL.get(token, token)


def crosscheck(delivery_text: str, goal: dict[str, str]) -> list[str]:
    """交付 Markdown 与母契约的正反向对账。

    正向：契约每一项在交付中必须有落点，找不到即交付漏写。
    反向：交付中出现的每一项声明必须能回溯到契约且值相等，
          回溯不到或值不等即私自新增或漂移。

    模式取自 references/v3/05-dialogue-and-audio.md 的语音对账。
    只做正向会漏掉「交付里多出一个母契约没授权的声明」。
    """
    errors: list[str] = []

    for name, pattern in _DELIVERY_ANCHORS.items():
        expected = goal[name].strip()
        found = [m.strip() for m in pattern.findall(delivery_text)]
        if not found:
            errors.append(
                f"正向对账失败：母契约声明 {name}＝{expected}，"
                f"但交付 Markdown 里找不到对应字段"
            )
            continue
        wrong = sorted({value for value in found if value != expected})
        if wrong:
            errors.append(
                f"反向对账失败：{name} 契约值＝{expected}，交付值＝{'／'.join(wrong)}；"
                "全剧级声明不得在交付中被私自改写"
            )

    expected_medium = goal["媒介"].strip()
    found_media = {_canonical_medium(m) for m in _MEDIUM_RE.findall(delivery_text)}
    if expected_medium == "其它":
        # 「其它」无法用 MEDIUM_RE 机器比对，其含义由 STYLE-ID 承载，跳过。
        pass
    elif not found_media:
        errors.append(
            f"正向对账失败：母契约声明媒介＝{expected_medium}，"
            "但交付 Markdown 里没有任何媒介声明"
        )
    else:
        wrong_media = sorted(found_media - {expected_medium})
        if wrong_media:
            errors.append(
                f"反向对账失败：媒介契约值＝{expected_medium}，"
                f"交付中还出现了未授权的媒介声明：{'／'.join(wrong_media)}；"
                "媒介必须全剧统一，中途不得更换"
            )
    return errors


def diff(old: dict[str, str], new: dict[str, str]) -> list[str]:
    """字段级差异，供作废时告知用户「改了什么」。"""
    changed: list[str] = []
    for name in ALL_FIELDS:
        before = old.get(name, "—")
        after = new.get(name, "—")
        if before != after:
            changed.append(f"{name}：{before} → {after}")
    return changed
