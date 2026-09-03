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


class TimecodeScriptFormatTests(unittest.TestCase):
    """时间码体标准剧本（`场景 N … 00:00-00:44` + `[00:00] 画面`）的解析。

    真实样本：万妖图录传-scripts-asian/01-第01集.docx。
    修复前该体例画面单元抽取为 0，且每条画面描述被误判为台词——
    因为 `[00:00]` 自带的冒号让 `[^：:]{0,12}[：:]` 命中。
    script_units 是九步状态机第一步，它归零则整条产线在第一步停住。
    """

    STANDARD = [
        "第01集",
        "场景 1　外　日　荒野战场  00:00-00:44",
        "人物：姜月初(破烂粗布衣)、裴长青(重伤官服)　　道具：虎妖尸体、破损囚车",
        "[00:00] 镜头从下往上摇，阴沉的天空下，阳光透过云层洒在荒野上。",
        "[00:02] 极近景特写，姜月初猛地睁开眼睛，瞳孔微缩，眼神惊恐。",
        "姜月初（内心）：[00:03] 我……穿越了。",
        "裴长青（虚弱）：[00:40] 过来，扶我起来。",
    ]

    def test_timecode_prefixed_lines_are_visual_units(self):
        units = MODULE.extract(self.STANDARD, episode=1)
        texts = [u["text"] for u in units]
        self.assertEqual(len(units), 2, texts)
        self.assertTrue(all(u["kind"] == "visual" for u in units), units)
        self.assertTrue(texts[0].startswith("[00:00]"))

    def test_timecode_line_is_not_swallowed_as_dialogue(self):
        # 回归本体：时间码里的冒号不得让画面行命中台词正则
        self.assertIsNone(
            MODULE.SCRIPT_DIALOGUE_LINE_RE.match("[00:00] 镜头从下往上摇，阴沉的天空下。")
        )
        self.assertIsNotNone(
            MODULE.SCRIPT_DIALOGUE_LINE_RE.match("姜月初（内心）：[00:03] 我……穿越了。")
        )

    def test_speaker_lines_still_land_in_the_voice_ledger(self):
        units = MODULE.extract(self.STANDARD, episode=1, kinds=MODULE.VOICE_KINDS)
        self.assertEqual([u["kind"] for u in units], ["dialogue", "dialogue"])
        self.assertIn("穿越了", units[0]["text"])

    def test_standard_scene_header_does_not_overwrite_episode_number(self):
        # 「场景 1」里的 1 是场次序号；若被当成集号自纠，episode=2 的单元会全部丢失
        paragraphs = [
            "第02集",
            "场景 1　内　夜　卧室  00:00-00:20",
            "[00:00] 姜月初推门进屋。",
        ]
        units = MODULE.extract(paragraphs, episode=2)
        self.assertEqual(len(units), 1, units)
        self.assertEqual(units[0]["episode"], 2)
        self.assertTrue(units[0]["scene"].startswith("场景 1"))

    def test_marker_style_script_still_parses(self):
        # 两种体例必须并存：▲ 体（抽取型剧本）不得因本次修复受影响
        paragraphs = [
            "第1集",
            "1-1 荒村 外 雨",
            "▲ 暴雨过后的荒废村落，残垣断壁遍布碎石瓦砾。",
            "狼妖：（【狂暴】）：\"（嘶吼声）\"",
        ]
        units = MODULE.extract(paragraphs, episode=1)
        self.assertEqual(len(units), 1, units)
        self.assertEqual(units[0]["kind"], "visual")
        self.assertTrue(units[0]["text"].startswith("▲"))


if __name__ == "__main__":
    unittest.main()
