"""语料回归：闸的判据必须与真实语料对照，不能只照着规范自洽。

存在理由——已经踩过三次的同一个坑：校验器是照着规范写的，不是照着真实通过的提示词
写的，于是对真实写法系统性误报。`\\b` 在中文旁不成立（"系统VO" 的 VO 从未被识别）、
`#7A4FBD暗紫` 判不出 HEX、`NOT卡通渲染` 判不出 NOT 链、"晨光" 不在光源词表里——
这些都不是理论问题，是真实语料一跑就现形的问题。

因此规则是：**任何正则或词表的改动，都必须先在本语料上跑一遍。**
- 假阳性禁止：语料里客观存在的东西，闸必须认得（本文件的 must_not_flag）
- 真阳性保留：语料里客观缺失的东西，闸必须照报（本文件的 must_flag）

语料是真实生产提示词脱敏而来，保留了全部排版特征（中文紧贴的 HEX 与 NOT、
系统VO 写法、台词右侧括注、【】结构块），只替换了专有名词。
"""

from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_delivery_md", ROOT / "scripts" / "validate_delivery_md.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

CORPUS = json.loads(
    (ROOT / "tests" / "corpus" / "real_prompts.json").read_text(encoding="utf-8")
)

# 带完整万物生结构的样本（V1-V5、V10-V11）；V6-V9 是旧写法，另作对照。
CRAFT_SAMPLES = [key for key in CORPUS if key not in {"V6", "V7", "V8", "V9"}]
LEGACY_SAMPLES = ["V6", "V7", "V8", "V9"]


class CorpusRegressionTests(unittest.TestCase):
    def prompt(self, key: str) -> str:
        return CORPUS[key]["prompt"]

    def test_corpus_is_present(self):
        self.assertEqual(len(CORPUS), 11)

    # ---- 假阳性禁止：语料里有的，闸必须认得 ----

    def test_chinese_adjacent_hex_is_detected(self):
        for key in CRAFT_SAMPLES:
            with self.subTest(key):
                self.assertTrue(
                    MODULE.INLINE_HEX_RE.search(self.prompt(key)),
                    "真实语料写作 #7A4FBD暗紫，HEX 必须能识别",
                )

    def test_chinese_adjacent_not_chain_is_detected(self):
        for key in CRAFT_SAMPLES:
            with self.subTest(key):
                self.assertTrue(
                    MODULE.NOT_CHAIN_RE.search(self.prompt(key)),
                    "真实语料写作 NOT卡通渲染+NOT三维动画，NOT 链必须能识别",
                )

    def test_voice_over_marked_after_line_is_recognized(self):
        # 真实写法把声源标在台词右侧：{台词}(系统VO,使用Mixed 3音色)
        vo_samples = [
            key for key in CORPUS if "VO" in self.prompt(key)
        ]
        self.assertTrue(vo_samples, "语料里应当有 VO 样本")
        for key in vo_samples:
            with self.subTest(key):
                speakers = MODULE.text_voice_subjects(self.prompt(key))
                self.assertTrue(
                    any("VO" in s for s in speakers),
                    f"{key} 的 VO 声源没有被识别为说话人：{speakers}",
                )

    def test_self_luminous_and_natural_light_are_detected(self):
        for key in CORPUS:
            with self.subTest(key):
                self.assertTrue(
                    MODULE.PHYSICAL_LIGHT_RE.search(self.prompt(key)),
                    "虚空的光束/电弧与室内的晨光都是具体可识别光源",
                )

    def test_style_lock_line_is_detected(self):
        for key in CRAFT_SAMPLES:
            with self.subTest(key):
                first = self.prompt(key).splitlines()[0]
                self.assertTrue(
                    MODULE.STYLE_LOCK_RE.match(first),
                    f"{key} 首行是风格锁定行，必须能识别：{first[:40]}",
                )

    def test_asset_anchor_phrasing_is_detected(self):
        for key in CRAFT_SAMPLES:
            with self.subTest(key):
                self.assertTrue(
                    MODULE.ASSET_ANCHOR_RE.search(self.prompt(key)),
                    "真实写法是「严格按此图渲染+不可改造」",
                )

    def test_structure_blocks_are_allowed_brackets(self):
        for key in CRAFT_SAMPLES:
            with self.subTest(key):
                bad = [
                    token for token in MODULE.BRACKET_RE.findall(self.prompt(key))
                    if not MODULE.ALLOWED_BRACKETS_RE.match(token)
                ]
                self.assertEqual(bad, [], f"{key} 的结构块不应被判为画面文字")

    def test_sound_design_seconds_do_not_trip_timecode_ban(self):
        for key in CRAFT_SAMPLES:
            with self.subTest(key):
                prompt = self.prompt(key)
                if "【声音设计】" not in prompt:
                    continue
                stripped = MODULE.SOUND_DESIGN_BLOCK_RE.sub("", prompt)
                self.assertFalse(
                    MODULE.ABSOLUTE_TIME_RE.search(stripped),
                    f"{key} 的秒层只出现在声音设计段内，段外不该有绝对时间码",
                )

    # ---- 真阳性保留：语料里确实缺的，闸必须照报 ----

    def test_missing_official_subject_definition_is_still_flagged(self):
        # 真实缺陷：万物生锚定语替代了官方「定义为 <主体N>」，两者必须并存
        for key in CORPUS:
            with self.subTest(key):
                self.assertIsNone(
                    re.search(r"定义为\s*<主体\d+>", self.prompt(key)),
                    f"{key} 若已补上官方定义法，请更新本回归基线",
                )

    def test_legacy_samples_still_lack_craft_structure(self):
        for key in LEGACY_SAMPLES:
            with self.subTest(key):
                prompt = self.prompt(key)
                self.assertNotIn("【声音设计】", prompt)
                self.assertIsNone(MODULE.NOT_CHAIN_RE.search(prompt))

    def test_vague_quality_words_are_still_rejected(self):
        # 反向锁：放宽词表不等于放水
        for text in ("画面整体明亮", "光影柔和", "电影质感十足"):
            with self.subTest(text):
                self.assertIsNone(MODULE.PHYSICAL_LIGHT_RE.search(text))


if __name__ == "__main__":
    unittest.main()
