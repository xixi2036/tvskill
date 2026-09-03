import importlib.util
import struct
import tempfile
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
                    "标题文字置于顶部中央：WANWU SHENG TEST COLOR REFERENCE。"
                    "所有色块均为纯平色、锐利硬边，无渐变、无纹理、无噪点、无阴影。"
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertEqual(errors, [])

    def test_color_card_prompt_is_audited_without_name_metadata(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "prompt": (
                    "A clean color palette swatch reference card design. "
                    "13 evenly-sized swatches in a single row."
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertTrue(any("16:9" in item for item in errors))
        self.assertTrue(any("COLOR REFERENCE" in item for item in errors))

    def test_color_card_accepts_wanwusheng_english_sharp_clean_edges(self):
        colors = " ".join(f"#{index:06X}" for index in range(1, 14))
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "prompt": (
                    "16:9 horizontal layout. White background. "
                    "13 evenly-sized swatches in a single row. "
                    "Below each swatch, black monospace HEX labels. "
                    f"{colors}. "
                    "sharp clean edges, pure flat color, no gradient, no texture, "
                    "no noise, no shadows. Title text at the top center: "
                    "TEST COLOR REFERENCE."
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
        self.assertTrue(any("13 个" in item for item in errors))
        self.assertTrue(any("9:16" in item for item in errors))
        self.assertTrue(any("HEX" in item for item in errors))
        self.assertTrue(any("无文字/无标签" in item for item in errors))

    def test_accepts_standard_3d_character_reference_board(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "name": "EP01-C01-角色-顾续尘-标准参考图-v01",
                "resolution": "2048x1152",
                "prompt": (
                    "16:9横版影视级国漫风格化3D官方角色设定展示板，纯白无缝背景。"
                    "左侧约三分之一为完整正面头肩肖像，其余区域并排展示全身正面、"
                    "全身侧面、全身背面三视图。人物保持中性站姿与中性表情。"
                    "无标题、无文字、无水印，不出现剧情场景或道具。"
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertEqual(errors, [])

    def test_rejects_portrait_character_board_without_name_metadata(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "resolution": "1152x2048",
                "prompt": (
                    "9:16竖版高端日韩风格化3D官方角色设定展示板，纯白无缝背景。"
                    "左侧约三分之一为完整正面头肩肖像，其余区域并排展示全身正面、"
                    "全身侧面、全身背面三视图。人物保持中性站姿与中性表情。"
                    "无标题、无文字、无水印，不出现剧情场景或道具。"
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertTrue(any("16:9" in item for item in errors))
        self.assertTrue(any("不得继承 9:16" in item for item in errors))
        self.assertTrue(any("分辨率必须为横向 16:9" in item for item in errors))

    def test_rejects_landscape_prompt_with_portrait_node_resolution(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "resolution": "1152x2048",
                "prompt": (
                    "16:9横版高端日韩风格化3D官方角色设定展示板，纯白无缝背景。"
                    "左侧约三分之一为完整正面头肩肖像，其余区域并排展示全身正面、"
                    "全身侧面、全身背面三视图。人物保持中性站姿与中性表情。"
                    "无标题、无文字、无水印，不出现剧情场景或道具。"
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertTrue(any("分辨率必须为横向 16:9" in item for item in errors))

    def test_ratio_does_not_hide_conflicting_portrait_resolution(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "ratio": "16:9",
                "resolution": "1152x2048",
                "prompt": (
                    "16:9横版高端日韩风格化3D标准人物四视图，纯白无缝背景。"
                    "包含正面头肩肖像、全身正面、全身侧面、全身背面。"
                    "人物保持中性站姿与中性表情，无文字、无水印。"
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertTrue(any("分辨率必须为横向 16:9" in item for item in errors))

    def test_generic_standard_character_multiview_is_audited(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "resolution": "1152x2048",
                "prompt": (
                    "9:16竖版高端日韩风格化3D标准人物四视图，纯白无缝背景。"
                    "包含正面头肩肖像、全身正面、全身侧面、全身背面。"
                    "人物保持中性站姿与中性表情，无文字、无水印。"
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertTrue(any("不得继承 9:16" in item for item in errors))

    def test_post_run_output_file_must_be_landscape_16_9(self):
        with tempfile.TemporaryDirectory() as directory:
            portrait = Path(directory) / "portrait.png"
            portrait.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + struct.pack(">I", 13)
                + b"IHDR"
                + struct.pack(">II", 1152, 2048)
            )
            landscape = Path(directory) / "landscape.png"
            landscape.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + struct.pack(">I", 13)
                + b"IHDR"
                + struct.pack(">II", 2048, 1152)
            )
            self.assertTrue(MOD.audit_character_output_file(portrait))
            self.assertEqual(MOD.audit_character_output_file(landscape), [])

    def test_succeeded_character_board_requires_downloaded_output_file(self):
        target = {"status": "succeeded"}
        errors = MOD.audit_character_output_requirement(target, True, None)
        self.assertTrue(any("缺少 --output-file" in item for item in errors))
        self.assertEqual(
            MOD.audit_character_output_requirement({"status": "idle"}, True, None),
            [],
        )

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

    def test_negated_or_future_still_markers_do_not_block_reference_board(self):
        target = {
            "type": "image-generator",
            "status": "idle",
            "params": {
                "resolution": "2048x1152",
                "prompt": (
                    "16:9横版高端日韩风格化3D官方角色设定展示板，纯白无缝背景。"
                    "包含正面头肩肖像、全身正面、全身侧面、全身背面。"
                    "人物保持中性站姿与中性表情，无文字、无水印。"
                    "哭泣与红肿双眼均属后续状态，本板不生成。"
                    "不得出现报纸、沙发、场景或道具。"
                ),
            },
        }
        errors, _ = MOD.audit(target, [], {}, [], True)
        self.assertEqual(errors, [])

    def test_unrelated_negation_does_not_hide_positive_still_markers(self):
        base = (
            "16:9横版高端日韩风格化3D官方角色设定展示板，纯白无缝背景。"
            "包含正面头肩肖像、全身正面、全身侧面、全身背面。"
            "人物保持中性站姿与中性表情，无文字、无水印。"
        )
        for sentence in (
            "人物端坐沙发未起身。",
            "人物端坐沙发但不得出现道具。",
            "人物不得哭泣但端坐沙发。",
            "人物无道具、端坐沙发。",
        ):
            with self.subTest(sentence=sentence):
                target = {
                    "type": "image-generator",
                    "status": "idle",
                    "params": {
                        "resolution": "2048x1152",
                        "prompt": base + sentence,
                    },
                }
                errors, _ = MOD.audit(target, [], {}, [], True)
                self.assertTrue(any("剧照/表演锚语义" in item for item in errors))

    def test_distributed_action_negation_still_exempts_the_target_marker(self):
        for sentence in (
            "人物不得扶门框、端坐沙发。",
            "不得出现报纸、沙发、场景。",
        ):
            with self.subTest(sentence=sentence):
                self.assertEqual(MOD.positive_still_markers(sentence), [])

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

    def test_video_first_frame_is_not_misclassified_by_character_reference_words(self):
        prompt = (
            "资产类型：EP01-V01 的 9:16 干净视频首帧。"
            "输出一张完整单幅影视画面，不是人物设定板。"
            "参考图1（吴馨16:9人物三视图）只锁身份，不继承中性站姿。"
        )
        self.assertFalse(MOD.is_character_reference("", prompt))


if __name__ == "__main__":
    unittest.main()
