#!/usr/bin/env python3
"""Shared duration-to-shot guidance for TVSkill video prompt validators."""

from __future__ import annotations

import math


# 中文戏剧化念白的语速：每秒约 4 个字。用来把台词字数换算成必须留给表演的秒数。
SPOKEN_CHARS_PER_SECOND = 4.0
# 台词占到这个比例以上，本段就是「长对话段」，节奏须按官方 §6.1 走延长/长镜。
DIALOGUE_HEAVY_RATIO = 0.5
# 长对话段的目标刀长区间（秒）。取自参考成片《万妖图录传》EP01 对话段实测：
# 中位 4.0 秒、均值 4.5 秒；而同一集开篇蒙太奇是中位 2.8 秒。
DIALOGUE_SHOT_SECONDS = (3.5, 5.0)


def is_dialogue_heavy(duration: int, spoken_chars: int) -> bool:
    """台词占去半段以上时间，就是长对话段。"""
    if duration <= 0 or spoken_chars <= 0:
        return False
    return (spoken_chars / SPOKEN_CHARS_PER_SECOND) >= duration * DIALOGUE_HEAVY_RATIO


def recommended_shot_range(duration: int, spoken_chars: int = 0) -> tuple[int, int]:
    """Return the subshot target for one generated clip.

    快切基线来自用户 10,963 个子镜头语料：平均刀长约 2.1 秒（2s≈55%、3s≈30%）。
    但那份语料是**整体**分布，把它无差别套到长对话段上是过拟合。

    官方指南 §6.1 明确分两条路：
      - 单场文戏、长对话、情绪递进 → 优先视频延长，保持沉浸与连续；
      - 剧情转折、追逐、打斗、蒙太奇 → 独立分段生成后剪辑。

    2026-09-04 三条独立证据指向同一结论：
      1. 参考成片《万妖图录传》EP01 对话段(60–150s)中位刀长 4.0 秒，
         而同集开篇蒙太奇是 2.8 秒——同一部片子里两种节奏；
      2. 按 12 秒 5 镜下发后，**模型自己在有长台词的段少切了镜**
         （V09 只切 2 次、V02/V10 只切 3–4 次），它需要时间把话说完；
      3. Seedance 2.0 是音画同出模型，2.4 秒一刀不给角色留出念白与反应的余地，
         等于把它降级成只出画面。

    因此台词密集的段落改用 3.5–5 秒刀长，不再套快切基线。
    """
    if duration <= 0:
        return (1, 8)
    if is_dialogue_heavy(duration, spoken_chars):
        slow, fast = DIALOGUE_SHOT_SECONDS
        return (max(1, math.floor(duration / fast)), max(2, math.ceil(duration / slow)))
    if duration <= 4:
        return (1, 2)
    if duration <= 6:
        return (2, 4)
    if duration <= 9:
        return (3, 5)
    if duration <= 13:
        return (4, 7)
    if duration <= 15:
        return (5, 8)
    center = duration / 2.1
    return (max(1, math.floor(center - 1)), max(2, math.ceil(center + 1)))


def shot_budget_messages(
    duration: int,
    shot_count: int,
    *,
    continuous_take: bool = False,
    has_long_take_intent: bool = False,
    spoken_chars: int = 0,
) -> tuple[list[str], list[str]]:
    """Validate structure without turning a recommended range into a rigid shot cap."""
    errors: list[str] = []
    warnings: list[str] = []
    if duration <= 0:
        return errors, warnings

    if continuous_take:
        if duration >= 10 and not has_long_take_intent:
            errors.append(
                f"{duration} 秒连续单镜缺少长镜头叙事意图；10 秒以上不能把“单一连续镜头”当通用默认"
            )
        return errors, warnings

    low, high = recommended_shot_range(duration, spoken_chars)
    heavy = is_dialogue_heavy(duration, spoken_chars)
    if heavy and shot_count > high:
        warnings.append(
            f"{duration} 秒里有 {spoken_chars} 字台词（约 "
            f"{spoken_chars / SPOKEN_CHARS_PER_SECOND:.1f} 秒念白），属长对话段，"
            f"却切了 {shot_count} 个 Shot。官方指南 §6.1 对长对话要求「优先视频延长，"
            f"保持沉浸与连续」，建议 {low}–{high} 个镜；"
            "刀太碎会让音画同出的模型没有时间把话说完"
        )
    elif shot_count < low:
        warnings.append(
            f"{duration} 秒只有 {shot_count} 个 Shot；万物生式节拍建议 {low}–{high} 个，"
            "请确认少镜是导演选择而非单镜模板污染"
        )
    elif shot_count > high:
        warnings.append(
            f"{duration} 秒包含 {shot_count} 个 Shot；建议范围为 {low}–{high} 个，"
            "请确认每镜都有独立叙事功能"
        )

    if shot_count > 1 and duration / shot_count < 1.5:
        errors.append(
            f"{duration} 秒包含 {shot_count} 个 Shot，平均不足 1.5 秒；"
            "镜头密度超过原生生成的可靠事件预算"
        )
    return errors, warnings
