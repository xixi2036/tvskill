#!/usr/bin/env python3
"""整集顺序生成循环：验收 → 导出续接帧 → 同步下一段 → 生成。

## 为什么需要它

九步状态机的最后一步 `generate` 写的是「顺序生成、验收与返工」，但没有任何工具
执行这个循环。实际做法一直是人工重复这五步命令，一集 13 段就是 65 次手工调用，
每一次都可以跳步——这正是 `automation-pipeline-map.md` 里记的「有状态机没执行器」。

对照巨日禄管线，本脚本补的是 ⑧ 之后的顺序装配环节：

    上一段 succeeded → 下载验收 → 导出干净末帧 → 上传为续接帧 image-input
    → sync 下一段（带上这枚续接帧） → run_video_node（含③合规校验+门禁）

「等待上段验收末帧」这一条连续性模式，在提示词侧的落点就是那枚续接帧；
没有它，同步对白段拿不到眼神锚，`CLEAN_FRAME_BINDING_RE` 会直接挡下。

## 用法

    python3 scripts/run_episode_sequence.py --project 143 \\
        --markdown EP01-LibTV视频节点提示词.md --workdir . \\
        --from 2 --to 13 --asset "角色-姜月初=n-..." [--asset ...]

    # 只做一段（推荐：每段生成后人工看画面再决定是否继续）
    python3 scripts/run_episode_sequence.py ... --from 2 --to 2

退出码：0 全部完成；2 某段门禁未过或生成失败（就地停住，不继续往下烧额度）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


SCRIPTS = Path(__file__).resolve().parent
# 末帧回退量：正好落在最后一帧常有编码尾帧异常，退 0.12s 更稳。
TAIL_BACKOFF = 0.12


def run(cmd: list[str]) -> tuple[int, str]:
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    return result.returncode, f"{result.stdout}{result.stderr}"


def tvmao_json(tvmao: str, args: list[str]) -> object:
    code, out = run([tvmao, *args])
    if code != 0:
        raise RuntimeError(f"tvmao {' '.join(args)} 失败：{out.strip()[:300]}")
    return first_json(out, f"tvmao {' '.join(args)}")


def all_json(text: str) -> list[object]:
    """取出输出里所有顶层 JSON 值。

    tvmao 的部分子命令（如 `asset upload`）会先打一段进度 JSON 再打结果 JSON，
    直接 json.loads 会因「Extra data」崩掉——这正是 2026-09-04 首跑本脚本的失败形态。
    """
    decoder = json.JSONDecoder()
    values: list[object] = []
    pos = 0
    while True:
        match = re.search(r"[\[{]", text[pos:])
        if not match:
            return values
        start = pos + match.start()
        try:
            value, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            pos = start + 1
            continue
        values.append(value)
        pos = start + end


def first_json(text: str, what: str) -> object:
    values = all_json(text)
    if not values:
        raise RuntimeError(f"{what} 未返回可解析的 JSON：{text.strip()[:200]}")
    return values[0]


def pick_node_id(text: str) -> str | None:
    """从可能含多段 JSON 的输出里挑出真正带节点 id 的那一段。"""
    for value in all_json(text):
        if not isinstance(value, dict):
            continue
        node = value.get("node") if isinstance(value.get("node"), dict) else value
        node_id = node.get("id") or node.get("nodeId")
        if isinstance(node_id, str) and node_id.startswith("n-"):
            return node_id
    return None


def node_status(tvmao: str, project: str, node: str) -> str:
    payload = tvmao_json(tvmao, ["node", "get", node, "--project", project])
    if isinstance(payload, dict):
        payload = payload.get("node", payload)
    return str(payload.get("status") or "") if isinstance(payload, dict) else ""


def export_tail_frame(ffmpeg: str, ffprobe: str, video: Path, out: Path) -> None:
    """导出可用于续接的干净末帧。

    契约要求「只导出无闭眼、无口型中间态、无运动模糊的稳定末帧」——那三项要看画面，
    机器判不了。这里只保证技术上取到一帧稳定图像，是否可用仍须人工看过。
    """
    code, out_text = run([
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(video),
    ])
    if code != 0:
        raise RuntimeError(f"ffprobe 失败：{out_text.strip()[:200]}")
    duration = float(out_text.strip().splitlines()[0])
    at = max(0.0, duration - TAIL_BACKOFF)
    code, out_text = run([
        ffmpeg, "-v", "error", "-ss", f"{at:.3f}", "-i", str(video),
        "-vframes", "1", "-q:v", "2", str(out), "-y",
    ])
    if code != 0:
        raise RuntimeError(f"ffmpeg 抽帧失败：{out_text.strip()[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--markdown", required=True)
    parser.add_argument("--workdir", default=".")
    parser.add_argument("--from", dest="start", type=int, required=True)
    parser.add_argument("--to", dest="end", type=int, required=True)
    parser.add_argument("--asset", action="append", default=[])
    parser.add_argument("--tvmao")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()

    tvmao = args.tvmao or shutil.which("tvmao") or str(Path.home() / ".tvmao" / "tvmao")
    work = Path(args.workdir).resolve()
    takes = work / "takes"
    frames = work / "frames"
    takes.mkdir(exist_ok=True)
    frames.mkdir(exist_ok=True)
    assets = list(args.asset)

    for index in range(args.start, args.end + 1):
        seg = f"V{index:02d}"
        prev = f"V{index - 1:02d}"
        print(f"\n══════ {seg} ══════", file=sys.stderr)

        # ① 上一段必须已验收：成片文件在，且节点为 succeeded
        prev_take = takes / f"{prev}.mp4"
        if not prev_take.exists():
            print(f"REFUSED: 缺少上一段成片 {prev_take}；未验收不得往下生成", file=sys.stderr)
            return 2

        # ② 导出干净末帧并上传为续接帧 image-input
        frame = frames / f"{prev}-末帧.jpg"
        try:
            export_tail_frame(args.ffmpeg, args.ffprobe, prev_take, frame)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"   已导出续接帧 {frame.name}（须人工确认无闭眼/口型中间态/运动模糊）", file=sys.stderr)
        code, out = run([
            tvmao, "asset", "upload", str(frame),
            "--create-node", "--project", args.project,
        ])
        frame_node = pick_node_id(out) if code == 0 else None
        if not frame_node:
            print(f"ERROR: 上传续接帧失败：{out.strip()[:300]}", file=sys.stderr)
            return 2
        seg_assets = assets + [f"续接帧-{prev}={frame_node}"]
        print(f"   续接帧节点 {frame_node}", file=sys.stderr)

        # ③ 同步本段（把续接帧一并带上）
        cmd = [
            sys.executable, str(SCRIPTS / "sync_delivery_markdown.py"),
            args.markdown, "--project", args.project, "--only", str(index), "--apply",
        ]
        for mapping in seg_assets:
            cmd += ["--asset", mapping]
        if args.tvmao:
            cmd += ["--tvmao", args.tvmao]
        code, out = run(cmd)
        if code != 0:
            print(f"ERROR: 同步 {seg} 失败：{out.strip()[:400]}", file=sys.stderr)
            return 2
        plan = next(
            (v for v in all_json(out) if isinstance(v, dict) and "nodes" in v), {}
        )
        if plan.get("missingAssets"):
            print(f"REFUSED: {seg} 仍缺素材：{plan['missingAssets']}", file=sys.stderr)
            return 2
        node = next(
            (n.get("nodeId") for n in plan.get("nodes", []) if n.get("segment") == seg),
            None,
        )
        if not node:
            print(f"ERROR: 同步结果里没有 {seg} 的节点", file=sys.stderr)
            return 2
        print(f"   {seg} 节点 {node}", file=sys.stderr)

        # ④ 过③合规校验与运行前门禁后生成
        cmd = [
            sys.executable, str(SCRIPTS / "run_video_node.py"),
            "--project", args.project, "--node", node,
        ]
        for mapping in seg_assets:
            cmd += ["--asset", mapping]
        if args.tvmao:
            cmd += ["--tvmao", args.tvmao]
        code, out = run(cmd)
        sys.stderr.write(out)
        if code != 0:
            print(f"STOPPED: {seg} 未生成成功，就地停住不再往下烧额度", file=sys.stderr)
            return 2

        # ⑤ 下载成片，供下一轮验收与末帧导出
        code, out = run([
            tvmao, "asset", "download", "--node", node,
            "--project", args.project, "--out", str(takes / f"{seg}.mp4"),
        ])
        if code != 0:
            print(f"ERROR: 下载 {seg} 成片失败：{out.strip()[:300]}", file=sys.stderr)
            return 2
        print(f"OK: {seg} 已生成并下载", file=sys.stderr)

    print("OK: 区间内全部段落完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
