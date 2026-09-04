#!/usr/bin/env python3
"""带强制门禁的视频节点运行器——`tvmao node run` 的唯一合法入口。

## 为什么需要它

tvskill 的运行前门禁一直存在（`audit_canvas_nodes.py --pre-run`），但它是**另一条命令**，
靠人记得先跑。2026-09-04 一次真实产线试跑里，同一类错误连犯三次：

1. 用 `tvmao node create` 手工建节点，绕过 `sync_delivery_markdown.py`
   → 连线错（线性链而非并列 image-input）、漏绑角色资产、误用 720p
2. 普通模式跑审计，素材合规态只以 WARNING 出现，被无视
3. 直接 `tvmao node run` → 烧掉 456 积分，节点永久 `failed`

三次都不是「不知道规则」，是「规则在另一条命令里，跳过它零阻力」。
SKILL.md 自己写着：**能落成闸的规则一律落成闸，只能靠自觉的规则一律假定会被跳过。**
本脚本把那句话对 run 这一步兑现。

## 它做什么

    ③合规校验（提交+轮询到 active） → 审计（--pre-run，硬错误即中止） → 才调用 tvmao node run

第一段对应巨日禄管线的节点③「Seedance 素材库注册」——真人人像的官方授权通道。
画布侧等价命令是 `tvmao compliance verify/status`，CLI 帮助写明的标准流程是：

    先把图片节点都生成出来 → verify 逐个提交 → status 等它们变成 active → 再跑视频生成

这一步此前只写在 `manual-video-node-delivery.md` 与 `libtv-canvas-contract.md` 的正文里，
没有任何工具执行它。2026-09-04 实盘因此漏跑，素材停在 `unverified`，
生成被 Ark 以 `InputImageSensitiveContentDetected.PrivacyInformation` 拒绝并烧掉额度。
文档挡不住跳步，故在此落成闸。详见 `references/libtv/automation-pipeline-map.md`。

任何一条硬错误都会让它拒绝运行并返回 2，不会碰生成额度。
`--asset` 映射必须与同步时一致，否则审计拿不到语义 label，会产生一片假错。

用法：
    python3 scripts/run_video_node.py --project 143 --node n-XXXX \\
        --asset "角色-姜月初=n-0vI1hTqQ" --asset "视频场景锚-荒野战场-S1=n-dcWCh5re"

    # 只审不跑（等价于单独跑 --pre-run 审计）
    python3 scripts/run_video_node.py --project 143 --node n-XXXX --asset ... --check-only

退出码：0 生成成功；2 门禁未过或生成失败；1 执行错误。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


SCRIPTS = Path(__file__).resolve().parent
AUDIT = SCRIPTS / "audit_canvas_nodes.py"

# 合规校验轮询：巨日禄侧后台 worker 约 30s 收敛，这里给足冗余但不无限等。
COMPLIANCE_POLL_INTERVAL = 5.0
COMPLIANCE_TIMEOUT = 180.0
# 已是终态、再等也不会变的状态；`pending` 之外的未知状态一律按未就绪处理。
COMPLIANCE_TERMINAL_BAD = {"rejected", "failed", "blocked"}
# 生成轮询：12s 视频通常几分钟内收敛，给足冗余但不无限等。
RUN_POLL_INTERVAL = 10.0
RUN_TIMEOUT = 900.0


def tvmao_json(tvmao: str, args: list[str]) -> object:
    """调 tvmao 并解析输出里的 JSON（CLI 会在 JSON 前打印人类可读的进度行）。"""
    result = subprocess.run([tvmao, *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"tvmao {' '.join(args)} 失败：{result.stderr.strip()}")
    match = re.search(r"[\[{]", result.stdout)
    if not match:
        raise RuntimeError(f"tvmao {' '.join(args)} 未返回 JSON：{result.stdout.strip()[:200]}")
    return json.loads(result.stdout[match.start():])


def compliance_map(tvmao: str, project: str) -> dict[str, str]:
    payload = tvmao_json(tvmao, ["compliance", "status", "--project", project])
    items = payload if isinstance(payload, list) else payload.get("items") or payload.get("assets") or []
    return {
        str(item.get("nodeId")): str(item.get("status") or "").lower()
        for item in items
        if isinstance(item, dict) and item.get("nodeId")
    }


def ensure_compliance(tvmao: str, project: str, node_ids: list[str]) -> tuple[bool, str]:
    """管线节点③：把入边素材提交合规校验并轮询到 active。

    返回 (是否全部 active, 人类可读说明)。不抛异常——调用方需要把失败
    转成「拒绝运行」而不是崩溃，才能保证不烧额度。
    """
    try:
        status = compliance_map(tvmao, project)
    except (RuntimeError, json.JSONDecodeError) as exc:
        return False, f"读取合规状态失败：{exc}"

    unknown = [n for n in node_ids if n not in status]
    if unknown:
        return False, f"这些入边不在项目 {project} 的素材列表里，请先确认节点已出图：{unknown}"

    pending = [n for n in node_ids if status[n] != "active"]
    if not pending:
        return True, f"入边素材已全部 active（{len(node_ids)} 项），跳过提交。"

    bad = [n for n in pending if status[n] in COMPLIANCE_TERMINAL_BAD]
    if bad:
        return False, f"素材合规校验已是拒绝终态，重提无用，须换图重建：{bad}"

    to_submit = [n for n in pending if status[n] != "pending"]
    if to_submit:
        try:
            tvmao_json(tvmao, ["compliance", "verify", *to_submit, "--project", project])
        except (RuntimeError, json.JSONDecodeError) as exc:
            return False, f"提交合规校验失败：{exc}"
        print(f"   已提交合规校验：{to_submit}", file=sys.stderr)

    deadline = time.monotonic() + COMPLIANCE_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(COMPLIANCE_POLL_INTERVAL)
        try:
            status = compliance_map(tvmao, project)
        except (RuntimeError, json.JSONDecodeError) as exc:
            return False, f"轮询合规状态失败：{exc}"
        pending = [n for n in node_ids if status.get(n) != "active"]
        if not pending:
            return True, f"入边素材已全部收敛为 active（{len(node_ids)} 项）。"
        bad = [n for n in pending if status.get(n, "") in COMPLIANCE_TERMINAL_BAD]
        if bad:
            return False, (
                f"素材被平台判为不合规（写实真人脸会在此拦截）：{bad}；"
                "须换资产重建节点，不要原地重试。"
            )
        print(f"   等待收敛，未就绪 {len(pending)} 项…", file=sys.stderr)

    return False, f"合规校验 {COMPLIANCE_TIMEOUT:.0f}s 内未收敛，仍未 active：{pending}"


def run_gate(project: str, node: str, assets: list[str], tvmao: str | None) -> tuple[int, str]:
    command = [
        sys.executable,
        str(AUDIT),
        "--project",
        project,
        "--node",
        node,
        "--pre-run",
    ]
    for mapping in assets:
        command += ["--asset", mapping]
    if tvmao:
        command += ["--tvmao", tvmao]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    return result.returncode, f"{result.stdout}{result.stderr}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument(
        "--asset",
        action="append",
        default=[],
        help="语义=输入节点ID，可重复；必须与 sync_delivery_markdown 同步时一致",
    )
    parser.add_argument("--check-only", action="store_true", help="只跑门禁，不运行生成")
    parser.add_argument(
        "--no-ensure-compliance",
        dest="ensure_compliance",
        action="store_false",
        default=True,
        help="跳过节点③合规校验的提交与轮询（仅用于素材已确认 active 的复跑；跳过后门禁仍会拦）",
    )
    parser.add_argument("--tvmao")
    parser.add_argument(
        "--wait", action="store_true", default=True,
        help="等待生成完成（默认开启；生成是异步任务，不等就拿不到结果）",
    )
    args = parser.parse_args()

    tvmao = args.tvmao or shutil.which("tvmao") or str(Path.home() / ".tvmao" / "tvmao")
    if not Path(tvmao).exists() and not shutil.which(tvmao):
        print(f"ERROR: 找不到 tvmao CLI：{tvmao}", file=sys.stderr)
        return 1
    if not args.asset:
        print(
            "ERROR: 必须传 --asset 语义=节点ID（与同步时一致）。"
            "缺映射时审计拿不到语义 label，会把每条绑定误报成不一致，"
            "真错被假错淹没。",
            file=sys.stderr,
        )
        return 1

    if args.ensure_compliance:
        node_ids = []
        for mapping in args.asset:
            if "=" not in mapping:
                print(f"ERROR: --asset 需写成 语义=节点ID，收到：{mapping}", file=sys.stderr)
                return 1
            node_id = mapping.split("=", 1)[1].strip()
            if node_id and node_id not in node_ids:
                node_ids.append(node_id)
        print("── 节点③ 合规校验（tvmao compliance verify → active）──", file=sys.stderr)
        ok, detail = ensure_compliance(tvmao, args.project, node_ids)
        print(f"   {detail}", file=sys.stderr)
        if not ok:
            print(
                "REFUSED: 入边素材未全部通过合规校验，未调用 tvmao node run，未消耗生成额度。",
                file=sys.stderr,
            )
            return 2

    print("── 运行前门禁（audit_canvas_nodes --pre-run）──", file=sys.stderr)
    code, output = run_gate(args.project, args.node, args.asset, args.tvmao)
    print(output.rstrip(), file=sys.stderr)
    if code != 0:
        print(
            "REFUSED: 门禁未过，未调用 tvmao node run，未消耗生成额度。\n"
            "  常见三条硬错误：素材合规态未全部 active（含写实真人脸被平台拦截）／"
            "节点状态不是 idle／一次性视频预算已消耗。\n"
            "  合规态未 active 时应换资产另建节点，不要原地重跑——"
            "按一次性预算合同，failed 节点已是拒绝态。",
            file=sys.stderr,
        )
        return 2

    if args.check_only:
        print("OK: 门禁通过（--check-only，未运行生成）")
        return 0

    print("── 门禁通过，开始生成 ──", file=sys.stderr)
    command = [tvmao, "node", "run", args.node, "--project", args.project]
    if args.wait:
        command.append("--wait")
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        print(result.stderr.rstrip(), file=sys.stderr)
        return 2

    if not args.wait:
        return 0
    # `node run --wait` 并不保证阻塞到终态：2026-09-04 实测它返回 0 时节点仍是
    # generating，下游立刻 `asset download` 就报「还没有产物」。成功与否必须以
    # 节点状态为准，不能以命令退出码为准。
    status = wait_until_settled(tvmao, args.project, args.node)
    if status != "succeeded":
        print(
            f"FAILED: 节点最终状态为 {status or '未知'}，本段未出片。\n"
            "  按一次性预算，该节点已是拒绝态：须先记录根因、改写提示词，"
            "再建新节点（新指纹）重跑，不得原地重试。",
            file=sys.stderr,
        )
        return 2
    return 0


def wait_until_settled(tvmao: str, project: str, node: str) -> str:
    """轮询到 succeeded/failed 为止；超时返回最后看到的状态。"""
    deadline = time.monotonic() + RUN_TIMEOUT
    status = ""
    while time.monotonic() < deadline:
        try:
            payload = tvmao_json(tvmao, ["node", "get", node, "--project", project])
        except (RuntimeError, json.JSONDecodeError) as exc:
            print(f"   轮询节点状态失败：{exc}", file=sys.stderr)
            time.sleep(RUN_POLL_INTERVAL)
            continue
        if isinstance(payload, dict):
            payload = payload.get("node", payload)
        status = str(payload.get("status") or "") if isinstance(payload, dict) else ""
        if status in {"succeeded", "failed"}:
            return status
        time.sleep(RUN_POLL_INTERVAL)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
