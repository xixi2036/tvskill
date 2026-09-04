from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "goal_contract.py"
SPEC = importlib.util.spec_from_file_location("goal_contract", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

PIPELINE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "pipeline_state.py"
PIPELINE_SPEC = importlib.util.spec_from_file_location("pipeline_state", PIPELINE_PATH)
PIPELINE = importlib.util.module_from_spec(PIPELINE_SPEC)
assert PIPELINE_SPEC.loader is not None
PIPELINE_SPEC.loader.exec_module(PIPELINE)


FILLED = """# 万妖图录传 目标契约

## 媒介与风格
- 媒介：3D CG
- 3D 子风格：影视级国漫风格化3D
- STYLE-ID：万妖图录传-写实国漫
- 保真取向：电影感
- 成像基底：35mm 发行拷贝

## 技术口径
- 模型展示名：Seedance 2.0 Fast VIP
- 画幅：9:16
- 分辨率：480p
- 视频预算路线：一次性预算

## 交付边界
- 交付到哪一步：仅 Markdown
- 集数范围：EP01-EP12

## 资产策略
- 资产来源：全新生成
- 跨集身份根归属：EP01 首建

## 声音路线
- 音色来源：人工上传
- 音色采样预览例外：否
- BGM：无

## 质量目标
- 对标成片：万妖图录传 EP01
- 验收严格度：十轴审计全过
"""

# 交付 fixture 必须带真正的「### LibTV 完成提示词（整块复制）」代码块：
# 媒介对账的粒度就是逐条提示词（与 validate_delivery_md.py 的 MEDIUM_RE.search 同粒度），
# 散文与 NOT 链不再参与。旧 fixture 只有一行散文，正因如此六轮逐任务审查都没暴露
# 「NOT 三维动画被当成媒介声明」这条硬失败。
DELIVERY = """# EP01｜LibTV 完成提示词

- 模型：Seedance 2.0 Fast VIP
- 画幅：9:16
- 分辨率：480p

## 生成段 V01｜开场

### LibTV 完成提示词（整块复制）

```text
主体标签锁定：角色A。
3D CG 写实国漫质感，中景，画面中主角站在门口。
NOT slow motion+NOT 真人实拍+NOT 定格动画。
```
"""

# 追加一段声明了另一种媒介的正式提示词——反向对账必须抓到。
DRIFTED_SEGMENT = """
## 生成段 V02｜追加

### LibTV 完成提示词（整块复制）

```text
主体标签锁定：角色B。
真人实拍，近景，自然光。
```
"""


class TestParse(unittest.TestCase):
    def test_parses_all_fields(self):
        goal, linenos = MODULE.parse(FILLED)
        self.assertEqual(goal["媒介"], "3D CG")
        self.assertEqual(goal["成像基底"], "35mm 发行拷贝")
        self.assertEqual(goal["BGM"], "无")
        self.assertEqual(len(goal), sum(len(v) for v in MODULE.SECTIONS.values()))
        self.assertEqual(linenos["媒介"], 4)

    def test_template_itself_parses(self):
        goal, _ = MODULE.parse(MODULE.TEMPLATE)
        self.assertEqual(len(goal), sum(len(v) for v in MODULE.SECTIONS.values()))

    def test_missing_section_names_it(self):
        text = FILLED.replace("## 声音路线", "## 声音路线XX")
        with self.assertRaises(MODULE.GoalContractError) as ctx:
            MODULE.parse(text)
        self.assertIn("声音路线", str(ctx.exception))

    def test_missing_field_names_it(self):
        text = FILLED.replace("- 成像基底：35mm 发行拷贝\n", "")
        with self.assertRaises(MODULE.GoalContractError) as ctx:
            MODULE.parse(text)
        self.assertIn("成像基底", str(ctx.exception))


class TestStructureErrors(unittest.TestCase):
    def test_pending_value_reports_line_number(self):
        text = FILLED.replace("- STYLE-ID：万妖图录传-写实国漫", "- STYLE-ID：待定")
        goal, linenos = MODULE.parse(text)
        errors = MODULE.structure_errors(goal, linenos)
        self.assertTrue(any("STYLE-ID" in e and "第 6 行" in e for e in errors))

    def test_leftover_inferred_marker_reports_line_number(self):
        text = FILLED.replace("- 媒介：3D CG", "- 媒介：3D CG [推断]")
        goal, linenos = MODULE.parse(text)
        errors = MODULE.structure_errors(goal, linenos)
        self.assertTrue(any("媒介" in e and "[推断]" in e for e in errors))

    def test_fullwidth_inferred_marker_is_caught(self):
        # 本分支自己的约束就是「全角标点是承重的」：［推断］不能漏过。
        text = FILLED.replace("- 媒介：3D CG", "- 媒介：3D CG ［推断］")
        goal, linenos = MODULE.parse(text)
        errors = MODULE.structure_errors(goal, linenos)
        self.assertTrue(any("媒介" in e and "推断" in e for e in errors))

    def test_clean_contract_has_no_structure_errors(self):
        goal, linenos = MODULE.parse(FILLED)
        self.assertEqual(MODULE.structure_errors(goal, linenos), [])


class TestAvailableChoices(unittest.TestCase):
    def test_model_choices_are_intersection_of_whitelist_and_aliases(self):
        choices = MODULE.available_choices()
        self.assertIn("Seedance 2.0 Fast VIP", choices["模型展示名"])
        # 2.5 在 SUPPORTED_MODELS 里，但 sync 的 MODEL_ALIASES 没有它；
        # 选了会在 sync 阶段才炸，因此不得进入候选集。
        self.assertNotIn("Seedance 2.5", choices["模型展示名"])

    def test_ratio_and_resolution_choices_present(self):
        choices = MODULE.available_choices()
        self.assertIn("9:16", choices["画幅"])
        self.assertIn("480p", choices["分辨率"])


class TestValueErrors(unittest.TestCase):
    def _goal(self, **overrides):
        text = FILLED
        for key, value in overrides.items():
            text = re.sub(rf"^- {re.escape(key)}：.*$", f"- {key}：{value}", text, flags=re.M)
        return MODULE.parse(text)

    def test_clean_contract_has_no_value_errors(self):
        goal, linenos = MODULE.parse(FILLED)
        self.assertEqual(MODULE.value_errors(goal, linenos), [])

    def test_illegal_enum_lists_legal_values(self):
        goal, linenos = self._goal(**{"保真取向": "很电影"})
        errors = MODULE.value_errors(goal, linenos)
        self.assertTrue(any("保真取向" in e and "电影感" in e for e in errors))

    def test_3dcg_requires_substyle(self):
        goal, linenos = self._goal(**{"3D 子风格": "不适用"})
        errors = MODULE.value_errors(goal, linenos)
        self.assertTrue(any("3D 子风格" in e for e in errors))

    def test_non_3dcg_requires_substyle_na(self):
        goal, linenos = self._goal(**{"媒介": "真人实拍"})
        errors = MODULE.value_errors(goal, linenos)
        self.assertTrue(any("3D 子风格" in e and "不适用" in e for e in errors))

    def test_cinematic_requires_substrate(self):
        goal, linenos = self._goal(**{"成像基底": "不适用"})
        errors = MODULE.value_errors(goal, linenos)
        self.assertTrue(any("成像基底" in e for e in errors))

    def test_lowfi_requires_substrate_na(self):
        goal, linenos = self._goal(**{"保真取向": "低保真"})
        errors = MODULE.value_errors(goal, linenos)
        self.assertTrue(any("成像基底" in e and "不适用" in e for e in errors))


class TestCrosscheck(unittest.TestCase):
    def test_consistent_delivery_passes(self):
        goal, _ = MODULE.parse(FILLED)
        self.assertEqual(MODULE.crosscheck(DELIVERY, goal), [])

    def test_forward_missing_anchor_reports(self):
        text = DELIVERY.replace("- 分辨率：480p\n", "")
        goal, _ = MODULE.parse(FILLED)
        errors = MODULE.crosscheck(text, goal)
        self.assertTrue(any("分辨率" in e for e in errors))

    def test_model_mismatch_shows_both_values(self):
        text = DELIVERY.replace("Seedance 2.0 Fast VIP", "Seedance 2.0 VIP")
        goal, _ = MODULE.parse(FILLED)
        errors = MODULE.crosscheck(text, goal)
        self.assertTrue(any("Seedance 2.0 Fast VIP" in e and "Seedance 2.0 VIP" in e
                            for e in errors))

    def test_ratio_mismatch_reports(self):
        text = DELIVERY.replace("- 画幅：9:16", "- 画幅：16:9")
        goal, _ = MODULE.parse(FILLED)
        self.assertTrue(any("画幅" in e for e in MODULE.crosscheck(text, goal)))

    def test_resolution_mismatch_reports(self):
        text = DELIVERY.replace("- 分辨率：480p", "- 分辨率：720p")
        goal, _ = MODULE.parse(FILLED)
        errors = MODULE.crosscheck(text, goal)
        self.assertTrue(any("分辨率" in e and "480p" in e and "720p" in e
                            for e in errors))

    def test_reverse_unauthorized_medium_reports(self):
        # 契约声明 3D CG，交付里某一段冒出「真人实拍」——反向对账必须抓到。
        text = DELIVERY + DRIFTED_SEGMENT
        goal, _ = MODULE.parse(FILLED)
        errors = MODULE.crosscheck(text, goal)
        self.assertTrue(any("真人实拍" in e for e in errors))

    def test_other_medium_still_catches_internal_drift(self):
        # 契约写「其它」时跳过正向落点检查，但反向不能一起放行：
        # 交付里同时出现两个不同的标准媒介词，仍必须报错。
        goal, _ = MODULE.parse(FILLED)
        goal["媒介"] = "其它"
        text = DELIVERY + DRIFTED_SEGMENT
        errors = MODULE.crosscheck(text, goal)
        self.assertTrue(any("其它" in e and "真人实拍" in e for e in errors))

    def test_not_chain_is_not_a_medium_declaration(self):
        # 强制 NOT 链里的「NOT 三维动画」是**排除**声明，不是媒介声明。
        # 全文 findall 会把它归一成 3D CG，让真人实拍的契约在自带模板上必然硬失败。
        goal, _ = MODULE.parse(FILLED)
        goal["媒介"] = "真人实拍"
        text = DELIVERY.replace(
            "3D CG 写实国漫质感，中景，画面中主角站在门口。\n"
            "NOT slow motion+NOT 真人实拍+NOT 定格动画。",
            "真人实拍，中景，画面中主角站在门口。\n"
            "NOT slow motion+NOT 卡通渲染+NOT 三维动画+NOT 换脸。",
        )
        self.assertEqual(MODULE.crosscheck(text, goal), [])

    def test_prose_outside_prompt_blocks_is_not_a_medium_declaration(self):
        goal, _ = MODULE.parse(FILLED)
        text = DELIVERY + "\n> 说明：本片不是真人实拍，参考片是定格动画。\n"
        self.assertEqual(MODULE.crosscheck(text, goal), [])

    def test_resolution_case_is_normalized(self):
        # 契约候选集只给 480p，自带模板与手册都写 480P；大小写敏感比较开箱即炸。
        goal, _ = MODULE.parse(FILLED)
        text = DELIVERY.replace("- 分辨率：480p", "- 分辨率：480P")
        self.assertEqual(MODULE.crosscheck(text, goal), [])

    def test_resolution_mismatch_still_reported_after_normalization(self):
        goal, _ = MODULE.parse(FILLED)
        text = DELIVERY.replace("- 分辨率：480p", "- 分辨率：720P")
        self.assertTrue(any("分辨率" in e for e in MODULE.crosscheck(text, goal)))
    def test_other_medium_consistent_delivery_passes(self):
        goal, _ = MODULE.parse(FILLED)
        goal["媒介"] = "其它"
        self.assertEqual(MODULE.crosscheck(DELIVERY, goal), [])

    def test_medium_synonym_accepted(self):
        text = DELIVERY.replace("3D CG 写实国漫质感", "三维动画 写实国漫质感")
        goal, _ = MODULE.parse(FILLED)
        self.assertEqual(MODULE.crosscheck(text, goal), [])

    def test_record_only_and_quality_fields_not_crosschecked(self):
        goal, _ = MODULE.parse(FILLED)
        goal["集数范围"] = "EP01-EP99"
        goal["对标成片"] = "完全不同的片子"
        goal["BGM"] = "有"
        self.assertEqual(MODULE.crosscheck(DELIVERY, goal), [])


TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "assets" / "libtv-video-prompts.template.md"
)

