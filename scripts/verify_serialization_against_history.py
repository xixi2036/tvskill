#!/usr/bin/env python3
"""用画布上已成功节点的真实提交内容，反验 serialize_canvas_prompt 的预测。

背景：`audit_canvas_nodes.serialize_canvas_prompt` 声称镜像网页端 model-facing
序列化，但"审计预测的模型输入"与"模型真收到的输入"是否相等，长期无法直接验证——
除非跑一次生成再人工比对，而视频是一次性预算，不能为验证而消耗。

2026-09-04 发现 `tvmao node get` 返回的 `history[N].prompt` 记录的正是**实际提交
给模型的 prompt**（已序列化、无 canonical mention）。这提供了一条零成本的
ground truth 通道：拿存储 prompt 跑一遍本地序列化，与 history 里的实际提交对拍。

用法：
    python3 scripts/verify_serialization_against_history.py --project 138
    python3 scripts/verify_serialization_against_history.py --project 138 --node n-abc

退出码：0 全部一致；2 存在不一致；1 执行错误。

注意：本脚本只调用 `node list` / `node get` / `edge list` 三个只读命令，
不创建、不修改、不运行任何节点。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import audit_canvas_nodes  # noqa: E402


def cli_json(tvmao: str, args: list[str]) -> Any:
    result = subprocess.run([tvmao, *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"tvmao {' '.join(args)} 失败：{result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"tvmao {' '.join(args)} 没有返回合法 JSON") from exc


def compare_node(
    tvmao: str, project: str, node_id: str, node_types: dict[str, str]
) -> dict[str, Any] | None:
    """返回比对结果；节点没有可比材料时返回 None。"""
    detail = cli_json(tvmao, ["node", "get", node_id, "--project", project])
    stored = str((detail.get("params") or {}).get("prompt") or "")
    history = detail.get("history") or []
    if not stored or "@[" not in stored:
        return None
    if not history or not isinstance(history, list):
        return None
    actual = str(history[0].get("prompt") or "")
    if not actual:
        return None

    edges = cli_json(tvmao, ["edge", "list", "--to", node_id, "--project", project])
    inputs = [
        {
            "nodeId": edge["fromNodeId"],
            # 入边类型决定各媒体的独立计数，必须用真实类型，
            # 一律当成 image-input 会让音频 mention 匹配不上而被误判为不一致。
            "type": node_types.get(edge["fromNodeId"], "image-input"),
            "label": "",
        }
        for edge in (edges if isinstance(edges, list) else [])
    ]
    predicted, _errors, _count = audit_canvas_nodes.serialize_canvas_prompt(stored, inputs)
    return {
        "nodeId": node_id,
        "match": predicted.rstrip() == actual.rstrip(),
        "predicted": predicted,
        "actual": actual,
        "inputKinds": [node_types.get(e["fromNodeId"], "?") for e in (edges if isinstance(edges, list) else [])],
    }


def first_difference(predicted: str, actual: str) -> str:
    for index in range(min(len(predicted), len(actual))):
        if predicted[index] != actual[index]:
            lo = max(0, index - 45)
            return (
                f"      预测：…{predicted[lo:index + 45]}…\n"
                f"      实际：…{actual[lo:index + 45]}…"
            )
    return f"      长度不同：预测 {len(predicted)} / 实际 {len(actual)}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--node", help="只验单个节点；省略则验全部已成功的视频节点")
    parser.add_argument("--tvmao")
    args = parser.parse_args()
    tvmao = args.tvmao or shutil.which("tvmao") or str(Path.home() / ".tvmao" / "tvmao")
    try:
        if not Path(tvmao).exists() and not shutil.which(tvmao):
            raise ValueError(f"找不到 tvmao CLI：{tvmao}")
        nodes = cli_json(tvmao, ["node", "list", "--project", args.project])
        if not isinstance(nodes, list):
            raise ValueError("node list 顶层必须是数组")
        node_types = {str(n.get("id")): str(n.get("type") or "") for n in nodes}

        if args.node:
            targets = [args.node]
        else:
            targets = [
                str(n["id"])
                for n in nodes
                if n.get("type") == "video-generator" and n.get("status") == "succeeded"
            ]
        if not targets:
            print("没有可验证的已成功视频节点", file=sys.stderr)
            return 1

        matched = 0
        mismatched: list[dict[str, Any]] = []
        skipped = 0
        for node_id in targets:
            outcome = compare_node(tvmao, args.project, node_id, node_types)
            if outcome is None:
                skipped += 1
                continue
            if outcome["match"]:
                matched += 1
            else:
                mismatched.append(outcome)

        print(f"一致 {matched} / 不一致 {len(mismatched)} / 跳过 {skipped}（无 history 或无 mention）")
        for outcome in mismatched:
            print(f"  MISMATCH {outcome['nodeId']}  入边类型={outcome['inputKinds']}", file=sys.stderr)
            print(first_difference(outcome["predicted"], outcome["actual"]), file=sys.stderr)
        return 2 if mismatched else 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
