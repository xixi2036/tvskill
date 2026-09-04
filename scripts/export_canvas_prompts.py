#!/usr/bin/env python3
"""把画布上所有节点的提示词导出到本地文件。

## 为什么需要它

2026-09-04 实证：tvmao 服务 TLS 握手连续超时期间，画布只读接口也不可用，
而**11 条资产提示词的原文只存在于画布节点里，本地没有副本**——服务一挂就取不出来，
整条产线只能干等。同批的 12 条起手帧提示词因为当初写到了本地文件，反而不受影响。

**提示词是资产，不该只存在远端。** 资产图丢了可以重生成，
提示词丢了连「原来怎么写的」都无从查起，等于把可复现性交给了服务可用性。

## 用法

    # 导出整张画布的提示词
    python3 scripts/export_canvas_prompts.py --project 143 --out 提示词备份/

    # 只导出图片生成节点
    python3 scripts/export_canvas_prompts.py --project 143 --out 备份/ --type image-generator

产出：每个节点一个 `.txt`（正文即提示词），外加一份 `_manifest.tsv`
（节点 ID / 类型 / 模型 / 状态 / 分辨率 / 入边数 / 文件名），便于事后对账与重建。

退出码：0 成功；1 执行错误；2 画布读取失败。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


def tvmao_json(tvmao: str, args: list[str]) -> object:
    """调 tvmao 并取出第一个完整 JSON 值。

    部分子命令会先打进度 JSON 再打结果 JSON，直接 json.loads 会因
    「Extra data」崩掉，故用 raw_decode 逐段取。
    """
    result = subprocess.run([tvmao, *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"tvmao {' '.join(args)} 失败：{result.stderr.strip()[:300]}")
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", result.stdout):
        try:
            value, _end = decoder.raw_decode(result.stdout[match.start():])
        except json.JSONDecodeError:
            continue
        return value
    raise RuntimeError(f"tvmao {' '.join(args)} 未返回可解析的 JSON")


def safe_name(text: str, fallback: str) -> str:
    """节点没有 label 时用 ID 兜底；文件名去掉路径分隔符与空白。"""
    name = (text or "").strip() or fallback
    name = re.sub(r"[\\/:*?\"<>|\s]+", "_", name)
    return name[:80]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--out", required=True, help="导出目录")
    parser.add_argument("--type", dest="node_type", help="只导出指定类型的节点")
    parser.add_argument("--tvmao")
    args = parser.parse_args()

    tvmao = args.tvmao or shutil.which("tvmao") or str(Path.home() / ".tvmao" / "tvmao")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    try:
        payload = tvmao_json(tvmao, ["node", "list", "--project", args.project])
    except RuntimeError as exc:
        print(f"ERROR: 读取画布失败：{exc}", file=sys.stderr)
        return 2
    items = payload if isinstance(payload, list) else (
        payload.get("items") or payload.get("nodes") or []
    )
    if not items:
        print(f"ERROR: 画布 {args.project} 没有节点", file=sys.stderr)
        return 2

    rows: list[str] = ["node_id\ttype\tmodel\tstatus\tresolution\tinputs\tfile"]
    saved = skipped = failed = 0
    for item in items:
        node_id = item.get("id") or item.get("nodeId")
        node_type = item.get("type") or ""
        if not node_id:
            continue
        if args.node_type and node_type != args.node_type:
            continue
        try:
            detail = tvmao_json(tvmao, ["node", "get", node_id, "--project", args.project])
        except RuntimeError as exc:
            print(f"WARNING: {node_id} 读取失败：{exc}", file=sys.stderr)
            failed += 1
            continue
        if isinstance(detail, dict):
            detail = detail.get("node", detail)
        params = detail.get("params") or {}
        prompt = params.get("prompt") or ""
        if not prompt.strip():
            skipped += 1
            continue
        label = detail.get("label") or detail.get("name") or ""
        filename = f"{safe_name(label, node_id)}__{node_id}.txt"
        (out / filename).write_text(prompt, encoding="utf-8")
        rows.append(
            "\t".join([
                str(node_id), node_type, str(params.get("modelId") or ""),
                str(detail.get("status") or ""), str(params.get("resolution") or ""),
                str(len(detail.get("inputs") or [])), filename,
            ])
        )
        saved += 1

    (out / "_manifest.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"OK: 导出 {saved} 条提示词到 {out}（无提示词节点 {skipped} 个，读取失败 {failed} 个）")
    print(f"    清单：{out / '_manifest.tsv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
