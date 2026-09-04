from __future__ import annotations

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
