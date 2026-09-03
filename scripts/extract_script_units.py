#!/usr/bin/env python3
"""Extract picture/subtitle/SFX units from a Chinese short-drama script.

The extracted list is the source of truth for 画面对账 coverage: the delivery
Markdown must account for every unit, and validate_delivery_md.py re-derives the
list from the same script instead of trusting a hand-written count.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


# 集号行允许同行带标题（「第1集 开局系统」）或冒号，也接受中文数字。
# 原先要求整行只有集号，遇到带标题的剧本会一条单元都抽不到，
# 而报错信息说的是"请确认集号"，把人引向错误方向。
EPISODE_RE = re.compile(
    r"^第\s*([0-9〇零一二三四五六七八九十百]+)\s*集(?:(?:\s*[：:])|\s|$)"
)
# 场次号与描述之间不强制空白：中文剧本常写「1-2课间走廊 日 内」。
# 原先漏匹配时该行被静默丢弃且 current_scene 不更新，
# 导致其后所有画面单元被错误归属到上一场——比丢一行更难发现。
SCENE_RE = re.compile(r"^(\d+)-(\d+)\s*(\S.*)$")
SUBTITLE_RE = re.compile(r"【字幕[：:]([^】]*)】")
UI_PANEL_RE = re.compile(
    r"^【(?:第[^】]*任务|目标[：:]|任务时限|系统提示|检测到|.*好感度)[^】]*】$"
)
# 音效标签后常带内容：【音效：玻璃碎裂】。与 SUBTITLE_RE 同样收全半角冒号。
SFX_MARK_RE = re.compile(r"^(?:△\s*)?【音效(?:[：:]|】)")
VISUAL_PREFIX_RE = re.compile(r"^[△▲]")
BRACKET_LINE_RE = re.compile(r"^【([^】]*)】$")
# 剧本里的台词行（`角色名：台词`），与 _shared_patterns.DIALOGUE_RE（提示词里的
# `{}` 台词真值锁）语义完全不同，故不同名，避免被误当成同一判据。
# 场次元信息行（人物表/场景/时间），形式上像台词行但不是台词。
META_LINE_RE = re.compile(r"^(?:人物|角色|场景|地点|时间|时间地点|服装|道具)\s*[：:]")
BRACKET_CAST_META_RE = re.compile(
    r"^【(?:出场人物|出场角色|人物|角色)\s*[：:][^】]*】$"
)
SCRIPT_DIALOGUE_LINE_RE = re.compile(
    r"^[^△【\s][^：:]{0,12}(?:OS|VO|OV)?(?:（[^）]*）)?[：:]"
)


CN_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def parse_episode_number(text: str) -> int | None:
    """集号可能写成阿拉伯数字或中文数字（第一集 / 第十二集）。"""
    if text.isdigit():
        return int(text)
    total = 0
    section = 0
    for char in text:
        if char in CN_DIGITS:
            section = CN_DIGITS[char]
        elif char == "十":
            section = (section or 1) * 10
            total += section
            section = 0
        elif char == "百":
            section = (section or 1) * 100
            total += section
            section = 0
        else:
            return None
    return total + section or None


def docx_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    word = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for block in root.iter(f"{word}p"):
        logical_lines: list[str] = []
        fragments: list[str] = []
        for element in block.iter():
            if element.tag == f"{word}t":
                fragments.append(element.text or "")
            elif element.tag in (f"{word}br", f"{word}cr"):
                logical_lines.append("".join(fragments))
                fragments = []
        logical_lines.append("".join(fragments))
        for logical_line in logical_lines:
            for text in re.split(r"[\u2028\u2029]", logical_line):
                text = text.strip()
                if text:
                    paragraphs.append(text)
    return paragraphs


def read_paragraphs(path: Path) -> list[str]:
    if path.suffix.lower() == ".docx":
        return docx_paragraphs(path)
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def normalize_markdown_structure(text: str) -> str:
    """Remove Markdown wrappers only for structural matching.

    Keep the original paragraph as the extracted source text. This lets .md
    scripts use headings such as ``# 第1集`` / ``## 1-1 地点`` and bold meta
    labels without changing dialogue or visual facts in the coverage ledger.
    """
    value = re.sub(r"^#{1,6}\s+", "", text).strip()
    if value.startswith("**") and value.endswith("**") and len(value) > 4:
        value = value[2:-2].strip()
    value = re.sub(r"^\*\*([^*]+)\*\*([：:].*)$", r"\1\2", value)
    return value


def classify(text: str) -> str:
    if SFX_MARK_RE.match(text):
        return "sfx"
    if VISUAL_PREFIX_RE.match(text):
        return "visual"
    if UI_PANEL_RE.match(text):
        return "ui"
    if BRACKET_LINE_RE.match(text):
        return "note"
    return ""


VISUAL_KINDS = ("visual", "subtitle", "sfx", "note", "ui")
VOICE_KINDS = ("dialogue",)


def extract(
    paragraphs: list[str],
    episode: int | None,
    kinds: tuple[str, ...] = VISUAL_KINDS,
) -> list[dict[str, object]]:
    units: list[dict[str, object]] = []
    current_episode: int | None = None
    current_scene = ""
    awaiting_first_scene = False
    for text in paragraphs:
        structural_text = normalize_markdown_structure(text)
        episode_match = EPISODE_RE.match(structural_text)
        if episode_match:
            parsed = parse_episode_number(episode_match.group(1))
            if parsed is None:
                continue
            current_episode = parsed
            current_scene = ""
            awaiting_first_scene = True
            continue
        scene_match = SCENE_RE.match(structural_text)
        if scene_match:
            scene_episode = int(scene_match.group(1))
            if awaiting_first_scene and current_episode != scene_episode:
                current_episode = scene_episode
            current_scene = structural_text
            awaiting_first_scene = False
            continue
        awaiting_first_scene = False
        if episode is not None and current_episode != episode:
            continue
        if (
            META_LINE_RE.match(structural_text)
            or BRACKET_CAST_META_RE.match(structural_text)
        ):
            continue
        if SCRIPT_DIALOGUE_LINE_RE.match(structural_text):
            # 台词行同样入库（kind=dialogue），供语音对账对源；
            # 默认输出只含画面类，画面对账的条数不受影响。
            units.append(
                {
                    "episode": current_episode,
                    "scene": current_scene,
                    "kind": "dialogue",
                    "text": structural_text,
                }
            )
            continue

        # 一条画面行里内嵌的【字幕：…】是独立任务（后期叠字），单独成行；
        # 否则它永远拿不到自己的对账行，正是 EP1 三处字幕丢失的形状。
        subtitles = SUBTITLE_RE.findall(text)
        remainder = SUBTITLE_RE.sub("", text).strip()
        kind = classify(remainder if remainder else text)
        if remainder and kind:
            units.append(
                {
                    "episode": current_episode,
                    "scene": current_scene,
                    "kind": kind,
                    "text": remainder,
                }
            )
        for subtitle in subtitles:
            units.append(
                {
                    "episode": current_episode,
                    "scene": current_scene,
                    "kind": "subtitle",
                    "text": f"【字幕：{subtitle}】",
                }
            )
    selected = [unit for unit in units if unit["kind"] in kinds]
    for index, unit in enumerate(selected, start=1):
        unit["index"] = index
    return selected


def render_table(units: list[dict[str, object]]) -> str:
    lines = [
        "## 画面对账",
        "",
        "| 序号 | 类型 | 原剧本画面指令 | 落点 | 处置 |",
        "|---|---|---|---|---|",
    ]
    for unit in units:
        text = str(unit["text"]).replace("|", "｜")
        lines.append(f"| {unit['index']} | {unit['kind']} | {text} |  |  |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path, help="原剧本 .docx / .txt / .md")
    parser.add_argument("--episode", type=int, help="只抽取指定集号")
    parser.add_argument(
        "--format", choices=("json", "table", "count"), default="json"
    )
    parser.add_argument(
        "--kind",
        choices=("visual", "voice", "all"),
        default="visual",
        help="visual=画面/字幕/音效（画面对账用）；voice=台词（语音对账用）",
    )
    args = parser.parse_args()
    try:
        paragraphs = read_paragraphs(args.script)
    except (OSError, KeyError, zipfile.BadZipFile, UnicodeError, ET.ParseError) as exc:
        print(f"ERROR: 无法读取剧本：{exc}", file=sys.stderr)
        return 1
    kinds = {
        "visual": VISUAL_KINDS,
        "voice": VOICE_KINDS,
        "all": VISUAL_KINDS + VOICE_KINDS,
    }[args.kind]
    units = extract(paragraphs, args.episode, kinds)
    if not units:
        print("ERROR: 没有抽到任何画面单元，请确认集号与剧本格式", file=sys.stderr)
        return 1
    if args.format == "count":
        print(len(units))
    elif args.format == "table":
        print(render_table(units))
    else:
        print(json.dumps(units, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
