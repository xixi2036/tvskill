#!/usr/bin/env python3
"""从时间码体标准剧本的场次声明行，抽出资产清单草稿（人物/场景/道具）。

时间码体剧本每场自带结构化声明：

    场景 1　外　日　荒野战场  00:00-00:44
    人物：姜月初(破烂粗布衣)、裴长青(重伤官服)　　道具：虎妖尸体、破损囚车

这两行已经包含 `references/v3/02-entity-extraction.md` 要的三个关键维度：
角色的**形态**（括号内状态）、场景的**内外/日夜/人数状态**、道具的**出场场次**。
此前这两行被解析器当作元信息整行跳过，信息全部丢弃，`entities` 步要人重新誊一遍。

本脚本只产出**草稿**，不产出结论：
- 剧本没写的字段（canonical 外观、空间拓扑、主光源、音色需求）一律留空并标 `待填`，
  因为这些剧本里根本没有，凭空补就是发明。
- 合同要求「形态是资产的单位，不是角色」，故同一角色的不同括号状态**各算一份资产**。
- 合同要求「同一空间的不同人数状态是独立资产」，故同一地点按人数分列状态。

用法：
    python3 scripts/extract_script_entities.py <剧本.docx 或 .md> [--json]

▲ 体剧本（无 `场景 N` 声明行）会得到空草稿并给出提示，不报错——
那类剧本的实体只能靠通读正文提取，不在本脚本职责内。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import extract_script_units as units_mod  # noqa: E402


# 场景 1　外　日　荒野战场  00:00-00:44   （全角空格分隔，时间区间可缺）
SCENE_DECL_RE = re.compile(
    r"^场景\s*(?P<no>[0-9〇零一二三四五六七八九十百]+)"
    r"[\s　]+(?P<io>[内外])"
    r"[\s　]+(?P<tod>[^\s　]+)"
    r"[\s　]+(?P<place>[^\s　]+)"
    r"(?:[\s　]+(?P<span>\d{1,3}:\d{2}\s*[-–—]\s*\d{1,3}:\d{2}))?"
)
# 人物：A(状态)、B(状态)　　道具：X、Y     两段同行，段间是全角空格
CAST_DECL_RE = re.compile(r"人物\s*[：:]\s*(?P<cast>[^　\n]*)")
PROP_DECL_RE = re.compile(r"道具\s*[：:]\s*(?P<props>[^　\n]*)")
# 姜月初(破烂粗布衣) / 虎山神（半步鸣骨境） / 裴长青
MEMBER_RE = re.compile(r"^(?P<name>[^(（]+)(?:[(（](?P<state>[^)）]*)[)）])?$")
NONE_TOKENS = {"无", "无。", "none", "None", "—", "-"}


def split_members(value: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for raw in re.split(r"[、,，]\s*", value.strip()):
        item = raw.strip()
        if not item or item in NONE_TOKENS:
            continue
        match = MEMBER_RE.match(item)
        if not match:
            out.append((item, ""))
            continue
        out.append((match.group("name").strip(), (match.group("state") or "").strip()))
    return out


def parse_span(span: str | None) -> tuple[int | None, int | None]:
    if not span:
        return None, None
    parts = re.split(r"\s*[-–—]\s*", span)
    if len(parts) != 2:
        return None, None
    seconds = []
    for part in parts:
        mm, ss = part.split(":")
        seconds.append(int(mm) * 60 + int(ss))
    return seconds[0], seconds[1]


def collect(paragraphs: list[str]) -> dict[str, Any]:
    scenes: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in paragraphs:
        text = raw.strip()
        if not text:
            continue
        scene_match = SCENE_DECL_RE.match(text)
        if scene_match:
            start, end = parse_span(scene_match.group("span"))
            current = {
                "no": scene_match.group("no"),
                "interiorExterior": scene_match.group("io"),
                "timeOfDay": scene_match.group("tod"),
                "place": scene_match.group("place"),
                "startSec": start,
                "endSec": end,
                "cast": [],
                "props": [],
                # 「没写人物行」与「人物：无」是两件事：
                # 前者是声明缺失（正文里可能真有人），后者是已核对的零。
                # 混为一谈会静默漏资产——真实样本 01-第01集 场景2 牡丹园没有人物行，
                # 但正文写着「穿着华丽红色汉服的姜月初」，那是姜月初的第二个形态。
                "castDeclared": False,
                "propsDeclared": False,
            }
            scenes.append(current)
            continue
        if current is None:
            continue
        cast_match = CAST_DECL_RE.search(text)
        prop_match = PROP_DECL_RE.search(text)
        if cast_match:
            current["cast"] = split_members(cast_match.group("cast"))
            current["castDeclared"] = True
        if prop_match:
            current["props"] = [name for name, _ in split_members(prop_match.group("props"))]
            current["propsDeclared"] = True
    return {"scenes": scenes}


def build_draft(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    # 角色 × 形态：合同规定形态是资产单位，同一角色两个状态 = 两份资产
    characters: dict[str, dict[str, Any]] = {}
    for scene in scenes:
        for name, state in scene["cast"]:
            entry = characters.setdefault(
                name, {"name": name, "forms": {}, "scenes": []}
            )
            entry["scenes"].append(scene["no"])
            form = state or "（剧本未注明状态）"
            entry["forms"].setdefault(form, []).append(scene["no"])

    # 场景状态：同一地点按「内外 + 日夜 + 人数」分状态，人数不同即独立资产
    places: dict[str, dict[str, Any]] = {}
    for scene in scenes:
        key = scene["place"]
        entry = places.setdefault(key, {"place": key, "states": {}})
        if scene["castDeclared"]:
            state_key = (
                f"{scene['interiorExterior']}·{scene['timeOfDay']}·{len(scene['cast'])}人"
            )
        else:
            # 声明缺失不等于零人：不得据此生成「0人场景资产」，
            # 否则正文里真实在场的角色（及其形态）会被静默漏掉。
            state_key = (
                f"{scene['interiorExterior']}·{scene['timeOfDay']}·人数未声明⚠需通读正文"
            )
        entry["states"].setdefault(state_key, []).append(scene["no"])

    props: dict[str, list[str]] = {}
    for scene in scenes:
        for prop in scene["props"]:
            props.setdefault(prop, []).append(scene["no"])

    return {
        "characters": [
            {
                "name": c["name"],
                "sceneCount": len(c["scenes"]),
                "forms": [
                    {"form": form, "scenes": scs, "assetUnit": True}
                    for form, scs in c["forms"].items()
                ],
                "canonicalLook": "待填（剧本未给发型/面部/体型）",
                "voiceSlot": "待填（需按台词判定是否必须绑音色）",
            }
            for c in characters.values()
        ],
        "scenes": [
            {
                "place": p["place"],
                "states": [
                    {"state": state, "scenes": scs, "assetUnit": True}
                    for state, scs in p["states"].items()
                ],
                "topology": "待填（剧本未给出入口/家具朝向/功能前方）",
                "keyLight": "待填（剧本未给主光源方向与色温）",
            }
            for p in places.values()
        ],
        "props": [
            {"name": name, "scenes": scs, "narrativeRole": "待确认是否承担叙事功能"}
            for name, scs in props.items()
        ],
    }


def render(draft: dict[str, Any], scenes: list[dict[str, Any]]) -> str:
    lines = ["## 资产清单草稿（自剧本场次声明行抽取）", ""]
    lines.append(f"- 场次数：{len(scenes)}")
    undeclared = [s["no"] for s in scenes if not s["castDeclared"]]
    if undeclared:
        lines.append(
            f"- ⚠ **场次 {'、'.join(undeclared)} 没有人物声明行**——这不等于该场无人。"
            "必须通读这几场的正文补齐在场角色；漏掉的往往是同一角色的**另一套形态**"
            "（真实样本：某集牡丹园场无人物行，正文里是「华丽红色汉服的姜月初」，"
            "与其他场的「破烂粗布衣」是两份独立资产）。"
        )
    lines.append(
        "- 本草稿只搬运剧本已写明的内容；标「待填」的字段剧本没有，"
        "必须人工补齐或向用户确认，不得自行发明。"
    )
    lines.append("")

    lines += ["### 人物", "", "| 角色 | 形态（每个形态 = 一份独立资产） | 出场场次 | canonical 外观 | 音色 |", "|---|---|---|---|---|"]
    if not draft["characters"]:
        lines.append("| 无（已核对：剧本场次声明行未列人物） | — | — | — | — |")
    for c in draft["characters"]:
        for form in c["forms"]:
            lines.append(
                f"| {c['name']} | {form['form']} | {'、'.join(form['scenes'])} "
                f"| {c['canonicalLook']} | {c['voiceSlot']} |"
            )
    lines.append("")

    lines += ["### 场景", "", "| 地点 | 状态（内外·日夜·人数，每个状态 = 一份独立资产） | 出场场次 | 空间拓扑 | 主光源 |", "|---|---|---|---|---|"]
    if not draft["scenes"]:
        lines.append("| 无（已核对） | — | — | — | — |")
    for s in draft["scenes"]:
        for state in s["states"]:
            lines.append(
                f"| {s['place']} | {state['state']} | {'、'.join(state['scenes'])} "
                f"| {s['topology']} | {s['keyLight']} |"
            )
    lines.append("")

    lines += ["### 道具", "", "| 道具 | 出场场次 | 叙事功能 |", "|---|---|---|"]
    if not draft["props"]:
        lines.append("| 无（已核对：剧本场次声明行未列道具） | — | — |")
    for p in draft["props"]:
        lines.append(f"| {p['name']} | {'、'.join(p['scenes'])} | {p['narrativeRole']} |")
    lines.append("")

    lines += [
        "### 色卡",
        "",
        "| 逻辑场 | 色卡 | 说明 |",
        "|---|---|---|",
        "| 待填 | 待填 | 剧本不提供色彩信息，须按 LOOK-ID 与场景定调另行登记 |",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.script.suffix.lower() == ".docx":
            paragraphs = units_mod.docx_paragraphs(args.script)
        else:
            paragraphs = args.script.read_text(encoding="utf-8").splitlines()
        collected = collect(paragraphs)
        scenes = collected["scenes"]
        if not scenes:
            print(
                "没有找到 `场景 N　内/外　时段　地点` 声明行——"
                "本脚本只处理时间码体标准剧本；▲ 体剧本的实体须通读正文提取。",
                file=sys.stderr,
            )
            return 1
        draft = build_draft(scenes)
        if args.json:
            print(json.dumps({"scenes": scenes, "draft": draft}, ensure_ascii=False, indent=2))
        else:
            print(render(draft, scenes))
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
