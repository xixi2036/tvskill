from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "pipeline_state.py"
SPEC = importlib.util.spec_from_file_location("pipeline_state", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


SCRIPT = """第1集

1-1 日 内 系统空间
人物：单知影
△ 虚空中，十个棱镜牢笼悬浮着。
单知影：要赌吗。
△ 竖瞳合拢，消失在黑暗中。
"""

MARKDOWN_SCRIPT = """# 第1集

## 1-1 婚房门口 夜 内

**人物**：叶敏、顾续尘

△叶敏拍打房门。

【音效】砰！砰！

叶敏OS（无话可说地认栽）：……他真的，壕无人性。
"""

ASSETS_FULL = """# EP01｜LibTV 完成提示词

## 资产清单

| 类型 | 名称 | 形态 | 备注 |
|---|---|---|---|
| 人物 | 单知影 | 独立身份图 | 有台词 |
| 场景 | 系统空间 | 场景状态图 | |
| 道具 | 无 | 本集无承担叙事功能的道具 | 已核对 |
| 色卡 | 色卡-系统空间 | 色卡图 | 本场色板 |
"""


class PipelineStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.script = self.dir / "script.txt"
        self.script.write_text(SCRIPT, encoding="utf-8")
        self.delivery = self.dir / "EP01-LibTV视频节点提示词.md"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def state(self) -> dict:
        return MODULE.load_state("EP01", self.dir)

    def check(self, step: str, script: Path | None = None):
        return MODULE.check_step(step, "EP01", self.dir, script, 1)

    def test_first_step_extracts_units_from_real_script(self):
        ok, detail = self.check("script_units", self.script)
        self.assertTrue(ok, detail)
        units = json.loads((self.dir / "EP01-画面单元.json").read_text(encoding="utf-8"))
        self.assertEqual(len(units), 2)

    def test_first_step_accepts_markdown_headings_and_bare_sfx(self):
        markdown_script = self.dir / "script.md"
        markdown_script.write_text(MARKDOWN_SCRIPT, encoding="utf-8")
        ok, detail = self.check("script_units", markdown_script)
        self.assertTrue(ok, detail)
        units = json.loads(
            (self.dir / "EP01-画面单元.json").read_text(encoding="utf-8")
        )
        self.assertEqual([unit["kind"] for unit in units], ["visual", "sfx"])
        self.assertEqual(units[0]["scene"], "1-1 婚房门口 夜 内")

    def test_script_units_refuses_without_script(self):
        ok, detail = self.check("script_units", None)
        self.assertFalse(ok)
        self.assertIn("不能凭记忆写", detail)

    def test_entities_gate_requires_all_four_kinds(self):
        self.delivery.write_text(
            ASSETS_FULL.replace(
                "| 道具 | 无 | 本集无承担叙事功能的道具 | 已核对 |\n", ""
            ).replace("| 色卡 | 色卡-系统空间 | 色卡图 | 本场色板 |\n", ""),
            encoding="utf-8",
        )
        ok, detail = self.check("entities")
        self.assertFalse(ok)
        self.assertIn("道具", detail)
        self.assertIn("色卡", detail)

    def test_entities_gate_accepts_explicit_none(self):
        self.delivery.write_text(ASSETS_FULL, encoding="utf-8")
        ok, detail = self.check("entities")
        self.assertTrue(ok, detail)

    def test_coverage_refuses_without_script(self):
        self.delivery.write_text(ASSETS_FULL, encoding="utf-8")
        ok, detail = self.check("coverage", None)
        self.assertFalse(ok)
        self.assertIn("--script", detail)

    def test_prerequisites_block_skipping(self):
        state = {"episode": "EP01", "steps": {}, "deliveryHash": ""}
        self.assertEqual(
            MODULE.blocking_prerequisites("validate", state), ["coverage"]
        )
        state["steps"]["coverage"] = "done"
        self.assertEqual(MODULE.blocking_prerequisites("validate", state), [])

    def test_script_units_now_requires_intake(self):
        """★2026-08-01 加:grilling 前置问答步必须挡在 script_units 之前，
        不能像之前那样一进门就抽画面单元——媒介/范围这些决策必须先问清楚。"""
        state = {"episode": "EP01", "steps": {}, "deliveryHash": ""}
        self.assertEqual(
            MODULE.blocking_prerequisites("script_units", state), ["intake"]
        )
        state["steps"]["intake"] = "done"
        self.assertEqual(MODULE.blocking_prerequisites("script_units", state), [])

    def test_intake_gate_rejects_missing_file(self):
        ok, detail = self.check("intake")
        self.assertFalse(ok)
        self.assertIn("任务前置决策.json", detail)

    def test_intake_gate_rejects_missing_required_fields(self):
        intake_file = self.dir / "EP01-任务前置决策.json"
        intake_file.write_text(
            json.dumps({"媒介": "真人实拍", "范围": "单集"}, ensure_ascii=False),
            encoding="utf-8",
        )
        ok, detail = self.check("intake")
        self.assertFalse(ok)
        self.assertIn("资产现状", detail)
        self.assertIn("画布操作", detail)
        self.assertIn("音色状态", detail)

    def test_intake_gate_requires_3d_substyle_when_medium_is_3d_cg(self):
        intake_file = self.dir / "EP01-任务前置决策.json"
        intake_file.write_text(
            json.dumps(
                {
                    "媒介": "3D CG",
                    "范围": "单集",
                    "资产现状": "需要从零生产",
                    "画布操作": "仅生成Markdown",
                    "音色状态": "需要占位等待人工上传",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        ok, detail = self.check("intake")
        self.assertFalse(ok)
        self.assertIn("3D子风格", detail)

    def test_intake_gate_accepts_complete_decisions(self):
        intake_file = self.dir / "EP01-任务前置决策.json"
        intake_file.write_text(
            json.dumps(
                {
                    "媒介": "真人实拍",
                    "范围": "单集",
                    "资产现状": "已有可复用",
                    "画布操作": "仅生成Markdown",
                    "音色状态": "全部已上传",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        ok, detail = self.check("intake")
        self.assertTrue(ok, detail)

    def test_intake_gate_rejects_malformed_json(self):
        intake_file = self.dir / "EP01-任务前置决策.json"
        intake_file.write_text("{不是合法json", encoding="utf-8")
        ok, detail = self.check("intake")
        self.assertFalse(ok)
        self.assertIn("不是合法 JSON", detail)

    def test_delivery_change_invalidates_downstream_steps(self):
        self.delivery.write_text(ASSETS_FULL, encoding="utf-8")
        state = {
            "episode": "EP01",
            "steps": {step: "done" for step in MODULE.STEP_IDS},
            "deliveryHash": MODULE.file_hash(self.delivery),
        }
        self.assertEqual(MODULE.invalidate_stale(state, "EP01", self.dir), [])
        self.delivery.write_text(ASSETS_FULL + "\n改了一个字\n", encoding="utf-8")
        dropped = MODULE.invalidate_stale(state, "EP01", self.dir)
        self.assertEqual(dropped, list(MODULE.CONTENT_SENSITIVE))
        # 交付 Markdown 是这些步骤的判据来源，改了就全部过期
        for step in ("entities", "assets", "segments", "coverage", "validate"):
            self.assertEqual(state["steps"][step], "pending", step)
        # script_units 只依赖原剧本，不受交付物改动影响
        self.assertEqual(state["steps"]["script_units"], "done")



    def test_review_step_rejects_pending_audit_fields(self):
        """「待二审」是打破死循环的中间态，不能一路混到交付。"""
        template = (
            Path(__file__).resolve().parents[1]
            / "assets" / "libtv-video-prompts.template.md"
        ).read_text(encoding="utf-8")
        self.delivery.write_text(template, encoding="utf-8")
        ok, detail = MODULE.check_step("review", "EP01", self.dir, None, None)
        self.assertFalse(ok, detail)
        self.assertIn("待二审", detail)

    def test_canvas_and_generate_require_real_evidence(self):
        """这两步曾只跑一遍单集校验就能标 done，画布可以从没连过。"""
        template = (
            Path(__file__).resolve().parents[1]
            / "assets" / "libtv-video-prompts.template.md"
        ).read_text(encoding="utf-8").replace("：待二审", "：已通过")
        self.delivery.write_text(template, encoding="utf-8")
        for step in ("canvas", "generate"):
            with self.subTest(step):
                ok, detail = MODULE.check_step(step, "EP01", self.dir, None, None)
                self.assertFalse(ok)
                self.assertIn("机器无法自证", detail)

    def test_review_step_accepts_completed_audit(self):
        template = (
            Path(__file__).resolve().parents[1]
            / "assets" / "libtv-video-prompts.template.md"
        ).read_text(encoding="utf-8").replace("：待二审", "：已通过")
        self.delivery.write_text(template, encoding="utf-8")
        ok, detail = MODULE.check_step("review", "EP01", self.dir, None, None)
        self.assertTrue(ok, detail)


class DeliverableGateTests(unittest.TestCase):
    """交付凭据闸：不跑状态机就直接跑校验器，等于绕过整条流程锁。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.delivery = self.dir / "EP01-LibTV视频节点提示词.md"
        self.delivery.write_text(ASSETS_FULL, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(
            "validate_delivery_md",
            Path(__file__).resolve().parents[1] / "scripts" / "validate_delivery_md.py",
        )
        self.validator = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(self.validator)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_state(self, steps: dict) -> None:
        (self.dir / "EP01-run_state.json").write_text(
            json.dumps({"episode": "EP01", "steps": steps, "deliveryHash": ""}),
            encoding="utf-8",
        )

    def test_missing_state_file_is_rejected(self):
        errors, _ = self.validator.check_pipeline_state(self.delivery)
        self.assertTrue(any("缺少流程凭据" in e for e in errors))

    def test_incomplete_steps_are_rejected(self):
        self.write_state({"script_units": "done", "entities": "done"})
        errors, _ = self.validator.check_pipeline_state(self.delivery)
        self.assertTrue(any("前置步骤尚未完成" in e for e in errors))

    def test_complete_state_passes(self):
        self.write_state(
            {s: "done" for s in
             ("script_units", "entities", "assets", "segments", "coverage")}
        )
        errors, _ = self.validator.check_pipeline_state(self.delivery)
        self.assertEqual(errors, [])

    def test_stale_hash_warns(self):
        (self.dir / "EP01-run_state.json").write_text(
            json.dumps({
                "episode": "EP01",
                "steps": {s: "done" for s in
                          ("script_units", "entities", "assets", "segments", "coverage")},
                "deliveryHash": "0" * 64,
            }),
            encoding="utf-8",
        )
        errors, warnings = self.validator.check_pipeline_state(self.delivery)
        self.assertEqual(errors, [])
        self.assertTrue(any("流程凭据已过期" in w for w in warnings))

    def test_state_machine_passes_standalone_to_avoid_deadlock(self):
        """coverage 步骤要调校验器；若校验器反查凭据会要求 coverage 已完成 = 死锁。"""
        source = (
            Path(__file__).resolve().parents[1] / "scripts" / "pipeline_state.py"
        ).read_text(encoding="utf-8")
        self.assertIn("--standalone", source)


if __name__ == "__main__":
    unittest.main()
