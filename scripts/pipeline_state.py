#!/usr/bin/env python3
"""TVSkill 流程状态机：决定"现在该做哪一步"，并在每一步落闸检查是否疏漏。

设计前提是"程序当司机，LLM 当工人"。规则写在文档里，LLM 就可能跳过；写进状态机，
跳过就走不下去：每一步必须先过自己的 gate 才能标记完成，下游步骤看到上游未完成直接拒绝。

用法：
    python3 scripts/pipeline_state.py status  <集号>            # 每次开工第一件事
    python3 scripts/pipeline_state.py check   <集号> <步骤>      # 只跑闸，不改状态
    python3 scripts/pipeline_state.py complete <集号> <步骤>     # 过闸才允许标记完成
    python3 scripts/pipeline_state.py reset   <集号> <步骤>      # 回退到某步重做

状态文件 `<集号>-run_state.json` 记录交付 Markdown 的内容哈希。Markdown 改动后，
`validate` 及其下游步骤自动失效——避免"改完不重跑校验就交付"。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
STEPS = [
    {
        "id": "script_units",
        "title": "抽取原剧本画面单元",
        "requires": [],
        "gate": "抽取器跑通且单元数大于 0，产出 <集号>-画面单元.json",
    },
    {
        "id": "entities",
        "title": "实体提取：人物/场景/道具/色卡",
        "requires": ["script_units"],
        "gate": "交付 Markdown 的资产清单四类齐全，道具与色卡都有显式声明（无则写明无）",
    },
    {
        "id": "assets",
        "title": "资产生产与验收",
        "requires": ["entities"],
        "gate": "资产清单每一行都写了形态，含精确文字的道具必须标注定版道具图",
    },
    {
        "id": "segments",
        "title": "切分生成段并编写提示词",
        "requires": ["assets"],
        "gate": "交付 Markdown 存在生成段与完成提示词代码块",
    },
    {
        "id": "coverage",
        "title": "填写画面对账",
        "requires": ["segments"],
        "gate": "画面对账逐条对源核验：行数与原文都必须与剧本一致",
    },
    {
        "id": "validate",
        "title": "确定性校验",
        "requires": ["coverage"],
        "gate": "validate_delivery_md.py --script 退出码为 0",
    },
    {
        "id": "review",
        "title": "全剧七遍语义二审",
        "requires": ["validate"],
        "gate": "由人或 LLM 完成后显式标记；机器只检查 validate 仍然有效",
    },
    {
        "id": "canvas",
        "title": "画布两阶段预检",
        "requires": ["review"],
        "gate": "sync dry-run 与画布只读审计零硬错误（需用户授权操作画布）",
    },
    {
        "id": "generate",
        "title": "顺序生成、验收与返工",
        "requires": ["canvas"],
        "gate": "需用户逐节点授权；成片十轴审计通过",
    },
]
STEP_IDS = [step["id"] for step in STEPS]
# 交付物内容变化后必须重走的步骤：校验结论不能比被校验的内容还旧。
# 交付 Markdown 是这些步骤的判据来源，内容一变，它们的结论就都过期了。
# 只作废 validate 及下游是不够的：改完画面对账表后 coverage=done 会永久留存，
# "逐条对源"的结论便能在任意后续编辑后原样存活。
CONTENT_SENSITIVE = (
    "entities", "assets", "segments", "coverage",
    "validate", "review", "canvas", "generate",
)
MANUAL_STEPS = ("review", "canvas", "generate")


def state_path(episode: str, directory: Path) -> Path:
    return directory / f"{episode}-run_state.json"


def delivery_path(episode: str, directory: Path) -> Path:
    return directory / f"{episode}-LibTV视频节点提示词.md"


def load_state(episode: str, directory: Path) -> dict:
    path = state_path(episode, directory)
    if not path.exists():
        return {"episode": episode, "steps": {}, "deliveryHash": ""}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"状态文件损坏：{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("状态文件顶层必须是 object")
    value.setdefault("steps", {})
    value.setdefault("deliveryHash", "")
    return value


def save_state(episode: str, directory: Path, state: dict) -> None:
    path = state_path(episode, directory)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invalidate_stale(state: dict, episode: str, directory: Path) -> list[str]:
    """交付 Markdown 变了就作废校验类步骤——防止拿旧结论盖新内容。"""
    current = file_hash(delivery_path(episode, directory))
    if not current or current == state.get("deliveryHash"):
        return []
    dropped = [
        step_id for step_id in CONTENT_SENSITIVE if state["steps"].get(step_id) == "done"
    ]
    for step_id in dropped:
        state["steps"][step_id] = "pending"
    state["deliveryHash"] = current
    return dropped


def section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    body = start + len(heading)
    following = re.search(r"^#{1,3}\s+", text[body:], re.M)
    return text[body:body + following.start()] if following else text[body:]


def run_validator(delivery: Path, script: Path | None, episode_no: int | None) -> tuple[bool, str]:
    # 加 --standalone：流程凭据由本状态机自己维护，若让校验器反过来查凭据，
    # coverage 步骤会要求"coverage 已完成"才能通过，形成永远过不去的死锁。
    command = [
        sys.executable,
        str(SCRIPT_DIR / "validate_delivery_md.py"),
        str(delivery),
        "--standalone",
    ]
    if script:
        command += ["--script", str(script)]
    if episode_no is not None:
        command += ["--episode", str(episode_no)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def check_step(
    step_id: str,
    episode: str,
    directory: Path,
    script: Path | None,
    episode_no: int | None,
) -> tuple[bool, str]:
    delivery = delivery_path(episode, directory)
    units_file = directory / f"{episode}-画面单元.json"

    if step_id == "script_units":
        if not script:
            return False, "必须用 --script 指定原剧本，画面单元不能凭记忆写"
        command = [
            sys.executable, str(SCRIPT_DIR / "extract_script_units.py"), str(script),
        ]
        if episode_no is not None:
            command += ["--episode", str(episode_no)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return False, result.stderr.strip() or "抽取失败"
        units_file.write_text(result.stdout, encoding="utf-8")
        count = len(json.loads(result.stdout))
        return True, f"抽到 {count} 条画面单元，已写入 {units_file.name}"

    if not delivery.exists():
        return False, f"缺少交付 Markdown：{delivery.name}"
    text = delivery.read_text(encoding="utf-8")

    if step_id == "entities":
        assets = section(text, "## 资产清单")
        if not assets.strip():
            return False, "交付 Markdown 缺少资产清单"
        missing = [
            kind for kind in ("人物", "场景", "道具", "色卡")
            if not re.search(rf"^\|\s*{kind}\s*\|", assets, re.M)
        ]
        if missing:
            return False, (
                f"资产清单缺少这几类的显式声明：{missing}；"
                "本集确实没有的类别也要写一行说明，沉默不等于没有"
            )
        return True, "资产清单四类齐全"

    if step_id == "assets":
        assets = section(text, "## 资产清单")
        rows = re.findall(r"^\|\s*(人物|场景|道具|色卡)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|$", assets, re.M)
        blank = [row[1].strip() for row in rows if not row[2].strip()]
        if blank:
            return False, f"这些资产没有写形态：{blank}"
        return True, f"{len(rows)} 项资产均已写明形态"

    if step_id == "segments":
        if "## 生成段 V01" not in text:
            return False, "还没有任何生成段"
        if "### LibTV 完成提示词（整块复制）" not in text:
            return False, "生成段缺少完成提示词代码块"
        return True, "生成段与提示词已就位"

    if step_id in ("coverage", "validate"):
        if not script:
            return False, (
                "必须用 --script 指定原剧本：不对源时画面对账只会降级成一条警告，"
                "整表可以是编的"
            )
        ok, output = run_validator(delivery, script, episode_no)
        if step_id == "coverage":
            error_lines = [
                line for line in output.splitlines() if line.startswith("ERROR")
            ]
            # 致命错误必须先抛：集号传错会导致一条画面单元都抽不到，
            # 此时"对源比对"一行都没跑过，绝不能因为没有画面对账类错误就放行。
            fatal = [
                line for line in error_lines
                if any(mark in line for mark in (
                    "没有抽到画面单元", "无法读取原剧本", "无法加载 extract_script_units",
                ))
            ]
            if fatal:
                return False, "\n".join(fatal)
            coverage_errors = [
                line for line in error_lines
                if "画面对账" in line or "拆节点" in line
            ]
            if coverage_errors:
                return False, "\n".join(coverage_errors)
            return True, "画面对账已逐条对源核验"
        return ok, output

    if step_id in MANUAL_STEPS:
        ok, output = run_validator(delivery, script, episode_no)
        if not ok:
            return False, f"上游确定性校验已失效，先修好再推进：\n{output}"
        if step_id in ("canvas", "generate"):
            # 此前这两步只跑一遍单集校验就返回通过，画布可以从没连过、成片可以不存在，
            # 等于闸是空转的。机器无法替用户连画布与授权生成，但可以拒绝"无凭据即通过"。
            return False, (
                f"{step_id} 步需要真实画布/成片证据，机器无法自证：\n"
                "  1) 先按 SKILL.md §8 跑 sync dry-run 与 audit_canvas_nodes（零硬错误）；\n"
                "  2) generate 还需用户逐节点授权并完成十轴审计；\n"
                "  3) 人工确认上述证据后，用 complete 显式标记，"
                "并在交付 Markdown 里写明凭证。"
            )
        if step_id == "review":
            # 「待二审」是为了打破"必须先自称已通过才能过机器闸"的死循环而存在的
            # 中间态；二审这一步完成时必须已经改成「已通过」，否则它会一路混到交付。
            pending = re.findall(r"^- (全剧二审|提示词二审)：待二审$", text, re.M)
            if pending:
                return False, (
                    f"仍有 {len(pending)} 处二审字段停留在「待二审」；"
                    "完成七遍语义二审后请改为「已通过」再 complete"
                )
        return True, "机器闸通过；本步需由人确认后显式 complete"

    return False, f"未知步骤：{step_id}"


def blocking_prerequisites(step_id: str, state: dict) -> list[str]:
    step = next(item for item in STEPS if item["id"] == step_id)
    return [
        required for required in step["requires"]
        if state["steps"].get(required) != "done"
    ]


def cmd_status(args, state: dict) -> int:
    dropped = invalidate_stale(state, args.episode, args.dir)
    save_state(args.episode, args.dir, state)
    print(f"集号：{args.episode}")
    if dropped:
        print(f"⚠ 交付 Markdown 已变更，以下步骤自动作废需重跑：{dropped}")
    next_step = None
    for step in STEPS:
        status = state["steps"].get(step["id"], "pending")
        mark = {"done": "✔", "failed": "✘"}.get(status, "·")
        print(f"  {mark} {step['id']:<13} {step['title']}")
        if next_step is None and status != "done":
            next_step = step
    if next_step is None:
        print("\n全部步骤已完成。")
        return 0
    blocked = blocking_prerequisites(next_step["id"], state)
    print(f"\n下一步：{next_step['id']}（{next_step['title']}）")
    print(f"  本步闸：{next_step['gate']}")
    if blocked:
        print(f"  ⚠ 前置未完成：{blocked}")
    # 必须带上用户本次传的 --dir：否则照提示继续会跑到 cwd，
    # 在错误目录新建状态文件，导致状态分叉。
    dir_flag = f" --dir {args.dir}" if str(args.dir) != "." else ""
    print(
        f"  跑闸：python3 scripts/pipeline_state.py check {args.episode} "
        f"{next_step['id']}{dir_flag} --script <原剧本> --episode-no <集号数字>"
    )
    return 0


def cmd_check(args, state: dict, mark_done: bool) -> int:
    if args.step not in STEP_IDS:
        print(f"ERROR: 未知步骤 {args.step}，可选：{STEP_IDS}", file=sys.stderr)
        return 2
    invalidate_stale(state, args.episode, args.dir)
    blocked = blocking_prerequisites(args.step, state)
    if blocked:
        print(
            f"ERROR: {args.step} 的前置步骤尚未完成：{blocked}；"
            "流程不允许跳步，请先完成前置",
            file=sys.stderr,
        )
        return 1
    ok, detail = check_step(args.step, args.episode, args.dir, args.script, args.episode_no)
    print(detail)
    if not ok:
        state["steps"][args.step] = "failed"
        save_state(args.episode, args.dir, state)
        print(f"ERROR: {args.step} 未通过本步闸，不允许标记完成", file=sys.stderr)
        return 1
    if mark_done:
        state["steps"][args.step] = "done"
        state["deliveryHash"] = file_hash(delivery_path(args.episode, args.dir))
        save_state(args.episode, args.dir, state)
        print(f"OK: {args.step} 已完成")
    else:
        save_state(args.episode, args.dir, state)
        print(f"OK: {args.step} 通过本步闸（未标记完成）")
    return 0


def cmd_reset(args, state: dict) -> int:
    if args.step not in STEP_IDS:
        print(f"ERROR: 未知步骤 {args.step}", file=sys.stderr)
        return 2
    index = STEP_IDS.index(args.step)
    for step_id in STEP_IDS[index:]:
        state["steps"][step_id] = "pending"
    save_state(args.episode, args.dir, state)
    print(f"OK: 已回退 {STEP_IDS[index:]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "check", "complete", "reset"))
    parser.add_argument("episode", help="集号，例如 EP01")
    parser.add_argument("step", nargs="?", help="步骤 id")
    parser.add_argument("--dir", type=Path, default=Path.cwd(), help="交付目录")
    parser.add_argument("--script", type=Path, help="原剧本 .docx/.txt/.md")
    parser.add_argument("--episode-no", type=int, help="原剧本中的集号数字")
    args = parser.parse_args()
    try:
        state = load_state(args.episode, args.dir)
        if args.command == "status":
            return cmd_status(args, state)
        if not args.step:
            print("ERROR: 该命令需要指定步骤 id", file=sys.stderr)
            return 2
        if args.command == "reset":
            return cmd_reset(args, state)
        return cmd_check(args, state, mark_done=args.command == "complete")
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
