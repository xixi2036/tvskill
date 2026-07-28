import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_delivery_md.py"
SPEC = importlib.util.spec_from_file_location("validate_delivery_md", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


VALID = """# EP01｜LibTV 完成提示词

- 总时长：10秒
- 生成段：1个
- 模型：Seedance 2.0 Fast VIP
- 画幅：9:16
- 分辨率：480P

## 使用方法

按表上传后整块复制。

## 公共素材清单

| 素材 | 类型 | 用途 |
|---|---|---|
| 单知影独立人物图 | 图片 | 身份 |

## 全剧连续性声明

- 剧名：测试短剧
- 审核范围：单集
- 全剧集数：未知
- 剧情时间锚：DAY01-白日
- 前集承接：开篇
- 本集最终出点：李威继续倾听
- 全剧二审：已通过

## 全剧连续性母版

| 连续键 | 类型 | 锁定版本 | 本集允许变化 | 变更依据 |
|---|---|---|---|---|
| character:单知影 | 人物 | CH-DZY-v1 | 否 | 无 |
| character:李威 | 人物 | CH-LW-v1 | 否 | 无 |
| scene:Z班 | 场景 | SC-Z-v1 | 否 | 无 |
| timeline:主线 | 时间 | DAY01-白日 | 否 | 无 |
| axis:CG-Z-DAY01 | 轴线 | AX-Z-v1 | 否 | 无 |

## 生成段 V01｜单人同步对白

- 段号：3-1-B
- 时长：10秒
- 连续组：CG-Z-DAY01
- 前置段：开场
- 提示词二审：已通过
- 交付等级：正式
- 制作路线：绑定逐句音频原生同步
- 风险标签：同步对白
- 运行状态：可运行
- 连续性模式：场景母版
- 声音：开启
- 文字策略：无画面文字
- 音色状态：已绑定李威逐句音频

### Mixed 上传顺序

| Mixed | 素材 | 类型 | 绑定语义 |
|---|---|---|---|
| Mixed 1 | 单知影独立人物图 | 图片 | @[单知影] |
| Mixed 2 | 李威独立人物图 | 图片 | @[李威] |
| Mixed 3 | 李威逐句音频 | 音频 | @[李威-逐句音频] |
| Mixed 4 | 干净首帧 | 图片 | @[首帧-3-1-B] |
| Mixed 5 | 双人教室场景状态图 | 图片 | @[场景状态-Z班-S1] |

### LibTV 完成提示词（整块复制）

```text
现代学院教室白日文戏，Kodak Vision3 35mm film grain 颗粒 + 低饱和冷调写实色调。将 @[单知影] {{Mixed 1}} 中的稳定身份特征定义为 <主体1>，该图作为 <主体1> 的视觉锚定，五官、发型与制服严格按此图渲染，不可改造；将 @[李威] {{Mixed 2}} 中的稳定身份特征定义为 <主体2>，该图作为 <主体2> 的视觉锚定，严格按此图渲染，不可改造。@[李威-逐句音频] {{Mixed 3}} 只控制 <主体2> 本句的音色与口型，不继承其它台词、情绪和背景声。参考 @[首帧-3-1-B] {{Mixed 4}} 的干净画面、人物位置和真实视线对象；将 @[场景状态-Z班-S1] {{Mixed 5}} 定义为 <场景1>，只参考空间、光线和当前人数。人物图只锁各自身份，不继承原姿势和原视线。

单一连续镜头，无剪切。中近景，稳定三分之四侧机位。【阶段1：起手】右侧 #C9D8E4 冷白窗光落在 <主体1> 的右肩，室内顶灯投出 #8A7A5E 暖色补光，两人保持既有座位。【阶段2：开口】<主体2> 听见房间安静后才开口，把视线锁在 <主体1> 的右肩背；<主体2> 严格使用 Mixed 3 的音色，自然说出 {哼，装什么装！}，一口自然说完；说完恢复鼻息，继续听着 <主体1> 的方向，右手自然留在桌沿。

【声音设计】0-2秒：教室低频环境底噪与远处走廊人声；2-4秒：<主体2> 的原声台词与轻微椅面摩擦声；4-10秒持续：环境底噪延续到落幅。仅生成人声与环境音效，不要 bgm。

【关键约束】机位铁律：全程稳定三分之四侧，不推不拉不摇。身份铁律：<主体1> 与 <主体2> 各只出现一人，禁止人物重复复刻，不得交换身份或服装。光向铁律：右侧窗光与室内顶灯方向全程固定。

真人实拍，保持人物身份、服装、人数、位置和眼神轴线一致。保持无字幕，不生成可辨识文字、水印或 Logo。NOT slow motion+NOT speed ramping+NOT 卡通渲染+NOT 三维动画+NOT 换脸+NOT 多余人物入画。
```

### 衔接

- 入点：场景母版。
- 出点：人物恢复鼻息并继续倾听。

### 状态交接

| 连续键 | 入点状态 | 出点状态 |
|---|---|---|
| character:单知影 | CH-DZY-v1-画面左 | CH-DZY-v1-画面左 |
| character:李威 | CH-LW-v1-画面右 | CH-LW-v1-画面右 |
| scene:Z班 | SC-Z-v1 | SC-Z-v1 |
| timeline:主线 | DAY01-白日 | DAY01-白日 |
| axis:CG-Z-DAY01 | AX-Z-v1 | AX-Z-v1 |

### 剧本事实对账

| 类型 | 原剧本事实 | 提示词落实 | 结果 |
|---|---|---|---|
| 台词 | 李威说“哼，装什么装！” | 代码块仅一次精确台词 | 通过 |
| 动作 | 李威开口 | 单一连续镜头同步对白 | 通过 |
| 空间 | 二人在Z班 | 场景状态与首帧一致 | 通过 |

## 段间衔接总表

| 前段 | 后段 | 切点 | 连续状态 |
|---|---|---|---|

## 语音对账

| 序号 | 原剧本声音 | 所在段 | 对账 |
|---|---|---|---|
"""


class DeliveryMarkdownTests(unittest.TestCase):
    def validate_text(self, text: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delivery.md"
            path.write_text(text, encoding="utf-8")
            return MODULE.validate(path)

    def errors(self, text: str) -> list[str]:
        return self.validate_text(text)[0]

    def test_valid_formal_dialogue_delivery(self):
        errors, warnings, summary = self.validate_text(VALID)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(summary["videoSegments"], 1)
        self.assertEqual(summary["totalDurationSeconds"], 10)

    def test_unknown_mixed_is_rejected(self):
        invalid = VALID.replace("@[场景状态-Z班-S1] {{Mixed 5}}", "@[场景状态-Z班-S1] {{Mixed 6}}")
        self.assertTrue(any("上传表不存在" in e for e in self.errors(invalid)))

    def test_nonconsecutive_mixed_table_is_rejected(self):
        invalid = VALID.replace("| Mixed 2 | 李威", "| Mixed 7 | 李威")
        self.assertTrue(any("必须从 1 连续递增" in e for e in self.errors(invalid)))

    def test_different_characters_cannot_share_mixed(self):
        invalid = VALID.replace("@[李威] {{Mixed 2}}", "@[李威] {{Mixed 1}}")
        self.assertTrue(any("多个独立语义共用" in e for e in self.errors(invalid)))

    def test_table_semantic_must_match_prompt_binding(self):
        invalid = VALID.replace("| 图片 | @[单知影] |", "| 图片 | @[错误人物] |", 1)
        self.assertTrue(any("上传表语义" in e for e in self.errors(invalid)))

    def test_absolute_timecode_is_rejected(self):
        invalid = VALID.replace(
            "单一连续镜头，无剪切。",
            "单一连续镜头，无剪切。00:00.00–00:03.00。",
        )
        self.assertTrue(any("绝对时间码" in e for e in self.errors(invalid)))

    def test_planning_map_in_mixed_is_rejected(self):
        invalid = VALID.replace("干净首帧", "人物位置图").replace(
            "@[首帧-3-1-B]", "@[位置-3-1-B]"
        )
        self.assertTrue(any("规划用资产" in e for e in self.errors(invalid)))

    def test_native_audio_multishot_is_allowed(self):
        candidate = VALID.replace(
            "单一连续镜头，无剪切。中近景",
            "Shot 1: 近景，固定机位。<主体1> 自然眨眼。\n\nShot 2: 中近景",
        )
        self.assertEqual(self.errors(candidate), [])

    def test_legacy_chinese_shot_label_is_rejected(self):
        invalid = VALID.replace("单一连续镜头，无剪切。", "镜头1：")
        self.assertTrue(any("禁止旧“镜头N：”标签" in e for e in self.errors(invalid)))

    def test_multishot_is_not_rejected_by_duration_alone(self):
        candidate = VALID.replace("- 时长：10秒", "- 时长：8秒").replace(
            "- 总时长：10秒", "- 总时长：8秒"
        ).replace(
            "单一连续镜头，无剪切。中近景",
            "Shot 1: 中景，固定机位。<主体1> 自然眨眼。\n\n"
            "Shot 2: 中近景",
        ).replace("- 交付等级：正式", "- 交付等级：预览")
        errors, warnings, _ = self.validate_text(candidate)
        self.assertFalse(any("超过保守预算" in e for e in errors))
        self.assertFalse(any("平均不足 2 秒" in w for w in warnings))

    def test_four_native_shots_in_short_node_are_rejected(self):
        candidate = VALID.replace(
            "单一连续镜头，无剪切。中近景",
            "Shot 1: 近景，固定机位。<主体1> 自然眨眼。\n\n"
            "Shot 2: 中近景",
        ).replace(
            "\n真人实拍",
            "\nShot 3: 固定道具近景，道具停稳。\n"
            "Shot 4: 固定环境镜头，背景保持低幅微动。\n\n真人实拍",
            1,
        )
        self.assertTrue(any("4 个生成 Shot" in e for e in self.errors(candidate)))

    def test_continuous_take_cannot_mix_with_shot_labels(self):
        invalid = VALID.replace(
            "单一连续镜头，无剪切。中近景",
            "单一连续镜头，无剪切。\nShot 1: 中近景",
        )
        self.assertTrue(any("不能同时声明连续镜头和 Shot N" in e for e in self.errors(invalid)))

    def test_short_line_cannot_be_stretched(self):
        invalid = VALID.replace(
            "{哼，装什么装！}，一口自然说完",
            "{你，很吵。}，放慢并停半拍",
        )
        self.assertTrue(any("六字以内短句" in e for e in self.errors(invalid)))

    def test_text_voice_requires_bound_audio(self):
        invalid = VALID.replace(
            "| Mixed 3 | 李威逐句音频 | 音频 | @[李威-逐句音频] |\n", ""
        ).replace("| Mixed 4 |", "| Mixed 3 |").replace("| Mixed 5 |", "| Mixed 4 |").replace(
            "{{Mixed 4}}", "{{Mixed 3}}"
        ).replace("{{Mixed 5}}", "{{Mixed 4}}").replace(
            "。@[李威-逐句音频] {{Mixed 3}} 只控制 <主体2> 本句的音色与口型，不继承其它台词、情绪和背景声",
            "",
        )
        self.assertTrue(any("必须为每名说话人绑定独立音色音频" in e for e in self.errors(invalid)))

    def test_preview_without_audio_is_blocked(self):
        invalid = VALID.replace(
            "| Mixed 3 | 李威逐句音频 | 音频 | @[李威-逐句音频] |\n", ""
        ).replace("| Mixed 4 |", "| Mixed 3 |").replace("| Mixed 5 |", "| Mixed 4 |").replace(
            "{{Mixed 4}}", "{{Mixed 3}}"
        ).replace("{{Mixed 5}}", "{{Mixed 4}}").replace(
            "。@[李威-逐句音频] {{Mixed 3}} 只控制 <主体2> 本句的音色与口型，不继承其它台词、情绪和背景声",
            "",
        ).replace("- 交付等级：正式", "- 交付等级：预览").replace(
            "- 制作路线：绑定逐句音频原生同步", "- 制作路线：模型合成预览"
        ).replace("- 音色状态：已绑定李威逐句音频", "- 音色状态：未绑定")
        self.assertTrue(any("必须为每名说话人绑定独立音色音频" in e for e in self.errors(invalid)))

    def test_dialogue_requires_eyeline_target(self):
        invalid = VALID.replace("把视线锁在 <主体1> 的右肩背", "保持原来的表情").replace(
            "继续听着 <主体1> 的方向", "姿势保持不变"
        )
        self.assertTrue(any("缺少具体眼神对象" in e for e in self.errors(invalid)))

    def test_dialogue_requires_living_endpoint(self):
        invalid = VALID.replace(
            "；说完恢复鼻息，继续听着 <主体1> 的方向，右手自然留在桌沿", ""
        )
        self.assertTrue(any("缺少说完后的可剪辑落点" in e for e in self.errors(invalid)))

    def test_sync_dialogue_cannot_include_os_in_same_shot(self):
        invalid = VALID.replace(
            "<主体2> 严格使用 Mixed 3 的音色，自然说出 {哼，装什么装！}",
            "OS {她不会回头。}；<主体2> 严格使用 Mixed 3 的音色，自然说出 {哼，装什么装！}",
        )
        self.assertTrue(any("同一 Shot 内不能混合口型对白与 OS/VO/旁白" in e for e in self.errors(invalid)))

    def test_formal_dialogue_requires_clean_frame_anchor(self):
        invalid = VALID.replace("@[首帧-3-1-B]", "@[场景状态-双人近景-S1]")
        self.assertTrue(any("缺少干净首帧" in e for e in self.errors(invalid)))

    def test_exact_model_text_generation_is_rejected(self):
        invalid = VALID.replace(
            "保持无字幕", "报告必须生成并清晰显示且只显示精确文字；保持无字幕"
        )
        self.assertTrue(any("精确文字交给视频模型" in e for e in self.errors(invalid)))

    def test_fast_vip_model_is_accepted(self):
        self.assertFalse(any("节点模型必须" in e for e in self.errors(VALID)))

    def test_empty_room_conflicts_with_wide_crowd(self):
        invalid = VALID.replace(
            "单一连续镜头，无剪切。中近景，稳定三分之四侧机位。",
            "单一连续镜头，无剪切。大全景，固定机位。全班学生同时转头后保持呼吸。",
        ).replace("双人教室场景状态图", "空教室场景图").replace(
            "只参考空间、光线和当前人数", "只参考无人物教室空间和光线"
        )
        self.assertTrue(any("全景可见人群却绑定空场景" in e for e in self.errors(invalid)))

    def test_classroom_crowd_requires_functional_orientation(self):
        invalid = VALID.replace(
            "单一连续镜头，无剪切。中近景，稳定三分之四侧机位。",
            "单一连续镜头，无剪切。大全景，稳定三分之四侧机位。"
            "全班学生看向右侧过道。",
        )
        errors = self.errors(invalid)
        self.assertTrue(any("教学朝向" in error for error in errors))
        self.assertTrue(any("骨盆、膝盖和坐姿朝向" in error for error in errors))

    def test_missing_production_metadata_is_rejected(self):
        invalid = VALID.replace("- 交付等级：正式\n", "")
        self.assertTrue(any("缺少或错误的交付等级" in e for e in self.errors(invalid)))

    def test_missing_series_review_is_rejected(self):
        invalid = VALID.replace("- 全剧二审：已通过\n", "")
        self.assertTrue(any("全剧二审" in e for e in self.errors(invalid)))

    def test_missing_segment_handoff_is_rejected(self):
        invalid = VALID.replace("### 状态交接", "### 其它记录")
        self.assertTrue(any("缺少状态交接" in e for e in self.errors(invalid)))

    def test_missing_script_fact_check_is_rejected(self):
        invalid = VALID.replace("### 剧本事实对账", "### 普通备注")
        self.assertTrue(any("缺少剧本事实对账" in e for e in self.errors(invalid)))

    def test_failed_script_fact_check_is_rejected(self):
        invalid = VALID.replace(
            "| 动作 | 李威开口 | 单一连续镜头同步对白 | 通过 |",
            "| 动作 | 李威开口 | 连续镜头增加了走位 | 未通过 |",
        )
        self.assertTrue(any("存在未通过项目" in e for e in self.errors(invalid)))

    def test_slop_quality_bundle_is_rejected(self):
        invalid = VALID.replace(
            "真人实拍，保持人物身份、服装、人数、位置和眼神轴线一致。",
            "真人实拍，高清，细节丰富，电影质感，色彩自然，光影柔和，保持人物身份一致。",
        )
        self.assertTrue(any("空泛画质词过多" in e for e in self.errors(invalid)))

    def test_arbitrary_bracket_text_is_still_rejected(self):
        invalid = VALID.replace("【关键约束】机位铁律", "【标题：Z班开学】【关键约束】机位铁律")
        self.assertTrue(any("禁用的【】画面文字语法" in e for e in self.errors(invalid)))

    def test_sound_design_block_may_layer_by_second(self):
        errors, _, _ = self.validate_text(VALID)
        self.assertFalse(any("绝对时间码" in e for e in errors))

    def test_timecode_outside_sound_design_is_still_rejected(self):
        invalid = VALID.replace(
            "【阶段1：起手】右侧",
            "【阶段1：起手】第3秒时右侧",
        )
        self.assertTrue(any("绝对时间码" in e for e in self.errors(invalid)))

    def test_timecode_after_trailing_sound_design_block_is_rejected(self):
        sound_block = (
            "【声音设计】0-2秒：教室低频环境底噪与远处走廊人声；"
            "2-4秒：<主体2> 的原声台词与轻微椅面摩擦声；"
            "4-10秒持续：环境底噪延续到落幅。仅生成人声与环境音效，不要 bgm。\n\n"
        )
        closing = (
            "真人实拍，保持人物身份、服装、人数、位置和眼神轴线一致。"
            "保持无字幕，不生成可辨识文字、水印或 Logo。"
            "NOT slow motion+NOT speed ramping+NOT 卡通渲染+NOT 三维动画+"
            "NOT 换脸+NOT 多余人物入画。"
        )
        # 把声音设计挪到末尾，并在其后追加一段带绝对时间码的收尾：豁免不得越出本段
        invalid = VALID.replace(sound_block, "").replace(
            closing, sound_block + closing.replace("真人实拍，", "真人实拍，第5秒时"),
        )
        self.assertIn("第5秒", invalid)
        self.assertTrue(any("绝对时间码" in e for e in self.errors(invalid)))

    def test_missing_wanwu_craft_warns_on_formal_segment(self):
        candidate = VALID.replace(
            "【关键约束】机位铁律：全程稳定三分之四侧，不推不拉不摇。", ""
        )
        errors, warnings, _ = self.validate_text(candidate)
        self.assertEqual(errors, [])
        self.assertTrue(any("万物生结构六件套" in w for w in warnings))

    def voice_slot_text(self) -> str:
        return VALID.replace(
            "| Mixed 3 | 李威逐句音频 | 音频 | @[李威-逐句音频] |",
            "| Mixed 3 | 李威-音色占位槽（待人工上传） | 音频（待上传） | @[李威-逐句音频] |",
        ).replace(
            "- 音色状态：已绑定李威逐句音频",
            "- 音色状态：待关联｜占位槽：李威-音色参考（待人工上传）",
        ).replace("- 运行状态：可运行", "- 运行状态：阻塞")

    def test_voice_slot_passes_and_warns(self):
        errors, warnings, _ = self.validate_text(self.voice_slot_text())
        self.assertEqual(errors, [])
        self.assertTrue(any("音色占位槽待人工上传后关联" in w for w in warnings))

    def test_voice_slot_cannot_be_runnable(self):
        invalid = self.voice_slot_text().replace("- 运行状态：阻塞", "- 运行状态：可运行")
        self.assertTrue(any("运行状态必须为阻塞" in e for e in self.errors(invalid)))

    def test_voice_slot_requires_pending_status(self):
        invalid = self.voice_slot_text().replace(
            "- 音色状态：待关联｜占位槽：李威-音色参考（待人工上传）",
            "- 音色状态：已绑定李威逐句音频",
        )
        self.assertTrue(any("音色状态必须写明“待关联”" in e for e in self.errors(invalid)))

    def test_pending_status_requires_real_slot_row(self):
        invalid = VALID.replace(
            "- 音色状态：已绑定李威逐句音频", "- 音色状态：待关联"
        )
        self.assertTrue(any("没有对应的音色占位槽" in e for e in self.errors(invalid)))


if __name__ == "__main__":
    unittest.main()
