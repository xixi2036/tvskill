import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "audit_image_asset_node.py"
SPEC = importlib.util.spec_from_file_location("audit_image_asset_node", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


class AuditImageAssetNodeTests(unittest.TestCase):
    def test_semantic_tokens_match_ordered_edges(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {"prompt": "以参考图1（手袋）锁定手袋，以参考图2（女鞋）锁定女鞋。"},
        }
        edges = [{"fromNodeId": "n-bag"}, {"fromNodeId": "n-shoe"}]
        upstream = {
            "n-bag": {"status": "succeeded", "content": "https://x/bag.png"},
            "n-shoe": {"status": "succeeded", "history": ["https://x/shoe.png"]},
        }
        errors, _ = MOD.audit(target, edges, upstream, [("手袋", "n-bag"), ("女鞋", "n-shoe")], True)
        self.assertEqual(errors, [])

    def test_rejects_plain_image_number_and_internal_prefix(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {"prompt": "A01 叶敏-v02。图片1是手袋。"},
        }
        errors, _ = MOD.audit(target, [{"fromNodeId": "n-bag"}], {}, [("手袋", "n-bag")], False)
        self.assertTrue(any("内部资产编号" in item for item in errors))
        self.assertTrue(any("未绑定" in item for item in errors))

    def test_pre_run_requires_successful_parent_output(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {"prompt": "使用参考图1（人物定妆）。"},
        }
        errors, _ = MOD.audit(
            target,
            [{"fromNodeId": "n-parent"}],
            {"n-parent": {"status": "idle"}},
            [("人物定妆", "n-parent")],
            True,
        )
        self.assertTrue(any("父图未成功" in item for item in errors))

    def test_accepts_fixed_wanwusheng_color_card_layout(self):
        colors = "、".join(f"颜色{i} #{i:06X}（用途{i}）" for i in range(1, 14))
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "name": "EP01-A06-色卡-客厅",
                "prompt": (
                    "16:9横版万物生标准色卡参考图，纯白背景。"
                    "13个等大矩形色块在同一行从左到右单排排列，每个色块下方以小号黑色等宽字体标注HEX。"
                    f"从左到右：{colors}。"
                    "所有色块均为纯平色、锐利硬边，无渐变、无纹理、无噪点、无阴影。"
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertEqual(errors, [])

    def test_rejects_video_aspect_five_band_color_card(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "name": "EP01-A06-色卡-客厅",
                "prompt": (
                    "9:16竖版纯色色卡，五个等面积水平大色块。"
                    "边界干净，无渐变、无纹理、无文字。"
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertTrue(any("16:9" in item for item in errors))
        self.assertTrue(any("13/22/24" in item for item in errors))
        self.assertTrue(any("9:16" in item for item in errors))
        self.assertTrue(any("HEX" in item for item in errors))
        self.assertTrue(any("无文字/无标签" in item for item in errors))

    def test_accepts_22_color_wanwu_wenxin_extension(self):
        """问心复杂场景色卡:22色档,版式约束不变,只放开数量(2026-08-01补)。"""
        colors = "、".join(f"颜色{i} #{i:06X}（用途{i}）" for i in range(1, 23))
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "name": "EP01-A09-色卡-废墟战场",
                "prompt": (
                    "16:9横版万物生标准色卡参考图，纯白背景。"
                    "22个等大矩形色块在同一行从左到右单排排列，每个色块下方以小号黑色等宽字体标注HEX。"
                    f"从左到右：{colors}。"
                    "所有色块均为纯平色、锐利硬边，无渐变、无纹理、无噪点、无阴影。"
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertEqual(errors, [])

    def test_rejects_declared_count_mismatching_actual_hex_count(self):
        """文字声明22色但实际只列13个HEX——数量对不上必须拦。"""
        colors = "、".join(f"颜色{i} #{i:06X}（用途{i}）" for i in range(1, 14))
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "name": "EP01-A09-色卡-废墟战场",
                "prompt": (
                    "16:9横版万物生标准色卡参考图，纯白背景。"
                    "22个等大矩形色块在同一行从左到右单排排列，每个色块下方以小号黑色等宽字体标注HEX。"
                    f"从左到右：{colors}。"
                    "所有色块均为纯平色、锐利硬边，无渐变、无纹理、无噪点、无阴影。"
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertTrue(any("声明色块数(22)与实际列出的 HEX 数(13)不一致" in item for item in errors))

    def test_accepts_standard_3d_character_reference_board(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "name": "EP01-C01-角色-顾续尘-标准参考图-v01",
                "prompt": (
                    "影视级国漫风格化3D官方角色设定展示板，纯白无缝背景。"
                    "左侧约三分之一为完整正面头肩肖像，其余区域并排展示全身正面、"
                    "全身侧面、全身背面三视图。人物保持中性站姿与中性表情。"
                    "无标题、无文字、无水印，不出现剧情场景或道具。"
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertEqual(errors, [])

    def test_rejects_character_still_as_standard_reference(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "name": "EP01-A02-角色-顾续尘定妆-候选-v02",
                "prompt": (
                    "9:16单人全身定妆照，暖灰影棚底。人物一手扶门框，"
                    "视线落在画外较低位置，电影实用光，无文字无水印。"
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertTrue(any("角色设定展示板" in item for item in errors))
        self.assertTrue(any("剧照/表演锚语义" in item for item in errors))

    def test_performance_anchor_is_not_forced_into_reference_board_layout(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "name": "EP01-A13-角色-顾续尘-表演锚-v01",
                "prompt": "人物端坐沙发，视线落在画外，无文字无水印。",
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
