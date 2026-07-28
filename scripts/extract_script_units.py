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
import zipfile
from pathlib import Path


EPISODE_RE = re.compile(r"^第\s*(\d+)\s*集\s*$")
SCENE_RE = re.compile(r"^(\d+)-(\d+)\s+(.+)$")
SUBTITLE_RE = re.compile(r"【字幕[：:]([^】]*)】")
UI_PANEL_RE = re.compile(
    r"^【(?:第[^】]*任务|目标[：:]|任务时限|系统提示|检测到|.*好感度)[^】]*】$"
)
SFX_MARK_RE = re.compile(r"^△\s*【音效】")
VISUAL_PREFIX_RE = re.compile(r"^△")
BRACKET_LINE_RE = re.compile(r"^【([^】]*)】$")
DIALOGUE_RE = re.compile(r"^[^△【\s][^：:]{0,12}(?:VO)?(?:（[^）]*）)?[：:]")


def docx_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    paragraphs = []
    for block in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        text = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", block, re.S))
        text = re.sub(r"<[^>]+>", "", text)
        text = (
            text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        ).strip()
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


def extract(paragraphs: list[str], episode: int | None) -> list[dict[str, object]]:
    units: list[dict[str, object]] = []
    current_episode: int | None = None
    current_scene = ""
    for text in paragraphs:
        episode_match = EPISODE_RE.match(text)
        if episode_match:
            current_episode = int(episode_match.group(1))
            current_scene = ""
            continue
        scene_match = SCENE_RE.match(text)
        if scene_match:
            current_scene = text
            continue
        if episode is not None and current_episode != episode:
            continue
        if DIALOGUE_RE.match(text):
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
    for index, unit in enumerate(units, start=1):
        unit["index"] = index
    return units


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
    args = parser.parse_args()
    try:
        paragraphs = read_paragraphs(args.script)
    except (OSError, KeyError, zipfile.BadZipFile, UnicodeError) as exc:
        print(f"ERROR: 无法读取剧本：{exc}", file=sys.stderr)
        return 1
    units = extract(paragraphs, args.episode)
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
