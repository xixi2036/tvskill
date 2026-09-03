#!/usr/bin/env python3
"""Audit one TVMao image-generator node and its ordered reference-image edges."""

from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
from pathlib import Path


INTERNAL_PREFIX_RE = re.compile(r"^\s*(?:EP\d+-)?A\d{2}\b[^\n。.]*(?:v\d+)[。.]", re.I)
PROMPT_METADATA_RE = re.compile(
    r"(?:冻结历史提示词|禁止复用|当前\s*canonical|不作为\s*canonical|"
    r"EP\d+-L\d+|`[^`\n]+`|n-[A-Za-z0-9_-]{6,})",
    re.I,
)
REF_TOKEN_RE = re.compile(r"参考图\s*(\d+)（([^）]+)）")
UNBOUND_IMAGE_RE = re.compile(r"(?:图片\s*\d+|(?<!参考)图\s*\d+)")
CANONICAL_MENTION_RE = re.compile(r"@\[图片:[^\]]+\]")
COLOR_CARD_NAME_RE = re.compile(r"(?:色卡|color\s*(?:palette|script|card))", re.I)
COLOR_CARD_PROMPT_RE = re.compile(
    r"(?:color\s+palette\s+(?:swatch\s+)?reference\s+card|"
    r"13\s*(?:个|色|枚)?[^。\n]{0,80}(?:色块|swatches?)[^\n]{0,80}(?:单行|单排|single\s+row))",
    re.I | re.S,
)
CHARACTER_REFERENCE_NAME_RE = re.compile(
    r"(?=.*(?:人物|角色|character))(?=.*(?:标准图|参考图|设定|定妆|根资产|sheet))",
    re.I,
)
CHARACTER_REFERENCE_PROMPT_RE = re.compile(
    r"(?:官方)?角色设定(?:展示板|板)|人物设定(?:展示板|板)|character\s*(?:reference\s*)?sheet",
    re.I,
)
CHARACTER_MULTI_VIEW_PROMPT_RE = re.compile(
    r"(?=.*(?:标准人物|标准角色|人物标准|角色标准|身份根|人物根|角色根))"
    r"(?=.*(?:三视图|四视图|全身正面.{0,120}全身侧面.{0,120}全身背面))",
    re.I | re.S,
)
CHARACTER_STILL_NAME_RE = re.compile(r"(?:人物剧照|角色剧照|剧照|表演锚|performance\s*anchor)", re.I)
VIDEO_FRAME_OUTPUT_RE = re.compile(
    r"资产类型[：:].{0,40}(?:干净视频首帧|视频首帧|干净首帧|视频场景锚)"
    r"|输出.{0,40}(?:完整)?单幅影视画面",
    re.I | re.S,
)
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
DIRECT_STILL_NEGATION_RE = re.compile(
    r"(?:不得|不应|不能|不生成|未生成|不出现|禁止|严禁|避免|排除|无|未)\s*$",
    re.I,
)
DISTRIBUTED_STILL_NEGATION_RE = re.compile(
    r"(?:不得|不应|不能|不生成|未生成|不出现|禁止|严禁|避免|排除)"
    r"[^，,。；;\n：:但而却]{0,24}(?:、[^，,。；;\n：:但而却]{0,24})*$",
    re.I,
)
FUTURE_STILL_STATE_RE = re.compile(
    r"^[^，,。；;\n]{0,30}(?:属于后续状态|均属后续状态|作为后续状态|"
    r"列为后续状态|本板不生成|不纳入本板)",
    re.I,
)


def is_character_reference(name: str, prompt: str) -> bool:
    if VIDEO_FRAME_OUTPUT_RE.search(prompt):
        return False
    return bool(
        CHARACTER_REFERENCE_NAME_RE.search(name)
        or CHARACTER_REFERENCE_PROMPT_RE.search(prompt)
        or CHARACTER_MULTI_VIEW_PROMPT_RE.search(prompt)
    ) and not CHARACTER_STILL_NAME_RE.search(name)


def is_color_card(name: str, prompt: str) -> bool:
    return bool(COLOR_CARD_NAME_RE.search(name) or COLOR_CARD_PROMPT_RE.search(prompt))


def positive_still_markers(prompt: str) -> list[str]:
    markers: list[str] = []
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
    ):
        for match in re.finditer(re.escape(marker), prompt):
            before = prompt[:match.start()]
            after = prompt[match.end():]
            clause_start = max(
                [before.rfind(separator) for separator in "，,。；;\n：:"] + [-1]
            ) + 1
            ends = [
                index for separator in "，,。；;\n"
                if (index := after.find(separator)) >= 0
            ]
            clause_end = match.end() + (min(ends) if ends else len(after))
            prefix = prompt[clause_start:match.start()]
            suffix = prompt[match.end():clause_end]
            if not (
                DIRECT_STILL_NEGATION_RE.search(prefix)
                or DISTRIBUTED_STILL_NEGATION_RE.search(prefix)
                or FUTURE_STILL_STATE_RE.search(suffix)
            ):
                markers.append(marker)
                break
    return markers


