from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "extract_script_entities.py"
SPEC = importlib.util.spec_from_file_location("extract_script_entities", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ExtractScriptEntitiesTests(unittest.TestCase):
    SCRIPT = [
        "第01集",
        "场景 1　外　日　荒野战场  00:00-00:44",
        "人物：姜月初(破烂粗布衣)、裴长青(重伤官服)　　道具：虎妖尸体、破损囚车",
        "[00:00] 全景，荒野上散落着尸体。",
        "场景 2　外　日　牡丹园  00:44-01:03",
        "[00:47] 阳光明媚的牡丹园，穿着华丽红色汉服的姜月初微笑着看着花丛。",
        "场景 3　内　日　神秘空间  01:51-01:55",
        "人物：无　　道具：妖物图鉴卷轴",
        "[01:51] 蓝色代码空间中悬浮着卷轴。",
    ]

    def _draft(self):
        scenes = MODULE.collect(self.SCRIPT)["scenes"]
        return scenes, MODULE.build_draft(scenes)

    def test_each_form_is_its_own_asset_unit(self):
        # 合同：形态是资产的单位，不是角色
        _scenes, draft = self._draft()
        jiang = [c for c in draft["characters"] if c["name"] == "姜月初"][0]
        self.assertEqual([f["form"] for f in jiang["forms"]], ["破烂粗布衣"])
        self.assertTrue(all(f["assetUnit"] for f in jiang["forms"]))

    def test_undeclared_cast_is_not_treated_as_zero_people(self):
        # 场景 2 没有人物行,但正文里有「华丽红色汉服的姜月初」——
        # 若当成 0 人,会静默漏掉姜月初的第二个形态资产
        scenes, draft = self._draft()
        scene2 = [s for s in scenes if s["no"] == "2"][0]
        self.assertFalse(scene2["castDeclared"])
        peony = [s for s in draft["scenes"] if s["place"] == "牡丹园"][0]
        state = peony["states"][0]["state"]
        self.assertIn("未声明", state)
        self.assertNotIn("0人", state)

    def test_explicit_none_is_a_verified_zero(self):
        # 「人物：无」是已核对的零,与声明缺失必须区别对待
        scenes, draft = self._draft()
        scene3 = [s for s in scenes if s["no"] == "3"][0]
        self.assertTrue(scene3["castDeclared"])
        self.assertEqual(scene3["cast"], [])
        space = [s for s in draft["scenes"] if s["place"] == "神秘空间"][0]
        self.assertIn("0人", space["states"][0]["state"])

    def test_scene_span_is_parsed_into_seconds(self):
        scenes, _draft = self._draft()
        self.assertEqual((scenes[0]["startSec"], scenes[0]["endSec"]), (0, 44))

    def test_props_carry_scene_appearances(self):
        _scenes, draft = self._draft()
        names = {p["name"]: p["scenes"] for p in draft["props"]}
        self.assertEqual(names["虎妖尸体"], ["1"])
        self.assertEqual(names["妖物图鉴卷轴"], ["3"])

    def test_marker_style_script_yields_no_scenes(self):
        # ▲ 体没有「场景 N」声明行,应得空结果由 CLI 层给提示,而不是编造实体
        scenes = MODULE.collect(["第1集", "1-1 荒村 外 雨", "▲ 暴雨过后的荒废村落。"])["scenes"]
        self.assertEqual(scenes, [])


if __name__ == "__main__":
    unittest.main()
