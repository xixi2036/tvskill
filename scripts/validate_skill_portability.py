#!/usr/bin/env python3
"""Validate that TVSkill has no runtime dependency on another local skill."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".json"}
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
LEGACY_FILES = {
    "asset-plan-schema.json",
    "movement-ledger-schema.json",
    "reference-manifest.template.json",
    "payload-schema.json",
    "example-asset-plan.json",
    "example-movement-ledger.json",
    "example-payload.json",
    "libtv_canvas.py",
    "validate_bundle.py",
    "test_libtv_canvas.py",
    "test_validate_bundle.py",
    "02-asset-extraction.md",
    "07-json-assembly-and-quality-gates.md",
    "08-examples.md",
}
FORBIDDEN = (
    (re.compile(r"\[skill:[^\]]+\]"), "外部 skill 路由"),
    (re.compile(r"/Users/[^/\s]+/(?:\.codex|\.agents)/skills/"), "本机 skill 绝对路径"),
    (re.compile(r"(?:^|[\s`])~/\.(?:codex|agents)/skills/"), "用户目录 skill 路径"),
)


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    required = (
        root / "SKILL.md",
        root / "agents" / "openai.yaml",
        root / "assets" / "libtv-video-prompts.template.md",
        root / "references" / "v3-to-libtv-mapping.md",
        root / "references" / "libtv" / "performance-dialogue-contract.md",
        root / "references" / "libtv" / "scene-topology-and-functional-orientation.md",
        root / "references" / "libtv" / "series-continuity-audit-contract.md",
        root / "references" / "libtv" / "visual-look-and-style-bible.md",
        root / "references" / "libtv" / "generated-take-quality-audit.md",
        root / "references" / "libtv" / "libtv-canvas-contract.md",
        root / "scripts" / "validate_delivery_md.py",
        root / "scripts" / "audit_series_continuity.py",
        root / "scripts" / "audit_canvas_nodes.py",
        root / "scripts" / "audit_take_files.py",
        root / "scripts" / "extract_voice_reference.py",
        root / "scripts" / "sync_delivery_markdown.py",
    )
    for path in required:
        if not path.is_file():
            errors.append(f"缺少独立运行文件：{path.relative_to(root)}")

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink():
            errors.append(f"禁止符号链接：{relative}")
            continue
        if path.is_file() and path.name in LEGACY_FILES:
            errors.append(f"包含废弃 JSON 管线文件：{relative}")
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if relative == Path("scripts/validate_skill_portability.py") or "tests" in relative.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            continue
        for pattern, description in FORBIDDEN:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{relative}:{line} 含{description}：{match.group(0)}"
                )
        if path.suffix.lower() == ".md":
            link_text = re.sub(r"```.*?```", "", text, flags=re.S)
            link_text = re.sub(r"`[^`\n]*`", "", link_text)
            for target in MARKDOWN_LINK_RE.findall(link_text):
                target = target.strip().split("#", 1)[0]
                if not target or "://" in target or target.startswith(("mailto:", "#")):
                    continue
                linked = (path.parent / target).resolve()
                try:
                    linked.relative_to(root.resolve())
                except ValueError:
                    errors.append(f"{relative} 引用 skill 外部文件：{target}")
                    continue
                if not linked.exists():
                    errors.append(f"{relative} 含失效本地链接：{target}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    errors = validate(root)
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"SUMMARY: errors={len(errors)}")
        return 1
    print("OK: TVSkill is self-contained and portable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