def audit_color_card_prompt(prompt: str) -> list[str]:
    """Enforce the fixed Wanwusheng 13-color reference-card layout."""
    errors: list[str] = []
    checks = [
        (re.search(r"16\s*:\s*9", prompt), "色卡必须是 16:9 横版参考资产"),
        (re.search(r"(?:横版|横向|horizontal)", prompt, re.I), "色卡必须明确横版布局"),
        (re.search(r"(?:纯白背景|白色背景|白底|white background)", prompt, re.I), "色卡必须使用纯白背景"),
        (re.search(r"(?:13|十三)\s*(?:个|色|枚)?[^。\n]{0,24}(?:色块|色卡|swatches?)", prompt, re.I), "色卡必须明确 13 个色块"),
        (re.search(r"(?:单行|单排|同一行|一字排开|single row)", prompt, re.I), "13 个色块必须单行排列"),
        (re.search(r"(?:等大|等宽|等面积|均等|evenly[- ]sized|equal[- ]sized)", prompt, re.I), "13 个色块必须等大"),
        (re.search(r"(?:下方|下面|below)", prompt, re.I), "每个色块下方必须放置 HEX 标签"),
        (re.search(r"(?:等宽|monospace)", prompt, re.I), "HEX 标签必须使用等宽字体"),
        (re.search(r"(?:黑色|black)", prompt, re.I), "HEX 标签必须使用黑色字体"),
        (re.search(r"(?:纯平色|纯色|flat color)", prompt, re.I), "色块必须是纯平色"),
        (
            re.search(
                r"(?:锐利硬边|锐利边缘|清晰硬边|sharp\s+(?:clean\s+)?edges?)",
                prompt,
                re.I,
            ),
            "色块必须使用锐利硬边",
        ),
        (re.search(r"(?:无渐变|no gradient)", prompt, re.I), "色块必须明确无渐变"),
        (re.search(r"(?:无纹理|no texture)", prompt, re.I), "色块必须明确无纹理"),
        (re.search(r"(?:无噪点|无噪声|no noise)", prompt, re.I), "色块必须明确无噪点"),
        (re.search(r"(?:无阴影|no shadow)", prompt, re.I), "色块必须明确无阴影"),
        (
            re.search(r"(?:标题|title\s+text)[^。\n]{0,80}(?:顶部|顶端|top\s+center|color\s+reference)", prompt, re.I),
            "万物生色卡必须在顶部声明 COLOR REFERENCE 标题",
        ),
    ]
    errors.extend(message for matched, message in checks if not matched)
    unique_hex = {value.upper() for value in HEX_RE.findall(prompt)}
    if len(unique_hex) != 13:
        errors.append(f"色卡必须列出恰好 13 个不同 HEX：actual={len(unique_hex)}")
    if re.search(r"(?:无文字|无标签|不生成[^。\n]{0,12}(?:文字|标签)|只有纯色块)", prompt):
        errors.append("色卡提示词与固定版式冲突：HEX 标签是必需设计信息，不得声明无文字/无标签")
    if re.search(
        r"(?:【格式】[^。\n]{0,80}9\s*:\s*16|9\s*:\s*16[^。\n]{0,24}(?:竖版|竖向|vertical))",
        prompt,
        re.I,
    ):
        errors.append("色卡不得继承 9:16 视频画幅")
    return errors


