from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_canvas_nodes  # noqa: E402


# 网页端 model-facing 序列化的参考实现。
# 逐行复刻自 www.tvmao.net 生产 bundle（assets/index-BNk-Lo9n.js）中的 e0()/xE()：
#
#   const Are={image:"图片",video:"视频",audio:"音频"}
#   const cg=/@\[(图片|视频|音频):([^\]]+)\]/g
#   function xE(e){const t={image:0,video:0,audio:0};
#     return e.map(n=>(t[n.kind]+=1,{...n,label:`${Are[n.kind]} ${t[n.kind]}`}))}
#   function e0(e,t){const n=xE(t);
#     return e.replace(cg,(r,o,a)=>{const i=N9[o],s=n.find(l=>l.nodeId===a&&l.kind===i);
#       return s?s.label.replace(" ",""):""})}
#
# 注意两个易错点：
#   1. cg 只吃 `@[类型:节点ID]`，紧随其后的 `（语义名）` 是普通正文，原样保留；
#   2. 未匹配到同类型入边的 mention 被替换为空串（不是保留原文）。
WEB_MENTION_RE = re.compile(r"@\[(图片|视频|音频):([^\]]+)\]")
_WEB_KIND = {"图片": "image", "视频": "video", "音频": "audio"}
_WEB_LABEL = {"image": "图片", "video": "视频", "audio": "音频"}


def web_serialize(prompt: str, inputs: list[dict]) -> str:
    counters = {"image": 0, "video": 0, "audio": 0}
    labels: dict[tuple[str, str], str] = {}
    for item in inputs:
        kind = item["kind"]
        counters[kind] += 1
        labels[(kind, item["nodeId"])] = f"{_WEB_LABEL[kind]}{counters[kind]}"

    def repl(match: re.Match[str]) -> str:
        kind = _WEB_KIND[match.group(1)]
        return labels.get((kind, match.group(2)), "")

    return WEB_MENTION_RE.sub(repl, prompt)


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
            "单一连续镜头，无剪切。中近景稳定机位，",
            "\n本段共 4 个约 2–3 秒的硬切镜头。\nShot 1: 中近景，稳定机位，"
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

    def test_generic_only_semantic_cannot_wave_through_wrong_asset(self):
        detail = good_detail()
        detail["_tvskillInputs"][0]["label"] = "TVSkill-EP03-李威-独立人物图"
        detail["params"]["prompt"] = detail["params"]["prompt"].replace(
            "@[图片:char]（单知影）", "@[图片:char]（独立人物图）"
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("无可校验标识" in error for error in errors))

    def test_short_suffix_still_disambiguates_generic_role_label(self):
        detail = good_detail()
        detail["_tvskillInputs"][0]["label"] = "TVSkill-EP03-角色A-独立人物图"
        detail["params"]["prompt"] = detail["params"]["prompt"].replace(
            "@[图片:char]（单知影）", "@[图片:char]（角色A）"
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertEqual(errors, [])

        detail["params"]["prompt"] = detail["params"]["prompt"].replace(
            "@[图片:char]（角色A）", "@[图片:char]（角色B）"
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("语义“角色B”与实际素材" in error for error in errors))

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
            "单一连续镜头，无剪切。中近景稳定机位，",
            "\n本段共 4 个约 2–3 秒的硬切镜头。\nShot 1: 中近景，稳定机位，",
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
            "\n本段共 5 个约 2–3 秒的硬切镜头。\n"
            "Shot 1: 双人中景，建立人物关系。\n"
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

    def test_sync_preview_cannot_bypass_clean_first_frame(self):
        detail = good_detail()
        detail["_tvskillInputs"] = [
            item for item in detail["_tvskillInputs"] if item["nodeId"] != "first"
        ]
        detail["params"]["prompt"] = detail["params"]["prompt"].replace(
            "参考 @[图片:first]（首帧-EP03-V01）；", "原生声画同出预览。"
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(any("缺少干净首帧" in error for error in errors))

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


class IdentitySovereigntyTests(unittest.TestCase):
    """每个出场 <主体N> 必须有且只有一份身份锚。

    Rule of 12 只卡参考图**数量**，不卡**职责**。这两种形状都真实发生过：
      ① 覆盖缺口——正文用了 <主体1> 却一张角色图都没绑，人脸每段随机、跨段无法一致
      ② 双 Primary——两张图都锚定同一个 <主体N>，参考竞争导致身份漂移
    ②正是十轴审计「参考污染／身份漂移 → 减少竞争参考」记录过的失败，
    此前只能事后返工才发现。
    """

    def test_subject_without_identity_anchor_is_blocked(self):
        detail = good_detail()
        prompt = detail["params"]["prompt"]
        stripped = re.sub(r"将[^。\n]{0,80}?定义为\s*<主体\d+>", "画面中出现一名年轻女性", prompt)
        self.assertNotEqual(prompt, stripped, "夹具里应当存在身份锚定句")
        detail["params"]["prompt"] = stripped
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(
            any("没有任何身份锚定" in e for e in errors),
            f"用了 <主体N> 却无锚定应被拦下，实际 errors={errors}",
        )

    def test_two_images_claiming_the_same_subject_are_blocked(self):
        detail = good_detail()
        detail["params"]["prompt"] += (
            "\n将 @[图片:scene]（场景状态-Z班-S1） 定义为 <主体1>。"
        )
        errors, _, _ = audit_canvas_nodes.audit_node(detail)
        self.assertTrue(
            any("同一职责只能有一个主权来源" in e for e in errors),
            f"同一主体被两张图锚定应被拦下，实际 errors={errors}",
        )

    def test_properly_anchored_node_is_not_flagged(self):
        # 零误报：真值形态（每个主体恰好一份锚定）不得报错
        errors, _, _ = audit_canvas_nodes.audit_node(good_detail())
        self.assertFalse([e for e in errors if "身份锚定" in e or "主权来源" in e])

    def test_anchor_is_recognised_in_both_canonical_and_serialized_form(self):
        # 审计既可能拿到存储 prompt（@[图片:nodeId]），也可能拿到 history 的实际提交（图片N）
        for text in (
            "将 @[图片:n-abc]（角色-吴馨） 中的稳定身份特征定义为 <主体1>",
            "将 图片1（角色-吴馨） 中的稳定身份特征定义为 <主体1>",
        ):
            with self.subTest(text=text):
                hits = list(audit_canvas_nodes.IDENTITY_ANCHOR_RE.finditer(text))
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0].group("subject"), "<主体1>")