# 与自带交付模板逐字匹配的母契约：媒介 真人实拍、模型/画幅/分辨率取模板头部四行。
TEMPLATE_CONTRACT = re.sub(
    r"^- 3D 子风格：.*$", "- 3D 子风格：不适用",
    re.sub(r"^- 媒介：.*$", "- 媒介：真人实拍", FILLED, flags=re.M),
    flags=re.M,
)


class TestCrosscheckAgainstShippedTemplate(unittest.TestCase):
    """拿 skill 自带的真实产物跑对账。

    C2 的两个成因（NOT 链误伤、分辨率大小写）之所以躲过六轮逐任务审查，
    正是因为分支里没有任何测试拿 crosscheck 跑过真实产物，只跑过六行玩具 fixture。
    """

    def setUp(self):
        self.template = TEMPLATE_PATH.read_text(encoding="utf-8")
        self.goal, self.linenos = MODULE.parse(TEMPLATE_CONTRACT)

    def test_contract_itself_is_legal(self):
        self.assertEqual(MODULE.structure_errors(self.goal, self.linenos), [])
        self.assertEqual(MODULE.value_errors(self.goal, self.linenos), [])

    def test_shipped_template_passes_crosscheck(self):
        self.assertEqual(MODULE.crosscheck(self.template, self.goal), [])

    def test_shipped_template_still_catches_model_drift(self):
        goal = dict(self.goal, 模型展示名="Seedance 2.0 VIP")
        self.assertTrue(any("模型展示名" in e for e in MODULE.crosscheck(self.template, goal)))

    def test_shipped_template_still_catches_medium_drift(self):
        goal = dict(self.goal, 媒介="2D 动漫")
        errors = MODULE.crosscheck(self.template, goal)
        self.assertTrue(any("媒介" in e and "真人实拍" in e for e in errors))


