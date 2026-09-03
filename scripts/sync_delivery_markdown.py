#!/usr/bin/env python3
"""Create/update unrun TVMao video-generator nodes from a TVSkill Markdown delivery.

Use ``--fresh-set`` when the user asks to rebuild the complete episode with new
video nodes.  That mode deliberately forbids both partial selection and target
node mappings, so an old or half-old node set cannot be mistaken for a rebuild.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared_patterns import DIALOGUE_RE, OS_VO_RE, PLANNING_RE, VOICE_SLOT_RE  # noqa: E402
from _fast_drama_contract import prompt_quality_messages  # noqa: E402

import audit_canvas_nodes  # noqa: E402


SEGMENT_RE = re.compile(r"^## 生成段 V(\d{2})｜(.+)$", re.M)
PROMPT_RE = re.compile(
    r"### (?:LibTV|TVMao) 完成提示词（整块复制）\s*\n```text\n(.*?)\n```", re.S
)
MIXED_RE = re.compile(
    r"^\| Mixed (\d+) \|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", re.M
)
MIXED_BINDING_RE = re.compile(
    r"@\[(?P<label>[^\]]+)\]\s*\{\{Mixed\s+(?P<number>\d+)\}\}"
)
BARE_MIXED_RE = re.compile(
    r"(?<!\{\{)(?<![A-Za-z0-9_@])Mixed\s+(?P<number>\d+)(?![A-Za-z0-9_])(?!\}\})"
)
CANVAS_MENTION_RE = re.compile(
    r"@\[(?P<kind>图片|视频|音频):(?P<node_id>[^\]\s]+)\]"
)
DEFAULT_MODEL_ID = "doubao-seedance-2-0-fast-260128"
REFERENCE_LIMITS = {"总计": 12, "图片": 9, "视频": 3, "音频": 3}
MODEL_ALIASES = {
    "Seedance 2.0 Fast VIP": DEFAULT_MODEL_ID,
    "Seedance 2.0 VIP": "doubao-seedance-2-0-260128",
    "doubao-seedance-2-0-fast": DEFAULT_MODEL_ID,
    "doubao-seedance-2-0-pro": "doubao-seedance-2-0-260128",
}


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def run(command: list[str], *, cwd: Path) -> Any:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"命令失败：{message}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"命令未返回 JSON：{result.stdout[:300]}") from exc


def scalar(text: str, key: str) -> str:
    match = re.search(rf"^- {re.escape(key)}：(.+)$", text, re.M)
    if not match:
        raise ValueError(f"缺少元数据：{key}")
    return match.group(1).strip()


def normalized(value: str) -> str:
    value = re.sub(r"^TVSkill-EP\d+-", "", value, flags=re.I)
    return re.sub(r"[\s_·（）()【】\[\]-]+", "", value).lower()


def kind_for_media(media_type: str) -> str:
    if "音频" in media_type:
        return "音频"
    if "视频" in media_type:
        return "视频"
    return "图片"


def expected_node_type(media_type: str) -> str:
    return {"图片": "image-input", "视频": "video-input", "音频": "audio-input"}[
        kind_for_media(media_type)
    ]


def clean_frame_block_reason(
    prompt: str, rows: list[dict[str, Any]], run_status: str
) -> str | None:
    has_sync_dialogue = bool(DIALOGUE_RE.search(prompt) and re.search(r"说出\s*\{", prompt))
    has_clean_frame = any(
        re.search(r"首帧|续接帧|验收末帧|稳定末帧", f"{row['asset']} {row['semantic']}")
        for row in rows
    )
    if has_sync_dialogue and run_status == "可运行" and not has_clean_frame:
        return "可运行同步对白缺少干净首帧或已验收续接帧；预览标签不能绕过"
    return None


def parse_markdown(path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    text = path.read_text(encoding="utf-8")
    headings = list(SEGMENT_RE.finditer(text))
    segments: list[dict[str, Any]] = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        block = text[match.start():end]
        prompt_match = PROMPT_RE.search(block)
        if not prompt_match:
            raise ValueError(f"V{match.group(1)} 缺少完成提示词代码块")
        rows = [
            {
                "number": int(number), "asset": asset.strip(),
                "mediaType": media_type.strip(), "semantic": semantic.strip(),
            }
            for number, asset, media_type, semantic in MIXED_RE.findall(block)
        ]
        if [row["number"] for row in rows] != list(range(1, len(rows) + 1)):
            raise ValueError(f"V{match.group(1)} Mixed 必须从 1 连续递增")
        sound = scalar(block, "声音")
        run_status = scalar(block, "运行状态")
        audio_rows = [row for row in rows if kind_for_media(row["mediaType"]) == "音频"]
        planning_rows = [row["asset"] for row in rows if PLANNING_RE.search(row["asset"])]
        prompt = prompt_match.group(1).strip()
        has_text_voice = bool(DIALOGUE_RE.search(prompt) or OS_VO_RE.search(prompt))
        voice_slots = [
            row["asset"] for row in audio_rows
            if VOICE_SLOT_RE.search(f"{row['asset']} {row['mediaType']}")
        ]
        blocked: list[str] = []
        if voice_slots:
            blocked.append(f"音色仍是占位槽 {voice_slots}")
        if run_status == "阻塞":
            blocked.append("运行状态为阻塞")
        if planning_rows:
            blocked.append(f"规划资产禁止进入输入边：{planning_rows}")
        if has_text_voice and (sound != "开启" or not audio_rows):
            blocked.append("含台词/OS/VO/旁白，必须声明声音开启并绑定独立音色 audio-input")
        frame_block = clean_frame_block_reason(prompt, rows, run_status)
        if frame_block:
            blocked.append(frame_block)
        segments.append(
            {
                "number": match.group(1), "title": match.group(2).strip(),
                "duration": int(scalar(block, "时长").removesuffix("秒")),
                "sound": sound, "prompt": prompt, "mixed": rows, "blocked": blocked,
            }
        )
    if not segments:
        raise ValueError("Markdown 中没有生成段")
    return {
        "model": scalar(text, "模型"), "ratio": scalar(text, "画幅"),
        "resolution": scalar(text, "分辨率").lower(),
    }, segments


def compile_prompt(segment: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    by_number = {row["number"]: row for row in segment["mixed"]}
    counters = {"图片": 0, "视频": 0, "音频": 0}
    compiled_rows: list[dict[str, Any]] = []
    for row in segment["mixed"]:
        kind = kind_for_media(row["mediaType"])
        counters[kind] += 1
        copied = dict(row)
        copied["kind"] = kind
        copied["kindIndex"] = counters[kind]
        copied["nodeType"] = expected_node_type(row["mediaType"])
        compiled_rows.append(copied)

    rows_by_number = {row["number"]: row for row in compiled_rows}
    used: set[int] = set()

    def replacement(match: re.Match[str]) -> str:
        number = int(match.group("number"))
        row = rows_by_number.get(number)
        if row is None:
            raise ValueError(f"V{segment['number']} 提示词引用未知 Mixed {number}")
        semantic = match.group("label").strip()
        declared = row["semantic"].strip().removeprefix("@[").removesuffix("]")
        if normalized(semantic) != normalized(declared):
            raise ValueError(
                f"V{segment['number']} Mixed {number} 语义不一致：提示词 {semantic} / 表格 {declared}"
            )
        used.add(number)
        return f"{row['kind']}{row['kindIndex']}（{semantic}）"

    prompt = MIXED_BINDING_RE.sub(replacement, segment["prompt"])

    def replace_bare(match: re.Match[str]) -> str:
        number = int(match.group("number"))
        row = rows_by_number.get(number)
        if row is None:
            raise ValueError(f"V{segment['number']} 正文引用未知 Mixed {number}")
        semantic = row["semantic"].strip().removeprefix("@[").removesuffix("]")
        used.add(number)
        return f"{row['kind']}{row['kindIndex']}（{semantic}）"

    prompt = BARE_MIXED_RE.sub(replace_bare, prompt)
    missing = sorted(set(by_number) - used)
    if missing:
        raise ValueError(f"V{segment['number']} 输入表存在未绑定素材：{missing}")
    if re.search(r"\{\{(?:Mixed|Image|Portrait)\s+\d+\}\}|\bMixed\s+\d+\b", prompt):
        raise ValueError(f"V{segment['number']} 编译后仍残留 LibTV token")
    return prompt, compiled_rows


def validate_reference_budget(
    segment_number: str,
    segment_prompt: str,
    rows: list[dict[str, Any]],
    duration: int,
) -> None:
    counts = {kind: sum(row["kind"] == kind for row in rows) for kind in ("图片", "视频", "音频")}
    counts["总计"] = sum(counts.values())
    over = [f"{kind}={counts[kind]}>{limit}" for kind, limit in REFERENCE_LIMITS.items() if counts[kind] > limit]
    if over:
        raise ValueError(
            f"V{segment_number} 超过 Seedance 2.0 Rule of 12：{', '.join(over)}；"
            "请拆段或移除非核心道具/背景资产"
        )
    if "主体标签锁定：" not in segment_prompt:
        raise ValueError(f"V{segment_number} 缺少稳定主体标签锁定行")
    quality_errors, _quality_warnings = prompt_quality_messages(
        segment_prompt,
        duration,
        has_character_references=any(
            str(row.get("asset") or "").startswith("独立身份图-") for row in rows
        ),
    )
    if quality_errors:
        raise ValueError(
            f"V{segment_number} Seedance 快节奏提示词门禁失败：{'；'.join(quality_errors)}"
        )


def compile_canvas_prompt(prompt: str, rows: list[dict[str, Any]]) -> str:
    """Replace model-facing 图片N text with the canvas editor's node-id mention token."""
    result = prompt
    for row in rows:
        node_id = str(row.get("nodeId") or "")
        if not node_id:
            raise ValueError(f"素材 {row['asset']} 缺少 TVMao 节点 ID，无法建立画布引用")
        numbered = f"{row['kind']}{row['kindIndex']}"
        token = f"@[{row['kind']}:{node_id}]"
        # Python's ``\w`` includes CJK characters, so a natural phrase such as
        # “图片5与图片6” used to make the second reference look embedded in a
        # word. Only ASCII identifier characters and an existing mention sigil
        # should block replacement here.
        result, count = re.subn(
            rf"(?<![A-Za-z0-9_@]){re.escape(numbered)}(?=（)", token, result
        )
        if count == 0:
            raise ValueError(f"素材 {row['asset']} 没有可转换的 {numbered} 引用")
    return result


