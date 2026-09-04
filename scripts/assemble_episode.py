#!/usr/bin/env python3
"""整集装配：按段序拼接成片，并按剧本时码烧录字幕。

## 它补的是哪一节

对照巨日禄管线，这是 ⑪「导出：剪映草稿 / 前端预览成片」。tvskill 此前止步于 ⑧，
每段成片下载到本地就结束了，没有任何工具把它们装配成一集。

## 字幕为什么由本脚本承担而不是模型

视频提示词一律写「保持无字幕，不生成可辨识文字」——让模型渲染汉字既不可靠、
也会污染画面。字幕是后期通道：本脚本从**原剧本抽出的台词单元**取字，时码取自
剧本自带的 `[MM:SS]`，因此字幕与剧本逐字一致，不受生成结果影响。

《万妖图录传》参考成片正是这个做法：画面无字，字幕与人物名牌都是后期叠加。

## 用法

    python3 scripts/assemble_episode.py --workdir . --script 01-第01集.docx \\
        --episode 1 --out 成片/EP01.mp4

    # 不烧字幕，只拼接
    python3 scripts/assemble_episode.py ... --no-subtitles

退出码：0 成功；2 段落缺失或时长与剧本不符；1 执行错误。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

# 逐段响度归一目标：短剧成片的常用落点。
LOUDNESS_TARGET = "I=-16:TP=-1.5:LRA=11"

# 一句字幕最长停留时间：超过它多半是下一句缺时码，宁可短也不要糊在屏幕上。
MAX_CUE_SECONDS = 6.0
MIN_CUE_SECONDS = 1.2


def srt_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d},{int(round((secs % 1) * 1000)):03d}"


def map_to_actual(start: float, seg_seconds: float, durations: list[float]) -> float:
    """把剧本时码映射到实际成片时间轴。

    剧本时码假定每段正好 seg_seconds 秒，实际每段是模型返回的时长
    （2026-09-04 实测 12s 段返回 12.096s）。不映射的话误差按段累积——
    13 段下来字幕会比语音晚约 1.2 秒，越到后面越明显。
    """
    if not durations:
        return start
    index = min(int(start // seg_seconds), len(durations) - 1)
    within = start - index * seg_seconds
    scale = durations[index] / seg_seconds if seg_seconds else 1.0
    return sum(durations[:index]) + within * scale


def build_srt(
    script: Path, episode: int | None, total: float,
    durations: list[float] | None = None, seg_seconds: float = 12.0,
) -> str:
    """从原剧本的台词单元生成 SRT：字取剧本原文，时码取剧本自带 [MM:SS]。

    时码再按实际段时长映射到成片时间轴，避免逐段累积漂移。
    """
    import extract_script_units as extractor

    units = extractor.extract(
        extractor.read_paragraphs(script), episode, extractor.VOICE_KINDS
    )
    cues: list[tuple[float, str]] = []
    for unit in units:
        text = str(unit["text"])
        stamp = re.search(r"\[(\d{1,3}):(\d{2})(?::(\d{2}))?\]", text)
        if not stamp:
            continue
        start = int(stamp.group(1)) * 60 + int(stamp.group(2))
        if stamp.group(3):
            start = int(stamp.group(1)) * 3600 + int(stamp.group(2)) * 60 + int(stamp.group(3))
        line = text.split("]", 1)[1].strip()
        if line:
            cues.append((map_to_actual(float(start), seg_seconds, durations or []), line))
    if not cues:
        return ""
    blocks: list[str] = []
    for index, (start, line) in enumerate(cues, 1):
        nxt = cues[index][0] if index < len(cues) else total
        end = min(start + MAX_CUE_SECONDS, max(nxt - 0.08, start + MIN_CUE_SECONDS))
        end = min(end, total)
        if end <= start:
            continue
        blocks.append(f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{line}\n")
    return "\n".join(blocks)



# 参考成片的字幕形态：白字、黑描边、居中、贴近下缘。
SUB_FONT_CANDIDATES = (
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/PingFang.ttc",
)


def parse_srt(srt_text: str) -> list[tuple[float, float, str]]:
    cues: list[tuple[float, float, str]] = []
    for block in srt_text.strip().split("\n\n"):
        lines = [x for x in block.splitlines() if x.strip()]
        if len(lines) < 3:
            continue
        stamp = re.match(
            r"(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)", lines[1]
        )
        if not stamp:
            continue
        g = [int(x) for x in stamp.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        cues.append((start, end, " ".join(lines[2:])))
    return cues


def burn_with_overlay(args, merged: Path, srt_text: str, out: Path):
    """没有 subtitles 滤镜时的硬烧路径：Pillow 渲字幕图 + ffmpeg overlay。

    字幕是这类短剧的主叙事通道，退成软字幕等于把主通道关掉，所以先走这条。
    返回 True 表示成功；返回 str 表示不可用的原因。
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return "缺少 Pillow"
    font_path = next((f for f in SUB_FONT_CANDIDATES if Path(f).exists()), None)
    if not font_path:
        return "找不到可用中文字体"
    cues = parse_srt(srt_text)
    if not cues:
        return "SRT 解析不出字幕行"

    probe = subprocess.run(
        [args.ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(merged)],
        text=True, capture_output=True, check=False,
    )
    if probe.returncode != 0:
        return "读不到视频尺寸"
    width, height = (int(x) for x in probe.stdout.strip().split(",")[:2])

    size = max(18, int(height * 0.058))
    try:
        font = ImageFont.truetype(font_path, size)
    except OSError as exc:
        return f"字体加载失败：{exc}"

    sub_dir = out.parent / (out.stem + "-字幕图")
    if sub_dir.exists():
        shutil.rmtree(sub_dir)
    sub_dir.mkdir(parents=True)
    pngs: list[Path] = []
    for index, (_s, _e, line) in enumerate(cues):
        image = Image.new("RGBA", (width, size * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        box = draw.textbbox((0, 0), line, font=font, stroke_width=3)
        x = (width - (box[2] - box[0])) // 2 - box[0]
        y = (size * 2 - (box[3] - box[1])) // 2 - box[1]
        draw.text(
            (x, y), line, font=font, fill=(255, 255, 255, 255),
            stroke_width=3, stroke_fill=(0, 0, 0, 255),
        )
        png = sub_dir / f"cue{index:03d}.png"
        image.save(png)
        pngs.append(png)

    cmd = [args.ffmpeg, "-v", "error", "-i", str(merged)]
    for png in pngs:
        cmd += ["-i", str(png)]
    margin = max(12, int(height * 0.045))
    chain: list[str] = []
    label = "0:v"
    for index, (start, end, _line) in enumerate(cues):
        nxt = f"v{index}"
        chain.append(
            f"[{label}][{index + 1}:v]overlay=x=0:y=H-h-{margin}:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{nxt}]"
        )
        label = nxt
    cmd += [
        "-filter_complex", ";".join(chain),
        "-map", f"[{label}]", "-map", "0:a?",
        "-c:v", "libx264", "-crf", "18", "-c:a", "copy", str(out), "-y",
    ]
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return f"overlay 烧录失败：{result.stderr.strip()[:200]}"
    return True


def probe_duration(ffprobe: str, path: Path) -> float:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        text=True, capture_output=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 失败：{result.stderr.strip()[:200]}")
    return float(result.stdout.strip().splitlines()[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", default=".")
    parser.add_argument("--script", type=Path, help="原剧本，用于生成字幕")
    parser.add_argument("--episode", type=int)
    parser.add_argument("--out", required=True)
    parser.add_argument("--no-subtitles", action="store_true")
    parser.add_argument("--no-normalize", action="store_true", help="跳过逐段响度归一")
    parser.add_argument("--font", default="PingFang SC")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()

    if not shutil.which(args.ffmpeg) or not shutil.which(args.ffprobe):
        print("ERROR: 找不到 ffmpeg/ffprobe", file=sys.stderr)
        return 1

    work = Path(args.workdir).resolve()
    takes = sorted(
        (p for p in (work / "takes").glob("V*.mp4") if re.fullmatch(r"V\d{2}", p.stem)),
        key=lambda p: p.stem,
    )
    if not takes:
        print(f"ERROR: {work / 'takes'} 下没有 V01.mp4 这样的段落成片", file=sys.stderr)
        return 2

    expected = [f"V{i:02d}" for i in range(1, len(takes) + 1)]
    actual = [p.stem for p in takes]
    if actual != expected:
        print(
            f"REFUSED: 段落不连续，缺段即为画面丢失。\n  期望：{expected}\n  实际：{actual}",
            file=sys.stderr,
        )
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 逐段响度归一：各段是独立生成任务，响度落点差异很大
    # （2026-09-04 实测 EP01 七段跨度 -12.6 ~ -25.0 LUFS，12.4 dB）。
    # 不归一就直接拼，成片音量忽大忽小，是成片级缺陷而非小瑕疵。
    concat_sources = takes
    if not args.no_normalize:
        norm_dir = work / "takes" / "_normalized"
        norm_dir.mkdir(exist_ok=True)
        normalized: list[Path] = []
        for take in takes:
            target = norm_dir / take.name
            result = subprocess.run(
                [args.ffmpeg, "-v", "error", "-i", str(take),
                 "-c:v", "copy", "-af", f"loudnorm={LOUDNESS_TARGET}",
                 "-c:a", "aac", "-b:a", "192k", str(target), "-y"],
                text=True, capture_output=True, check=False,
            )
            if result.returncode != 0:
                print(
                    f"WARNING: {take.name} 响度归一失败，改用原始音轨："
                    f"{result.stderr.strip()[:160]}",
                    file=sys.stderr,
                )
                normalized.append(take)
            else:
                normalized.append(target)
        concat_sources = normalized
        print(f"已逐段归一响度到 {LOUDNESS_TARGET}", file=sys.stderr)

    listing = (concat_sources[0].parent) / "_concat.txt"
    listing.write_text(
        "".join(f"file '{p.name}'\n" for p in concat_sources), encoding="utf-8"
    )

    merged = out.with_name(out.stem + "-无字幕" + out.suffix)
    # 各段来自同一模型同一参数，编码一致，可以走 concat demuxer 直接流拷贝。
    result = subprocess.run(
        [args.ffmpeg, "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", str(merged), "-y"],
        text=True, capture_output=True, check=False,
    )
    if result.returncode != 0:
        # 参数不一致时退回重编码，保证一定能出片。
        result = subprocess.run(
            [args.ffmpeg, "-v", "error", "-f", "concat", "-safe", "0",
             "-i", str(listing), "-c:v", "libx264", "-crf", "18",
             "-c:a", "aac", "-b:a", "192k", str(merged), "-y"],
            text=True, capture_output=True, check=False,
        )
        if result.returncode != 0:
            print(f"ERROR: 拼接失败：{result.stderr.strip()[:300]}", file=sys.stderr)
            return 2

    take_durations = [probe_duration(args.ffprobe, p) for p in concat_sources]
    total = probe_duration(args.ffprobe, merged)
    print(f"拼接完成：{len(takes)} 段 / {total:.2f}s → {merged}", file=sys.stderr)

    if args.no_subtitles or args.script is None:
        shutil.move(str(merged), str(out))
        print(f"OK: {out}（未烧字幕）")
        return 0

    srt_text = build_srt(args.script, args.episode, total, take_durations)
    if not srt_text:
        shutil.move(str(merged), str(out))
        print(f"OK: {out}（原剧本没有带时码的台词，未烧字幕）")
        return 0
    srt = out.with_suffix(".srt")
    srt.write_text(srt_text, encoding="utf-8")

    style = (
        f"FontName={args.font},FontSize=20,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
        "Alignment=2,MarginV=28"
    )
    # subtitles 滤镜的路径转义极易写错：在 cwd 下用纯文件名，把转义问题整个绕开。
    # （2026-09-04 实测：对绝对路径转义 ':' 会让整串被当成一个选项名而报
    #  "No option name near ..."。）
    burned = subprocess.run(
        [args.ffmpeg, "-v", "error", "-i", merged.name,
         "-vf", f"subtitles=filename={srt.name}:force_style='{style}'",
         "-c:v", "libx264", "-crf", "18", "-c:a", "copy", out.name, "-y"],
        text=True, capture_output=True, check=False, cwd=str(out.parent),
    )
    if burned.returncode == 0:
        print(f"OK: {out}（{len(takes)} 段 / {total:.2f}s / 已烧字幕 {srt.name}）")
        return 0

    # 没编 libass 的 ffmpeg 没有 subtitles 滤镜。字幕是这类短剧的主叙事通道，
    # 不能因为烧不上就退成软字幕——先用 Pillow 自渲字幕图 + overlay 硬烧。
    burned2 = burn_with_overlay(args, merged, srt_text, out)
    if burned2 is True:
        print(f"OK: {out}（{len(takes)} 段 / {total:.2f}s / 已烧硬字幕（Pillow+overlay））")
        return 0
    if isinstance(burned2, str):
        print(f"   自渲字幕不可用：{burned2}", file=sys.stderr)

    # 两条硬烧路径都不通时才退回内嵌软字幕轨，并明确告知。
    soft = subprocess.run(
        [args.ffmpeg, "-v", "error", "-i", merged.name, "-i", srt.name,
         "-c", "copy", "-c:s", "mov_text", "-metadata:s:s:0", "language=chi",
         out.name, "-y"],
        text=True, capture_output=True, check=False, cwd=str(out.parent),
    )
    if soft.returncode != 0:
        print(
            f"ERROR: 既不能烧字幕也不能内嵌软字幕。\n"
            f"  烧录：{burned.stderr.strip()[:200]}\n"
            f"  内嵌：{soft.stderr.strip()[:200]}",
            file=sys.stderr,
        )
        return 2
    print(
        f"OK: {out}（{len(takes)} 段 / {total:.2f}s / 已内嵌软字幕轨）\n"
        f"WARNING: 本机 ffmpeg 未编 libass，没有 subtitles 滤镜，无法烧录硬字幕。\n"
        f"  参考成片以硬字幕为主叙事通道，交付前需用带 libass 的 ffmpeg 或剪映\n"
        f"  按 {srt.name} 补烧，否则成片信息量低于参考片。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
