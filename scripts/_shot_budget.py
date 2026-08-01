#!/usr/bin/env python3
"""Shared duration-to-shot guidance for TVSkill video prompt validators."""

from __future__ import annotations

import math


def recommended_shot_range(duration: int) -> tuple[int, int]:
    """Return the Wanwu-style native subshot target for one generated clip."""
    if duration <= 0:
        return (1, 6)
    if duration <= 4:
        return (1, 2)
    if duration <= 6:
        return (1, 3)
    if duration <= 9:
        return (2, 4)
    if duration <= 13:
        return (3, 5)
    if duration <= 15:
        return (4, 6)
    return (max(1, math.floor(duration / 4)), max(2, math.ceil(duration / 2.5)))


def shot_budget_messages(
    duration: int,
    shot_count: int,
    *,
    continuous_take: bool = False,
    has_long_take_intent: bool = False,
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

    low, high = recommended_shot_range(duration)
    if shot_count < low:
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