class WebSerializationParityTests(unittest.TestCase):
    """serialize_canvas_prompt 必须与网页端 model-facing 序列化逐字节一致。

    2026-09-04 用生产画布真实节点（project 138 / n-mfJQfdhE，4 入边）实测过一次一致；
    本类把该结论固化为回归闸——网页若改序列化规则，这里立刻失败，
    而不是等到成片出来才发现模型收到的输入与审计预测不符。
    """

    def _pair(self, prompt: str, spec: list[tuple[str, str]]) -> tuple[str, str]:
        web_inputs = [{"kind": k, "nodeId": n} for k, n in spec]
        tv_inputs = [
            {
                "nodeId": n,
                "type": {"image": "image-input", "video": "video-input", "audio": "audio-input"}[k],
                "label": "",
            }
            for k, n in spec
        ]
        tv, _errors, _count = audit_canvas_nodes.serialize_canvas_prompt(prompt, tv_inputs)
        return web_serialize(prompt, web_inputs), tv

    def test_matches_web_on_production_shaped_prompt(self):
        prompt = (
            "高端日韩风格化 3D 低饱和生活流家庭剧视觉美学。"
            "将 @[图片:n-UQuY9gZY]（角色-吴馨） 中的稳定身份特征定义为 <主体1>。"
            "将 @[图片:n-22kMOsWU]（角色-李承） 中的稳定身份特征定义为 <主体2>。"
            "将 @[图片:n-pdRcy0eJ]（场景状态-李家卧室-夜-S2） 定义为 <场景1>。"
            "参考 @[图片:n-0SXo3jeN]（色卡-李家卧室-夜） 的色彩关系。"
        )
        spec = [
            ("image", "n-UQuY9gZY"),
            ("image", "n-22kMOsWU"),
            ("image", "n-pdRcy0eJ"),
            ("image", "n-0SXo3jeN"),
        ]
        web, tv = self._pair(prompt, spec)
        self.assertEqual(web, tv)
        # 括号语义名是紧随 mention 的正文，两边都必须原样保留
        self.assertIn("图片1（角色-吴馨）", tv)
        self.assertNotIn("@[", tv)

    def test_matches_web_across_three_media_kinds(self):
        prompt = (
            "@[图片:n-a]（单知影） 与 @[图片:n-b]（李威） 对坐；"
            "动作参考 @[视频:n-v1]（动作-递物）；"
            "音色 @[音频:n-au1]（单知影音色）与 @[音频:n-au2]（李威音色）。"
        )
        spec = [
            ("image", "n-a"),
            ("audio", "n-au1"),
            ("image", "n-b"),
            ("video", "n-v1"),
            ("audio", "n-au2"),
        ]
        web, tv = self._pair(prompt, spec)
        self.assertEqual(web, tv)
        # 三类媒体各自从 1 连续编号，编号取决于入边顺序而非文中出现顺序
        self.assertIn("图片1（单知影）", tv)
        self.assertIn("图片2（李威）", tv)
        self.assertIn("视频1（动作-递物）", tv)
        self.assertIn("音频1（单知影音色）", tv)
        self.assertIn("音频2（李威音色）", tv)

    def test_matches_web_when_mention_has_no_matching_input(self):
        prompt = "锁定 @[图片:n-present]（在场） 与 @[图片:n-missing]（缺失）。"
        spec = [("image", "n-present")]
        web, tv = self._pair(prompt, spec)
        # 网页把无对应入边的 mention 替换为空串；审计侧必须同样处理，否则
        # 预测出的模型输入会多出一段实际不存在的引用
        self.assertEqual(web, tv)
        self.assertNotIn("n-missing", tv)


if __name__ == "__main__":
    unittest.main()
