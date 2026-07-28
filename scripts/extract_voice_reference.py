#!/usr/bin/env python3
"""Extract and verify one character's approximately five-second WAV voice reference."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import wave


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="历史成片路径")
    parser.add_argument("output", type=Path, help="输出 .wav 路径")
    parser.add_argument("--start", type=float, default=0.0, help="裁切起点秒数")
    parser.add_argument("--duration", type=float, default=5.0, help="输出时长，限 4.5–5.5 秒")
    parser.add_argument("--ffmpeg", help="ffmpeg 可执行文件路径")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"输入成片不存在：{args.input}")
    if args.output.suffix.lower() != ".wav":
        parser.error("输出必须使用 .wav 扩展名")
    if not 4.5 <= args.duration <= 5.5:
        parser.error("--duration 必须在 4.5–5.5 秒之间")
    if args.start < 0:
        parser.error("--start 不能为负数")

    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        parser.error("未找到 ffmpeg；请安装后重试，或通过 --ffmpeg 指定路径")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-ss",
        str(args.start),
        "-i",
        str(args.input),
        "-t",
        str(args.duration),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "48000",
        "-af",
        "highpass=f=80,lowpass=f=12000,loudnorm=I=-18:TP=-2:LRA=7",
        "-c:a",
        "pcm_s16le",
        str(args.output),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        print(result.stderr.strip() or "ffmpeg 裁切失败", file=sys.stderr)
        return 1

    with wave.open(str(args.output), "rb") as audio:
        channels = audio.getnchannels()
        rate = audio.getframerate()
        duration = audio.getnframes() / rate
    if channels != 1 or rate != 48000 or not 4.4 <= duration <= 5.6:
        print(
            f"输出校验失败：channels={channels} rate={rate} duration={duration:.3f}",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: {args.output} duration={duration:.3f}s rate={rate}Hz channels={channels}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
