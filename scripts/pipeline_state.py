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
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
STEPS = [
    {
        "id": "intake",
        "title": "对齐目标并落盘母契约",
        "requires": [],
        "gate": "母契约字段齐全、无待定、无残留 [推断]，且由用户 --manual-confirmed 确认",
    },
    {
        "id": "script_units",
        "title": "抽取原剧本画面单元",
        "requires": ["intake"],
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
        "gate": "资产清单每一行都写了形态，公共素材中的图片均已脱离候选/待生成/待确认状态",
    },
    {
        "id": "segments",
        "title": "切分生成段并编写提示词",
        "requires": ["assets"],
        "gate": "交付 Markdown 存在生成段与完成提示词代码块",
    },
    {
        "id": "keyframe",
        "title": "合成每段起手帧",
        "requires": ["segments"],
        "gate": "每个生成段都声明了起手帧，且起手帧不是空场景（不得写「不出现任何人物」）",
    },
    {
        "id": "coverage",
        "title": "填写画面对账",
        "requires": ["keyframe"],
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
CONTRACT_SENSITIVE = ("validate", "review", "canvas", "generate")
MANUAL_STEPS = ("review", "canvas", "generate")
# 目标契约变更时，除 intake 自身外全部作废——契约是所有下游结论的前提。
GOAL_SENSITIVE = tuple(step_id for step_id in STEP_IDS if step_id != "intake")


def state_path(episode: str, directory: Path) -> Path:
    return directory / f"{episode}-run_state.json"


def delivery_path(episode: str, directory: Path) -> Path:
    return directory / f"{episode}-LibTV视频节点提示词.md"


GOAL_FILENAME = "目标契约.md"
GOAL_SEARCH_DEPTH = 3


def goal_search_paths(directory: Path) -> list[Path]:
    """从交付目录起向上最多 3 层的候选路径，顺序即优先级。"""
    current = directory.resolve()
    paths = [current / GOAL_FILENAME]
    for _ in range(GOAL_SEARCH_DEPTH):
        parent = current.parent
        if parent == current:
            break
        current = parent
        paths.append(current / GOAL_FILENAME)
    return paths


def find_goal_contract(directory: Path, explicit: Path | None) -> Path | None:
    """显式 --goal 优先；否则向上查找。找不到返回 None，不自动创建。

    不自动创建空契约:那会让「用户确认过」这件事失真,而这正是本设计要防的。
    """
    if explicit is not None:
        return explicit if explicit.exists() else None
    for candidate in goal_search_paths(directory):
        if candidate.exists():
            return candidate
    return None


def load_state(episode: str, directory: Path) -> dict:
    path = state_path(episode, directory)
    if not path.exists():
        return {
            "episode": episode, "steps": {}, "deliveryHash": "",
            "contractHash": "", "goalHash": "", "goal": {},
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"状态文件损坏：{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("状态文件顶层必须是 object")
    value.setdefault("steps", {})
    value.setdefault("deliveryHash", "")
    value.setdefault("contractHash", "")
    value.setdefault("goalHash", "")
    value.setdefault("goal", {})
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


def validation_contract_hash() -> str:
    digest = hashlib.sha256()
    for name in (
        "validate_delivery_md.py",
        "_shared_patterns.py",
        "_shot_budget.py",
        "_fast_drama_contract.py",
        "goal_contract.py",
    ):
        path = SCRIPT_DIR / name
        digest.update(name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def invalidate_stale(
    state: dict, episode: str, directory: Path, goal_file: Path | None = None,
) -> tuple[list[str], list[str]]:
    """交付 Markdown 或母契约变了就作废对应步骤——防止拿旧结论盖新内容。

    返回 (被作废的步骤, 母契约字段级 diff)。
    """
    import goal_contract

    current = file_hash(delivery_path(episode, directory))
    dropped: set[str] = set()
    if current and current != state.get("deliveryHash"):
        dropped.update(
            step_id for step_id in CONTENT_SENSITIVE
            if state["steps"].get(step_id) == "done"
        )
        state["deliveryHash"] = current
    contract = validation_contract_hash()
    if contract != state.get("contractHash"):
        dropped.update(
            step_id for step_id in CONTRACT_SENSITIVE
            if state["steps"].get(step_id) == "done"
        )
        state["contractHash"] = contract

    goal_diff: list[str] = []
    if goal_file is None:
        goal_file = find_goal_contract(directory, None)
    if goal_file is not None and goal_file.exists():
        goal_hash = file_hash(goal_file)
        if goal_hash != state.get("goalHash"):
            try:
                new_goal, _ = goal_contract.parse(
                    goal_file.read_text(encoding="utf-8")
                )
            except (goal_contract.GoalContractError, OSError):
                new_goal = {}
            goal_diff = goal_contract.diff(state.get("goal") or {}, new_goal)
            if state.get("goalHash"):
                dropped.update(
                    step_id for step_id in GOAL_SENSITIVE
                    if state["steps"].get(step_id) == "done"
                )
            state["goalHash"] = goal_hash
            state["goal"] = new_goal
    for step_id in dropped:
        state["steps"][step_id] = "pending"
    return [step_id for step_id in STEP_IDS if step_id in dropped], goal_diff


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
    manual_confirmed: bool = False,
    goal_path: Path | None = None,
) -> tuple[bool, str]:
    delivery = delivery_path(episode, directory)
    units_file = directory / f"{episode}-画面单元.json"

    if step_id == "intake":
        # intake 发生在交付 Markdown 存在之前，因此必须放在下方
        # `if not delivery.exists()` 守卫之前，也不能走 MANUAL_STEPS 分支
        # ——那条分支会先跑 run_validator，而此时无交付物可校验。
        import goal_contract

        goal_file = find_goal_contract(directory, goal_path)
        if goal_file is None:
            searched = "\n".join(f"    {p}" for p in goal_search_paths(directory))
            return False, (
                f"找不到 {GOAL_FILENAME}。搜索过：\n{searched}\n"
                "  请先起草母契约并经用户逐项确认，再跑本闸。"
                "本步不会自动创建空契约——那会让「用户确认过」失真。"
            )
        try:
            goal, linenos = goal_contract.parse(
                goal_file.read_text(encoding="utf-8")
            )
        except goal_contract.GoalContractError as exc:
            return False, str(exc)
        problems = (
            goal_contract.structure_errors(goal, linenos)
            + goal_contract.value_errors(goal, linenos)
        )
        if problems:
            return False, "母契约尚未就绪：\n" + "\n".join(f"  - {p}" for p in problems)
        if not manual_confirmed:
            return False, (
                "母契约字段已齐全，但机器无法证明用户真的看过它。\n"
                "  助手可以自己编一份契约、自己填满、自己 complete——那样这套闸等于空转。\n"
                f"  请与用户逐项确认 {goal_file}，确认后用 "
                "complete <集号> intake --manual-confirmed 显式标记。"
            )
        return True, (
            f"母契约已就绪并经用户确认：{goal_file}\n"
            f"  媒介={goal['媒介']}／模型={goal['模型展示名']}／"
            f"画幅={goal['画幅']}／分辨率={goal['分辨率']}"
        )

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

    if step_id == "keyframe":
        # 起手帧不是场景图。tvskill 此前把「角色板＋空场景锚＋色卡」直接绑给视频
        # 节点，让视频模型现场组构图——《万妖图录传》EP01 实证的后果是构图不受控
        # （定场主体偏小偏远）。万物生的做法是先用图像模型把这一镜的构图、角色站位、
        # 光影色调钉成一张图，再让视频模型只负责让它动。
        # 详见 references/libtv/keyframe-composition-contract.md
        # 不能用 section()：它在下一个 ### 处截断，只会拿到段的元信息块，
        # 而起手帧绑定写在更后面的提示词代码块里。必须切到下一个「## 生成段」。
        heads = list(re.finditer(r"^## 生成段 (V\d{2})｜", text, re.M))
        if not heads:
            return False, "交付 Markdown 里没有生成段，无法核对起手帧"
        missing = []
        for index, head in enumerate(heads):
            end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
            block = text[head.start():end]
            if "起手帧" not in block:
                missing.append(head.group(1))
        if missing:
            return False, (
                f"这些段没有声明起手帧：{missing}；"
                "每段必须有一张钉死构图、人物在位的起手帧，空场景锚不算"
            )
        if "不出现任何人物" in text:
            return False, (
                "交付 Markdown 里仍有「不出现任何人物」——那是空场景锚的写法。"
                "起手帧必须人物在位、站位与构图确定；场景参考降级为合成起手帧时的底子"
            )
        return True, f"{len(heads)} 段均已声明起手帧"

    if step_id == "assets":
        assets = section(text, "## 资产清单")
        rows = re.findall(r"^\|\s*(人物|场景|道具|色卡)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|$", assets, re.M)
        blank = [row[1].strip() for row in rows if not row[2].strip()]
        if blank:
            return False, f"这些资产没有写形态：{blank}"
        public_assets = section(text, "## 公共素材清单")
        if not public_assets.strip():
            return False, "交付 Markdown 缺少公共素材清单，无法证明生成资产已经验收"
        public_rows = re.findall(
            r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|$",
            public_assets,
            re.M,
        )
        pending_images = [
            name.strip()
            for name, media_type, usage in public_rows
            if name.strip() not in {"素材", "---"}
            and "图片" in media_type
            and re.search(
                r"候选|待生成|待确认|待验收|未验收|待返工",
                f"{name} {media_type} {usage}",
            )
        ]
        if pending_images:
            return False, (
                "这些图片仍是候选或待生成/待确认状态，不能把 assets 标为完成："
                f"{pending_images}；逐层视觉验收并晋升 canonical 后再更新公共素材清单"
            )
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
        if step_id in ("canvas", "generate") and not manual_confirmed:
            # 此前这两步只跑一遍单集校验就返回通过，画布可以从没连过、成片可以不存在，
            # 等于闸是空转的。机器无法替用户连画布与授权生成，但可以拒绝"无凭据即通过"。
            return False, (
                f"{step_id} 步需要真实画布/成片证据，机器无法自证：\n"
                "  1) 先按 SKILL.md §8 跑 sync dry-run 与 audit_canvas_nodes（零硬错误）；\n"
                "  2) generate 还需用户逐节点授权并完成十轴审计；\n"
                "  3) 人工确认上述证据并在交付 Markdown 里写明凭证后，"
                "用 complete --manual-confirmed 显式标记。"
            )
        if step_id in ("canvas", "generate"):
            return True, (
                f"{step_id} 的机器校验有效，且调用方已通过 "
                "--manual-confirmed 确认真实画布/成片证据"
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
    dropped, goal_diff = invalidate_stale(
        state, args.episode, args.dir, find_goal_contract(args.dir, args.goal)
    )
    save_state(args.episode, args.dir, state)
    print(f"集号：{args.episode}")
    if goal_diff:
        print("⚠ 目标契约已变更：")
        for line in goal_diff:
            print(f"    {line}")
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
    _, goal_diff = invalidate_stale(
        state, args.episode, args.dir, find_goal_contract(args.dir, args.goal)
    )
    if goal_diff:
        print("⚠ 目标契约已变更：")
        for line in goal_diff:
            print(f"    {line}")
    blocked = blocking_prerequisites(args.step, state)
    if blocked:
        print(
            f"ERROR: {args.step} 的前置步骤尚未完成：{blocked}；"
            "流程不允许跳步，请先完成前置",
            file=sys.stderr,
        )
        return 1
    ok, detail = check_step(
        args.step,
        args.episode,
        args.dir,
        args.script,
        args.episode_no,
        manual_confirmed=args.manual_confirmed,
        goal_path=args.goal,
    )
    print(detail)
    if not ok:
        state["steps"][args.step] = "failed"
        save_state(args.episode, args.dir, state)
        print(f"ERROR: {args.step} 未通过本步闸，不允许标记完成", file=sys.stderr)
        return 1
    if mark_done:
        state["steps"][args.step] = "done"
        state["deliveryHash"] = file_hash(delivery_path(args.episode, args.dir))
        state["contractHash"] = validation_contract_hash()
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
    parser.add_argument(
        "--goal",
        type=Path,
        help=f"母契约路径；省略时从 --dir 向上最多 {GOAL_SEARCH_DEPTH} 层查找 {GOAL_FILENAME}",
    )
    parser.add_argument(
        "--manual-confirmed",
        action="store_true",
        help="用于 intake/canvas/generate：确认用户已逐项确认母契约，或真实画布/成片凭证已落盘",
    )
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
