#!/usr/bin/env python3
"""目标契约：开工前与用户对齐的全剧级决策，落盘为不可漂移的契约。

设计依据见 docs/superpowers/specs/2026-09-04-tvskill-目标契约-design.md。

母契约是人读人改的 Markdown（`<项目根>/目标契约.md`）。本模块是它的
**唯一**解析与校验实现——pipeline_state.py 与 validate_delivery_md.py
都从这里导入，不各自重新解析，避免"规则散在多处"。
"""

from __future__ import annotations

import re


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
