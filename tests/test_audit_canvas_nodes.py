from __future__ import annotations

from pathlib import Path
import sys
import unittest


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

    def test_four_native_shots_in_short_node_are_blocked(self):
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
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("4 个生成 Shot" in error for error in errors))

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
