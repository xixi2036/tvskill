from __future__ import annotations

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

## 资产清单

| 类型 | 名称 | 形态 | 备注 |
|---|---|---|---|
| 人物 | 单知影 | 独立身份图 | 无台词 |
| 人物 | 李威 | 独立身份图 | 有台词 |
| 场景 | Z班-S1 | 双人场景状态图 | 与可见人数一致 |
| 道具 | 道具-桌沿 | 由场景图承担 | 陈设级，本段无叙事道具 |

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
主体标签锁定：本段仅使用 <主体N>；角色名和服装状态只保留在参考语义与台词原文中。
现代学院教室白日文戏，Kodak Vision3 35mm film grain 颗粒 + 低饱和冷调写实色调。将 @[单知影] {{Mixed 1}} 中的稳定身份特征定义为 <主体1>，该图作为 <主体1> 的视觉锚定，五官、发型与制服严格按此图渲染，不可改造；将 @[李威] {{Mixed 2}} 中的稳定身份特征定义为 <主体2>，该图作为 <主体2> 的视觉锚定，严格按此图渲染，不可改造。@[李威-逐句音频] {{Mixed 3}} 只控制 <主体2> 本句的音色与口型，不继承其它台词、情绪和背景声。参考 @[首帧-3-1-B] {{Mixed 4}} 的干净画面、人物位置和真实视线对象；将 @[场景状态-Z班-S1] {{Mixed 5}} 定义为 <场景1>，只参考空间、光线和当前人数。人物图只锁各自身份，不继承原姿势和原视线。

长镜头叙事意图：用不中断的等待保持两人对峙压力。
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

## 画面对账

| 序号 | 类型 | 原剧本画面指令 | 落点 | 处置 |
|---|---|---|---|---|
| 1 | visual | △ 李威在教室安静下来后开口。 | V01-Shot1 | 已落实 |
| 2 | visual | △ 单知影没有回头，右手留在桌沿。 | V01-Shot1 | 已落实 |
| 3 | subtitle | 【字幕：李威 Z班班长】 | — | 转后期叠字 |

## 段间衔接总表

| 前段 | 后段 | 切点 | 连续状态 |
|---|---|---|---|

## 语音对账

