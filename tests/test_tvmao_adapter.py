from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_delivery_markdown as sync  # noqa: E402


def segment() -> dict:
    return {
        "number": "01",
        "prompt": (
            "将 @[单知影] {{Mixed 1}} 定义为 <主体1>；"
            "@[单知影音色] {{Mixed 2}} 只控制 <主体1> 的音色；"
            "参考 @[干净首帧] {{Mixed 3}}；"
            "参考 @[动作视频] {{Mixed 4}}；使用 Mixed 2 的音色。"
        ),
        "mixed": [
            {"number": 1, "asset": "单知影身份图", "mediaType": "图片", "semantic": "@[单知影]"},
            {"number": 2, "asset": "单知影音色", "mediaType": "音频", "semantic": "@[单知影音色]"},
            {"number": 3, "asset": "干净首帧", "mediaType": "图片", "semantic": "@[干净首帧]"},
            {"number": 4, "asset": "动作视频", "mediaType": "视频", "semantic": "@[动作视频]"},
        ],
    }


class TVMaoAdapterTests(unittest.TestCase):
    def test_mixed_dsl_compiles_to_per_media_official_references(self):
        prompt, rows = sync.compile_prompt(segment())
        self.assertIn("图片1（单知影）", prompt)
        self.assertIn("音频1（单知影音色）", prompt)
        self.assertIn("图片2（干净首帧）", prompt)
        self.assertIn("视频1（动作视频）", prompt)
        self.assertIn("使用 音频1（单知影音色） 的音色", prompt)
        self.assertNotIn("{{Mixed", prompt)
        self.assertNotIn("Mixed 2", prompt)
        self.assertEqual(
            [(row["kind"], row["kindIndex"]) for row in rows],
            [("图片", 1), ("音频", 1), ("图片", 2), ("视频", 1)],
        )

    def test_canvas_prompt_uses_node_id_mentions_and_round_trips_for_model(self):
        run_prompt, rows = sync.compile_prompt(segment())
        for row, node_id in zip(rows, ["n-char", "n-voice", "n-frame", "n-motion"]):
            row["nodeId"] = node_id
        canvas_prompt = sync.compile_canvas_prompt(run_prompt, rows)
        self.assertIn("@[图片:n-char]（单知影）", canvas_prompt)
        self.assertIn("@[音频:n-voice]（单知影音色）", canvas_prompt)
        self.assertIn("@[图片:n-frame]（干净首帧）", canvas_prompt)
        self.assertIn("@[视频:n-motion]（动作视频）", canvas_prompt)
        self.assertEqual(sync.serialize_canvas_prompt(canvas_prompt, rows), run_prompt)

    def test_semantic_mismatch_is_rejected(self):
        value = segment()
        value["mixed"][0]["semantic"] = "@[李威]"
        with self.assertRaisesRegex(ValueError, "语义不一致"):
            sync.compile_prompt(value)

    def test_unreferenced_input_is_rejected(self):
        value = segment()
        value["prompt"] = value["prompt"].replace("参考 @[动作视频] {{Mixed 4}}；", "")
        with self.assertRaisesRegex(ValueError, "未绑定素材"):
            sync.compile_prompt(value)

    def test_legacy_model_name_maps_to_stable_tvmao_id(self):
        defaults = {"model": "Seedance 2.0 Fast VIP"}
        self.assertEqual(sync.resolve_model(defaults, None), sync.DEFAULT_MODEL_ID)

    def test_schema_accepts_live_default_shape(self):
        schema = {
            "modelId": sync.DEFAULT_MODEL_ID,
            "available": True,
            "inputSchema": {
                "properties": {
                    "prompt": {"type": "string"},
                    "duration": {"type": "number", "enum": list(range(4, 16))},
                    "ratio": {"type": "string", "enum": ["9:16", "16:9"]},
                    "resolution": {"type": "string", "enum": ["480p", "720p"]},
                }
            },
        }
        sync.validate_model_schema(
            schema,
            {"prompt": "test", "duration": 6, "ratio": "9:16", "resolution": "480p"},
            sync.DEFAULT_MODEL_ID,
        )

    def test_schema_rejects_old_nested_settings(self):
        schema = {
            "modelId": sync.DEFAULT_MODEL_ID,
            "available": True,
            "inputSchema": {"properties": {"prompt": {"type": "string"}}},
        }
        with self.assertRaisesRegex(ValueError, "不支持参数 settings"):
            sync.validate_model_schema(
                schema, {"prompt": "test", "settings": {"duration": 6}},
                sync.DEFAULT_MODEL_ID,
            )

    def test_asset_mapping_accepts_asset_or_semantic(self):
        row = segment()["mixed"][0]
        self.assertEqual(sync.mapping_lookup({"单知影身份图": "n-a"}, row), "n-a")
        self.assertEqual(sync.mapping_lookup({"单知影": "n-b"}, row), "n-b")

    def test_node_model_reads_live_tvmao_params_shape(self):
        detail = {"params": {"modelId": sync.DEFAULT_MODEL_ID}}
        self.assertEqual(sync.node_model(detail), sync.DEFAULT_MODEL_ID)

    def test_update_splits_snapshot_params_from_multi_edge_rewire(self):
        params = {
            "prompt": "test", "ratio": "9:16", "resolution": "480p", "duration": 4,
        }
        params_command = sync.build_params_update_command("tvmao", "n-video", 96, params, 17)
        rewire_command = sync.build_rewire_command(
            "tvmao", "n-video", 96, ["n-old-a", "n-old-b"], ["n-new-a", "n-new-b"]
        )
        self.assertIn("--snapshot-version", params_command)
        self.assertNotIn("--left", params_command)
        self.assertNotIn("--left-rm", params_command)
        self.assertNotIn("--snapshot-version", rewire_command)
        self.assertEqual(
            rewire_command[-8:],
            [
                "--left-rm", "n-old-a", "--left-rm", "n-old-b",
                "--left", "n-new-a", "--left", "n-new-b",
            ],
        )


if __name__ == "__main__":
    unittest.main()