def serialize_canvas_prompt(prompt: str, rows: list[dict[str, Any]]) -> str:
    """Mirror PromptMentionEditor.serializeMentionPrompt from huabu_studio."""
    counters = {"图片": 0, "视频": 0, "音频": 0}
    labels: dict[tuple[str, str], str] = {}
    for row in rows:
        kind = row["kind"]
        counters[kind] += 1
        labels[(kind, str(row.get("nodeId") or ""))] = f"{kind}{counters[kind]}"

    def replacement(match: re.Match[str]) -> str:
        key = (match.group("kind"), match.group("node_id"))
        if key not in labels:
            raise ValueError(f"画布提示词引用未连线节点：{match.group(0)}")
        return labels[key]

    return CANVAS_MENTION_RE.sub(replacement, prompt)


def parse_mapping(values: list[str], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{label} 必须使用 左值=节点ID：{value}")
        key, node = value.split("=", 1)
        key = key.strip()
        node = node.strip()
        if not key or not node:
            raise ValueError(f"{label} 映射不能为空：{value}")
        result[key] = node
    return result


def resolve_sync_mode(
    *, fresh_set: bool, only: str | None, node_mapping: dict[str, str]
) -> str:
    """Resolve the write contract before any TVMao mutation is allowed."""
    if fresh_set and only:
        raise ValueError(
            "--fresh-set 表示整集全量新建，禁止同时使用 --only；"
            "不得只挑选被认为‘受影响’的段"
        )
    if fresh_set and node_mapping:
        raise ValueError(
            "--fresh-set 禁止使用 --node；旧视频节点必须冻结保留，"
            "V01–VNN 每段都创建新的 video-generator"
        )
    if fresh_set:
        return "fresh-set"
    if node_mapping:
        return "update-idle"
    return "create-selected" if only else "create-all"


def mapping_lookup(mapping: dict[str, str], row: dict[str, Any]) -> str | None:
    candidates = [row["asset"], row["semantic"], row["semantic"].strip("@[]")]
    matches = {
        value for key, value in mapping.items()
        if any(normalized(key) == normalized(candidate) for candidate in candidates)
    }
    if len(matches) > 1:
        raise ValueError(f"素材 {row['asset']} 命中多个 --asset 节点：{sorted(matches)}")
    return next(iter(matches), None)


def object_id(value: dict[str, Any]) -> str:
    return str(value.get("id") or value.get("nodeId") or value.get("nodeKey") or "")


def response_node_id(value: Any) -> str:
    if isinstance(value, dict):
        direct = object_id(value)
        if direct:
            return direct
        for key in ("node", "data", "result"):
            found = response_node_id(value.get(key))
            if found:
                return found
    return ""


def resolve_model(defaults: dict[str, str], override: str | None) -> str:
    requested = override or defaults["model"]
    return MODEL_ALIASES.get(requested, requested)


def validate_model_schema(schema: Any, params: dict[str, Any], model_id: str) -> None:
    if not isinstance(schema, dict):
        raise ValueError("tvmao model get 顶层必须是 object")
    if schema.get("available") is False:
        raise ValueError(f"模型当前不可用：{model_id}")
    actual_id = str(schema.get("modelId") or "")
    if actual_id and actual_id != model_id:
        raise ValueError(f"模型解析漂移：请求 {model_id}，返回 {actual_id}")
    input_schema = schema.get("inputSchema")
    properties = input_schema.get("properties") if isinstance(input_schema, dict) else None
    if not isinstance(properties, dict):
        raise ValueError(f"模型 {model_id} 缺少 inputSchema.properties")
    for key, value in params.items():
        spec = properties.get(key)
        if not isinstance(spec, dict):
            raise ValueError(f"模型 {model_id} schema 不支持参数 {key}")
        choices = spec.get("enum")
        if isinstance(choices, list) and value not in choices:
            raise ValueError(f"模型 {model_id} 参数 {key}={value!r} 不在允许集合 {choices}")


def node_type(item: dict[str, Any]) -> str:
    return str(item.get("type") or item.get("nodeType") or "")


def node_status(item: dict[str, Any]) -> str:
    return str(item.get("status") or item.get("runStatus") or "").lower()


def node_model(item: dict[str, Any]) -> str:
    params = item.get("params")
    nested_model = params.get("modelId") or params.get("model") if isinstance(params, dict) else ""
    return str(item.get("modelId") or item.get("model") or nested_model or "")


def edge_from(item: dict[str, Any]) -> str:
    source = item.get("from") or item.get("fromNodeId") or item.get("source")
    if isinstance(source, dict):
        return object_id(source)
    return str(source or "")


def build_detail_for_audit(
    detail: dict[str, Any], rows: list[dict[str, Any]], compliance: dict[str, str]
) -> dict[str, Any]:
    labels_by_id = {row["nodeId"]: row["asset"] for row in rows}
    types_by_id = {row["nodeId"]: row["nodeType"] for row in rows}
    detail = dict(detail.get("node") if isinstance(detail.get("node"), dict) else detail)
    detail["_tvskillInputs"] = [
        {
            "nodeId": row["nodeId"], "type": types_by_id[row["nodeId"]],
            "mediaType": types_by_id[row["nodeId"]], "label": labels_by_id[row["nodeId"]],
            "compliance": compliance.get(row["nodeId"]),
        }
        for row in rows
    ]
    return detail


def build_params_update_command(
    tvmao: str, node_id: str, project: int, params: dict[str, Any], version: int | None
) -> list[str]:
    command = [tvmao, "node", "update", node_id, "--project", str(project)]
    if isinstance(version, int):
        command += ["--snapshot-version", str(version)]
    command += ["--param-string", f"prompt={params['prompt']}"]
    command += ["--param-string", f"ratio={params['ratio']}"]
    command += ["--param-string", f"resolution={params['resolution']}"]
    command += ["--param", f"duration={params['duration']}"]
    return command


def build_rewire_command(
    tvmao: str, node_id: str, project: int, old_ids: list[str], desired_ids: list[str]
) -> list[str]:
    command = [tvmao, "node", "update", node_id, "--project", str(project)]
    for old_id in old_ids:
        command += ["--left-rm", old_id]
    for desired_id in desired_ids:
        command += ["--left", desired_id]
    return command


def plan_create_positions(
    existing_nodes: list[dict[str, Any]], count: int, *, columns: int = 7
) -> list[dict[str, int]]:
    """Place new generators in a visible, non-overlapping grid below the canvas."""
    if count <= 0:
        return []
    positions: list[tuple[float, float, float, float]] = []
    for item in existing_nodes:
        position = item.get("position") if isinstance(item.get("position"), dict) else {}
        size = item.get("size") if isinstance(item.get("size"), dict) else {}
        x = float(position.get("x") or 0)
        y = float(position.get("y") or 0)
        width = float(size.get("width") or 400)
        height = float(size.get("height") or 500)
        positions.append((x, y, width, height))
    left = min((item[0] for item in positions), default=0)
    bottom = max((item[1] + item[3] for item in positions), default=0)
    base_x = math.floor(left / 100) * 100
    base_y = math.ceil((bottom + 200) / 100) * 100
    return [
        {
            "x": int(base_x + (index % columns) * 480),
            "y": int(base_y + (index // columns) * 600),
        }
        for index in range(count)
    ]


def build_create_command(
    tvmao: str, project: int, model_id: str, segment: dict[str, Any],
    desired_ids: list[str], position: dict[str, int],
) -> list[str]:
    command = [
        tvmao, "node", "create", "--project", str(project),
        "--type", "video-generator", "--model", model_id,
        "--param-string", f"prompt={segment['compiledPrompt']}",
        "--param-string", f"ratio={segment['params']['ratio']}",
        "--param-string", f"resolution={segment['params']['resolution']}",
        "--param", f"duration={segment['params']['duration']}",
        "--x", str(position["x"]), "--y", str(position["y"]),
    ]
    for node in desired_ids:
        command += ["--left", node]
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--project", type=int, required=True)
    parser.add_argument("--only", help="仅同步指定段号，逗号分隔，例如 1,2,15")
    parser.add_argument("--asset", action="append", default=[], help="素材名或语义=输入节点ID，可重复")
    parser.add_argument("--node", action="append", default=[], help="现有段号=video-generator节点ID，可重复")
    parser.add_argument(
        "--fresh-set", action="store_true",
        help="整集重建：禁止 --only/--node，并为 Markdown 中每一段创建全新视频节点",
    )
    parser.add_argument("--model", help="覆盖 Markdown 模型；建议使用稳定 modelId")
    parser.add_argument("--tvmao")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    cwd = Path.cwd()
    tvmao = args.tvmao or shutil.which("tvmao") or str(Path.home() / ".tvmao" / "tvmao")
    try:
        defaults, segments = parse_markdown(args.markdown)
        all_segment_numbers = [segment["number"] for segment in segments]
        node_mapping_raw = parse_mapping(args.node, "--node")
        node_mapping = {
            f"{int(key.removeprefix('V')):02d}": value for key, value in node_mapping_raw.items()
        }
        sync_mode = resolve_sync_mode(
            fresh_set=args.fresh_set, only=args.only, node_mapping=node_mapping
        )
        if args.only:
            selected = {f"{int(value):02d}" for value in args.only.split(",") if value.strip()}
            segments = [segment for segment in segments if segment["number"] in selected]
            if not segments:
                raise ValueError("--only 没有匹配任何生成段")
        blocked = [segment for segment in segments if segment["blocked"]]
        if blocked:
            detail = "；".join(
                f"V{segment['number']} {'／'.join(segment['blocked'])}" for segment in blocked
            )
            ready = [segment["number"] for segment in segments if not segment["blocked"]]
            hint = f"；其余段可用 --only {','.join(ready)}" if ready else ""
            raise ValueError(detail + hint)

        asset_mapping = parse_mapping(args.asset, "--asset")
        model_id = resolve_model(defaults, args.model)
        base_params = {
            "ratio": defaults["ratio"], "resolution": defaults["resolution"],
        }
        schema = run([tvmao, "model", "get", model_id], cwd=cwd)

        compiled: list[dict[str, Any]] = []
        missing_assets: set[str] = set()
        for segment in segments:
            prompt, rows = compile_prompt(segment)
            validate_reference_budget(
                segment["number"], segment["prompt"], rows, segment["duration"]
            )
            for row in rows:
                row["nodeId"] = mapping_lookup(asset_mapping, row)
                if not row["nodeId"]:
                    missing_assets.add(row["asset"])
            complete_mapping = all(row["nodeId"] for row in rows)
            canvas_prompt = compile_canvas_prompt(prompt, rows) if complete_mapping else prompt
            params = {
                **base_params, "duration": segment["duration"], "prompt": canvas_prompt,
            }
            validate_model_schema(schema, params, model_id)
            compiled.append({
                **segment, "compiledPrompt": canvas_prompt, "runPrompt": prompt,
                "inputs": rows, "params": params,
            })

        plan = [
            {
                "segment": f"V{segment['number']}",
                "action": "update" if segment["number"] in node_mapping else "create",
                "nodeId": node_mapping.get(segment["number"]),
                "modelId": model_id, "params": segment["params"],
                "runPrompt": segment["runPrompt"],
                "inputs": [
                    {
                        "asset": row["asset"], "semantic": row["semantic"],
                        "nodeId": row["nodeId"], "nodeType": row["nodeType"],
                        "compiledRef": f"{row['kind']}{row['kindIndex']}",
                    }
                    for row in segment["inputs"]
                ],
            }
            for segment in compiled
        ]
        if not args.apply:
            print(compact({
                "mode": "dry-run", "backend": "tvmao", "project": args.project,
                "syncMode": sync_mode,
                "completeEpisode": sync_mode == "fresh-set",
                "sourceSegments": [f"V{number}" for number in all_segment_numbers],
                "modelId": model_id, "missingAssets": sorted(missing_assets), "nodes": plan,
            }))
            return 0
        if missing_assets:
            raise ValueError(
                "TVMao 节点没有可依赖的展示名；--apply 必须显式提供 --asset 素材=节点ID。"
                f"缺少：{sorted(missing_assets)}"
            )

        listed = run([tvmao, "node", "list", "--project", str(args.project)], cwd=cwd)
        if not isinstance(listed, list):
            raise ValueError("tvmao node list 顶层必须是数组")
        by_id = {object_id(item): item for item in listed if isinstance(item, dict) and object_id(item)}
        preexisting_ids = set(by_id)
        create_segments = [
            segment for segment in compiled if segment["number"] not in node_mapping
        ]
        position_by_segment = {
            segment["number"]: position
            for segment, position in zip(
                create_segments, plan_create_positions(listed, len(create_segments))
            )
        }
        for segment in compiled:
            for row in segment["inputs"]:
                item = by_id.get(row["nodeId"])
                if item is None:
                    raise ValueError(f"V{segment['number']} 输入节点不存在：{row['nodeId']}")
                if node_type(item) != row["nodeType"]:
                    raise ValueError(
                        f"V{segment['number']} {row['asset']} 需要 {row['nodeType']}，实际 {node_type(item)}"
                    )

        compliance_payload = run([tvmao, "compliance", "status", "--project", str(args.project)], cwd=cwd)
        compliance = {
            object_id(item): str(item.get("status") or "")
            for item in compliance_payload if isinstance(compliance_payload, list) and isinstance(item, dict)
        }

        results: list[dict[str, Any]] = []
        created_ids: set[str] = set()
        for segment in compiled:
            desired_ids = [row["nodeId"] for row in segment["inputs"]]
            existing_id = node_mapping.get(segment["number"])
            if existing_id:
                existing = run([tvmao, "node", "get", existing_id, "--project", str(args.project)], cwd=cwd)
                if not isinstance(existing, dict):
                    raise ValueError(f"V{segment['number']} node get 顶层必须是 object")
                actual = existing.get("node") if isinstance(existing.get("node"), dict) else existing
                if node_status(actual) != "idle":
                    raise ValueError(
                        f"V{segment['number']} 现有节点状态为 {node_status(actual) or 'unknown'}；只能更新 idle 节点"
                    )
                if node_model(actual) and node_model(actual) != model_id:
                    raise ValueError(
                        f"V{segment['number']} TVMao node update 不能修改模型；现有 {node_model(actual)} / 目标 {model_id}，请新建版本节点"
                    )
                edges = run([tvmao, "edge", "list", "--to", existing_id, "--project", str(args.project)], cwd=cwd)
                if not isinstance(edges, list):
                    raise ValueError("tvmao edge list 顶层必须是数组")
                old_ids = [edge_from(edge) for edge in edges if isinstance(edge, dict) and edge_from(edge)]
                canvas = run([tvmao, "canvas", "get", "--project", str(args.project)], cwd=cwd)
                version = canvas.get("version") if isinstance(canvas, dict) else None
                run(
                    build_params_update_command(
                        tvmao, existing_id, args.project, segment["params"], version
                    ),
                    cwd=cwd,
                )
                if old_ids != desired_ids:
                    # TVMao CLI 2.0.0 expands multi-edge updates into sequential canvas
                    # writes. A fixed snapshot version therefore conflicts with the
                    # command's own second write; rely on idempotent edge operations and
                    # the exact ordered-edge readback below for this phase.
                    run(
                        build_rewire_command(
                            tvmao, existing_id, args.project, old_ids, desired_ids
                        ),
                        cwd=cwd,
                    )
                node_id = existing_id
                action = "updated"
            else:
                expected_position = position_by_segment[segment["number"]]
                command = build_create_command(
                    tvmao, args.project, model_id, segment, desired_ids,
                    expected_position,
                )
                response = run(command, cwd=cwd)
                node_id = response_node_id(response)
                if not node_id:
                    raise ValueError(f"V{segment['number']} 无法从 node create 响应解析节点 ID")
                if node_id in preexisting_ids or node_id in created_ids:
                    raise ValueError(
                        f"V{segment['number']} node create 未返回全新唯一节点 ID：{node_id}"
                    )
                created_ids.add(node_id)
                action = "created"

            detail = run([tvmao, "node", "get", node_id, "--project", str(args.project)], cwd=cwd)
            if not isinstance(detail, dict):
                raise ValueError(f"V{segment['number']} node get 顶层必须是 object")
            edges = run([tvmao, "edge", "list", "--to", node_id, "--project", str(args.project)], cwd=cwd)
            if not isinstance(edges, list):
                raise ValueError("tvmao edge list 顶层必须是数组")
            actual_ids = [edge_from(edge) for edge in edges if isinstance(edge, dict)]
            if actual_ids != desired_ids:
                raise ValueError(f"V{segment['number']} 入边回读不一致：{actual_ids} / {desired_ids}")
            actual_detail = detail.get("node") if isinstance(detail.get("node"), dict) else detail
            if action == "created":
                actual_position = actual_detail.get("position")
                if actual_position != position_by_segment[segment["number"]]:
                    raise ValueError(
                        f"V{segment['number']} 新节点布局回读不一致："
                        f"{actual_position} / {position_by_segment[segment['number']]}"
                    )
            audit_detail = build_detail_for_audit(detail, segment["inputs"], compliance)
            errors, warnings, summary = audit_canvas_nodes.audit_node(audit_detail)
            if errors:
                raise ValueError(f"V{segment['number']} TVMao 回读门禁失败：{errors}")
            results.append({
                "segment": f"V{segment['number']}", "nodeId": node_id,
                "action": action, "position": actual_detail.get("position"),
                "fingerprint": summary["fingerprint"], "warnings": warnings,
            })
        if sync_mode == "fresh-set":
            expected = [f"V{number}" for number in all_segment_numbers]
            actual = [row["segment"] for row in results]
            if actual != expected or any(row["action"] != "created" for row in results):
                raise ValueError(
                    f"整集全新节点集合不完整：expected={expected} actual={actual}"
                )
        print(compact({
            "mode": "applied", "backend": "tvmao", "syncMode": sync_mode,
            "completeEpisode": sync_mode == "fresh-set", "nodes": results,
        }))
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
