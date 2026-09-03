#!/usr/bin/env python3
"""Create a Markdown technical audit and contact sheets for downloaded takes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}


def run_json(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip())
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("ffprobe 没有返回合法 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("ffprobe 顶层必须是 object")
    return value


def fraction(value: str) -> float:
    try:
        numerator, denominator = value.split("/", 1)
        return float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return 0.0


def media_facts(value: dict[str, Any]) -> dict[str, Any]:
    streams = value.get("streams")
    streams = streams if isinstance(streams, list) else []
    video = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        {},
    )
    audio = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        None,
    )
    format_data = value.get("format")
    format_data = format_data if isinstance(format_data, dict) else {}
    try:
        duration = float(format_data.get("duration") or video.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "duration": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": fraction(str(video.get("avg_frame_rate") or "0/1")),
        "videoCodec": str(video.get("codec_name") or ""),
        "hasAudio": audio is not None,
        "audioCodec": str(audio.get("codec_name") or "") if audio else "",
        "audioChannels": int(audio.get("channels") or 0) if audio else 0,
    }


def probe(path: Path, ffprobe: str) -> dict[str, Any]:
    value = run_json(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    return media_facts(value)


def contact_sheet(path: Path, output: Path, ffmpeg: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            "fps=1,scale=240:-1,tile=5x3",
            "-frames:v",
            "1",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(
            f"{path.name} 接触表生成失败："
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


# 十轴审计里第 4、10 轴此前没有任何机器口径,只能靠人眼数。下面三项用 ffmpeg 自带
# 滤镜给出确定性判据,不引入任何新依赖(freezedetect/silencedetect/ebur128 均为内置)。
# 阈值来源:freezedetect 与 silencedetect 取 ffmpeg 常用保守值;末帧悬空的判定窗口取
# 0.40s,因为 Seedance 段落普遍 4-15s,尾部 0.4s 冻结已足以在成片里被看出"卡住"。
TAIL_FREEZE_WINDOW = 0.40
SILENCE_COVERAGE_LIMIT = 0.90

FREEZE_START_RE = re.compile(r"lavfi\.freezedetect\.freeze_start:\s*([0-9.]+)")
FREEZE_END_RE = re.compile(r"lavfi\.freezedetect\.freeze_end:\s*([0-9.]+)")
SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[0-9.]+)")
SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")
LOUDNESS_RE = re.compile(r"^\s*I:\s*(-?[0-9.]+|-inf)\s*LUFS", re.M)
PEAK_RE = re.compile(r"^\s*Peak:\s*(-?[0-9.]+|-inf)\s*dBFS", re.M)


def _last_float(pattern: re.Pattern[str], text: str) -> float | None:
    hits = pattern.findall(text)
    if not hits:
        return None
    try:
        return float(hits[-1])
    except ValueError:
        return None


def signal_probe(path: Path, duration: float, ffmpeg: str) -> dict[str, Any]:
    """单次 ffmpeg 走查:末帧冻结、静音覆盖率、整体响度与真峰。"""
    result = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-i",
            str(path),
            "-vf",
            "freezedetect=n=-50dB:d=0.30",
            "-af",
            "silencedetect=n=-45dB:d=0.35,ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    text = f"{result.stderr}\n{result.stdout}"

    freeze_starts = [float(v) for v in FREEZE_START_RE.findall(text)]
    freeze_ends = [float(v) for v in FREEZE_END_RE.findall(text)]
    # 末帧悬空:存在一段冻结,其起点之后再没有 freeze_end,或末次 freeze_end 已到片尾窗口内
    tail_freeze_from: float | None = None
    if freeze_starts:
        last_start = freeze_starts[-1]
        closed = [end for end in freeze_ends if end > last_start]
        if not closed or (duration and duration - closed[-1] <= TAIL_FREEZE_WINDOW):
            tail_freeze_from = last_start

    silence_starts = [float(v) for v in SILENCE_START_RE.findall(text)]
    silence_ends = [float(v) for v in SILENCE_END_RE.findall(text)]
    silent = 0.0
    for index, start in enumerate(silence_starts):
        end = silence_ends[index] if index < len(silence_ends) else duration
        if end > start:
            silent += end - start
    coverage = (silent / duration) if duration else 0.0

    return {
        "tailFreezeFrom": tail_freeze_from,
        "silenceCoverage": round(min(coverage, 1.0), 3),
        "loudnessLufs": _last_float(LOUDNESS_RE, text),
        "truePeakDb": _last_float(PEAK_RE, text),
    }


def signal_findings(row: dict[str, Any]) -> list[str]:
    """把探测结果翻译成十轴口径的硬伤。空列表表示这三轴机器侧通过。"""
    findings: list[str] = []
    tail = row.get("tailFreezeFrom")
    if tail is not None:
        findings.append(f"末帧动作悬空：{tail:.2f}s 起画面冻结直到片尾")
    coverage = row.get("silenceCoverage")
    if row.get("hasAudio") and coverage is not None and coverage >= SILENCE_COVERAGE_LIMIT:
        findings.append(f"缺少应有音轨：静音覆盖 {coverage:.0%}，音轨存在但几乎无声")
    return findings


def markdown(root: Path, rows: list[dict[str, Any]], contact_dir: Path | None) -> str:
    with_audio = sum(bool(row["hasAudio"]) for row in rows)
    lines = [
        "# TVSkill 下载成片技术审计",
        "",
        f"- 目录：`{root}`",
        f"- 视频：{len(rows)}",
        f"- 有音轨：{with_audio}",
        f"- 无音轨：{len(rows) - with_audio}",
        "",
        "| 文件 | 时长 | 画面 | FPS | 视频编码 | 音轨 |",
        "|---|---:|---|---:|---|---|",
    ]
    for row in rows:
        audio = (
            f"{row['audioCodec']} / {row['audioChannels']}ch"
            if row["hasAudio"]
            else "无"
        )
        lines.append(
            f"| {row['name']} | {row['duration']:.2f}s | "
            f"{row['width']}×{row['height']} | {row['fps']:.2f} | "
            f"{row['videoCodec']} | {audio} |"
        )
    if contact_dir:
        lines.extend(["", f"- 接触表：`{contact_dir}`"])

    probed = [row for row in rows if "silenceCoverage" in row]
    if probed:
        lines.extend(
            [
                "",
                "## 信号闸（第 4、10 轴的机器口径）",
                "",
                "| 文件 | 末帧冻结 | 静音覆盖 | 整体响度 | 真峰 | 判定 |",
                "|---|---|---:|---:|---:|---|",
            ]
        )
        for row in probed:
            tail = row.get("tailFreezeFrom")
            lufs = row.get("loudnessLufs")
            peak = row.get("truePeakDb")
            findings = row.get("findings") or []
            lines.append(
                f"| {row['name']} "
                f"| {'—' if tail is None else f'{tail:.2f}s 起'} "
                f"| {row['silenceCoverage']:.0%} "
                f"| {'—' if lufs is None else f'{lufs:.1f} LUFS'} "
                f"| {'—' if peak is None else f'{peak:.1f} dBFS'} "
                f"| {'；'.join(findings) if findings else '通过'} |"
            )
        lines.extend(
            [
                "",
                "> 信号闸只判机器可判的部分：末帧是否冻结、音轨是否几乎全静、响度落点。",
                "> 它不替代第 4、10 轴的观看结论——听得清不等于说对了，画面动不等于动得对。",
            ]
        )

    lines.extend(
        [
            "",
            "## 观察审计",
            "",
            "技术检查不能替代观看和复听。逐片补齐以下十轴结论：",
            "",
            "1. 节点与参考；",
            "2. 人物身份；",
            "3. 表演与眼神；",
            "4. 对白与声音；",
            "5. 空间与人群；",
            "6. 动作、道具与物理；",
            "7. 镜头与剪辑；",
            "8. 光影、质感与风格；",
            "9. 文字与画面卫生；",
            "10. 边界连续性。",
            "",
            "每片最终判定只能为：保留、后期修复、局部编辑、重抽、重写/拆段。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--contact-sheets", action="store_true")
    parser.add_argument("--contact-dir", type=Path)
    parser.add_argument("--signal-gates", action="store_true",
                        help="额外跑末帧冻结/静音覆盖/响度探测；命中硬伤时退出码为 2")
    parser.add_argument("--ffprobe")
    parser.add_argument("--ffmpeg")
    args = parser.parse_args()
    ffprobe = args.ffprobe or shutil.which("ffprobe")
    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    try:
        if not ffprobe:
            raise ValueError("找不到 ffprobe")
        if args.contact_sheets and not ffmpeg:
            raise ValueError("生成接触表需要 ffmpeg")
        if args.signal_gates and not ffmpeg:
            raise ValueError("信号闸探测需要 ffmpeg")
        files = sorted(
            path
            for path in args.directory.iterdir()
            if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
        )
        if not files:
            raise ValueError("目录中没有支持的视频文件")
        contact_dir = (
            args.contact_dir
            or (args.directory / "qc" if args.contact_sheets else None)
        )
        rows: list[dict[str, Any]] = []
        for path in files:
            facts = probe(path, ffprobe)
            row = {"name": path.name, **facts}
            if args.signal_gates:
                row.update(signal_probe(path, float(facts.get("duration") or 0.0), ffmpeg))
                row["findings"] = signal_findings(row)
            rows.append(row)
            if args.contact_sheets and contact_dir:
                contact_sheet(path, contact_dir / f"{path.stem}-contact.jpg", ffmpeg)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            markdown(args.directory, rows, contact_dir),
            encoding="utf-8",
        )
        flagged = [row for row in rows if row.get("findings")]
        print(
            f"OK: videos={len(rows)} audio={sum(row['hasAudio'] for row in rows)} "
            f"report={args.out}"
        )
        if flagged:
            for row in flagged:
                for finding in row["findings"]:
                    print(f"HARD: {row['name']} {finding}", file=sys.stderr)
            print(f"HARD: 信号闸命中 {len(flagged)} 条成片", file=sys.stderr)
            return 2
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

