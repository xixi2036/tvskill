from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "_fast_drama_contract.py"
SPEC = importlib.util.spec_from_file_location("fast_drama_contract", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FastDramaContractTests(unittest.TestCase):
    def messages(self, prompt: str, duration: int = 12, has_characters: bool = False):
        return MODULE.prompt_quality_messages(
            prompt,
            duration,
            has_character_references=has_characters,
        )

    def test_twelve_second_six_shot_rhythm_passes(self):
        prompt = "本段共 6 个约 2 秒的硬切镜头。\n" + "\n".join(
            f"Shot {index}:（约2秒·功能）固定机位，动作完成并停稳。"
            for index in range(1, 7)
        )
        errors, warnings = self.messages(prompt)
        self.assertEqual(errors, [])
        self.assertFalse(any("节拍建议" in item for item in warnings))

    def test_generic_dialogue_templates_are_rejected(self):
        prompt = (
            "Shot 1: 稳定近景，<主体1>听见前一句结束后才开口，"
            "视线落在画面内真实对象的眼睛。\n"
            "【声音设计】保留场景连续底噪、衣料摩擦、脚步或道具接触的自然声。"
        )
        errors, _ = self.messages(prompt, duration=4)
        self.assertTrue(any("无指向" in item for item in errors))
        self.assertTrue(any("通用占位句" in item for item in errors))

    def test_generic_performance_boilerplate_is_rejected(self):
        prompt = (
            "Shot 1:（约4秒）<主体1>说完恢复鼻息并继续倾听，保持自然活状态。"
        )
        errors, _ = self.messages(prompt, duration=4)
        self.assertTrue(any("机械表演通用句" in item for item in errors))

    def test_scene_planning_board_cannot_be_cleansed_by_negative_prompt(self):
        prompt = (
            "将 @[场景状态-客厅] {{Mixed 1}} 定义为 <场景1>；"
            "只继承空间，不继承多视图排版、文字标签或灰色占位人形。\n"
            "Shot 1:（约4秒）固定中景，人物保持当前动作。"
        )
        errors, _ = self.messages(prompt, duration=4)
        self.assertTrue(any("规划板" in item for item in errors))

    def test_seated_multi_character_blocking_requires_screen_positions(self):
        prompt = (
            "Shot 1:（约4秒）<主体1>与<主体2>坐在同一张沙发上，保持人物关系轴。"
        )
        errors, _ = self.messages(prompt, duration=4)
        self.assertTrue(any("多人坐姿段" in item for item in errors))

        prompt = (
            "Shot 1:（约4秒）<主体1>坐在画面左侧沙发位，"
            "<主体2>坐在画面右侧沙发位，保持人物关系轴。"
        )
        errors, _ = self.messages(prompt, duration=4)
        self.assertEqual(errors, [])

    def test_long_dialogue_requires_multicamera_audio_bridge(self):
        line = "这句话足够长，需要在说话人和听者反应之间切换画面才能保持短剧节奏。"
        prompt = f"Shot 1:（约8秒）固定近景，<主体1>说出 {{{line}}}。"
        errors, _ = self.messages(prompt, duration=8)
        self.assertTrue(any("多机位声连画断" in item for item in errors))

    def test_long_dialogue_audio_bridge_passes(self):
        line = "这句话较长，需要在说话人和听者反应之间连续切换。"
        prompt = (
            "本段共 4 个约 2 秒的硬切镜头。\n"
            f"Shot 1:（约2秒）<主体1>开始说出 {{{line}}}，声连画断贯穿至 Shot 3。\n"
            "Shot 2:（约2秒）<主体2>闭口反应，同一句对白持续。\n"
            "Shot 3:（约2秒）回到<主体1>，尾句结束。\n"
            "Shot 4:（约2秒）双人关系镜落幅。"
        )
        errors, _ = self.messages(prompt, duration=8)
        self.assertEqual(errors, [])

    def test_long_dialogue_rejects_repeated_reaction_closeups(self):
        line = "这句话足够长，需要连续切换多个机位来保持竖屏短剧应有的叙事速度。"
        prompt = (
            "本段共 6 个约 2 秒的硬切镜头。\n"
            f"Shot 1:（约2秒·说话人起句）<主体1>说出 {{{line}}}，声连画断贯穿至 Shot 6。\n"
            "Shot 2:（约2秒·听者反应）<主体2>闭口反应，同一句对白持续。\n"
            "Shot 3:（约2秒·听者反应）<主体2>闭口反应，同一句对白持续。\n"
            "Shot 4:（约2秒·听者反应）<主体2>闭口反应，同一句对白持续。\n"
            "Shot 5:（约2秒·听者反应）<主体2>闭口反应，同一句对白持续。\n"
            "Shot 6:（约2秒·说话人落句）回到<主体1>，尾句结束。"
        )
        errors, _ = self.messages(prompt, duration=12)
        self.assertTrue(any("跨四镜以上" in item for item in errors))
        self.assertTrue(any("连续重复三次" in item for item in errors))

    def test_long_dialogue_four_shot_multicamera_passes(self):
        line = "这句话足够长，需要连续切换多个机位来保持竖屏短剧应有的叙事速度。"
        prompt = (
            "本段共 4 个约 2 秒的硬切镜头。\n"
            f"Shot 1:（约2秒·说话人起句）<主体1>说出 {{{line}}}，声连画断贯穿至 Shot 4。\n"
            "Shot 2:（约2秒·听者反应）<主体2>闭口反应，同一句对白持续。\n"
            "Shot 3:（约2秒·双人关系镜）<主体1>前景说话，<主体2>在对侧听。\n"
            "Shot 4:（约2秒·说话人落句）回到<主体1>，尾句结束。"
        )
        errors, _ = self.messages(prompt, duration=8)
        self.assertEqual(errors, [])

    def test_unbound_offscreen_counterpart_is_rejected(self):
        prompt = (
            "本段共 2 个约 2 秒的硬切镜头。\n"
            "Shot 1:（约2秒）<主体1>看向画外对话方。\n"
            "Shot 2:（约2秒）画外对话方反应近景。"
        )
        errors, _ = self.messages(prompt, duration=4)
        self.assertTrue(any("未绑定" in item for item in errors))

    def test_character_board_requires_transfer_exclusion(self):
        prompt = "Shot 1:（约4秒）固定机位，人物保持呼吸。"
        errors, _ = self.messages(prompt, duration=4, has_characters=True)
        self.assertTrue(any("人物参考缺少传递边界" in item for item in errors))

    def test_exact_text_cannot_conflict_with_textless_constraint(self):
        prompt = "Shot 1:（约4秒）纸张抬头显示「协议」。画面无画面文字。"
        errors, _ = self.messages(prompt, duration=4)
        self.assertTrue(any("一边要求显示" in item for item in errors))


if __name__ == "__main__":
    unittest.main()


def test_shot_budget_is_dialogue_aware():
    """长对话段不能套快切基线——那是把整体语料均值过拟合到对话戏上。

    官方指南 §6.1：单场文戏、长对话、情绪递进 → 优先视频延长保持连续；
    剧情转折、追逐、打斗、蒙太奇 → 独立分段快切。

    2026-09-04 三条独立证据：
      1. 参考成片《万妖图录传》EP01 对话段(60–150s)中位刀长 4.0 秒，
         同集开篇蒙太奇 2.8 秒——同一部片子两种节奏；
      2. 按 12 秒 5 镜下发后，模型自己在有长台词的段少切镜（V09 只切 2 次）；
      3. Seedance 2.0 音画同出，2.4 秒一刀不给念白与反应留余地。
    """
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "_shot_budget.py"
    spec = importlib.util.spec_from_file_location("_shot_budget", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 无台词：维持爆款快切基线
    assert module.recommended_shot_range(12, 0) == (4, 7)
    # 台词占去半段以上：改用 3.5–5 秒刀长
    low, high = module.recommended_shot_range(12, 26)
    assert (low, high) == (2, 4)
    # 零星短台词不触发
    assert module.recommended_shot_range(12, 10) == (4, 7)

    # 长对话段切太碎要告警，并说明原因
    _errors, warns = module.shot_budget_messages(12, 5, spoken_chars=26)
    assert warns and "长对话段" in warns[0] and "§6.1" in warns[0]
    # 同样镜数在无台词段不告警
    _errors, warns_none = module.shot_budget_messages(12, 5, spoken_chars=0)
    assert not any("长对话段" in w for w in warns_none)
