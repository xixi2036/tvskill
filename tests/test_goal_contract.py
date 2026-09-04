from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "goal_contract.py"
SPEC = importlib.util.spec_from_file_location("goal_contract", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


FILLED = """# 万妖图录传 目标契约

## 媒介与风格
- 媒介：3D CG
- 3D 子风格：影视级国漫风格化3D
- STYLE-ID：万妖图录传-写实国漫
- 保真取向：电影感
- 成像基底：35mm 发行拷贝

## 技术口径
- 模型展示名：Seedance 2.0 Fast VIP
- 画幅：9:16
- 分辨率：480p
- 视频预算路线：一次性预算

## 交付边界
- 交付到哪一步：仅 Markdown
- 集数范围：EP01-EP12

## 资产策略
- 资产来源：全新生成
- 跨集身份根归属：EP01 首建

## 声音路线
- 音色来源：人工上传
- 音色采样预览例外：否
- BGM：无

## 质量目标
- 对标成片：万妖图录传 EP01
- 验收严格度：十轴审计全过
"""

DELIVERY = """# EP01｜LibTV 完成提示词

- 模型：Seedance 2.0 Fast VIP
- 画幅：9:16
- 分辨率：480p

## 生成段 V01｜开场
镜头1：中景。3D CG 写实国漫质感，画面中主角站在门口。
"""


class TestParse(unittest.TestCase):
    def test_parses_all_fields(self):
        goal, linenos = MODULE.parse(FILLED)
        self.assertEqual(goal["媒介"], "3D CG")
        self.assertEqual(goal["成像基底"], "35mm 发行拷贝")
        self.assertEqual(goal["BGM"], "无")
        self.assertEqual(len(goal), sum(len(v) for v in MODULE.SECTIONS.values()))
        self.assertEqual(linenos["媒介"], 4)

    def test_template_itself_parses(self):
        goal, _ = MODULE.parse(MODULE.TEMPLATE)
        self.assertEqual(len(goal), sum(len(v) for v in MODULE.SECTIONS.values()))

    def test_missing_section_names_it(self):
        text = FILLED.replace("## 声音路线", "## 声音路线XX")
        with self.assertRaises(MODULE.GoalContractError) as ctx:
            MODULE.parse(text)
        self.assertIn("声音路线", str(ctx.exception))

    def test_missing_field_names_it(self):
        text = FILLED.replace("- 成像基底：35mm 发行拷贝\n", "")
        with self.assertRaises(MODULE.GoalContractError) as ctx:
            MODULE.parse(text)
        self.assertIn("成像基底", str(ctx.exception))


class TestStructureErrors(unittest.TestCase):
    def test_pending_value_reports_line_number(self):
        text = FILLED.replace("- STYLE-ID：万妖图录传-写实国漫", "- STYLE-ID：待定")
        goal, linenos = MODULE.parse(text)
        errors = MODULE.structure_errors(goal, linenos)
        self.assertTrue(any("STYLE-ID" in e and "第 6 行" in e for e in errors))

    def test_leftover_inferred_marker_reports_line_number(self):
        text = FILLED.replace("- 媒介：3D CG", "- 媒介：3D CG [推断]")
        goal, linenos = MODULE.parse(text)
        errors = MODULE.structure_errors(goal, linenos)
        self.assertTrue(any("媒介" in e and "[推断]" in e for e in errors))

    def test_clean_contract_has_no_structure_errors(self):
        goal, linenos = MODULE.parse(FILLED)
        self.assertEqual(MODULE.structure_errors(goal, linenos), [])


class TestAvailableChoices(unittest.TestCase):
    def test_model_choices_are_intersection_of_whitelist_and_aliases(self):
        choices = MODULE.available_choices()
        self.assertIn("Seedance 2.0 Fast VIP", choices["模型展示名"])
        # 2.5 在 SUPPORTED_MODELS 里，但 sync 的 MODEL_ALIASES 没有它；
        # 选了会在 sync 阶段才炸，因此不得进入候选集。
        self.assertNotIn("Seedance 2.5", choices["模型展示名"])

    def test_ratio_and_resolution_choices_present(self):
        choices = MODULE.available_choices()
        self.assertIn("9:16", choices["画幅"])
        self.assertIn("480p", choices["分辨率"])


class TestValueErrors(unittest.TestCase):
    def _goal(self, **overrides):
        text = FILLED
        for key, value in overrides.items():
            text = re.sub(rf"^- {re.escape(key)}：.*$", f"- {key}：{value}", text, flags=re.M)
        return MODULE.parse(text)

    def test_clean_contract_has_no_value_errors(self):
        goal, linenos = MODULE.parse(FILLED)
        self.assertEqual(MODULE.value_errors(goal, linenos), [])

    def test_illegal_enum_lists_legal_values(self):
        goal, linenos = self._goal(**{"保真取向": "很电影"})
        errors = MODULE.value_errors(goal, linenos)
        self.assertTrue(any("保真取向" in e and "电影感" in e for e in errors))

    def test_3dcg_requires_substyle(self):
        goal, linenos = self._goal(**{"3D 子风格": "不适用"})
        errors = MODULE.value_errors(goal, linenos)
        self.assertTrue(any("3D 子风格" in e for e in errors))

    def test_non_3dcg_requires_substyle_na(self):
        goal, linenos = self._goal(**{"媒介": "真人实拍"})
        errors = MODULE.value_errors(goal, linenos)
        self.assertTrue(any("3D 子风格" in e and "不适用" in e for e in errors))

    def test_cinematic_requires_substrate(self):
        goal, linenos = self._goal(**{"成像基底": "不适用"})
        errors = MODULE.value_errors(goal, linenos)
        self.assertTrue(any("成像基底" in e for e in errors))

    def test_lowfi_requires_substrate_na(self):
        goal, linenos = self._goal(**{"保真取向": "低保真"})
        errors = MODULE.value_errors(goal, linenos)
        self.assertTrue(any("成像基底" in e and "不适用" in e for e in errors))


class TestCrosscheck(unittest.TestCase):
    def test_consistent_delivery_passes(self):
        goal, _ = MODULE.parse(FILLED)
        self.assertEqual(MODULE.crosscheck(DELIVERY, goal), [])

    def test_forward_missing_anchor_reports(self):
        text = DELIVERY.replace("- 分辨率：480p\n", "")
        goal, _ = MODULE.parse(FILLED)
        errors = MODULE.crosscheck(text, goal)
        self.assertTrue(any("分辨率" in e for e in errors))

    def test_model_mismatch_shows_both_values(self):
        text = DELIVERY.replace("Seedance 2.0 Fast VIP", "Seedance 2.0 VIP")
        goal, _ = MODULE.parse(FILLED)
        errors = MODULE.crosscheck(text, goal)
        self.assertTrue(any("Seedance 2.0 Fast VIP" in e and "Seedance 2.0 VIP" in e
                            for e in errors))

    def test_ratio_mismatch_reports(self):
        text = DELIVERY.replace("- 画幅：9:16", "- 画幅：16:9")
        goal, _ = MODULE.parse(FILLED)
        self.assertTrue(any("画幅" in e for e in MODULE.crosscheck(text, goal)))

    def test_resolution_mismatch_reports(self):
        text = DELIVERY.replace("- 分辨率：480p", "- 分辨率：720p")
        goal, _ = MODULE.parse(FILLED)
        errors = MODULE.crosscheck(text, goal)
        self.assertTrue(any("分辨率" in e and "480p" in e and "720p" in e
                            for e in errors))

    def test_reverse_unauthorized_medium_reports(self):
        # 契约声明 3D CG，交付里某一段冒出「真人实拍」——反向对账必须抓到。
        text = DELIVERY + "\n镜头2：近景。真人实拍，自然光。\n"
        goal, _ = MODULE.parse(FILLED)
        errors = MODULE.crosscheck(text, goal)
        self.assertTrue(any("真人实拍" in e for e in errors))

    def test_medium_synonym_accepted(self):
        text = DELIVERY.replace("3D CG 写实国漫质感", "三维动画 写实国漫质感")
        goal, _ = MODULE.parse(FILLED)
        self.assertEqual(MODULE.crosscheck(text, goal), [])

    def test_record_only_and_quality_fields_not_crosschecked(self):
        goal, _ = MODULE.parse(FILLED)
        goal["集数范围"] = "EP01-EP99"
        goal["对标成片"] = "完全不同的片子"
        goal["BGM"] = "有"
        self.assertEqual(MODULE.crosscheck(DELIVERY, goal), [])


class TestDiff(unittest.TestCase):
    def test_reports_changed_fields_only(self):
        old, _ = MODULE.parse(FILLED)
        new = dict(old)
        new["媒介"] = "真人实拍"
        self.assertEqual(MODULE.diff(old, new), ["媒介：3D CG → 真人实拍"])

    def test_no_change_yields_empty(self):
        old, _ = MODULE.parse(FILLED)
        self.assertEqual(MODULE.diff(old, dict(old)), [])


if __name__ == "__main__":
    unittest.main()
