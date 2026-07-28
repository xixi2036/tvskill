"""禁止判据分叉：同一条规则不许在多个脚本里各写一份。

已经实证两次：`audio_control_subjects` 与一处内联正则不同步；`OS_VO_RE` 在
validate 里修好了中文词边界问题，audit_canvas_nodes 里却还是坏的旧版，
导致画布审计继续漏判"系统VO"。修一处、漏一处，是这类缺陷的固定形态。

本测试扫描 scripts/ 下所有脚本，若发现共享判据被某个脚本重新本地定义，直接失败。
"""

from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SPEC = importlib.util.spec_from_file_location(
    "_shared_patterns", SCRIPTS / "_shared_patterns.py"
)
SHARED = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SHARED)

SHARED_NAMES = {
    name for name in dir(SHARED)
    if name.isupper() and name.endswith("_RE")
}
DEFINITION_RE = re.compile(r"^([A-Z_]+)\s*=\s*re\.compile\(", re.M)


class SharedPatternTests(unittest.TestCase):
    def script_files(self) -> list[Path]:
        return [
            path for path in sorted(SCRIPTS.glob("*.py"))
            if path.name != "_shared_patterns.py"
        ]

    def test_shared_patterns_are_not_redefined_locally(self):
        offenders: list[str] = []
        for path in self.script_files():
            source = path.read_text(encoding="utf-8")
            for name in DEFINITION_RE.findall(source):
                if name in SHARED_NAMES:
                    offenders.append(f"{path.name}:{name}")
        self.assertEqual(
            offenders, [],
            "这些判据已在 _shared_patterns.py 中定义，不得在脚本里重新定义："
            f"{offenders}",
        )

    def test_os_vo_matches_chinese_adjacent_form(self):
        # 真实语料写作「系统VO」「单知影VO：」，字母紧贴中文
        for text in ("系统VO，使用Mixed 3音色", "单知影VO：退学意味着", "画外音", "内心独白"):
            with self.subTest(text):
                self.assertTrue(SHARED.OS_VO_RE.search(text))
        self.assertIsNone(SHARED.OS_VO_RE.search("VOICE 不该匹配"))

    def test_every_shared_pattern_is_actually_used(self):
        """共享模块不该堆放没人用的判据。"""
        blob = "\n".join(
            path.read_text(encoding="utf-8") for path in self.script_files()
        )
        unused = [name for name in SHARED_NAMES if name not in blob]
        self.assertEqual(unused, [], f"共享判据无人使用，应删除：{unused}")


if __name__ == "__main__":
    unittest.main()
