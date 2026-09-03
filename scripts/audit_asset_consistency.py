#!/usr/bin/env python3
"""Audit cross-episode asset reuse, state coverage, and visual contracts."""

from __future__ import annotations

import argparse
import collections
import re
import struct
from pathlib import Path


ASSET_RE = re.compile(
    r"^\|\s*(人物|场景|道具|色卡)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|$",
    re.M,
)
MIXED_RE = re.compile(
    r"^\|\s*Mixed\s+\d+\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*@\[([^]]+)\]\s*\|$",
    re.M,
)
SEGMENT_RE = re.compile(r"^## 生成段 V(\d{2})｜", re.M)

BASE_NAMES = (
    "吴馨", "李承", "江琴", "吴志远", "吴母", "李国强", "警察", "律师",
    "王秘书", "安保队长", "业主甲", "保镖", "陈主任", "HR负责人",
    "商界大佬甲", "法官", "辩护律师", "路人甲", "路人乙",
)

BASE_STATE_ALIASES = {
    "吴馨-基础形态", "江琴-朱红大衣", "吴母-雾蓝披肩",
    "警察-A", "律师-A", "王秘书", "安保队长-A", "业主甲-A",
    "保镖-A", "商界大佬甲-A", "法官-A", "辩护律师-A",
    "路人甲-A", "路人甲-B", "路人乙-A", "陈主任-A", "HR负责人-A",
    "保镖群-A", "保镖群-C", "民警群-两人", "法警群-A",
    "安保群-B", "滨江湾安保群-A", "宴会宾客群-A",
    "设计院同事群-A", "商业街路人群-A", "老街路人群-A", "路人群-B",
}


def png_size(path: Path) -> tuple[int, int] | None:
    try:
        data = path.read_bytes()[:24]
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return struct.unpack(">II", data[16:24])
    except OSError:
        return None
    return None


def base_character(name: str) -> str | None:
    for base in sorted(BASE_NAMES, key=len, reverse=True):
        if name == base or name.startswith(base + "-"):
            return base
    return None


