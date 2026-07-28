#!/usr/bin/env python3
"""Audit LibTV Markdown files as one drama-wide continuity chain."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import re
import sys
from pathlib import Path

import validate_delivery_md


EPISODE_RE = re.compile(r"^#\s+([^｜\n]+)｜LibTV 完成提示词$", re.M)
EPISODE_NUMBER_RE = re.compile(r"EP\s*0*(\d+)", re.I)
SCOPE_RE = re.compile(r"^- 审核范围：(全剧|截至EP\d+|单集)$", re.M)
SERIES_COUNT_RE = re.compile(r"^- 全剧集数：(\d+|未知)$", re.M)
SERIES_REVIEW_RE = re.compile(r"^- 全剧二审：(已通过|未通过)$", re.M)
PREVIOUS_EPISODE_RE = re.compile(r"^- 前集承接：(.+)$", re.M)
SEGMENT_RE = re.compile(r"^## 生成段 V(\d{2})｜.+$", re.M)
GROUP_RE = re.compile(r"^- 连续组：(.+)$", re.M)
PREDECESSOR_RE = re.compile(r"^- 前置段：(.+)$", re.M)
PROMPT_REVIEW_RE = re.compile(r"^- 提示词二审：(已通过|未通过)$", re.M)
MASTER_HEADER = "| 连续键 | 类型 | 锁定版本 | 本集允许变化 | 变更依据 |"
HANDOFF_HEADER = "| 连续键 | 入点状态 | 出点状态 |"
MASTER_ROW_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(是|否)\s*\|\s*([^|]+?)\s*\|$",
    re.M,
)
HANDOFF_ROW_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", re.M
)
# 允许尾随标点与空白：写成「无。」曾可绕过这条拦截。
WEAK_CHANGE_RE = re.compile(r"^\s*(?:无|不适用|未知|待定|剧情需要|见剧本)[\s。．.,，;；!！]*$")


@dataclass
class MasterState:
    episode: str
    number: int
    key: str
    kind: str
    version: str
    change_allowed: bool
    basis: str


@dataclass
class SegmentState:
    episode: str
    episode_number: int
    segment_number: int
    segment_id: str
    group: str
    predecessor: str
    reviewed: bool
    states: dict[str, tuple[str, str]]


def section(text: str, heading: str, next_heading_level: int = 2) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    body_start = start + len(heading)
    match = re.search(rf"^#{{1,{next_heading_level}}}\s+", text[body_start:], re.M)
    end = body_start + match.start() if match else len(text)
    return text[body_start:end]


def segment_end(matches: list[re.Match[str]], index: int, text: str) -> int:
    return matches[index + 1].start() if index + 1 < len(matches) else len(text)


def parse_markdown(path: Path, standalone: bool = True) -> tuple[dict, list[str]]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    # standalone 的语义与 validate_delivery_md 的 CLI 保持一致：
    # 默认走流程时要查流程凭据，显式 --standalone 才只看文件本身。
    delivery_errors, _, _ = validate_delivery_md.validate(path, standalone=standalone)
    errors.extend(f"{path.name}: {error}" for error in delivery_errors)

    episode_match = EPISODE_RE.search(text)
    episode = episode_match.group(1).strip() if episode_match else path.stem
    number_match = EPISODE_NUMBER_RE.search(episode)
    if not number_match:
        errors.append(f"{path.name}: 集号必须包含可排序的 EP 数字")
        episode_number = 10**9
    else:
        episode_number = int(number_match.group(1))

    scope_match = SCOPE_RE.search(text)
    count_match = SERIES_COUNT_RE.search(text)
    review_match = SERIES_REVIEW_RE.search(text)
    previous_episode_match = PREVIOUS_EPISODE_RE.search(text)
    scope = scope_match.group(1) if scope_match else ""
    series_count = count_match.group(1) if count_match else ""
    if not review_match or review_match.group(1) != "已通过":
        errors.append(f"{path.name}: 全剧二审未标记为已通过")

    master_block = section(text, "## 全剧连续性母版")
    masters: list[MasterState] = []
    if MASTER_HEADER not in master_block:
        errors.append(f"{path.name}: 全剧连续性母版缺少固定表头")
    else:
        seen_master: set[str] = set()
        for key, kind, version, allowed, basis in MASTER_ROW_RE.findall(master_block):
            key = key.strip()
            if key in {"连续键", "---"}:
                continue
            if key in seen_master:
                errors.append(f"{path.name}: 连续性母版重复连续键 {key}")
                continue
            seen_master.add(key)
            masters.append(MasterState(
                episode, episode_number, key, kind.strip(), version.strip(),
                allowed == "是", basis.strip(),
            ))
        if not masters:
            errors.append(f"{path.name}: 全剧连续性母版没有有效状态行")

    segments: list[SegmentState] = []
    segment_matches = list(SEGMENT_RE.finditer(text))
    for index, match in enumerate(segment_matches):
        block = text[match.start():segment_end(segment_matches, index, text)]
        segment_number = int(match.group(1))
        segment_id = f"{episode}-V{segment_number:02d}"
        group_match = GROUP_RE.search(block)
        predecessor_match = PREDECESSOR_RE.search(block)
        prompt_review_match = PROMPT_REVIEW_RE.search(block)
        group = group_match.group(1).strip() if group_match else ""
        predecessor = predecessor_match.group(1).strip() if predecessor_match else ""
        reviewed = bool(prompt_review_match and prompt_review_match.group(1) == "已通过")
        if not group:
            errors.append(f"{path.name} {segment_id}: 缺少连续组")
        if not predecessor:
            errors.append(f"{path.name} {segment_id}: 缺少前置段")
        if not reviewed:
            errors.append(f"{path.name} {segment_id}: 提示词二审未通过")

        handoff_block = section(block, "### 状态交接", next_heading_level=3)
        states: dict[str, tuple[str, str]] = {}
        if HANDOFF_HEADER not in handoff_block:
            errors.append(f"{path.name} {segment_id}: 状态交接缺少固定表头")
        else:
            for key, start_state, end_state in HANDOFF_ROW_RE.findall(handoff_block):
                key = key.strip()
                if key in {"连续键", "---"}:
                    continue
                if key in states:
                    errors.append(f"{path.name} {segment_id}: 状态交接重复连续键 {key}")
                    continue
                states[key] = (start_state.strip(), end_state.strip())
            if not states:
                errors.append(f"{path.name} {segment_id}: 状态交接没有有效状态行")
        segments.append(SegmentState(
            episode, episode_number, segment_number, segment_id, group,
            predecessor, reviewed, states,
        ))

    return {
        "path": path,
        "episode": episode,
        "episode_number": episode_number,
        "scope": scope,
        "series_count": series_count,
        "previous_episode": (
            previous_episode_match.group(1).strip() if previous_episode_match else ""
        ),
        "masters": masters,
        "segments": segments,
    }, errors


def collect_paths(inputs: list[Path]) -> list[Path]:
    paths: set[Path] = set()
    for item in inputs:
        if item.is_dir():
            paths.update(item.rglob("*-LibTV视频节点提示词.md"))
        elif item.is_file():
            paths.add(item)
    return sorted(paths.resolve() for paths in paths)


def audit(
    paths: list[Path], standalone: bool = True
) -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    warnings: list[str] = []
    docs: list[dict] = []
    for path in paths:
        try:
            doc, doc_errors = parse_markdown(path, standalone)
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{path}: 无法读取：{exc}")
            continue
        docs.append(doc)
        errors.extend(doc_errors)
    docs.sort(key=lambda doc: (doc["episode_number"], str(doc["path"])))

    episode_numbers = [doc["episode_number"] for doc in docs]
    if len(episode_numbers) != len(set(episode_numbers)):
        errors.append("存在重复 EP 集号")
    scopes = {doc["scope"] for doc in docs}
    if len(scopes) > 1:
        errors.append(f"各集审核范围声明不一致：{sorted(scopes)}")
    known_counts = {doc["series_count"] for doc in docs if doc["series_count"].isdigit()}
    if len(known_counts) > 1:
        errors.append(f"各集全剧集数声明不一致：{sorted(known_counts)}")
    for doc in docs:
        scope = doc["scope"]
        if scope == "单集" and len(docs) != 1:
            errors.append(f"{doc['episode']}: 审核范围写单集，但本次传入了 {len(docs)} 集")
        if scope.startswith("截至EP"):
            expected_last = int(scope.removeprefix("截至EP"))
            expected = list(range(1, expected_last + 1))
            if episode_numbers != expected:
                errors.append(
                    f"{doc['episode']}: 声明审核至 EP{expected_last:02d}，"
                    f"但实际集号为 {episode_numbers}"
                )
        if scope == "全剧":
            if not doc["series_count"].isdigit():
                errors.append(f"{doc['episode']}: 声明全剧审核时必须填写全剧集数")
            else:
                expected = list(range(1, int(doc["series_count"]) + 1))
                if episode_numbers != expected:
                    errors.append(
                        f"{doc['episode']}: 声明全剧审核，但实际集号 {episode_numbers} "
                        f"不等于完整范围 {expected}"
                    )

    last_master: dict[str, MasterState] = {}
    master_keys_by_episode: dict[str, set[str]] = {}
    for doc in docs:
        master_keys_by_episode[doc["episode"]] = {item.key for item in doc["masters"]}
        for item in doc["masters"]:
            previous = last_master.get(item.key)
            if previous and item.kind != previous.kind:
                errors.append(
                    f"{item.episode}: {item.key} 类型从 {previous.kind} 变为 {item.kind}"
                )
            if previous and item.version != previous.version:
                if not item.change_allowed:
                    errors.append(
                        f"{item.episode}: {item.key} 从 {previous.version} 变为 "
                        f"{item.version}，但未声明允许变化"
                    )
                elif WEAK_CHANGE_RE.fullmatch(item.basis):
                    errors.append(
                        f"{item.episode}: {item.key} 版本变化缺少可回指剧本的具体依据"
                    )
                else:
                    warnings.append(
                        f"{item.episode}: {item.key} 版本变化 {previous.version} → "
                        f"{item.version}，需人工核对依据：{item.basis}"
                    )
            elif item.change_allowed and WEAK_CHANGE_RE.fullmatch(item.basis):
                errors.append(f"{item.episode}: {item.key} 声明允许变化但依据无效")
            last_master[item.key] = item

    segments = sorted(
        (segment for doc in docs for segment in doc["segments"]),
        key=lambda item: (item.episode_number, item.segment_number),
    )
    by_id = {segment.segment_id: segment for segment in segments}
    if len(by_id) != len(segments):
        errors.append("存在重复生成段 ID")
    position = {segment.segment_id: index for index, segment in enumerate(segments)}
    last_segment_by_episode: dict[int, str] = {}
    for segment in segments:
        last_segment_by_episode[segment.episode_number] = segment.segment_id
    for doc in docs:
        if doc["episode_number"] == 1:
            if doc["previous_episode"] != "开篇":
                errors.append(f"{doc['episode']}: 第一集前集承接必须为开篇")
            continue
        expected_previous = last_segment_by_episode.get(doc["episode_number"] - 1)
        if expected_previous and doc["previous_episode"] != expected_previous:
            errors.append(
                f"{doc['episode']}: 前集承接应为 {expected_previous}，"
                f"实际为 {doc['previous_episode'] or '空'}"
            )
    last_state_by_group: dict[str, dict[str, tuple[str, str]]] = {}
    group_seen: set[str] = set()
    for segment in segments:
        predecessor = segment.predecessor
        if predecessor not in {"开场", "独立"}:
            previous_segment = by_id.get(predecessor)
            if not previous_segment:
                errors.append(f"{segment.segment_id}: 前置段 {predecessor} 不存在")
            elif position[predecessor] >= position[segment.segment_id]:
                errors.append(f"{segment.segment_id}: 前置段 {predecessor} 顺序倒置")
            elif previous_segment.group != segment.group:
                errors.append(
                    f"{segment.segment_id}: 与前置段 {predecessor} 不属于同一连续组"
                )
        elif segment.group in group_seen:
            errors.append(f"{segment.segment_id}: 连续组已存在，不能再次使用{predecessor}")

        previous_states = last_state_by_group.setdefault(segment.group, {})
        if predecessor not in {"开场", "独立"}:
            for key, (start_state, _) in segment.states.items():
                if key in previous_states:
                    previous_id, previous_end = previous_states[key]
                    if start_state != previous_end:
                        errors.append(
                            f"{segment.segment_id}: {key} 入点“{start_state}”不等于"
                            f"{previous_id}出点“{previous_end}”"
                        )
        known_master = master_keys_by_episode.get(segment.episode, set())
        for key, (_, end_state) in segment.states.items():
            if key not in known_master:
                errors.append(
                    f"{segment.segment_id}: 状态交接连续键 {key} 未登记在本集连续性母版"
                )
            previous_states[key] = (segment.segment_id, end_state)
        group_seen.add(segment.group)

    return errors, warnings, {
        "episodes": len(docs),
        "segments": len(segments),
        "masterKeys": len(last_master),
        "errors": len(errors),
        "warnings": len(warnings),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="只检查文件本身，不查流程凭据（与 validate_delivery_md 同义）",
    )
    args = parser.parse_args()
    paths = collect_paths(args.inputs)
    if not paths:
        print("ERROR: 没有找到待审核的 LibTV Markdown", file=sys.stderr)
        return 2
    errors, warnings, summary = audit(paths, args.standalone)
    for error in errors:
        print(f"ERROR: {error}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    print(
        "SUMMARY: "
        f"episodes={summary['episodes']} segments={summary['segments']} "
        f"masterKeys={summary['masterKeys']} "
        f"errors={summary['errors']} warnings={summary['warnings']}"
    )
    if errors:
        return 1
    print("OK: drama-wide prompt continuity audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
