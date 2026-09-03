#!/usr/bin/env python3
"""Split the few TVSkill segments that exceed Seedance's three-audio limit."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


SEGMENT_RE = re.compile(r"^## 生成段 (V\d{2})｜", re.M)
PROMPT_RE = re.compile(r"```text\n(.*?)\n```", re.S)
MIXED_ROW_RE = re.compile(
    r"^\| Mixed (\d+) \|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$",
    re.M,
)
SHOT_RE = re.compile(r"^Shot (\d+):.*$", re.M)
ROLE_DEF_RE = re.compile(r"将 @\[角色-(?P<label>[^\]]+)\] \{\{Mixed \d+\}\}.*?定义为 <主体(?P<number>\d+)>")
AUDIO_DEF_RE = re.compile(r"@\[音色-(?P<label>[^\]]+)\] \{\{Mixed \d+\}\} 只控制 <主体(?P<number>\d+)>")

SPLITS = {
    ("EP06", "V04"): ([1, 2, 3], [4, 5], [8, 4]),
    ("EP10", "V02"): ([1, 2, 3], [4, 5], [8, 4]),
    ("EP10", "V03"): ([1, 2, 3], [4, 5], [8, 4]),
    ("EP12", "V04"): ([1, 2, 3], [4, 5], [8, 4]),
}


def selected_assets(prompt: str, rows: list[dict[str, str]], shot_numbers: list[int]) -> set[str]:
    shots = {int(match.group(1)): match.group(0) for match in SHOT_RE.finditer(prompt)}
    shot_text = "\n".join(shots[number] for number in shot_numbers)
    role_subjects = {f"<主体{m.group('number')}>": m.group('label') for m in ROLE_DEF_RE.finditer(prompt)}
    audio_subjects = {f"<主体{m.group('number')}>": m.group('label') for m in AUDIO_DEF_RE.finditer(prompt)}
    active_subjects = set(re.findall(r"<主体\d+>", shot_text))
    active_roles = {role_subjects[s] for s in active_subjects if s in role_subjects}
    active_audio = {audio_subjects[s] for s in active_subjects if s in audio_subjects}
    # Action-only Shots may name the character directly rather than using its
    # subject token. Keep that character reference in the split clip.
    for role in set(role_subjects.values()):
        base = role.split("-", 1)[0]
        if base in re.sub(r"\{[^{}]*\}", "", shot_text):
            active_roles.add(role)
    active_role_bases = {role.split("-", 1)[0] for role in active_roles}
    keep: set[str] = set()
    for row in rows:
        asset = row["asset"]
        media = row["media"]
        semantic = row["semantic"]
        label = semantic.removeprefix("@[").removesuffix("]")
        if asset.startswith("独立身份图-"):
            role = asset.removeprefix("独立身份图-").split("-", 1)[0]
            if role in active_roles or role in active_role_bases:
                keep.add(asset)
        elif asset.startswith("独立音色-"):
            if asset.removeprefix("独立音色-") in active_audio:
                keep.add(asset)
        elif asset.startswith("场景状态-") or asset.startswith("色卡-"):
            keep.add(asset)
        elif asset.startswith("定版道具图-"):
            # The later prop pass applies the stricter core-prop rule. Keep a
            # prop here only if its visible noun occurs in this shot group.
            stem = asset.removeprefix("定版道具图-")
            if re.search(r"手机|电话|协议|承诺书|催收函|判决|通报|文书|证据|手铐|针管|针头|眼镜|镜片|笔|油墨|行李", stem) and re.search(
                r"手机|电话|拨通|接听|免提|短信|来电|关机|振动|划开|拉黑|协议|承诺书|催收函|判决|通报|文书|证据|手铐|铐|针管|针头|袖口|眼镜|镜片|镜子|笔|油墨|行李|打包|搬离|搬家|签|签字|签名|写",
                shot_text,
            ):
                keep.add(asset)
    return keep


def normalize_prompt(prompt: str, rows: list[dict[str, str]], shot_numbers: list[int]) -> tuple[str, list[dict[str, str]]]:
    shots = {int(match.group(1)): match.group(0) for match in SHOT_RE.finditer(prompt)}
    keep = selected_assets(prompt, rows, shot_numbers)
    selected_rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        if row["asset"] not in keep:
            continue
        key = (row["asset"], row["media"], row["semantic"])
        if key in seen:
            continue
        seen.add(key)
        selected_rows.append(dict(row))
    for number, row in enumerate(selected_rows, start=1):
        row["number"] = str(number)
    by_semantic = {row["semantic"].removeprefix("@[").removesuffix("]"): row["number"] for row in selected_rows}

    start = prompt.find("Shot 1:")
    sound = prompt.find("【声音设计】")
    if start < 0 or sound < 0:
        raise ValueError("prompt missing Shot or sound design section")
    prefix = prompt[:start]
    # Remove definitions whose source asset is not present in this split.
    kept_semantics = set(by_semantic)
    prefix_lines = []
    for line in prefix.splitlines():
        m = re.search(r"@\[[^\]]+\] \{\{Mixed \d+\}\}", line)
        if m:
            label = m.group(0).split("@[", 1)[1].split("]", 1)[0]
            if label not in kept_semantics and not label.startswith(("角色-", "音色-", "场景状态-", "色卡-", "道具-")):
                pass
            if label not in kept_semantics:
                continue
        prefix_lines.append(line)
    selected_shots = []
    for new_number, old_number in enumerate(shot_numbers, start=1):
        line = shots[old_number]
        line = re.sub(r"^Shot \d+:", f"Shot {new_number}:", line)
        selected_shots.append(line)
    prompt = "\n".join(prefix_lines).rstrip() + "\n\n" + "\n".join(selected_shots) + "\n\n" + prompt[sound:]

    def remap_ref(match: re.Match[str]) -> str:
        label = match.group("label")
        number = by_semantic.get(label)
        if number is None:
            return match.group(0)
        return f"@[{label}] {{{{Mixed {number}}}}}"

    prompt = re.sub(r"@\[(?P<label>[^\]]+)\]\s*\{\{Mixed \d+\}\}", remap_ref, prompt)
    subject_tokens = list(dict.fromkeys(re.findall(r"<主体\d+>", prompt)))
    subject_map = {old: f"<主体{index}>" for index, old in enumerate(subject_tokens, start=1)}
    for old, new in subject_map.items():
        prompt = prompt.replace(old, new)
    return prompt, selected_rows


def build_block(block: str, episode: str, new_number: int, shot_numbers: list[int], duration: int) -> str:
    prompt_match = PROMPT_RE.search(block)
    if not prompt_match:
        raise ValueError("split source lacks prompt")
    rows = [
        {"number": number, "asset": asset.strip(), "media": media.strip(), "semantic": semantic.strip()}
        for number, asset, media, semantic in MIXED_ROW_RE.findall(block)
    ]
    prompt, selected_rows = normalize_prompt(prompt_match.group(1), rows, shot_numbers)
    heading = re.sub(r"^## 生成段 V\d{2}｜", f"## 生成段 V{new_number:02d}｜", block.splitlines()[0])
    before_mixed = block[: block.find("### Mixed 上传顺序")]
    before_mixed = re.sub(r"^- 段号：.+$", f"- 段号：{episode}-S{new_number:02d}", before_mixed, flags=re.M)
    before_mixed = re.sub(r"^- 时长：\d+秒$", f"- 时长：{duration}秒", before_mixed, flags=re.M)
    before_mixed = re.sub(
        r"^- 前置段：.+$",
        f"- 前置段：{episode}-V{new_number - 1:02d}" if new_number > 1 else "- 前置段：开场",
        before_mixed,
        flags=re.M,
    )
    before_mixed = re.sub(r"^## 生成段 V\d{2}｜.*$", heading, before_mixed, flags=re.M)
    before_mixed = re.sub(r"^- 音色状态：.+$", "- 音色状态：已绑定｜" + "、".join(
        dict.fromkeys(row["asset"].removeprefix("独立音色-") for row in selected_rows if row["asset"].startswith("独立音色-"))
    ), before_mixed, flags=re.M)
    table = "### Mixed 上传顺序\n\n| Mixed | 素材 | 类型 | 绑定语义 |\n|---:|---|---|---|\n"
    table += "\n".join(f"| Mixed {row['number']} | {row['asset']} | {row['media']} | {row['semantic']} |" for row in selected_rows)
    prompt_section_start = block.find("### LibTV 完成提示词（整块复制）")
    prompt_section_end = block.find("### 衔接", prompt_section_start)
    prompt_section = "### LibTV 完成提示词（整块复制）\n\n```text\n" + prompt + "\n```\n\n"
    handoff = block[prompt_section_end:] if prompt_section_end >= 0 else ""
    handoff = re.sub(r"- 入点：[^\n]+", f"- 入点：承接 {episode}-V{new_number - 1:02d} 的出点。" if new_number > 1 else "- 入点：本集开篇。", handoff, count=1)
    return before_mixed + table + "\n\n" + prompt_section + handoff


def split_document(path: Path) -> bool:
    episode = path.name[:4]
    text = path.read_text(encoding="utf-8")
    headings = list(SEGMENT_RE.finditer(text))
    if not headings:
        return False
    changed = False
    blocks: list[tuple[int, str]] = []
    new_number = 1
    mapping: dict[int, list[int]] = {}
    shot_mapping: dict[tuple[int, int], tuple[int, int]] = {}
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        block = text[heading.start():end]
        old_number = int(heading.group(1).removeprefix("V"))
        key = (episode, f"V{old_number:02d}")
        split = SPLITS.get(key)
        # Split plans are keyed by the original 12-second segment. After the
        # first pass the leading child is 8 seconds, so treat it as already
        # processed and keep the script idempotent.
        if split:
            duration_match = re.search(r"^- 时长：(\d+)秒$", block, re.M)
            if not duration_match or int(duration_match.group(1)) != sum(split[2]):
                split = None
        if split:
            changed = True
            for group_index, (shot_numbers, duration) in enumerate(zip(split[:2], split[2]), start=0):
                current = new_number + group_index
                new_block = build_block(block, episode, current, shot_numbers, duration)
                blocks.append((current, new_block))
                mapping.setdefault(old_number, []).append(current)
                for new_shot, old_shot in enumerate(shot_numbers, start=1):
                    shot_mapping[(old_number, old_shot)] = (current, new_shot)
            new_number += 2
        else:
            new_block = re.sub(r"^## 生成段 V\d{2}｜", f"## 生成段 V{new_number:02d}｜", block, count=1, flags=re.M)
            new_block = re.sub(r"^- 段号：.+$", f"- 段号：{episode}-S{new_number:02d}", new_block, flags=re.M)
            new_block = re.sub(r"^- 前置段：[^\n]+$", f"- 前置段：{episode}-V{new_number - 1:02d}" if new_number > 1 else "- 前置段：开场", new_block, flags=re.M)
            blocks.append((new_number, new_block))
            mapping.setdefault(old_number, []).append(new_number)
            source_prompt = (PROMPT_RE.search(block) or [None, ""])[1]
            for old_shot in (int(match.group(1)) for match in SHOT_RE.finditer(source_prompt)):
                shot_mapping[(old_number, old_shot)] = (new_number, old_shot)
            new_number += 1
    if not changed:
        return False
    prefix = text[:headings[0].start()]
    suffix = text[headings[-1].start():]
    # The suffix is reconstructed from the final block boundary rather than
    # the original text to retain segment-end tables after inserted blocks.
    suffix = text[headings[-1].start():]
    last_block_end = headings[-1].start()
    # Find the last generated block's end using the original heading list.
    last_end = len(text)
    suffix = text[last_end:last_end]
    result = prefix + "\n".join(block for _number, block in blocks)
    # Reuse non-segment tail from the original document.
    tail_start = headings[-1].start()
    tail_match = re.search(r"^## 段间衔接总表", text[tail_start:], re.M)
    if tail_match:
        tail = text[tail_start + tail_match.start():]
        for old, new_list in mapping.items():
            first_new = new_list[0]
            tail = re.sub(rf"\bV{old:02d}(?!\d)", f"V{first_new:02d}", tail)
            tail = re.sub(rf"{episode}-V{old:02d}(?!\d)", f"{episode}-V{first_new:02d}", tail)
        for (old_seg, old_shot), (new_seg, new_shot) in shot_mapping.items():
            tail = tail.replace(f"V{old_seg:02d}-Shot{old_shot}", f"V{new_seg:02d}-Shot{new_shot}")
        result += "\n" + tail
    # Update episode-level segment count.
    result = re.sub(r"^- 生成段：\d+个$", f"- 生成段：{len(blocks)}个", result, count=1, flags=re.M)
    path.write_text(result, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    changed = []
    for path in sorted(args.project.glob("EP*-LibTV视频节点提示词.md")):
        if split_document(path):
            changed.append(path.name)
    # A split changes the last segment number of its episode. Refresh the
    # next episode's declared handoff from the actual files so a global
    # continuity audit cannot retain stale predecessors (for example
    # EP06-V08 after EP06 becomes nine segments).
    episode_counts: dict[int, int] = {}
    for path in sorted(args.project.glob("EP*-LibTV视频节点提示词.md")):
        match = re.match(r"EP(\d+)-", path.name)
        if not match:
            continue
        episode_counts[int(match.group(1))] = len(SEGMENT_RE.findall(path.read_text(encoding="utf-8")))
    for path in sorted(args.project.glob("EP*-LibTV视频节点提示词.md")):
        match = re.match(r"EP(\d+)-", path.name)
        if not match:
            continue
        episode_number = int(match.group(1))
        previous_count = episode_counts.get(episode_number - 1)
        if episode_number <= 1 or previous_count is None:
            continue
        text = path.read_text(encoding="utf-8")
        expected = f"EP{episode_number - 1:02d}-V{previous_count:02d}"
        updated = re.sub(r"^- 前集承接：.+$", f"- 前集承接：{expected}", text, count=1, flags=re.M)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            if path.name not in changed:
                changed.append(path.name)
    print({"changed": changed, "count": len(changed)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