def audit(root: Path) -> tuple[list[str], list[str], dict]:
    errors: list[str] = []
    warnings: list[str] = []
    docs = sorted(root.glob("EP*-LibTV视频节点提示词.md"))
    semantic_occurrences: dict[str, set[str]] = collections.defaultdict(set)
    state_rows: list[tuple[str, str, str]] = []
    prop_rows: list[tuple[str, str]] = []
    color_rows: dict[str, set[str]] = collections.defaultdict(set)
    scene_rows: dict[str, set[str]] = collections.defaultdict(set)
    style_lines = set()
    model_lines = set()
    medium_lines = set()
    ratios = set()
    resolutions = set()
    segment_count = 0

    for doc in docs:
        episode = doc.stem.split("-", 1)[0]
        text = doc.read_text(encoding="utf-8")
        prompt_starts = re.findall(r"^\x60{3}text\s*\n([^\n]+)", text, re.M)
        style_lines.update(prompt_starts[:1])
        model_lines.update(re.findall(r"^- 模型：(.+)$", text, re.M))
        medium_lines.update(re.findall(r"^- 媒介：(.+)$", text, re.M))
        ratios.update(re.findall(r"^- 画幅：(.+)$", text, re.M))
        resolutions.update(re.findall(r"^- 分辨率：(.+)$", text, re.M))
        segments = list(SEGMENT_RE.finditer(text))
        segment_count += len(segments)
        for kind, name, _, _ in ASSET_RE.findall(text):
            name = name.strip()
            if kind == "人物":
                base = base_character(name)
                if base and name != base:
                    state_rows.append((episode, name, base))
            elif kind == "道具":
                prop_rows.append((episode, name))
            elif kind == "色卡":
                color_rows[name].add(episode)
            elif kind == "场景":
                scene_rows[name].add(episode)
        for asset, _, semantic in MIXED_RE.findall(text):
            asset = asset.strip()
            semantic = semantic.strip()
            semantic_occurrences[asset].add(episode)
            if asset.startswith("色卡-"):
                color_rows.setdefault(asset, set()).add(episode)
            if asset.startswith("场景状态-"):
                scene_rows.setdefault(asset.removeprefix("场景状态-"), set()).add(episode)

    mapping_path = root / ".tvmao" / "input-assets.tsv"
    mapping = {}
    if mapping_path.exists():
        mapping = {
            line.split("\t", 1)[0]: line.split("\t", 1)[1]
            for line in mapping_path.read_text(encoding="utf-8").splitlines()
            if "\t" in line
        }
    for extra in (
        root / ".tvmao" / "character-state-inputs.tsv",
        root / ".tvmao" / "character-state-board-inputs-v2.tsv",
        root / ".tvmao" / "prop-inputs.tsv",
    ):
        if extra.exists():
            mapping.update({
                line.split("\t", 1)[0]: line.split("\t", 1)[1]
                for line in extra.read_text(encoding="utf-8").splitlines()
                if "\t" in line
            })
    for asset, episodes in sorted(semantic_occurrences.items()):
        if asset.startswith(("独立身份图-", "场景状态-", "色卡-")) and asset not in mapping:
            errors.append(f"{asset} 在 EP{','.join(sorted(episodes))} 使用但没有 image-input 映射")
    for episode, name, base in state_rows:
        if name in BASE_STATE_ALIASES or any(
            token in name for token in ("电话音", "广播音", "来电音", "提示音")
        ):
            continue
        expected = f"独立身份图-{name}"
        if expected not in semantic_occurrences:
            errors.append(
                f"{episode} 人物状态「{name}」未派生独立身份图；"
                f"当前只复用基础身份「独立身份图-{base}」"
            )
    for episode, name in prop_rows:
        if name.startswith("无独立剧情道具"):
            # Explicit placeholder rows keep the four-category asset
            # contract intact when all ordinary props are carried by the
            # scene-state image; they are not expected in Mixed.
            continue
        needle = name.replace("/", "／")
        if not any(needle in asset for asset in semantic_occurrences):
            errors.append(f"{episode} 道具「{name}」已登记但未绑定到任何视频 Mixed")
    for episode, name in sorted((ep, name) for name, eps in color_rows.items() for ep in eps):
        semantic = name if name.startswith("色卡-") else f"色卡-{name}"
        if semantic not in semantic_occurrences:
            warnings.append(f"{episode} 色卡「{name}」登记但没有直接 Mixed 绑定")
    for episode, name in sorted((ep, name) for name, eps in scene_rows.items() for ep in eps):
        semantic = name if name.startswith("场景状态-") else f"场景状态-{name}"
        if semantic not in semantic_occurrences:
            warnings.append(f"{episode} 场景「{name}」登记但没有直接 Mixed 绑定")

    if len(style_lines) != 1:
        errors.append(f"STYLE 锁定行不统一：{sorted(style_lines)}")
    if model_lines != {"Seedance 2.0 VIP"}:
        errors.append(f"模型合同不统一或不是 Pro：{sorted(model_lines)}")
    if ratios != {"9:16"}:
        errors.append(f"视频画幅合同不统一：{sorted(ratios)}")
    if resolutions != {"480P"}:
        errors.append(f"视频分辨率合同不统一：{sorted(resolutions)}")
    if not all("3D CG" in line for line in medium_lines):
        errors.append(f"媒介声明不统一：{sorted(medium_lines)}")

    image_groups = {
        "characters": root / "assets" / "characters",
        "scenes": root / "assets" / "scenes",
        "props": root / "assets" / "props",
        "color-cards": root / "assets" / "color-cards",
    }
    bad_sizes = []
    for group, directory in image_groups.items():
        for path in directory.rglob("*.png"):
            size = png_size(path)
            if not size or abs(size[0] / size[1] - 16 / 9) >= 0.03:
                bad_sizes.append(f"{group}/{path.name}={size}")
    if bad_sizes:
        errors.append(f"存在非 16:9 资产：{bad_sizes[:12]}")

    return errors, warnings, {
        "episodes": len(docs),
        "segments": segment_count,
        "mixedSemantics": len(semantic_occurrences),
        "stateRows": len(state_rows),
        "propRows": len(prop_rows),
        "inputMappings": len(mapping),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    errors, warnings, summary = audit(args.project_dir)
    for item in errors:
        print(f"ERROR: {item}")
    for item in warnings:
        print(f"WARNING: {item}")
    print(f"SUMMARY: {summary} errors={len(errors)} warnings={len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
