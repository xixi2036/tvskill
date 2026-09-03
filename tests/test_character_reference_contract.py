import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CharacterReferenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.contract = (
            ROOT / "references" / "libtv" / "asset-production-contract.md"
        ).read_text(encoding="utf-8")

    def test_character_still_cannot_be_root_reference(self):
        self.assertIn("人物“标准参考图”和“人物剧照/表演锚”必须分开", self.skill)
        self.assertIn("禁止冒充身份根资产", self.skill)
        self.assertIn("人物剧照不得反向替代标准设定资产", self.skill)

    def test_3d_standard_board_has_required_views(self):
        for required in (
            "16:9",
            "横版",
            "正面头肩肖像",
            "全身正面",
            "全身侧面",
            "全身背面",
            "纯白无缝背景",
            "作为该角色唯一身份 Mixed",
            "排除白底、多分格",
        ):
            self.assertIn(required, self.contract)
        self.assertIn("`9:16` 只用于最终视频", self.skill)
        self.assertIn("站位、坐姿、表情和眼神一律由干净首帧", self.skill)
        self.assertNotIn("整图画布为 9:16", self.contract)
        self.assertNotIn("造资产前先看角色服装领口类型", self.contract)

    def test_still_markers_are_explicit(self):
        for marker in ("扶门框", "端坐沙发", "看向画外角色", "场景透视"):
            self.assertIn(marker, self.contract)

    def test_character_anatomy_gate_rejects_long_neck(self):
        for required in (
            "下巴到锁骨",
            "胸锁乳突肌",
            "斜方肌",
            "长颈鹿颈",
            "头颅悬浮",
            "不得登记 STYLE-ID",
        ):
            self.assertIn(required, self.contract)


if __name__ == "__main__":
    unittest.main()