class TestReconcile(unittest.TestCase):
    """reconcile()：不完整的 goal 不能被当作没问题（控制者裁决 Ruling-I）。"""

    def test_empty_goal_is_a_hard_error(self):
        errors = MODULE.reconcile(DELIVERY, {})
        self.assertTrue(errors)
        self.assertTrue(any("字段不全" in e or "未落盘" in e for e in errors))

    def test_field_short_goal_is_a_hard_error(self):
        goal, _ = MODULE.parse(FILLED)
        goal.pop("成像基底")
        errors = MODULE.reconcile(DELIVERY, goal)
        self.assertTrue(any("成像基底" in e for e in errors))

    def test_blank_valued_goal_is_a_hard_error(self):
        goal, _ = MODULE.parse(FILLED)
        goal["模型展示名"] = ""
        self.assertTrue(any("模型展示名" in e for e in MODULE.reconcile(DELIVERY, goal)))

    def test_complete_goal_delegates_to_crosscheck(self):
        goal, _ = MODULE.parse(FILLED)
        self.assertEqual(MODULE.reconcile(DELIVERY, goal), [])


class TestTemplateCli(unittest.TestCase):
    """SKILL.md 的第 0 步要能一条命令产出可解析的空白母契约（I2）。"""

    def test_template_flag_prints_parsable_template(self):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--template"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        goal, _ = MODULE.parse(result.stdout)
        self.assertEqual(len(goal), len(MODULE.ALL_FIELDS))

    def test_choices_flag_lists_available_values(self):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--choices"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("模型展示名", result.stdout)
        self.assertIn("480p", result.stdout)

    def test_skill_md_documents_the_template_entry(self):
        skill = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("goal_contract.py --template", skill)
        for field in MODULE.ALL_FIELDS:
            self.assertIn(field, skill, f"SKILL.md 未列出承重字段名：{field}")


