from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_canvas_nodes  # noqa: E402


def good_detail() -> dict:
    inputs = [
        {"nodeId": "char", "label": "TVSkill-EP03-单知影-独立人物图", "type": "image-input", "compliance": "active"},
        {"nodeId": "voice", "label": "TVSkill-EP03-单知影-逐句音频", "type": "audio-input", "compliance": "active"},
        {"nodeId": "first", "label": "TVSkill-EP03-V01-干净首帧", "type": "image-input", "compliance": "active"},
        {"nodeId": "scene", "label": "TVSkill-EP03-Z班教室-占座场景状态-S1", "type": "image-input", "compliance": "active"},
    ]
    return {
        "id": "good",
        "type": "video-generator",
        "name": "TVSkill-EP03-V01",
        "modelId": "doubao-seedance-2-0-fast-260128",
        "status": "idle",
        "params": {
            "prompt": (
                "将 @[图片:char]（单知影） 定义为 <主体1>；"
                "@[音频:voice]（单知影-逐句音频） 只控制 <主体1> 的音色，不继承原台词；"
                "参考 @[图片:first]（首帧-EP03-V01）；"
                "将 @[图片:scene]（场景状态-Z班-S1） 定义为 <场景1>。"
                "单一连续镜头，无剪切。中近景稳定机位，<主体1> 她说 {你，很吵。}，"
                "说完恢复鼻息。真人实拍，右侧窗光，无字幕、水印或 Logo。"
            ),
            "ratio": "9:16", "resolution": "480p", "duration": 6,
        },
        "_tvskillInputs": inputs,
    }


def bad_detail() -> dict:
    return {
        "id": "bad",
        "type": "video-generator",
        "name": "TVSkill-EP03-V01-旧节点",
        "modelId": "doubao-seedance-2-0-fast-260128",
        "status": "succeeded",
        "params": {
            "prompt": (
                "将 @[图片:char]（单知影） 定义为 <主体1>；"
                "将 @[图片:map]（李威） 定义为 <主体2>；"
                "参考 @[图片:scene]（构图-3-1-A）；"
                "将 @[图片:liwei]（场景-Z班教室） 定义为 <场景1>。"
                "\n镜头1：大全景，全班学生转头。"
                "\n镜头2：中景，<主体1>走向后排。"
                "\n镜头3：近景，他说 {马上退学！}。"
            ),
            "ratio": "9:16", "resolution": "480p", "duration": 10,
        },
        "_tvskillInputs": [
            {"nodeId": "char", "label": "TVSkill-EP03-单知影-独立人物图", "type": "image-input", "compliance": "active"},
            {"nodeId": "map", "label": "TVSkill-EP03-3-1-A-无身份位置图", "type": "image-input", "compliance": "unverified"},
            {"nodeId": "scene", "label": "TVSkill-EP03-Z班教室-无人物场景图", "type": "image-input", "compliance": "active"},
            {"nodeId": "liwei", "label": "TVSkill-EP03-李威-独立人物图", "type": "image-input", "compliance": "active"},
        ],
    }


