import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "validate_skill_portability.py"
)
SPEC = importlib.util.spec_from_file_location("validate_skill_portability", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SkillPortabilityTests(unittest.TestCase):
    def test_current_skill_is_portable(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(MODULE.validate(root), [])

    def test_external_skill_route_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "references" / "libtv").mkdir(parents=True)
            (root / "scripts").mkdir()
            (root / "SKILL.md").write_text(
                "---\nname: tvskill\ndescription: test\n---\n[skill:other]\n",
                encoding="utf-8",
            )
            (root / "references" / "libtv" / "performance-dialogue-contract.md").write_text(
                "contract", encoding="utf-8"
            )
            (root / "scripts" / "validate_delivery_md.py").write_text(
                "pass", encoding="utf-8"
            )
            errors = MODULE.validate(root)
            self.assertTrue(any("外部 skill 路由" in error for error in errors))

    def test_missing_scene_topology_module_is_rejected(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "tvskill"
            import shutil

            shutil.copytree(root, copied)
            (
                copied
                / "references"
                / "libtv"
                / "scene-topology-and-functional-orientation.md"
            ).unlink()
            errors = MODULE.validate(copied)
            self.assertTrue(
                any(
                    "scene-topology-and-functional-orientation.md" in error
                    for error in errors
                )
            )

    def test_legacy_json_pipeline_file_is_rejected(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "tvskill"
            import shutil

            shutil.copytree(root, copied)
            (copied / "references" / "asset-plan-schema.json").write_text(
                "{}", encoding="utf-8"
            )
            errors = MODULE.validate(copied)
            self.assertTrue(any("废弃 JSON 管线文件" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