| 序号 | 原剧本声音 | 所在段 | 对账 |
|---|---|---|---|
| 1 | 李威：哼，装什么装！ | V01 | 逐字一致 |
"""


class DeliveryMarkdownTests(unittest.TestCase):
    UNSOURCED_WARNING = "画面对账未对源校验"

    def validate_text(self, text: str, script: str | None = None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delivery.md"
            path.write_text(text, encoding="utf-8")
            script_path = None
            if script is not None:
                script_path = Path(directory) / "script.txt"
                script_path.write_text(script, encoding="utf-8")
            return MODULE.validate(path, script_path)

    def real_warnings(self, warnings: list[str]) -> list[str]:
        return [w for w in warnings if self.UNSOURCED_WARNING not in w]

    def errors(self, text: str) -> list[str]:
        return self.validate_text(text)[0]

    def test_valid_formal_dialogue_delivery(self):
        errors, warnings, summary = self.validate_text(VALID)
        self.assertEqual(errors, [])
        self.assertEqual(self.real_warnings(warnings), [])
        self.assertTrue(any(self.UNSOURCED_WARNING in w for w in warnings))
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
        warnings = self.real_warnings(warnings)
        self.assertFalse(any("超过保守预算" in e for e in errors))
        self.assertFalse(any("平均不足 2 秒" in w for w in warnings))

    def test_four_native_shots_in_ten_second_node_are_allowed(self):
        candidate = VALID.replace(
            "单一连续镜头，无剪切。中近景",
            "本段共 4 个约 2–3 秒的硬切镜头。\n"
            "Shot 1: 近景，固定机位。<主体1> 自然眨眼。\n\n"
            "Shot 2: 中近景",
        ).replace(
            "\n真人实拍",
            "\nShot 3: 固定道具近景，道具停稳。\n"
            "Shot 4: 固定环境镜头，背景保持低幅微动。\n\n真人实拍",
            1,
        )
        errors, warnings, _ = self.validate_text(candidate)
        self.assertEqual(errors, [])
        self.assertFalse(any("万物生式节拍建议" in warning for warning in warnings))

    def test_fifteen_second_wanwu_five_shot_structure_is_valid(self):
        candidate = VALID.replace("- 总时长：10秒", "- 总时长：15秒").replace(
            "- 时长：10秒", "- 时长：15秒"
        ).replace(
            "单一连续镜头，无剪切。中近景",
            "本段共 5 个约 2–3 秒的硬切镜头。\n"
            "Shot 1: 双人中景，建立人物关系和轴线。\n"
            "Shot 2: <主体1> 反应近景，只保持自然呼吸。\n"
            "Shot 3: <主体2> 中近景",
        ).replace(
            "\n真人实拍",
            "\nShot 4: <主体1> 反应近景，下颌轻收。\n"
            "Shot 5: 双人中景，回到关系落幅。\n\n真人实拍",
            1,
        )
        errors, warnings, _ = self.validate_text(candidate)
        self.assertEqual(errors, [])
        self.assertFalse(any("建议" in warning and "Shot" in warning for warning in warnings))

    def test_ten_second_continuous_take_requires_story_intent(self):
        invalid = VALID.replace(
            "长镜头叙事意图：用不中断的等待保持两人对峙压力。", ""
        )
        self.assertTrue(any("缺少长镜头叙事意图" in e for e in self.errors(invalid)))

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

    SCRIPT = """第1集