def audit_character_reference_prompt(prompt: str, params: dict) -> list[str]:
    """Reject character stills masquerading as the canonical 3D reference board."""
    errors: list[str] = []
    checks = [
        (
            re.search(r"16\s*:\s*9", prompt),
            "3D 标准人物参考图必须明确为 16:9 横版资产",
        ),
        (
            re.search(r"(?:横版|横向|horizontal|landscape)", prompt, re.I),
            "3D 标准人物参考图必须明确使用横版布局",
        ),
        (
            CHARACTER_REFERENCE_PROMPT_RE.search(prompt)
            or CHARACTER_MULTI_VIEW_PROMPT_RE.search(prompt),
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
    if re.search(r"9\s*:\s*16|(?:竖版|竖向|vertical|portrait)", prompt, re.I):
        errors.append("3D 标准人物参考图不得继承 9:16 视频画幅或竖版布局")

    ratio = str(params.get("ratio") or "").strip()
    resolution = str(params.get("resolution") or "").strip()
    resolution_match = re.fullmatch(r"(\d+)x(\d+)", resolution, re.I)
    has_verifiable_aspect = False
    if ratio:
        has_verifiable_aspect = True
        if ratio != "16:9":
            errors.append(f"3D 标准人物参考图节点 ratio 必须为 16:9：actual={ratio}")
    if resolution_match:
        has_verifiable_aspect = True
        width, height = (int(value) for value in resolution_match.groups())
        if height == 0 or abs(width / height - 16 / 9) > 0.03:
            errors.append(
                "3D 标准人物参考图节点分辨率必须为横向 16:9："
                f"actual={resolution}"
            )
    if not has_verifiable_aspect:
        errors.append(
            "3D 标准人物参考图节点缺少可验证的 16:9 参数："
            "需要 ratio=16:9 或横向 16:9 数字分辨率"
        )
    still_markers = positive_still_markers(prompt)
    if still_markers:
        errors.append(
            "人物节点包含剧照/表演锚语义，不能登记为标准人物参考图："
            + "、".join(still_markers)
        )
    return errors


def raster_dimensions(path: Path) -> tuple[int, int]:
    """Read PNG/JPEG dimensions using only the Python standard library."""
    with path.open("rb") as handle:
        header = handle.read(24)
        if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
            return struct.unpack(">II", header[16:24])
        if header[:2] != b"\xff\xd8":
            raise ValueError("只支持 PNG 或 JPEG 实图尺寸审计")
        handle.seek(2)
        while True:
            marker_start = handle.read(1)
            if not marker_start:
                break
            if marker_start != b"\xff":
                continue
            marker = handle.read(1)
            while marker == b"\xff":
                marker = handle.read(1)
            if marker in (b"\xd8", b"\xd9"):
                continue
            size_bytes = handle.read(2)
            if len(size_bytes) != 2:
                break
            segment_size = struct.unpack(">H", size_bytes)[0]
            if marker and marker[0] in {
                0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
            }:
                data = handle.read(5)
                if len(data) == 5:
                    height, width = struct.unpack(">HH", data[1:5])
                    return width, height
                break
            handle.seek(max(segment_size - 2, 0), 1)
    raise ValueError("无法读取图片尺寸")


def audit_character_output_file(path: Path) -> list[str]:
    try:
        width, height = raster_dimensions(path)
    except (OSError, ValueError, struct.error) as exc:
        return [f"无法审计人物标准参考图实图尺寸：{exc}"]
    if height == 0 or abs(width / height - 16 / 9) > 0.03:
        return [
            "3D 标准人物参考图实际输出必须为横向 16:9："
            f"actual={width}x{height}"
        ]
    return []


def audit_character_output_requirement(
    target: dict,
    character_reference: bool,
    output_file: Path | None,
) -> list[str]:
    if not character_reference or target.get("status") != "succeeded":
        return []
    if output_file is None:
        return [
            "人物标准参考图已生成但缺少 --output-file；"
            "必须下载原图并核对实际 16:9 横版尺寸"
        ]
    return audit_character_output_file(output_file)


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
    if PROMPT_METADATA_RE.search(prompt):
        errors.append("prompt 含审计/文件/节点管理元信息；图片生成提示词正文只能包含模型可执行描述")
    if CANONICAL_MENTION_RE.search(prompt):
        errors.append("image-generator 当前不支持视频节点 canonical mention；请使用有序入边")
    if UNBOUND_IMAGE_RE.search(prompt):
        errors.append("prompt 含未绑定的‘图片N/图N’文本；请改为‘参考图N（语义名）’")
    if is_color_card(name, prompt):
        errors.extend(audit_color_card_prompt(prompt))
    character_reference = is_character_reference(name, prompt)
    if character_reference:
        errors.extend(audit_character_reference_prompt(prompt, target.get("params", {})))

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
    parser.add_argument(
        "--output-file",
        type=Path,
        help="生成后下载的 PNG/JPEG 实图；人物标准参考图将确定性核对实际 16:9 横版尺寸",
    )
    args = parser.parse_args()

    target = run_json([args.tvmao, "node", "get", args.node, "--project", str(args.project)])
    edges = run_json([args.tvmao, "edge", "list", "--to", args.node, "--project", str(args.project)])
    upstream = {
        node_id: run_json([args.tvmao, "node", "get", node_id, "--project", str(args.project)])
        for _, node_id in args.ref
    }
    errors, warnings = audit(target, edges, upstream, args.ref, args.pre_run)
    prompt = str(target.get("params", {}).get("prompt") or "")
    name = str(target.get("params", {}).get("name") or target.get("name") or "")
    character_reference = is_character_reference(name, prompt)
    errors.extend(
        audit_character_output_requirement(target, character_reference, args.output_file)
    )
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
