from __future__ import annotations

import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "extract_script_units.py"
SPEC = importlib.util.spec_from_file_location("extract_script_units", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ExtractScriptUnitsTests(unittest.TestCase):
    def test_bracketed_cast_metadata_is_not_a_coverage_unit(self):
        paragraphs = [
            "第1集：",
            "1-1 客厅 日 内",
            "【出场人物：吴馨、李承】",
            "【出场角色:吴馨、李承】",
            "【人物：吴馨、李承】",
            "【角色:吴馨、李承】",
            "【备注：保留为普通剧本注记】",
            "△ 吴馨走进客厅。",
        ]

        units = MODULE.extract(paragraphs, episode=1)

        self.assertEqual(
            [(unit["kind"], unit["text"]) for unit in units],
            [
                ("note", "【备注：保留为普通剧本注记】"),
                ("visual", "△ 吴馨走进客厅。"),
            ],
        )

    def test_filled_triangle_transition_is_visual(self):
        units = MODULE.extract(
            ["第1集：", "1-1 客厅 日 内", "▲转场"],
            episode=1,
        )

        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["kind"], "visual")
        self.assertEqual(units[0]["text"], "▲转场")

    def test_docx_soft_breaks_become_ordered_logical_lines(self):
        document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r>
    <w:t>上一集末句。</w:t><w:br w:type="textWrapping"/>
    <w:t>第8集：</w:t><w:br/>
    <w:t>8-1 客厅 夜 内 吴馨：第一句。</w:t><w:br/>
    <w:t>李承：第二句。 △ 第一条画面。</w:t><w:cr/>
    <w:t>△ 第二条画面。</w:t>
  </w:r></w:p></w:body>
</w:document>
"""
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "soft-breaks.docx"
            with zipfile.ZipFile(script, "w") as archive:
                archive.writestr("word/document.xml", document_xml)
            paragraphs = MODULE.docx_paragraphs(script)

        self.assertEqual(
            paragraphs,
            [
                "上一集末句。",
                "第8集：",
                "8-1 客厅 夜 内",
                "吴馨：第一句。",
                "李承：第二句。",
                "△ 第一条画面。",
                "△ 第二条画面。",
            ],
        )
        units = MODULE.extract(
            paragraphs,
            episode=8,
            kinds=MODULE.VISUAL_KINDS + MODULE.VOICE_KINDS,
        )
        self.assertEqual(
            [(unit["kind"], unit["text"]) for unit in units],
            [
                ("dialogue", "吴馨：第一句。"),
                ("dialogue", "李承：第二句。"),
                ("visual", "△ 第一条画面。"),
                ("visual", "△ 第二条画面。"),
            ],
        )
        self.assertEqual({unit["episode"] for unit in units}, {8})

    def test_episode_heading_accepts_fullwidth_and_halfwidth_colons(self):
        for heading in ("第 1 集：", "第1集:", "第1集：开场", "第 1 集: 开场"):
            with self.subTest(heading=heading):
                units = MODULE.extract(
                    [heading, "1-1 客厅 日 内", "△ 女主推门进入。"],
                    episode=1,
                )
                self.assertEqual(len(units), 1)
                self.assertEqual(units[0]["episode"], 1)
                self.assertEqual(units[0]["scene"], "1-1 客厅 日 内")

    def test_first_scene_prefix_corrects_conflicting_episode_heading(self):
        paragraphs = [
            "第 118 集：",
            "18-1 滨江湾豪宅宴会厅 夜 内",
            "△ 宾客们望向宴会厅入口。",
            "18-2 滨江湾豪宅走廊 夜 内",
            "△ 女主沿走廊离开。",
        ]

        units = MODULE.extract(paragraphs, episode=18)

        self.assertEqual(
            [unit["scene"] for unit in units],
            ["18-1 滨江湾豪宅宴会厅 夜 内", "18-2 滨江湾豪宅走廊 夜 内"],
        )
        self.assertEqual([unit["episode"] for unit in units], [18, 18])
        self.assertEqual(MODULE.extract(paragraphs, episode=118), [])


if __name__ == "__main__":
    unittest.main()
