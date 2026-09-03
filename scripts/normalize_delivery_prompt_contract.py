#!/usr/bin/env python3
"""Normalize TVSkill delivery prompts for Seedance 2.0 reference and subject contracts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SEGMENT_RE = re.compile(r"^## 生成段 (V\d{2})｜", re.M)
PROMPT_RE = re.compile(r"```text\n(.*?)\n```", re.S)
MIXED_ROW_RE = re.compile(
    r"^\| Mixed (\d+) \|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$",
    re.M,
)
REF_RE = re.compile(r"@\[(?P<label>[^\]]+)\]\s*\{\{Mixed\s+(?P<number>\d+)\}\}")
ROLE_DEF_RE = re.compile(
    r"将 @\[角色-(?P<label>[^\]]+)\] \{\{Mixed \d+\}\}.*?定义为 <主体(?P<number>\d+)>"
)
AUDIO_DEF_RE = re.compile(
    r"@\[音色-(?P<label>[^\]]+)\] \{\{Mixed \d+\}\} 只控制 <主体(?P<number>\d+)>"
)
SHOT_RE = re.compile(r"^Shot \d+:.*$", re.M)

# Props that carry plot information. Ordinary furniture, drinks, luggage
# dressing, vehicles, lighting props, and crowd phones stay in scene states.
PROP_FAMILIES = {
    "phone": ("手机|电话|拨通|接听|免提|短信|来电|关机|振动|划开|拉黑|录音", "手机|电话|通话|拨号|短信|录音"),
    "document": ("协议|承诺书|催收函|判决|通报|文书|红头文件|证据照片|条款|签字|签名|读出来|写着", "协议|承诺书|催收函|判决|通报|文书|文件|证据|条款"),
    "needle": ("针管|针头|袖口|注射|扎入|扎向|刺入|刺向", "针管|针头|袖口"),
    "handcuff": ("手铐|铐", "手铐|铐"),
    "glasses": ("眼镜|镜片|镜子碎片|断腿", "眼镜|镜片|镜子"),
    "pen": ("派克笔|圆珠笔|签字笔|油墨|笔尖", "笔|油墨"),
    "luggage": ("行李箱|行李|打包|搬离|搬家", "行李箱|行李|打包|搬"),
}


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value).strip()


def prop_family(asset: str) -> tuple[str, re.Pattern[str], re.Pattern[str]] | None:
    stem = asset.removeprefix("定版道具图-")
    if "路人手机" in stem:
        return None
    for family, (shot_pattern, specific_pattern) in PROP_FAMILIES.items():
        if re.search(specific_pattern, stem):
            return family, re.compile(shot_pattern), re.compile(specific_pattern)
    return None


def replace_outside_braces(text: str, replacements: list[tuple[str, str]]) -> str:
    parts = re.split(r"(\{[^{}]*\})", text)
    for index, part in enumerate(parts):
        if part.startswith("{") and part.endswith("}"):
            continue
        for source, target in replacements:
            part = part.replace(source, target)
        parts[index] = part
    return "".join(parts)


def subject_replacements(prompt: str) -> tuple[list[tuple[str, str]], dict[str, str]]:
    mapping: dict[str, str] = {}
    canonical_by_role: dict[str, str] = {}
    for match in ROLE_DEF_RE.finditer(prompt):
        label = match.group("label")
        subject = f"<主体{match.group('number')}>"
        base = label.split("-", 1)[0]
        mapping[label] = subject
        mapping[base] = subject
        canonical_by_role.setdefault(base, subject)
    for match in AUDIO_DEF_RE.finditer(prompt):
        label = match.group("label")
        subject = f"<主体{match.group('number')}>"
        # A voice line can carry a stale subject number after an earlier
        # split.  If the same role already has an identity definition, use
        # that canonical token instead of creating a second subject alias.
        mapping[label] = canonical_by_role.get(label.split("-", 1)[0], subject)
    aliases = {
        "吴父": "吴志远", "吴志远-电话音": "吴志远", "李琴": "江琴",
        "律师乙": "律师", "吴馨 OS": "吴馨", "吴馨OS": "吴馨",
        "李承 OS": "李承", "黑手": "电话威胁声", "黑手-电话音": "电话威胁声",
        "视频中的男人": "视频认罪声", "物业音": "物业广播声",
        "办事处来电音": "办事处通知声", "画外音": "吴志远",
    }
    for source, target in aliases.items():
        if target in mapping:
            mapping[source] = mapping[target]
    replacements = sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True)
    return replacements, mapping


def canonical_subject_roles(prompt: str) -> dict[str, str]:
    """Return the role name declared by each subject token.

    Alias rewrites (for example ``吴馨 OS``) are useful when normalizing Shot
    prose, but they must not replace the canonical role used to decide which
    identity images remain in a segment.  Keep this map sourced only from the
    explicit role-definition lines and preserve the first declaration.
    """
    roles: dict[str, str] = {}
    for match in ROLE_DEF_RE.finditer(prompt):
        subject = f"<主体{match.group('number')}>"
        roles.setdefault(subject, match.group("label").split("-", 1)[0])
    for match in AUDIO_DEF_RE.finditer(prompt):
        subject = f"<主体{match.group('number')}>"
        roles.setdefault(subject, match.group("label").split("-", 1)[0])
    return roles


def canonical_subject_tokens(prompt: str) -> dict[str, str]:
    """Map duplicate subject tokens for one role to its identity token."""
    role_subject: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for match in ROLE_DEF_RE.finditer(prompt):
        role = match.group("label").split("-", 1)[0]
        subject = f"<主体{match.group('number')}>"
        role_subject.setdefault(role, subject)
        aliases[subject] = role_subject[role]
    for match in AUDIO_DEF_RE.finditer(prompt):
        role = match.group("label").split("-", 1)[0]
        subject = f"<主体{match.group('number')}>"
        aliases[subject] = role_subject.get(role, subject)
    return {old: new for old, new in aliases.items() if old != new}


def remap_mixed_rows(block: str, drop_assets: set[str]) -> tuple[str, set[str]]:
    matches = list(MIXED_ROW_RE.finditer(block))
    rows: list[tuple[int, str, str, str]] = []
    old_to_new: dict[int, int] = {}
    dropped_semantics: set[str] = set()
    seen_rows: dict[tuple[str, str, str], int] = {}
    next_number = 1
    for match in matches:
        old_number = int(match.group(1))
        asset, media_type, semantic = (value.strip() for value in match.groups()[1:])
        if asset in drop_assets:
            dropped_semantics.add(semantic.removeprefix("@[").removesuffix("]"))
            continue
        key = (asset, media_type, semantic)
        if key in seen_rows:
            old_to_new[old_number] = seen_rows[key]
            continue
        seen_rows[key] = next_number
        old_to_new[old_number] = next_number
        rows.append((next_number, asset, media_type, semantic))
        next_number += 1
    if not matches:
        return block, set()
    first, last = matches[0].start(), matches[-1].end()
    table = "\n".join(
        f"| Mixed {number} | {asset} | {media_type} | {semantic} |"
        for number, asset, media_type, semantic in rows
    )
    block = block[:first] + table + block[last:]
    if dropped_semantics:
        lines = []
        for line in block.splitlines():
            if any(f"@[{semantic}]" in line and "{{Mixed" in line for semantic in dropped_semantics):
                continue
            lines.append(line)
        block = "\n".join(lines)

    by_semantic = {
        semantic.removeprefix("@[").removesuffix("]"): number
        for number, _asset, _media_type, semantic in rows
    }

    def replace_ref(match: re.Match[str]) -> str:
        label = match.group("label")
        number = by_semantic.get(label)
        if number is None:
            return match.group(0)
        return f"@[{label}] {{{{Mixed {number}}}}}"

    block = REF_RE.sub(replace_ref, block)
    return block, {asset for _number, asset, _type, _semantic in rows if asset.startswith("定版道具图-")}


def normalize_segment(block: str) -> tuple[str, dict[str, object]]:
    prompt_match = PROMPT_RE.search(block)
    if not prompt_match:
        raise ValueError("segment missing text prompt block")
    prompt = prompt_match.group(1)
    shot_region = prompt.split("【声音设计】", 1)[0]
    shot_text = "\n".join(SHOT_RE.findall(shot_region))
    drop_assets: set[str] = set()
    for match in MIXED_ROW_RE.finditer(block):
        asset, media_type = match.group(2).strip(), match.group(3).strip()
        if "图片" not in media_type or not asset.startswith("定版道具图-"):
            continue
        family = prop_family(asset)
        if family is None or not family[1].search(shot_text):
            drop_assets.add(asset)

    # Scene-state images carry background people. Keep only characters who
    # speak or are explicitly visible in a Shot; this prevents a whole-cast
    # identity bundle from consuming the Seedance reference budget.
    replacements, subject_map = subject_replacements(prompt)
    reverse_subjects = canonical_subject_roles(prompt)
    active_names = set()
    for line in SHOT_RE.findall(shot_region):
        outside = re.sub(r"\{[^{}]*\}", "", line)
        active_names.update(
            name for name in subject_map
            if name and name not in {"电话威胁声", "视频认罪声", "办事处通知声", "物业广播声", "系统提示音"}
            and name in outside
        )
        for subject in re.findall(r"<主体\d+>", outside):
            role = reverse_subjects.get(subject)
            if role:
                active_names.add(role)
    for match in MIXED_ROW_RE.finditer(block):
        asset, media_type = match.group(2).strip(), match.group(3).strip()
        if "图片" not in media_type or not asset.startswith("独立身份图-"):
            continue
        role = asset.removeprefix("独立身份图-").split("-", 1)[0]
        if role not in active_names:
            drop_assets.add(asset)

    rewritten, kept_props = remap_mixed_rows(block, drop_assets)
    prompt_match = PROMPT_RE.search(rewritten)
    assert prompt_match
    prompt = prompt_match.group(1)
    token_aliases = canonical_subject_tokens(prompt)
    if token_aliases:
        prompt = re.sub(
            r"<主体\d+>",
            lambda match: token_aliases.get(match.group(0), match.group(0)),
            prompt,
        )
    replacements, mapping = subject_replacements(prompt)
    lines = []
    for line in prompt.splitlines():
        if line.startswith("Shot "):
            line = replace_outside_braces(line, replacements)
        lines.append(line)
    prompt = "\n".join(lines)
    # Compact the surviving subject tokens once, after all alias rewrites, so
    # every definition, Shot and audio binding shares one stable numbering.
    subject_tokens = list(dict.fromkeys(re.findall(r"<主体\d+>", prompt)))
    compact = {old: f"<主体{index}>" for index, old in enumerate(subject_tokens, start=1)}
    for old, new in compact.items():
        prompt = prompt.replace(old, new)
    if "主体标签锁定：" not in prompt:
        prompt = (
            "主体标签锁定：本段仅使用 <主体N>；角色名和服装状态只保留在参考语义与台词原文中。\n"
            + prompt.lstrip()
        )
    rewritten = rewritten[:prompt_match.start(1)] + prompt + rewritten[prompt_match.end(1):]
    text_strategy = re.search(r"^- 文字策略：(定版道具图|无画面文字|后期叠字)$", rewritten, re.M)
    if text_strategy and text_strategy.group(1) == "定版道具图" and not kept_props:
        rewritten = rewritten.replace("- 文字策略：定版道具图", "- 文字策略：无画面文字", 1)
    rows = list(MIXED_ROW_RE.finditer(rewritten))
    total = len(rows)
    images = sum("图片" in m.group(3) for m in rows)
    audio = sum("音频" in m.group(3) for m in rows)
    kept_characters = sorted(
        asset.removeprefix("独立身份图-")
        for asset in (
            match.group(2).strip()
            for match in MIXED_ROW_RE.finditer(rewritten)
        )
        if asset.startswith("独立身份图-")
    )
    return rewritten, {
        "kept_props": sorted(kept_props),
        "kept_characters": kept_characters,
        "subjects": mapping,
        "references_total": total,
        "references_images": images,
        "references_audio": audio,
        "over_budget": total > 12 or images > 9 or audio > 3,
    }


def prune_asset_section(text: str, kept_props: set[str]) -> str:
    start = text.find("## 资产清单")
    if start < 0:
        return text
    next_heading = re.search(r"^##\s+", text[start + len("## 资产清单"):], re.M)
    end = start + len("## 资产清单") + (next_heading.start() if next_heading else len(text[start + len("## 资产清单"):]))
    section = text[start:end]
    out = []
    for line in section.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        match = re.match(r"^\| 道具 \| ([^|]+) \|", content)
        if match and f"定版道具图-{match.group(1).strip()}" not in kept_props:
            continue
        out.append(line)
    section_text = "".join(out)
    # The state machine requires all four asset categories to be explicit.
    # When every standalone prop is correctly moved into the scene state,
    # retain a truthful category row instead of making the category disappear.
    if not re.search(r"^\| 道具 \|", section_text, re.M):
        marker = (
            "| 道具 | 无独立剧情道具 | 由场景图承担 | "
            "普通陈设、背景设备和非核心道具不单独进入 Mixed |\n"
        )
        section_text = section_text.rstrip("\n") + "\n" + marker
    return text[:start] + section_text + text[end:]


def normalize_document(path: Path) -> dict[str, object]:
    original = path.read_text(encoding="utf-8")
    headings = list(SEGMENT_RE.finditer(original))
    pieces: list[str] = []
    cursor = 0
    reports = []
    all_kept_props: set[str] = set()
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(original)
        block = original[heading.start():end]
        transformed, report = normalize_segment(block)
        pieces.append(original[cursor:heading.start()])
        pieces.append(transformed)
        cursor = end
        report["segment"] = heading.group(1)
        reports.append(report)
        all_kept_props.update(report["kept_props"])
    pieces.append(original[cursor:])
    transformed = "".join(pieces)
    transformed = transformed.replace("场景状态图承担普通陈设和非核心道具", "场景状态图承担普通陈设和非核心道具")
    transformed = prune_asset_section(transformed, all_kept_props)
    return {"path": str(path), "changed": transformed != original, "text": transformed, "segments": reports, "kept_props": sorted(all_kept_props)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    docs = sorted(args.project.glob("EP*-LibTV视频节点提示词.md"))
    if not docs:
        raise SystemExit("no episode Markdown files found")
    reports = []
    over_budget = []
    for path in docs:
        result = normalize_document(path)
        if result["changed"] and not args.check:
            path.write_text(result["text"], encoding="utf-8")
        for segment in result["segments"]:
            if segment["over_budget"]:
                over_budget.append({"file": path.name, **segment})
        reports.append({k: v for k, v in result.items() if k != "text"})
    summary = {
        "documents": len(docs),
        "changed_documents": sum(item["changed"] for item in reports),
        "over_budget_segments": len(over_budget),
        "over_budget": over_budget,
        "check_only": args.check,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if over_budget else 0


if __name__ == "__main__":
    raise SystemExit(main())