class TestDiff(unittest.TestCase):
    def test_reports_changed_fields_only(self):
        old, _ = MODULE.parse(FILLED)
        new = dict(old)
        new["媒介"] = "真人实拍"
        self.assertEqual(MODULE.diff(old, new), ["媒介：3D CG → 真人实拍"])

    def test_no_change_yields_empty(self):
        old, _ = MODULE.parse(FILLED)
        self.assertEqual(MODULE.diff(old, dict(old)), [])


class TestPipelineIntake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.delivery_dir = self.root / "交付"
        self.delivery_dir.mkdir()
        (self.root / "目标契约.md").write_text(FILLED, encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)

    def test_intake_is_first_step(self):
        self.assertEqual(PIPELINE.STEP_IDS[0], "intake")
        script_units = next(s for s in PIPELINE.STEPS if s["id"] == "script_units")
        self.assertEqual(script_units["requires"], ["intake"])

    def test_goal_sensitive_excludes_intake(self):
        self.assertNotIn("intake", PIPELINE.GOAL_SENSITIVE)
        self.assertIn("segments", PIPELINE.GOAL_SENSITIVE)

    def test_goal_contract_module_in_contract_hash(self):
        before = PIPELINE.validation_contract_hash()
        target = PIPELINE.SCRIPT_DIR / "goal_contract.py"
        original = target.read_bytes()
        try:
            target.write_bytes(original + b"\n# hash probe\n")
            self.assertNotEqual(before, PIPELINE.validation_contract_hash())
        finally:
            target.write_bytes(original)

    def test_finds_contract_by_walking_up(self):
        found = PIPELINE.find_goal_contract(self.delivery_dir, None)
        # .resolve() on both sides: macOS's TemporaryDirectory path lives under
        # /var/..., a symlink to /private/var/...; find_goal_contract() resolves
        # the directory internally, so comparing against the raw self.root would
        # fail on macOS for reasons unrelated to the function's correctness.
        self.assertEqual(found, (self.root / "目标契约.md").resolve())

    def test_missing_contract_lists_searched_paths(self):
        # 必须用**独立**的临时目录：self.root 下放着 目标契约.md，
        # 从 self.root 的子目录向上找 3 层会命中它，用例就白跑了。
        with tempfile.TemporaryDirectory() as other:
            deep = Path(other) / "空" / "深"
            deep.mkdir(parents=True)
            ok, detail = PIPELINE.check_step(
                "intake", "EP01", deep, None, None,
                manual_confirmed=True, goal_path=None,
            )
        self.assertFalse(ok)
        self.assertIn("搜索过", detail)

    def test_intake_requires_manual_confirmed(self):
        ok, detail = PIPELINE.check_step(
            "intake", "EP01", self.delivery_dir, None, None,
            manual_confirmed=False, goal_path=None,
        )
        self.assertFalse(ok)
        self.assertIn("--manual-confirmed", detail)

    def test_intake_passes_with_confirmed_and_clean_contract(self):
        ok, detail = PIPELINE.check_step(
            "intake", "EP01", self.delivery_dir, None, None,
            manual_confirmed=True, goal_path=None,
        )
        self.assertTrue(ok, detail)

    def test_intake_rejects_pending_field(self):
        (self.root / "目标契约.md").write_text(
            FILLED.replace("- STYLE-ID：万妖图录传-写实国漫", "- STYLE-ID：待定"),
            encoding="utf-8",
        )
        ok, detail = PIPELINE.check_step(
            "intake", "EP01", self.delivery_dir, None, None,
            manual_confirmed=True, goal_path=None,
        )
        self.assertFalse(ok)
        self.assertIn("STYLE-ID", detail)

    def test_script_units_blocked_until_intake_done(self):
        state = {"episode": "EP01", "steps": {}, "deliveryHash": "",
                 "contractHash": "", "goalHash": "", "goal": {}}
        self.assertEqual(
            PIPELINE.blocking_prerequisites("script_units", state), ["intake"]
        )
        state["steps"]["intake"] = "done"
        self.assertEqual(PIPELINE.blocking_prerequisites("script_units", state), [])

    def test_goal_change_invalidates_downstream_and_reports_diff(self):
        state = {
            "episode": "EP01",
            "steps": {"intake": "done", "script_units": "done", "segments": "done"},
            "deliveryHash": "",
            "contractHash": PIPELINE.validation_contract_hash(),
            "goalHash": "stale-hash",
            "goal": {"媒介": "3D CG"},
        }
        dropped, goal_diff, _ = PIPELINE.invalidate_stale(
            state, "EP01", self.delivery_dir, self.root / "目标契约.md",
        )
        self.assertIn("segments", dropped)
        self.assertIn("script_units", dropped)
        # 控制者裁决 Ruling-I：goalHash 由非空变为不同值时，intake 重置为 pending。
        # 「intake 不进 GOAL_SENSITIVE」说的是它不因契约变更被**连坐**作废，
        # 不是说改了契约还算「用户确认过」——它所担保的东西已经换了。
        self.assertEqual(state["steps"]["intake"], "pending")
        self.assertNotIn("intake", PIPELINE.GOAL_SENSITIVE)
        # 媒介 前后同值，不应出现在 diff 里；其余字段旧 goal 没有，出现属正常。
        self.assertFalse(any(line.startswith("媒介：") for line in goal_diff))

    def test_first_time_goal_record_does_not_reset_intake(self):
        # goalHash 由**空**变为有值＝第一次落盘，不是改写，不能反过来打掉刚过的闸。
        state = {
            "episode": "EP01",
            "steps": {"intake": "done"},
            "deliveryHash": "",
            "contractHash": PIPELINE.validation_contract_hash(),
            "goalHash": "",
            "goal": {},
        }
        PIPELINE.invalidate_stale(
            state, "EP01", self.delivery_dir, self.root / "目标契约.md",
        )
        self.assertEqual(state["steps"]["intake"], "done")

    def test_broken_contract_does_not_leave_intake_done(self):
        # 覆盖契约后写成不可解析的内容：goal 会被清空，此时 intake 绝不能仍是 done。
        state = {
            "episode": "EP01",
            "steps": {step: "done" for step in PIPELINE.STEP_IDS},
            "deliveryHash": "",
            "contractHash": PIPELINE.validation_contract_hash(),
            "goalHash": PIPELINE.file_hash(self.root / "目标契约.md"),
            "goal": MODULE.parse(FILLED)[0],
        }
        (self.root / "目标契约.md").write_text("彻底改坏了", encoding="utf-8")
        PIPELINE.invalidate_stale(
            state, "EP01", self.delivery_dir, self.root / "目标契约.md",
        )
        self.assertEqual(state["steps"]["intake"], "pending")
        self.assertEqual(state["goal"], {})

    def test_invalidation_reason_names_the_real_trigger(self):
        # M1：纯由 goalHash 触发的作废不能套「交付 Markdown 已变更」那句话。
        state = {
            "episode": "EP01",
            "steps": {step: "done" for step in PIPELINE.STEP_IDS},
            "deliveryHash": "",
            "contractHash": PIPELINE.validation_contract_hash(),
            "goalHash": "stale-hash",
            "goal": {},
        }
        _, _, reasons = PIPELINE.invalidate_stale(
            state, "EP01", self.delivery_dir, self.root / "目标契约.md",
        )
        self.assertIn("目标契约已变更", reasons)
        self.assertNotIn("交付 Markdown 已变更", reasons)

    def test_explicit_missing_goal_path_is_a_hard_error(self):
        # I1：显式 --goal 指向不存在的文件必须硬错，绝不回退到环境搜索——
        # 否则闸报「找不到」，state 里却记下了环境里另一份契约的哈希与 18 个字段。
        with self.assertRaises(OSError) as ctx:
            PIPELINE.find_goal_contract(
                self.delivery_dir, self.delivery_dir / "并不存在的契约.md"
            )
        self.assertIn("并不存在的契约.md", str(ctx.exception))

    def test_goal_diff_reports_changed_field(self):
        state = {
            "episode": "EP01",
            "steps": {"intake": "done", "segments": "done"},
            "deliveryHash": "",
            "contractHash": PIPELINE.validation_contract_hash(),
            "goalHash": "stale-hash",
            "goal": dict(MODULE.parse(FILLED)[0], 媒介="真人实拍"),
        }
        _, goal_diff, _ = PIPELINE.invalidate_stale(
            state, "EP01", self.delivery_dir, self.root / "目标契约.md",
        )
        self.assertIn("媒介：真人实拍 → 3D CG", goal_diff)


VALIDATOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_delivery_md.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location("validate_delivery_md", VALIDATOR_PATH)
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
assert VALIDATOR_SPEC.loader is not None
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)


class TestValidatorCrosscheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.md = self.dir / "EP01-LibTV视频节点提示词.md"
        self.md.write_text(DELIVERY, encoding="utf-8")
        goal, _ = MODULE.parse(FILLED)
        self.state = {
            "episode": "EP01",
            "steps": {s: "done" for s in ("intake", "script_units", "entities",
                                          "assets", "segments", "keyframe", "coverage")},
            "deliveryHash": "",
            "contractHash": "",
            "goalHash": "h",
            "goal": goal,
        }

    def _write_state(self):
        (self.dir / "EP01-run_state.json").write_text(
            json.dumps(self.state, ensure_ascii=False), encoding="utf-8"
        )

    def test_consistent_delivery_adds_no_goal_errors(self):
        self._write_state()
        errors, _ = VALIDATOR.check_pipeline_state(self.md)
        self.assertEqual([e for e in errors if "对账" in e], [])

    def test_model_drift_reported(self):
        self.state["goal"]["模型展示名"] = "Seedance 2.0 VIP"
        self._write_state()
        errors, _ = VALIDATOR.check_pipeline_state(self.md)
        self.assertTrue(any("对账" in e and "模型展示名" in e for e in errors))

    def test_intake_is_a_required_prerequisite(self):
        # 不跑 intake 就不该通过 validate:否则 goal 为空、对账被跳过,整套闸形同虚设。
        self.state["steps"].pop("intake")
        self._write_state()
        errors, _ = VALIDATOR.check_pipeline_state(self.md)
        self.assertTrue(any("intake" in e for e in errors))

    def test_missing_goal_block_is_not_fatal(self):
        # 尚未跑过 intake 的旧状态文件不应让校验器崩溃。
        self.state.pop("goal")
        self._write_state()
        errors, _ = VALIDATOR.check_pipeline_state(self.md)
        self.assertTrue(all("Traceback" not in e for e in errors))

    def test_empty_goal_is_a_hard_error_not_a_skip(self):
        # Ruling-I：契约被清空后不能「无需对账」——那等于把漂移的模型直接放行。
        self.state["goal"] = {}
        self._write_state()
        errors, _ = VALIDATOR.check_pipeline_state(self.md)
        self.assertTrue(any("契约" in e for e in errors), errors)

    def test_field_short_goal_is_a_hard_error_not_a_warning(self):
        # 旧实现在 crosscheck 中途抛 KeyError，把已收集的错误一并丢弃，只留一条 warning。
        self.state["goal"].pop("画幅")
        self._write_state()
        errors, warnings = VALIDATOR.check_pipeline_state(self.md)
        self.assertTrue(any("画幅" in e for e in errors), (errors, warnings))

    def test_keyframe_is_a_required_prerequisite(self):
        # M2：这个元组存在的意义正是拦手工篡改的状态文件。
        self.state["steps"].pop("keyframe")
        self._write_state()
        errors, _ = VALIDATOR.check_pipeline_state(self.md)
        self.assertTrue(any("keyframe" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