1-1 日 内 Z班教室
人物：李威、单知影
△ 李威在教室安静下来后开口。
李威：哼，装什么装！
△ 单知影没有回头，右手留在桌沿。
【字幕：李威 Z班班长】
"""

    def test_coverage_matches_source_script(self):
        errors, warnings, _ = self.validate_text(VALID, self.SCRIPT)
        self.assertEqual(errors, [])
        self.assertFalse(any(self.UNSOURCED_WARNING in w for w in warnings))

    def test_dropped_coverage_row_is_caught_against_source(self):
        # 删掉一行对账 = 一条画面指令被静默丢弃，正是 EP1 的失败形状
        invalid = VALID.replace(
            "| 2 | visual | \u25b3 \u5355\u77e5\u5f71\u6ca1\u6709\u56de\u5934\uff0c\u53f3\u624b\u7559\u5728\u684c\u6cbf\u3002 | V01-Shot1 | \u5df2\u843d\u5b9e |\n", ""
        ).replace(
            "| 3 | subtitle |", "| 2 | subtitle |",
        )
        errors = self.validate_text(invalid, self.SCRIPT)[0]
        self.assertTrue(any("\u4e0e\u539f\u5267\u672c\u5b9e\u9645\u753b\u9762\u5355\u5143\u6570" in e for e in errors))

    def test_rewritten_coverage_row_is_caught_against_source(self):
        # 行数对得上但原文被改写（细节被抹掉），同样要抓出来
        invalid = VALID.replace(
            "\u25b3 \u5355\u77e5\u5f71\u6ca1\u6709\u56de\u5934\uff0c\u53f3\u624b\u7559\u5728\u684c\u6cbf\u3002 | V01-Shot1",
            "\u25b3 \u5355\u77e5\u5f71\u6709\u53cd\u5e94\u3002 | V01-Shot1",
        )
        errors = self.validate_text(invalid, self.SCRIPT)[0]
        self.assertTrue(any("\u539f\u6587\u4e0e\u5267\u672c\u4e0d\u7b26" in e for e in errors))

    def test_units_crammed_into_one_shot_are_rejected(self):
        multishot = VALID.replace(
            "\u5355\u4e00\u8fde\u7eed\u955c\u5934\uff0c\u65e0\u526a\u5207\u3002\u4e2d\u8fd1\u666f",
            "Shot 1: \u8fd1\u666f\uff0c\u56fa\u5b9a\u673a\u4f4d\u3002<\u4e3b\u4f531> \u81ea\u7136\u7728\u773c\u3002\n\nShot 2: \u4e2d\u8fd1\u666f",
        ).replace(
            "| 3 | subtitle | \u3010\u5b57\u5e55\uff1a\u674e\u5a01 Z\u73ed\u73ed\u957f\u3011 | \u2014 | \u8f6c\u540e\u671f\u53e0\u5b57 |",
            "| 3 | visual | \u25b3 \u4e19\u3002 | V01-Shot1 | \u5df2\u843d\u5b9e |",
        )
        errors = self.errors(multishot)
        self.assertTrue(any("\u5fc5\u987b\u62c6\u8282\u70b9" in e for e in errors))

    def test_registered_color_card_must_be_bound(self):
        invalid = VALID.replace(
            "| \u573a\u666f | Z\u73ed-S1 | \u53cc\u4eba\u573a\u666f\u72b6\u6001\u56fe | \u4e0e\u53ef\u89c1\u4eba\u6570\u4e00\u81f4 |",
            "| \u573a\u666f | Z\u73ed-S1 | \u53cc\u4eba\u573a\u666f\u72b6\u6001\u56fe | \u4e0e\u53ef\u89c1\u4eba\u6570\u4e00\u81f4 |\n"
            "| \u8272\u5361 | \u8272\u5361-Z\u73ed | \u8272\u5361\u56fe | \u672c\u573a\u8272\u677f |",
        )
        errors = self.errors(invalid)
        self.assertTrue(any("\u672a\u7ed1\u5b9a\u4efb\u4f55\u8272\u5361\u8d44\u4ea7" in e for e in errors))

    def test_exact_text_prop_requires_locked_prop_image(self):
        invalid = VALID.replace(
            "| \u9053\u5177 | \u9053\u5177-\u684c\u6cbf | \u7531\u573a\u666f\u56fe\u627f\u62c5 | \u9648\u8bbe\u7ea7\uff0c\u672c\u6bb5\u65e0\u53d9\u4e8b\u9053\u5177 |",
            "| \u9053\u5177 | \u62a5\u7eb8 | \u5b9a\u7248\u9053\u5177\u56fe | \u542b\u7cbe\u786e\u6587\u5b57\uff1a\u5934\u7248\u6807\u9898 |",
        )
        errors = self.errors(invalid)
        self.assertTrue(any("\u5b9a\u7248\u9053\u5177\u56fe" in e for e in errors))

    def test_missing_coverage_section_is_rejected(self):
        invalid = VALID.replace("## \u753b\u9762\u5bf9\u8d26", "## \u5176\u5b83\u8bb0\u5f55")
        self.assertTrue(any("\u7f3a\u5c11\u7ae0\u8282\uff1a## \u753b\u9762\u5bf9\u8d26" in e for e in self.errors(invalid)))

    def test_missing_asset_section_is_rejected(self):
        invalid = VALID.replace("## \u8d44\u4ea7\u6e05\u5355", "## \u5176\u5b83\u6e05\u5355")
        self.assertTrue(any("\u7f3a\u5c11\u7ae0\u8282\uff1a## \u8d44\u4ea7\u6e05\u5355" in e for e in self.errors(invalid)))

    def vo_only_text(self) -> str:
        """把段改成纯画外音：VO 不是同步对白，不该被套用开口触发/眼神/首帧规则。"""
        return VALID.replace(
            "<主体2> 严格使用 Mixed 3 的音色，自然说出 {哼，装什么装！}，"
            "一口自然说完；说完恢复鼻息，继续听着 <主体1> 的方向，右手自然留在桌沿。",
            "画面保持空镜，无人物开口。{哼，装什么装！}(系统VO，使用 Mixed 3 音色)",
        ).replace(
            "@[李威-逐句音频] {{Mixed 3}} 只控制 <主体2> 本句的音色与口型，"
            "不继承其它台词、情绪和背景声。",
            "@[李威-逐句音频] {{Mixed 3}} 只控制系统VO的音色，不继承其它台词、情绪和背景声。",
        )

    def test_voice_over_is_not_treated_as_sync_dialogue(self):
        errors = self.errors(self.vo_only_text())
        for phrase in ("开口触发", "眼神对象", "可剪辑落点", "干净首帧"):
            self.assertFalse(
                any(phrase in e for e in errors), f"VO 不应触发同步对白规则：{phrase}"
            )

    def test_voice_over_source_can_be_bound_without_subject(self):
        errors = self.errors(self.vo_only_text())
        self.assertFalse(any("说话主体缺少对应独立音色绑定" in e for e in errors))
        self.assertFalse(any("未声明只控制指定主体音色" in e for e in errors))

    def test_self_luminous_light_counts_as_physical_light(self):
        candidate = VALID.replace(
            "右侧 #C9D8E4 冷白窗光落在 <主体1> 的右肩，室内顶灯投出 #8A7A5E 暖色补光",
            "一道 #C9D8E4 冷白光束落在 <主体1> 的右肩，#8A7A5E 电弧在侧后方明灭",
        ).replace("右侧冷白窗光与室内顶灯方向全程固定。", "光束与电弧方向全程固定。")
        self.assertFalse(
            any("物理光源" in e for e in self.errors(candidate))
        )

    def test_floor_lamp_counts_as_physical_light(self):
        candidate = VALID.replace(
            "右侧 #C9D8E4 冷白窗光落在 <主体1> 的右肩，室内顶灯投出 #8A7A5E 暖色补光",
            "画面左侧 #C9D8E4 落地灯照亮 <主体1> 的右肩",
        ).replace("右侧冷白窗光与室内顶灯方向全程固定。", "落地灯方向全程固定。")
        self.assertFalse(any("物理光源" in e for e in self.errors(candidate)))

    def test_vague_light_still_rejected(self):
        candidate = VALID.replace(
            "右侧 #C9D8E4 冷白窗光落在 <主体1> 的右肩，室内顶灯投出 #8A7A5E 暖色补光",
            "画面整体明亮",
        ).replace("右侧窗光与室内顶灯方向全程固定。", "光线保持一致。")
        self.assertTrue(any("物理光源" in e for e in self.errors(candidate)))

    def test_not_subtitle_phrasing_is_accepted(self):
        candidate = VALID.replace(
            "保持无字幕，不生成可辨识文字、水印或 Logo。",
            "不生成可辨识文字。NOT字幕+NOT水印+NOT Logo。",
        )
        self.assertFalse(
            any("字幕/水印/Logo" in e for e in self.errors(candidate))
        )

    def test_missing_watermark_guard_still_rejected(self):
        candidate = VALID.replace(
            "保持无字幕，不生成可辨识文字、水印或 Logo。", "保持画面干净。"
        )
        self.assertTrue(any("字幕/水印/Logo" in e for e in self.errors(candidate)))

    def test_chinese_adjacent_hex_and_not_chain_count(self):
        """真实语料里 HEX 与 NOT 紧贴中文，词边界/空格假设会造成系统性误报。"""
        candidate = VALID.replace(
            "右侧 #C9D8E4 冷白窗光", "右侧#C9D8E4冷白窗光"
        ).replace(
            "NOT slow motion+NOT speed ramping+NOT 卡通渲染+NOT 三维动画+NOT 换脸+NOT 多余人物入画。",
            "NOT慢动作+NOT速度渐变+NOT卡通渲染+NOT三维动画+NOT换脸。",
        )
        _, warnings, _ = self.validate_text(candidate)
        self.assertFalse(any("inline HEX" in w for w in warnings))
        self.assertFalse(any("NOT 链" in w for w in warnings))

    def test_empty_voice_ledger_is_rejected(self):
        """空表头不构成对账——这张表此前正是因为没有行级检查而形同虚设。"""
        invalid = VALID.replace(
            "| 1 | 李威：哼，装什么装！ | V01 | 逐字一致 |\n", ""
        )
        self.assertTrue(any("语音对账没有有效对账行" in e for e in self.errors(invalid)))

    def test_voice_ledger_checked_against_source(self):
        errors = self.validate_text(VALID, self.SCRIPT)[0]
        self.assertEqual(errors, [])

    def test_dropped_voice_row_is_caught_against_source(self):
        two_line_script = self.SCRIPT.replace(
            "李威：哼，装什么装！\n", "李威：哼，装什么装！\n单知影：你，很吵。\n"
        )
        errors = self.validate_text(VALID, two_line_script)[0]
        self.assertTrue(any("与原剧本实际台词数" in e for e in errors))

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


class PlatformParameterDomainTests(unittest.TestCase):
    """画幅/分辨率/模型闸按平台真实支持面校验，不按单一项目约定写死。

    此前写死「必须 9:16 / 必须 480P」。参考剧《万妖图录传》七季全部 1280×720（16:9），
    在这条上直接硬失败——产线连下游都走不到，而它并不是平台限制：
    `tvmao model get` 的 inputSchema.enum 明确支持 1:1/16:9/9:16/4:3/3:4。
    """

    def errors(self, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delivery.md"
            path.write_text(text, encoding="utf-8")
            return MODULE.validate(path, None)[0]

    def test_landscape_ratio_is_accepted(self):
        landscape = VALID.replace("- 画幅：9:16", "- 画幅：16:9")
        self.assertFalse(
            [e for e in self.errors(landscape) if "画幅" in e],
            "16:9 是平台支持档，不应被判死",
        )

    def test_higher_resolution_is_accepted(self):
        hd = VALID.replace("- 分辨率：480P", "- 分辨率：720p")
        self.assertFalse([e for e in self.errors(hd) if "分辨率" in e])

    def test_ratio_outside_platform_enum_still_fails(self):
        # 放开不等于不管：平台没有的档位仍须拦下
        bogus = VALID.replace("- 画幅：9:16", "- 画幅：21:9")
        self.assertTrue(any("画幅" in e for e in self.errors(bogus)))

    def test_resolution_outside_platform_enum_still_fails(self):
        bogus = VALID.replace("- 分辨率：480P", "- 分辨率：4K")
        self.assertTrue(any("分辨率" in e for e in self.errors(bogus)))

    def test_original_vertical_project_still_passes(self):
        # 向后兼容：原竖屏项目的 9:16/480P 组合不受影响
        self.assertFalse(
            [e for e in self.errors(VALID) if "画幅" in e or "分辨率" in e]
        )


class StatelessReadGateTests(unittest.TestCase):
    """无状态读闸：模型只拿到这一段 prompt，指向"另一次生成"的措辞它无法解析。

    反向用例比正向更重要——词表是按真实语料收窄过的；
    误杀合法写法会让整条产线卡住，比漏检一条更糟。
    """

    def _banned(self, text: str) -> list[str]:
        return [
            description
            for pattern, description in MODULE.BANNED_PROMPT_PATTERNS
            if pattern.search(text)
        ]

    def test_flags_reference_to_a_previous_generation(self):
        for phrase in (
            "不要像上次那样糊",
            "前面那版光位打反了",
            "沿用上一版的服装",
            "参考上个版本",
            "之前那版太快",
            "上次生成的问题",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(
                    "会话依赖措辞（模型看不到上一次生成）",
                    self._banned(f"中景固定机位。{phrase}。<主体1> 起身。"),
                )

    def test_does_not_flag_audio_continuity_written_into_the_prompt(self):
        # assets/libtv-video-prompts.template.md 的真实写法：声音层跨段延续是合法正文
        text = "【声音设计】0-2秒：室内低频底噪延续上一段；2-5秒：<主体1> 的原声台词。"
        self.assertEqual(self._banned(text), [])

    def test_does_not_flag_the_mandatory_subject_lock_line(self):
        # _fast_drama_contract 强制要求这两句，误杀会让所有正式段直接失败
        for text in (
            "主体标签锁定：本段仅使用 <主体N>；角色名不进正文。",
            "本段共 3 个约 2–3 秒的硬切镜头。",
        ):
            with self.subTest(text=text):
                self.assertEqual(self._banned(text), [])

    def test_does_not_flag_in_shot_narrative_ordering(self):
        # 「之前」指镜内叙事先后，不是指上一次生成
        text = "<主体1> 拿起他之前放在桌沿的钢笔，指腹擦过笔帽。"
        self.assertEqual(self._banned(text), [])


if __name__ == "__main__":
    unittest.main()


def test_voice_line_must_reach_prompt_with_correct_symbol():
    """语音对账里的台词必须以 {原文} 落进它自己那段的提示词。

    2026-09-04 实证：《万妖图录传》EP01 的 V01 只在【声音设计】里写
    「完成第一句内心独白」，未给原文；Seedance 生成出剧本中不存在的
    「我还活着／那是虎妖王」。台词被静默替换，而对账表全绿。

    更严重的是连带效应：整套同步对白规则（开口触发、眼神落点、固定机位、
    声连画断）都以 `{}` 内的台词为触发条件，提示词里没有 `{}` 就全部静默失效。
    """
    module = MODULE
    rows = [(1, "姜月初（内心）：[00:03] 我……穿越了。", "V01-Shot2", "已落实")]

    missing = (
        "## 生成段 V01｜开篇\n\n```text\n"
        "Shot 2:（苏醒）<主体1> 睁眼。\n\n"
        "【声音设计】<主体1> 完成第一句内心独白。\n```\n"
    )
    errors = module.check_voice_lines_reach_prompt(rows, missing)
    assert errors and "没有以 『原文』 进入 V01" in errors[0]

    # 内心独白必须用 『』：豆包官方符号表五个符号，tvskill 此前漏了旁白，
    # 结果内心独白与同步对白同符号，模型无从区分谁该有口型、谁该出字幕。
    present = (
        "## 生成段 V01｜开篇\n\n```text\n"
        "Shot 2:（苏醒）<主体1> 睁眼，内心独白 『我……穿越了。』，一口自然说完。\n```\n"
    )
    assert module.check_voice_lines_reach_prompt(rows, present) == []

    # 用错符号要点名，而不是含糊报「没写进提示词」
    wrong = present.replace("『我……穿越了。』", "{我……穿越了。}")
    got = module.check_voice_lines_reach_prompt(rows, wrong)
    assert got and "用错了符号" in got[0] and "『原文』" in got[0]

    # 同步对白（无内心/OS/VO 标记）仍用 {}
    sync_rows = [(2, "裴长青（虚弱）：[00:40] 过来，扶我起来。", "V01-Shot3", "已落实")]
    sync_ok = (
        "## 生成段 V01｜开篇\n\n```text\n"
        "Shot 3:（伸手）<主体2> 开口说 {过来，扶我起来。}。\n```\n"
    )
    assert module.check_voice_lines_reach_prompt(sync_rows, sync_ok) == []


def test_posture_must_be_restated_in_every_shot_with_that_subject():
    """状态交接表锁了体位，就要在该角色在场的每一个 Shot 正文里复述。

    2026-09-04 实证两处：V02 Shot 4 姜月初该坐着却站起、V07 裴长青该半跪却站起。
    两处的根因相同——体位只写在段末【状态交接】表，而那张表不进模型。

    V02 的逐镜核查尤其说明问题：Shot 1／5 都写了「保持坐姿」，Shot 2／3 是闪回、
    人物不在场，**唯一在场却漏写的 Shot 4 就是断裂点**。所以规则是逐镜复述，
    不是「段内提过一次就行」。
    """
    module = MODULE
    section = (
        "```text\n"
        "将 @[角色-姜月初]（角色-姜月初） 中的稳定身份特征定义为 <主体1>，不可改造。\n\n"
        "Shot 1:（起手）<主体1> 保持坐姿，视线落在前方。\n\n"
        "Shot 2:（延续）<主体1> 微微喘气，肩线起伏。\n\n"
        "Shot 3:（空镜）硝烟掠过，无人物。\n"
        "```\n"
    )
    rows = [("character:姜月初", "CH-JYC-v1-坐姿-尸堆中", "CH-JYC-v1-坐姿-注视前方")]
    got = module.check_posture_restated_per_shot("V02", section, rows)
    assert got and "Shot 2" in got[0] and "坐姿" in got[0]
    assert "Shot 1" not in got[0], "写了体位的镜不该被点名"
    assert "Shot 3" not in got[0], "该角色不在场的镜不该被点名"

    # 只有一侧写了体位也算锁死——V07 裴长青正是这个形状
    rows_one_sided = [
        ("character:裴长青", "CH-PCQ-v1-重伤-半跪开口", "CH-PCQ-v1-重伤-捂胸施压")
    ]
    section2 = section.replace("角色-姜月初", "角色-裴长青")
    assert module.check_posture_restated_per_shot("V07", section2, rows_one_sided)

    # 段内本就要变体位（半跪→站立）时不报
    rows_change = [
        ("character:裴长青", "CH-PCQ-v1-重伤-半跪", "CH-PCQ-v1-重伤-站立")
    ]
    assert module.check_posture_restated_per_shot("V11", section2, rows_change) == []


def test_same_line_must_not_repeat_in_one_shot():
    """同一句台词不得在同一个镜头里出现两次。

    2026-09-04 实证：手写镜头文本里已写了台词，自动注入又追加了一遍，
    同一行出现两份「内心独白 『我……穿越了。』」，模型会把一句说成两遍。
    交付校验此前只查「台词有没有进提示词」，不查「进了几次」——
    这个洞是验证方案里的反例测试抓出来的，正例全绿时它一直藏着。
    """
    module = MODULE
    ok = "Shot 2:（苏醒）<主体1> 的内心独白 『我……穿越了。』；闭口不做口型。\n"
    assert module.check_no_duplicate_lines(ok) == []

    dup = (
        "Shot 2:（苏醒）<主体1> 的内心独白 『我……穿越了。』；"
        "<主体1> 的内心独白 『我……穿越了。』。\n"
    )
    got = module.check_no_duplicate_lines(dup)
    assert got and "出现多次" in got[0]

    # {{Mixed N}} 不是台词，不该被算进来
    mixed = "Shot 1: @[角色] {{Mixed 1}} 与 @[色卡] {{Mixed 1}} 并列。\n"
    assert module.check_no_duplicate_lines(mixed) == []


def test_storyboard_grammar_gates():
    """分镜语法闸：四要素头、受控词表、POV 规则、转场、写作纪律。

    对标 doubao-creative-drama 的 storyboard.md。tvskill 此前的镜头是散文式的，
    最严重的是**完全没有「视角类型」这个维度**——从没区分过镜头是
    「从外面看」（第三人称客观）还是「从角色眼睛里看」（POV 第一人称）。

    只对时间戳新形态强制；旧的 Shot N 形态是既有产线在用的交付形式，不受约束。
    """
    module = MODULE

    def seg(body: str) -> str:
        return "## 生成段 V01｜测试\n\n```text\n" + body + "\n```\n"

    ok = seg(
        "0-3 秒：[中景｜第三人称客观视角｜固定｜半侧面] 姜月初走进屋内，"
        "右手推门后停住。 [硬切]"
    )
    errors, _w = module.check_storyboard_grammar(ok)
    assert errors == [], errors

    # 缺四要素头
    e, _ = module.check_storyboard_grammar(seg("0-3 秒：姜月初走进屋内。 [硬切]"))
    assert any("缺少四要素头" in x for x in e)

    # 景别不在词表
    e, _ = module.check_storyboard_grammar(
        seg("0-3 秒：[超级近｜第三人称客观视角｜固定｜正面] 她站住。 [硬切]")
    )
    assert any("景别" in x and "受控词表" in x for x in e)

    # 视角类型缺失是本次补的核心维度
    e, _ = module.check_storyboard_grammar(
        seg("0-3 秒：[中景｜客观镜头｜固定｜正面] 她站住。 [硬切]")
    )
    assert any("视角类型" in x for x in e)

    # POV 必须写明角色 + 眼睛高度，且不得出现该角色完整正脸
    e, _ = module.check_storyboard_grammar(
        seg("0-3 秒：[特写｜POV 第一人称视角｜手持感运镜｜俯拍] 看向桌面。 [硬切]")
    )
    assert any("没写明所属角色" in x for x in e)
    assert any("眼睛高度" in x for x in e)

    e, _ = module.check_storyboard_grammar(
        seg(
            "0-3 秒：[特写｜林远 POV 第一人称视角｜手持感运镜｜俯拍] "
            "从林远眼睛高度俯看桌面，画面里出现林远的完整正脸。 [硬切]"
        )
    )
    assert any("完整正脸" in x for x in e)

    # 转场必须标注
    e, _ = module.check_storyboard_grammar(
        seg("0-3 秒：[中景｜第三人称客观视角｜固定｜正面] 她站住。")
    )
    assert any("转场" in x for x in e)

    # 写作纪律
    base = "0-3 秒：[中景｜第三人称客观视角｜固定｜正面] {}。 [硬切]"
    e, _ = module.check_storyboard_grammar(seg(base.format("她非常愤怒地站着")))
    assert any("抽象情绪词" in x for x in e)
    e, _ = module.check_storyboard_grammar(seg(base.format("三个人面面相觑")))
    assert any("群体量词" in x for x in e)
    e, _ = module.check_storyboard_grammar(seg(base.format("那个男人走过来")))
    assert any("指代已命名角色" in x for x in e)

    # 旧 Shot N 形态不受本闸约束
    legacy = seg("Shot 1: 稳定中景，姜月初走进屋内。")
    assert module.check_storyboard_grammar(legacy) == ([], [])


def test_vague_quality_words_are_rejected():
    """模糊质量词不能单独作约束。

    对标 doubao-creative-drama assets.md：「禁止使用模糊质量词单独作为约束，
    例如"高级、漂亮、震撼、氛围感强"，必须替换为具体的构图、光影、色彩、
    材质和空间描述。」与 zy-cinematic-realism 的 Restraint Test 同向——
    风格词不能冒充实质。
    """
    module = MODULE

    def seg(body: str) -> str:
        return (
            "## 生成段 V01｜测试\n\n```text\n"
            "0-3 秒：[中景｜第三人称客观视角｜固定｜正面] " + body + " [硬切]\n```\n"
        )

    e, _ = module.check_storyboard_grammar(seg("画面氛围感强，非常高级。"))
    assert any("模糊质量词" in x for x in e)

    ok = seg(
        "#3F4A57 铅灰云层占画面上三成，云隙天光自左上斜射落在中景草地形成唯一高亮区；"
        "青灰草地高粗糙度微反射，湿泥呈窄反射带。"
    )
    assert not [x for x in module.check_storyboard_grammar(ok)[0] if "模糊质量词" in x]
