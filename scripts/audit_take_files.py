#!/usr/bin/env python3
"""Create a Markdown technical audit and contact sheets for downloaded takes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
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
            rows.append({"name": path.name, **facts})
            if args.contact_sheets and contact_dir:
                contact_sheet(path, contact_dir / f"{path.stem}-contact.jpg", ffmpeg)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            markdown(args.directory, rows, contact_dir),
            encoding="utf-8",
        )
        print(
            f"OK: videos={len(rows)} audio={sum(row['hasAudio'] for row in rows)} "
            f"report={args.out}"
        )
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

