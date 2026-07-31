#!/usr/bin/env python3
"""Audit one TVMao image-generator node and its ordered reference-image edges."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


INTERNAL_PREFIX_RE = re.compile(r"^\s*(?:EP\d+-)?A\d{2}\b[^\n。.]*(?:v\d+)[。.]", re.I)
REF_TOKEN_RE = re.compile(r"参考图\s*(\d+)（([^）]+)）")
UNBOUND_IMAGE_RE = re.compile(r"(?:图片\s*\d+|(?<!参考)图\s*\d+)")
CANONICAL_MENTION_RE = re.compile(r"@\[图片:[^\]]+\]")
COLOR_CARD_NAME_RE = re.compile(r"(?:色卡|color\s*(?:palette|script|card))", re.I)
CHARACTER_REFERENCE_NAME_RE = re.compile(
    r"(?=.*(?:人物|角色|character))(?=.*(?:标准图|参考图|设定|定妆|根资产|sheet))",
    re.I,
)
CHARACTER_STILL_NAME_RE = re.compile(r"(?:人物剧照|角色剧照|剧照|表演锚|performance\s*anchor)", re.I)
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")


# 万物生·问心（正传姊妹篇）在正传固定 13 色之外，对复杂场景（多角色同框/多光位/
# 巨物战场）实证出 22、24 色两档扩展版式——版式约束不变（16:9横版白底/纯色硬边/HEX标签/
# 单行排列），只放开色块数量。2026-08-01 补：正传单档 13 色时不区分，允许三档之一即可。
VALID_CARD_COUNTS = (13, 22, 24)
_CARD_COUNT_CN = {"十三": 13, "二十二": 22, "二十四": 24}


def audit_color_card_prompt(prompt: str) -> list[str]:
    """Enforce the fixed Wanwusheng color-card layout: 13-color baseline (正传)，
    22/24-color variants permitted for complex scenes (问心 wanwu-field-craft extension)。"""
    errors: list[str] = []
    count_match = re.search(
        r"(13|22|24|十三|二十二|二十四)\s*(?:个|色|枚)?[^。\n]{0,24}(?:色块|色卡|swatches?)",
        prompt, re.I,
    )
    declared = None
    if count_match:
        token = count_match.group(1)
        declared = int(token) if token.isdigit() else _CARD_COUNT_CN.get(token)
    checks = [
        (re.search(r"16\s*:\s*9", prompt), "色卡必须是 16:9 横版参考资产"),
        (re.search(r"(?:横版|横向|horizontal)", prompt, re.I), "色卡必须明确横版布局"),
        (re.search(r"(?:纯白背景|白色背景|白底|white background)", prompt, re.I), "色卡必须使用纯白背景"),
        (declared in VALID_CARD_COUNTS, "色卡必须明确色块数量为 13/22/24 之一（正传固定13，问心复杂场景可用22/24）"),
        (re.search(r"(?:单行|单排|同一行|一字排开|single row)", prompt, re.I), "色块必须单行排列"),
        (re.search(r"(?:等大|等宽|等面积|均等|evenly[- ]sized|equal[- ]sized)", prompt, re.I), "色块必须等大"),
        (re.search(r"(?:下方|下面|below)", prompt, re.I), "每个色块下方必须放置 HEX 标签"),
        (re.search(r"(?:等宽|monospace)", prompt, re.I), "HEX 标签必须使用等宽字体"),
        (re.search(r"(?:黑色|black)", prompt, re.I), "HEX 标签必须使用黑色字体"),
        (re.search(r"(?:纯平色|纯色|flat color)", prompt, re.I), "色块必须是纯平色"),
        (re.search(r"(?:锐利硬边|锐利边缘|清晰硬边|sharp edges?)", prompt, re.I), "色块必须使用锐利硬边"),
        (re.search(r"(?:无渐变|no gradient)", prompt, re.I), "色块必须明确无渐变"),
        (re.search(r"(?:无纹理|no texture)", prompt, re.I), "色块必须明确无纹理"),
        (re.search(r"(?:无噪点|无噪声|no noise)", prompt, re.I), "色块必须明确无噪点"),
        (re.search(r"(?:无阴影|no shadow)", prompt, re.I), "色块必须明确无阴影"),
    ]
    errors.extend(message for matched, message in checks if not matched)
    unique_hex = {value.upper() for value in HEX_RE.findall(prompt)}
    if len(unique_hex) not in VALID_CARD_COUNTS:
        errors.append(f"色卡 HEX 数量必须恰好是 13/22/24 之一：actual={len(unique_hex)}")
    elif declared is not None and len(unique_hex) != declared:
        errors.append(f"色卡文字声明色块数({declared})与实际列出的 HEX 数({len(unique_hex)})不一致")
    if re.search(r"(?:无文字|无标签|不生成[^。\n]{0,12}(?:文字|标签)|只有纯色块)", prompt):
        errors.append("色卡提示词与固定版式冲突：HEX 标签是必需设计信息，不得声明无文字/无标签")
    if re.search(
        r"(?:【格式】[^。\n]{0,80}9\s*:\s*16|9\s*:\s*16[^。\n]{0,24}(?:竖版|竖向|vertical))",
        prompt,
        re.I,
    ):
        errors.append("色卡不得继承 9:16 视频画幅")
    return errors


def audit_character_reference_prompt(prompt: str) -> list[str]:
    """Reject character stills masquerading as the canonical 3D reference board."""
    errors: list[str] = []
    checks = [
        (
            re.search(r"(?:官方)?角色设定(?:展示板|板)|人物设定(?:展示板|板)|character\s*(?:reference\s*)?sheet", prompt, re.I),
            "3D 标准人物参考图必须明确为角色设定展示板",
        ),
        (
            re.search(r"(?:纯白无缝背景|纯白背景|白色无缝背景|seamless white background)", prompt, re.I),
            "3D 标准人物参考图必须使用纯白无缝背景",
        ),
        (
            re.search(r"(?:正面头肩肖像|正面头肩像|front[^。\n]{0,20}(?:head.?and.?shoulders|bust|portrait))", prompt, re.I),
            "3D 标准人物参考图必须包含正面头肩肖像",
        ),
        (
            re.search(r"(?:全身正面|正面全身|full.?body front)", prompt, re.I),
            "3D 标准人物参考图必须包含全身正面视图",
        ),
        (
            re.search(r"(?:全身侧面|侧面全身|full.?body side)", prompt, re.I),
            "3D 标准人物参考图必须包含全身侧面视图",
        ),
        (
            re.search(r"(?:全身背面|背面全身|full.?body back)", prompt, re.I),
            "3D 标准人物参考图必须包含全身背面视图",
        ),
        (
            re.search(r"(?:中性站姿|自然直立|neutral (?:standing )?pose)", prompt, re.I),
            "3D 标准人物参考图必须使用中性站姿",
        ),
        (
            re.search(r"(?:中性表情|自然放松表情|neutral expression)", prompt, re.I),
            "3D 标准人物参考图必须使用中性表情",
        ),
        (
            re.search(r"(?:无文字|无标题|no text)", prompt, re.I),
            "3D 标准人物参考图必须明确无文字",
        ),
        (
            re.search(r"(?:无水印|no watermark)", prompt, re.I),
            "3D 标准人物参考图必须明确无水印",
        ),
    ]
    errors.extend(message for matched, message in checks if not matched)
    still_markers = [
        marker
        for marker in (
            "扶门框",
            "端坐",
            "沙发",
            "看向画外",
            "视线落在画外",
            "门把",
            "微醺",
            "哭泣",
            "醉意",
            "实用光",
        )
        if marker in prompt
    ]
    if still_markers:
        errors.append(
            "人物节点包含剧照/表演锚语义，不能登记为标准人物参考图："
            + "、".join(still_markers)
        )
    return errors


def parse_ref(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--ref 必须是 语义名=n-节点ID")
    label, node_id = (part.strip() for part in value.split("=", 1))
    if not label or not node_id.startswith("n-"):
        raise argparse.ArgumentTypeError("--ref 必须是 语义名=n-节点ID")
    return label, node_id


def run_json(argv: list[str]) -> object:
    proc = subprocess.run(argv, text=True, capture_output=True, check=False)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "TVMao CLI 调用失败")
    return json.loads(proc.stdout)


def has_output(node: dict) -> bool:
    if node.get("content"):
        return True
    history = node.get("history") or node.get("params", {}).get("history") or []
    return bool(history)


def audit(
    target: dict,
    edges: list[dict],
    upstream: dict[str, dict],
    refs: list[tuple[str, str]],
    pre_run: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    prompt = str(target.get("params", {}).get("prompt") or "")
    name = str(target.get("params", {}).get("name") or target.get("name") or "")

    if target.get("type") != "image-generator":
        errors.append(f"目标节点类型不是 image-generator：{target.get('type')}")
    if not prompt.strip():
        errors.append("目标节点缺少 prompt")
    if INTERNAL_PREFIX_RE.search(prompt):
        errors.append("prompt 含内部资产编号/版本前缀；节点名只能放 params.name")
    if CANONICAL_MENTION_RE.search(prompt):
        errors.append("image-generator 当前不支持视频节点 canonical mention；请使用有序入边")
    if UNBOUND_IMAGE_RE.search(prompt):
        errors.append("prompt 含未绑定的‘图片N/图N’文本；请改为‘参考图N（语义名）’")
    if COLOR_CARD_NAME_RE.search(name):
        errors.extend(audit_color_card_prompt(prompt))
    if CHARACTER_REFERENCE_NAME_RE.search(name) and not CHARACTER_STILL_NAME_RE.search(name):
        errors.extend(audit_character_reference_prompt(prompt))

    actual_ids = [str(edge.get("fromNodeId") or "") for edge in edges]
    expected_ids = [node_id for _, node_id in refs]
    if actual_ids != expected_ids:
        errors.append(f"有序入边不匹配：expected={expected_ids} actual={actual_ids}")

    tokens = [(int(index), label.strip()) for index, label in REF_TOKEN_RE.findall(prompt)]
    token_indexes = {index for index, _ in tokens}
    expected_indexes = set(range(1, len(refs) + 1))
    if token_indexes != expected_indexes:
        errors.append(f"参考图编号不连续或缺失：expected={sorted(expected_indexes)} actual={sorted(token_indexes)}")
    for index, (label, _) in enumerate(refs, start=1):
        if (index, label) not in tokens:
            errors.append(f"缺少精确语义绑定：参考图{index}（{label}）")

    if pre_run:
        if target.get("status") != "idle":
            errors.append(f"运行前目标节点必须为 idle：{target.get('status')}")
        for label, node_id in refs:
            node = upstream.get(node_id) or {}
            if node.get("status") != "succeeded":
                errors.append(f"父图未成功：{label}={node_id} status={node.get('status')}")
            elif not has_output(node):
                errors.append(f"父图成功但无可用输出：{label}={node_id}")
    elif refs:
        warnings.append("未启用 --pre-run；仅核对 prompt 与有序入边，不保证父图已有输出")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=int, required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--ref", action="append", default=[], type=parse_ref)
    parser.add_argument("--tvmao", default="tvmao")
    parser.add_argument("--pre-run", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    target = run_json([args.tvmao, "node", "get", args.node, "--project", str(args.project)])
    edges = run_json([args.tvmao, "edge", "list", "--to", args.node, "--project", str(args.project)])
    upstream = {
        node_id: run_json([args.tvmao, "node", "get", node_id, "--project", str(args.project)])
        for _, node_id in args.ref
    }
    errors, warnings = audit(target, edges, upstream, args.ref, args.pre_run)
    for item in errors:
        print(f"ERROR: {item}")
    for item in warnings:
        print(f"WARNING: {item}")
    print(f"SUMMARY: refs={len(args.ref)} errors={len(errors)} warnings={len(warnings)}")
    if errors:
        return 1
    if args.receipt:
        rows = "\n".join(
            f"| {index} | {label} | `{node_id}` |"
            for index, (label, node_id) in enumerate(args.ref, start=1)
        ) or "| - | 无 | - |"
        args.receipt.write_text(
            "# TVMao 图片资产节点运行前凭证\n\n"
            f"- 项目：{args.project}\n- 节点：`{args.node}`\n- 状态：通过\n\n"
            "| 顺序 | 语义 | 节点 |\n|---:|---|---|\n" + rows + "\n",
            encoding="utf-8",
        )
    print("OK: image asset node audit passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
