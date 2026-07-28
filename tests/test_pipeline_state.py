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
        self.assertIn("不对源就等于自证", detail)

    def test_prerequisites_block_skipping(self):
        state = {"episode": "EP01", "steps": {}, "deliveryHash": ""}
        self.assertEqual(
            MODULE.blocking_prerequisites("validate", state), ["coverage"]
        )
        state["steps"]["coverage"] = "done"
        self.assertEqual(MODULE.blocking_prerequisites("validate", state), [])

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
        self.assertEqual(state["steps"]["validate"], "pending")
        self.assertEqual(state["steps"]["entities"], "done")



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
