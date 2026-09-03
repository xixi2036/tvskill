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

    def test_canvas_prompt_converts_adjacent_references_joined_by_chinese_text(self):
        value = segment()
        value["prompt"] = (
            "@[单知影] {{Mixed 1}}与@[干净首帧] {{Mixed 3}}分别锁定身份和构图；"
            "@[单知影音色] {{Mixed 2}}只控制音色；"
            "@[动作视频] {{Mixed 4}}只控制动作。"
        )
        run_prompt, rows = sync.compile_prompt(value)
        for row, node_id in zip(rows, ["n-char", "n-voice", "n-frame", "n-motion"]):
            row["nodeId"] = node_id
        canvas_prompt = sync.compile_canvas_prompt(run_prompt, rows)
        self.assertIn("@[图片:n-char]（单知影）与@[图片:n-frame]（干净首帧）", canvas_prompt)
        self.assertEqual(sync.serialize_canvas_prompt(canvas_prompt, rows), run_prompt)

    def test_bare_mixed_reference_after_chinese_text_is_compiled(self):
        value = segment()
        value["prompt"] = value["prompt"].replace("使用 Mixed 2", "使用Mixed 2")
        prompt, _ = sync.compile_prompt(value)
        self.assertIn("使用音频1（单知影音色） 的音色", prompt)
        self.assertNotIn("Mixed 2", prompt)

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

    def test_runnable_sync_preview_cannot_bypass_clean_frame(self):
        rows = [
            {"asset": "角色A三视图", "semantic": "@[角色A]"},
            {"asset": "角色A音色", "semantic": "@[角色A音色]"},
        ]
        prompt = "原生声画同出预览。<主体1>使用独立音色说出 {你好。}"
        self.assertIn(
            "预览标签不能绕过",
            sync.clean_frame_block_reason(prompt, rows, "可运行") or "",
        )
        rows.append({"asset": "EP01-V01-干净首帧", "semantic": "@[首帧-EP01-V01]"})
        self.assertIsNone(sync.clean_frame_block_reason(prompt, rows, "可运行"))

    def test_fresh_set_forbids_partial_selection(self):
        with self.assertRaisesRegex(ValueError, "禁止同时使用 --only"):
            sync.resolve_sync_mode(
                fresh_set=True, only="3,7,8", node_mapping={}
            )

    def test_fresh_set_forbids_reusing_old_video_nodes(self):
        with self.assertRaisesRegex(ValueError, "禁止使用 --node"):
            sync.resolve_sync_mode(
                fresh_set=True, only=None, node_mapping={"01": "n-old-video"}
            )

    def test_fresh_set_resolves_to_complete_create_contract(self):
        self.assertEqual(
            sync.resolve_sync_mode(
                fresh_set=True, only=None, node_mapping={}
            ),
            "fresh-set",
        )

    def test_non_fresh_modes_remain_explicit(self):
        self.assertEqual(
            sync.resolve_sync_mode(
                fresh_set=False, only="3", node_mapping={}
            ),
            "create-selected",
        )
        self.assertEqual(
            sync.resolve_sync_mode(
                fresh_set=False, only=None, node_mapping={"03": "n-idle"}
            ),
            "update-idle",
        )

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

    def test_new_nodes_are_planned_below_existing_canvas_in_visible_grid(self):
        existing = [
            {
                "position": {"x": -8, "y": 1000},
                "size": {"width": 280, "height": 498},
            },
            {
                "position": {"x": 14000, "y": 1680},
                "size": {"width": 280, "height": 498},
            },
        ]
        positions = sync.plan_create_positions(existing, 8)
        self.assertEqual(len(positions), 8)
        self.assertEqual(len({(item["x"], item["y"]) for item in positions}), 8)
        self.assertTrue(all(item["y"] >= 2400 for item in positions))
        self.assertEqual(positions[0], {"x": -100, "y": 2400})
        self.assertEqual(positions[7], {"x": -100, "y": 3000})

    def test_create_command_contains_explicit_canvas_position(self):
        value = {
            "compiledPrompt": "test",
            "params": {
                "ratio": "9:16", "resolution": "480p", "duration": 8,
            },
        }
        command = sync.build_create_command(
            "tvmao", 97, sync.DEFAULT_MODEL_ID, value,
            ["n-image", "n-audio"], {"x": 1200, "y": 2400},
        )
        self.assertEqual(command[command.index("--x") + 1], "1200")
        self.assertEqual(command[command.index("--y") + 1], "2400")
        self.assertEqual(command[-4:], ["--left", "n-image", "--left", "n-audio"])


if __name__ == "__main__":
    unittest.main()
