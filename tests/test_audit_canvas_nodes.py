from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_canvas_nodes  # noqa: E402


def good_detail() -> dict:
    items = [
        {"nodeId": "char", "label": "TVSkill-EP03-单知影-独立人物图", "mediaType": "image"},
        {"nodeId": "voice", "label": "TVSkill-EP03-单知影-逐句音频", "mediaType": "audio"},
        {"nodeId": "first", "label": "TVSkill-EP03-V01-干净首帧", "mediaType": "image"},
        {"nodeId": "scene", "label": "TVSkill-EP03-Z班教室-占座场景状态-S1", "mediaType": "image"},
    ]
    return {
        "nodeKey": "good",
        "data": {
            "type": "video",
            "name": "TVSkill-EP03-V01",
            "params": {
                "prompt": (
                    "将 @[单知影] {{Mixed 1}} 定义为 <主体1>；"
                    "@[单知影-逐句音频] {{Mixed 2}} 只控制 <主体1> 的音色，不继承原台词；"
                    "参考 @[首帧-EP03-V01] {{Mixed 3}}；"
                    "将 @[场景状态-Z班-S1] {{Mixed 4}} 定义为 <场景1>。"
                    "单一连续镜头，无剪切。中近景稳定机位，<主体1> 她说 {你，很吵。}，"
                    "说完恢复鼻息。真人实拍，右侧窗光，无字幕、水印或 Logo。"
                ),
                "model": "Seedance 2.0 VIP",
                "mixedList": items,
                "mixedListOrder": ["char", "voice", "first", "scene"],
                "imageList": [items[0], items[2], items[3]],
                "imageListOrder": ["char", "first", "scene"],
                "audioList": [{"nodeId": "voice", "label": "TVSkill-EP03-单知影-逐句音频"}],
                "audioListOrder": ["voice"],
                "videoList": [],
                "videoListOrder": [],
                "settings": {
                    "ratio": "9:16", "resolution": "480p",
                    "duration": 6, "enableSound": "on",
                },
            },
        },
    }


def bad_detail() -> dict:
    items = [
        {"nodeId": "char", "label": "TVSkill-EP03-单知影-独立人物图", "mediaType": "image"},
        {"nodeId": "map", "label": "TVSkill-EP03-3-1-A-无身份位置图", "mediaType": "image"},
        {"nodeId": "scene", "label": "TVSkill-EP03-Z班教室-无人物场景图", "mediaType": "image"},
        {"nodeId": "liwei", "label": "TVSkill-EP03-李威-独立人物图", "mediaType": "image"},
    ]
    return {
        "nodeKey": "bad",
        "data": {
            "type": "video",
            "name": "TVSkill-EP03-V01-旧节点",
            "params": {
                "prompt": (
                    "将 @[单知影] {{Mixed 1}} 定义为 <主体1>；"
                    "将 @[李威] {{Mixed 2}} 定义为 <主体2>；"
                    "参考 @[构图-3-1-A] {{Mixed 3}}；"
                    "将 @[场景-Z班教室] {{Mixed 4}} 定义为 <场景1>。"
                    "\n镜头1：大全景，全班学生转头。"
                    "\n镜头2：中景，<主体1>走向后排。"
                    "\n镜头3：近景，他说 {马上退学！}。"
                ),
                "model": "Seedance 2.0 VIP",
                "mixedList": items,
                "mixedListOrder": ["char", "map", "scene", "liwei"],
                "audioList": [],
                "settings": {
                    "ratio": "9:16", "resolution": "480p",
                    "duration": 10, "enableSound": "on",
                },
            },
            "taskInfo": {"status": 2},
        },
    }


class CanvasNodeAuditTests(unittest.TestCase):
    def test_good_live_contract_passes(self):
        errors, warnings, summary = audit_canvas_nodes.audit_node(good_detail())
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(summary["mixed"], 4)

    def test_fast_vip_model_passes(self):
        detail = good_detail()
        detail["data"]["params"]["model"] = "Seedance 2.0 Fast VIP"
        errors, warnings, _ = audit_canvas_nodes.audit_node(detail)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_native_audio_multishot_is_allowed(self):
        detail = good_detail()
        params = detail["data"]["params"]
        params["prompt"] = params["prompt"].replace(
            "单一连续镜头，无剪切。中近景稳定机位，",
            "\nShot 1: 中近景，稳定机位，",
        ) + "\nShot 2: 固定反应近景，对方自然眨眼并恢复呼吸。"
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertEqual(errors, [])

    def test_real_failure_shape_is_blocked(self):
        errors, warnings, _ = audit_canvas_nodes.audit_node(bad_detail())
        self.assertTrue(any("语义“李威”" in error for error in errors))
        self.assertTrue(any("规划图进入 Mixed" in error for error in errors))
        self.assertTrue(any("旧“镜头N：”" in error for error in errors))
        self.assertTrue(any("audioList 为空" in error for error in errors))
        self.assertTrue(any("全景要求可见人群" in error for error in errors))
        self.assertTrue(any("节点已有生成结果" in warning for warning in warnings))

    def test_exact_text_generation_is_blocked(self):
        detail = good_detail()
        detail["data"]["params"]["prompt"] += "纸面清晰显示且只显示“反向做空”。"
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("精确画面文字" in error for error in errors))

    def test_out_of_range_mixed_is_blocked(self):
        detail = good_detail()
        detail["data"]["params"]["prompt"] = detail["data"]["params"]["prompt"].replace(
            "@[场景状态-Z班-S1] {{Mixed 4}}",
            "@[场景状态-Z班-S1] {{Mixed 9}}",
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("实际只有 4 个素材" in error for error in errors))

    def test_cached_media_order_mismatch_is_blocked(self):
        detail = good_detail()
        detail["data"]["params"]["imageListOrder"] = ["scene", "first", "char"]
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("imageList 与 imageListOrder 顺序不一致" in error for error in errors))

    def test_four_native_shots_in_short_node_are_blocked(self):
        detail = good_detail()
        params = detail["data"]["params"]
        params["settings"]["duration"] = 12
        params["prompt"] = params["prompt"].replace(
            "单一连续镜头，无剪切。中近景稳定机位，",
            "\nShot 1: 中近景，稳定机位，",
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
        detail["data"]["params"]["prompt"] = detail["data"]["params"]["prompt"].replace(
            "她说 {你，很吵。}",
            "她放慢并停半拍后说 {你，很吵。}",
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("机器人节奏风险" in error for error in errors))

    def test_fingerprint_changes_when_mixed_order_changes(self):
        detail = good_detail()
        before = audit_canvas_nodes.node_fingerprint(detail)
        detail["data"]["params"]["mixedListOrder"] = [
            "char", "first", "voice", "scene"
        ]
        after = audit_canvas_nodes.node_fingerprint(detail)
        self.assertNotEqual(before, after)

    def test_classroom_crowd_requires_functional_orientation(self):
        detail = good_detail()
        params = detail["data"]["params"]
        params["prompt"] = params["prompt"].replace(
            "中近景稳定机位",
            "大全景稳定机位，全班学生看向右侧过道",
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("教学朝向" in error for error in errors))
        self.assertTrue(any("骨盆、膝盖和坐姿朝向" in error for error in errors))

    def test_classroom_crowd_orientation_lock_passes(self):
        detail = good_detail()
        params = detail["data"]["params"]
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
