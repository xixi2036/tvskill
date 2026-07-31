from __future__ import annotations

import tempfile
from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_series_continuity  # noqa: E402
from test_validate_delivery_md import VALID  # noqa: E402


def episode_text(number: int) -> str:
    text = VALID.replace("# EP01｜", f"# EP{number:02d}｜")
    text = text.replace("- 审核范围：单集", "- 审核范围：截至EP02")
    if number == 2:
        text = text.replace("- 前集承接：开篇", "- 前集承接：EP01-V01")
        text = text.replace("- 前置段：开场", "- 前置段：EP01-V01")
    return text


class SeriesContinuityAuditTests(unittest.TestCase):
    def audit_texts(self, texts: list[str]):
        with tempfile.TemporaryDirectory() as directory:
            paths: list[Path] = []
            for index, text in enumerate(texts, start=1):
                path = Path(directory) / f"EP{index:02d}-LibTV视频节点提示词.md"
                path.write_text(text, encoding="utf-8")
                paths.append(path)
            return audit_series_continuity.audit(paths)

    def test_two_episode_chain_passes(self):
        errors, warnings, summary = self.audit_texts([episode_text(1), episode_text(2)])
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(summary["episodes"], 2)
        self.assertEqual(summary["segments"], 2)

    def test_cross_episode_state_jump_is_rejected(self):
        second = episode_text(2).replace(
            "| character:李威 | CH-LW-v1-画面右 | CH-LW-v1-画面右 |",
            "| character:李威 | CH-LW-v1-画面左 | CH-LW-v1-画面右 |",
        )
        errors, _, _ = self.audit_texts([episode_text(1), second])
        self.assertTrue(any("入点" in error and "不等于" in error for error in errors))

    def test_version_change_without_declaration_is_rejected(self):
        second = episode_text(2).replace(
            "| character:李威 | 人物 | CH-LW-v1 | 否 | 无 |",
            "| character:李威 | 人物 | CH-LW-v2 | 否 | 无 |",
        )
        errors, _, _ = self.audit_texts([episode_text(1), second])
        self.assertTrue(any("未声明允许变化" in error for error in errors))

    def test_false_partial_scope_is_rejected(self):
        errors, _, _ = self.audit_texts([episode_text(2)])
        self.assertTrue(any("声明审核至" in error for error in errors))

    def test_missing_predecessor_is_rejected(self):
        second = episode_text(2).replace("- 前置段：EP01-V01", "- 前置段：EP99-V09")
        errors, _, _ = self.audit_texts([episode_text(1), second])
        self.assertTrue(any("前置段 EP99-V09 不存在" in error for error in errors))

    def test_state_key_must_exist_in_master(self):
        second = episode_text(2).replace(
            "| axis:CG-Z-DAY01 | AX-Z-v1 | AX-Z-v1 |",
            "| prop:钢笔-A | PEN-A-HAND | PEN-A-WALL |",
        )
        errors, _, _ = self.audit_texts([episode_text(1), second])
        self.assertTrue(any("未登记在本集连续性母版" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