class CanvasNodeAuditTests(unittest.TestCase):
    def test_audit_all_rejects_project_without_video_nodes_as_unassociated(self):
        with patch.object(audit_canvas_nodes, "run_tvmao", return_value=[]):
            with self.assertRaisesRegex(ValueError, "没有 video-generator 节点"):
                audit_canvas_nodes.collect_live_details(
                    "tvmao", 97, [], audit_all=True, asset_labels={}
                )

    def test_good_live_contract_passes(self):
        errors, warnings, summary = audit_canvas_nodes.audit_node(good_detail())
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(summary["inputs"], 4)

    def test_supported_nondefault_model_warns(self):
        detail = good_detail()
        detail["modelId"] = "doubao-seedance-2-0-260128"
        errors, warnings, _ = audit_canvas_nodes.audit_node(detail)
        self.assertEqual(errors, [])
        self.assertTrue(any("不是默认" in warning for warning in warnings))

    def test_live_tvmao_model_in_params_passes(self):
        detail = good_detail()
        detail["params"]["modelId"] = detail.pop("modelId")
        errors, warnings, _ = audit_canvas_nodes.audit_node(detail)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_native_audio_multishot_is_allowed(self):
        detail = good_detail()
        params = detail["params"]
        params["prompt"] = params["prompt"].replace(
            "单一连续镜头，无剪切。中近景稳定机位，", "\nShot 1: 中近景，稳定机位，"
        ) + "\nShot 2: 固定反应近景，对方自然眨眼并恢复呼吸。"
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertEqual(errors, [])

    def test_real_failure_shape_is_blocked(self):
        errors, warnings, _ = audit_canvas_nodes.audit_node(bad_detail())
        self.assertTrue(any("语义“李威”" in error for error in errors))
        self.assertTrue(any("规划图进入 TVMao 输入边" in error for error in errors))
        self.assertTrue(any("旧“镜头N：”" in error for error in errors))
        self.assertTrue(any("没有 audio-input" in error for error in errors))
        self.assertTrue(any("全景要求可见人群" in error for error in errors))
        self.assertTrue(any("节点状态为 succeeded" in warning for warning in warnings))

    def test_legacy_mixed_token_is_blocked(self):
        detail = good_detail()
        detail["params"]["prompt"] += " @[旧语义] {{Mixed 1}}"
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("尚未编译" in error for error in errors))

    def test_legacy_mixed_token_adjacent_to_chinese_text_is_blocked(self):
        detail = good_detail()
        detail["params"]["prompt"] += "说完后继续使用Mixed 2的音色。"
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("尚未编译" in error for error in errors))

    def test_exact_text_generation_is_blocked(self):
        detail = good_detail()
        detail["params"]["prompt"] += "纸面清晰显示且只显示“反向做空”。"
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("精确画面文字" in error for error in errors))

    def test_out_of_range_input_is_blocked(self):
        detail = good_detail()
        detail["params"]["prompt"] = detail["params"]["prompt"].replace(
            "@[图片:scene]（场景状态-Z班-S1）", "@[图片:missing]（场景状态-Z班-S1）"
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("没有同类型入边" in error for error in errors))

    def test_plain_numbered_reference_is_not_a_canvas_association(self):
        detail = good_detail()
        detail["params"]["prompt"] = detail["params"]["prompt"].replace(
            "@[图片:char]", "@图片1"
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("不会显示素材关联 chip" in error for error in errors))

    def test_named_prop_asset_matches_semantic_prop_prefix(self):
        item = {"label": "手袋-A", "type": "image-input"}
        self.assertTrue(
            audit_canvas_nodes.binding_matches_asset("道具-手袋-A", item, "图片")
        )
        key_item = {"label": "钥匙-A", "type": "image-input"}
        self.assertTrue(
            audit_canvas_nodes.binding_matches_asset("道具-钥匙-A", key_item, "图片")
        )

    def test_numbered_bindings_joined_by_chinese_text_are_both_parsed(self):
        bindings = audit_canvas_nodes.parse_bindings(
            "图片5（道具-手机-A）与图片6（道具-钥匙-A）分别锁单一实例"
        )
        self.assertEqual(
            bindings,
            [("图片", 5, "道具-手机-A"), ("图片", 6, "道具-钥匙-A")],
        )

    def test_four_native_shots_in_twelve_second_node_are_allowed(self):
        detail = good_detail()
        params = detail["params"]
        params["duration"] = 12
        params["prompt"] = params["prompt"].replace(
            "单一连续镜头，无剪切。中近景稳定机位，", "\nShot 1: 中近景，稳定机位，"
        )
        params["prompt"] += (
            "\nShot 2: 固定反应近景，对方自然眨眼。"
            "\nShot 3: 固定道具近景，纸张保持静止。"
            "\nShot 4: 固定环境镜头，学生保持低幅微动。"
        )
        errors, warnings, _ = audit_canvas_nodes.audit_node(detail)
        self.assertEqual(errors, [])
        self.assertFalse(any("万物生式节拍建议" in warning for warning in warnings))

    def test_fifteen_second_five_shot_node_matches_wanwu_budget(self):
        detail = good_detail()
        params = detail["params"]
        params["duration"] = 15
        params["prompt"] = params["prompt"].replace(
            "单一连续镜头，无剪切。中近景稳定机位，",
            "\nShot 1: 双人中景，建立人物关系。\n"
            "Shot 2: <主体1>反应近景，自然眨眼。\n"
            "Shot 3: 中近景稳定机位，",
        ) + (
            "\nShot 4: 对方反应近景，保持自然呼吸。"
            "\nShot 5: 双人中景，回到关系落幅。"
        )
        errors, warnings, summary = audit_canvas_nodes.audit_node(detail)
        self.assertEqual(errors, [])
        self.assertEqual(summary["shots"], 5)
        self.assertFalse(any("建议" in warning and "Shot" in warning for warning in warnings))

    def test_long_continuous_take_requires_explicit_story_intent(self):
        detail = good_detail()
        detail["params"]["duration"] = 15
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("缺少长镜头叙事意图" in error for error in errors))

        detail["params"]["prompt"] = detail["params"]["prompt"].replace(
            "单一连续镜头，无剪切。",
            "长镜头叙事意图：保持审讯式压迫和不中断表演。单一连续镜头，无剪切。",
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertEqual(errors, [])

    def test_robotic_short_line_prosody_is_blocked(self):
        detail = good_detail()
        detail["params"]["prompt"] = detail["params"]["prompt"].replace(
            "她说 {你，很吵。}", "她放慢并停半拍后说 {你，很吵。}"
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("机器人节奏风险" in error for error in errors))

    def test_fingerprint_changes_when_input_order_changes(self):
        detail = good_detail()
        before = audit_canvas_nodes.node_fingerprint(detail)
        detail["_tvskillInputs"] = [
            detail["_tvskillInputs"][0], detail["_tvskillInputs"][2],
            detail["_tvskillInputs"][1], detail["_tvskillInputs"][3],
        ]
        after = audit_canvas_nodes.node_fingerprint(detail)
        self.assertNotEqual(before, after)

    def test_pre_run_requires_active_compliance(self):
        detail = good_detail()
        detail["_tvskillInputs"][0]["compliance"] = "pending"
        errors, _, _ = audit_canvas_nodes.audit_node(detail, require_compliance=True)
        self.assertTrue(any("未全部 active" in error for error in errors))

    def test_pre_run_rejects_consumed_one_shot_budget_even_if_idle(self):
        detail = good_detail()
        detail["history"] = [{"url": "https://example.invalid/take.mp4"}]
        errors, _, summary = audit_canvas_nodes.audit_node(
            detail, require_one_shot=True
        )
        self.assertEqual(summary["runCount"], 1)
        self.assertTrue(any("一次性视频预算已消耗" in error for error in errors))

    def test_one_shot_voice_bootstrap_preview_may_omit_audio_input(self):
        detail = good_detail()
        detail["_tvskillInputs"] = [
            item for item in detail["_tvskillInputs"] if item["type"] != "audio-input"
        ]
        detail["params"]["prompt"] = (
            "一次性音色采样预览，不作为正式成片或续接来源。"
            "将 @[图片:char]（单知影） 定义为 <主体1>；"
            "参考 @[图片:first]（首帧-EP03-V01）；"
            "将 @[图片:scene]（场景状态-Z班-S1） 定义为 <场景1>。"
            "单一连续镜头，无剪切。<主体1>只说一句：{你，很吵。}。"
            "对白前后留干净空白，不要音乐。"
        )
        errors, _, _ = audit_canvas_nodes.audit_node(
            detail, require_one_shot=True
        )
        self.assertEqual(errors, [])

    def test_offscreen_phone_vo_does_not_require_on_screen_subject_voice_or_first_frame(self):
        detail = good_detail()
        detail["_tvskillInputs"] = [
            item for item in detail["_tvskillInputs"] if item["nodeId"] != "first"
        ]
        detail["_tvskillInputs"][1]["label"] = "周妍VO-音色"
        detail["params"]["prompt"] = (
            "将 @[图片:char]（单知影） 定义为 <主体1>；"
            "@[音频:voice]（周妍VO-音色） 只控制周妍VO的音色；"
            "将 @[图片:scene]（场景状态-Z班-S1） 定义为 <场景1>。"
            "单一连续镜头，无剪切。<主体1>全程闭口倾听，"
            "周妍以画外电话VO说出 {宝，不会是你要求的吧？}。"
            "不要音乐，无字幕、水印或 Logo。"
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertEqual(errors, [])

    def test_classroom_crowd_requires_functional_orientation(self):
        detail = good_detail()
        params = detail["params"]
        params["prompt"] = params["prompt"].replace(
            "中近景稳定机位", "大全景稳定机位，全班学生看向右侧过道"
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("教学朝向" in error for error in errors))
        self.assertTrue(any("骨盆、膝盖和坐姿朝向" in error for error in errors))

    def test_classroom_crowd_orientation_lock_passes(self):
        detail = good_detail()
        params = detail["params"]
        params["prompt"] = params["prompt"].replace(
            "中近景稳定机位",
            "大全景稳定机位，黑板固定在教室前墙；"
            "课桌、座椅和学生骨盆、膝盖、双脚始终朝向黑板；"
            "全班学生看向右侧过道时，只移动眼睛和头部，坐姿保持朝向黑板",
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertFalse(any("教学朝向" in error for error in errors))
        self.assertFalse(any("骨盆、膝盖和坐姿朝向" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
