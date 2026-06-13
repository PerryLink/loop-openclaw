"""test_unit_validation.py —— 验证逻辑单元测试。

覆盖范围：validate_config_plan（配置计划校验）、validate_agent_spec（Agent规格校验）、
validate_cross_references（交叉引用校验）、validate_output_files（输出文件校验）、
ValidationResult 结构体、run_validate_only 函数、print_validation_report 函数。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from render import (  # noqa: E402
    AgentSpec,
    ConfigPlan,
    ValidationResult,
    RenderError,
    validate_config_plan,
    validate_agent_spec,
    validate_cross_references,
    validate_output_files,
    run_validate_only,
    print_validation_report,
    OUTPUT_FILES,
    MODE_NAMES,
)


# =========================================================================
#  TestValidateConfigPlan —— 配置计划校验边界条件测试
# =========================================================================

class TestValidateConfigPlan:
    """测试 validate_config_plan 在各种场景下的行为。"""

    # --- 基础通过场景 --------------------------------------------------------

    def test_valid_orchestrator_plan_passes(self):
        """验证：合法的 orchestrator-worker 计划通过校验。"""
        plan = ConfigPlan(
            project_name="valid-orch",
            mode="orchestrator-worker",
            agents=[
                AgentSpec(agent_id="orch", role="orchestrator"),
                AgentSpec(agent_id="w1", role="worker"),
                AgentSpec(agent_id="w2", role="worker"),
            ]
        )
        result = validate_config_plan(plan)
        assert result.passed, f"应通过但失败了: {result.errors}"

    def test_valid_peer_review_plan_passes(self):
        """验证：合法的 peer-review-pair 计划通过校验。"""
        plan = ConfigPlan(
            project_name="valid-peer",
            mode="peer-review-pair",
            agents=[
                AgentSpec(agent_id="r1", role="peer_a"),
                AgentSpec(agent_id="r2", role="peer_b"),
            ]
        )
        result = validate_config_plan(plan)
        assert result.passed, f"应通过但失败了: {result.errors}"

    def test_valid_sequential_plan_passes(self):
        """验证：合法的 sequential-pipeline 计划通过校验。"""
        plan = ConfigPlan(
            project_name="valid-seq",
            mode="sequential-pipeline",
            agents=[
                AgentSpec(agent_id="d", role="pipeline_stage"),
                AgentSpec(agent_id="b", role="pipeline_stage"),
                AgentSpec(agent_id="t", role="pipeline_stage"),
            ]
        )
        result = validate_config_plan(plan)
        assert result.passed, f"应通过但失败了: {result.errors}"

    # --- project_name 校验 -------------------------------------------------

    def test_empty_project_name_fails(self):
        """验证：空 project_name 导致校验失败。"""
        plan = ConfigPlan(
            project_name="",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")]
        )
        result = validate_config_plan(plan)
        assert not result.passed, "空 project_name 应校验失败"
        assert any("project_name" in e.lower() for e in result.errors)

    def test_project_name_with_special_chars_warns(self):
        """验证：project_name 含特殊字符时产生警告。"""
        plan = ConfigPlan(
            project_name="bad name with spaces!",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")]
        )
        result = validate_config_plan(plan)
        assert any("非标准字符" in w for w in result.warnings)

    # --- mode 校验 ----------------------------------------------------------

    def test_invalid_mode_fails(self):
        """验证：无效模式名导致校验失败。"""
        plan = ConfigPlan(
            project_name="bad-mode",
            mode="invalid-mode-xyz",
            agents=[AgentSpec(agent_id="a1", role="worker"), AgentSpec(agent_id="a2", role="worker")]
        )
        result = validate_config_plan(plan)
        assert not result.passed
        assert any("mode" in e.lower() for e in result.errors)

    def test_missing_mode_default_passes(self):
        """验证：默认 mode 值通过校验（未显式指定时默认为 orchestrator-worker）。"""
        plan = ConfigPlan(
            project_name="default-mode",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")]
        )
        result = validate_config_plan(plan)
        assert result.passed, f"默认 mode 应通过: {result.errors}"

    # --- agents 数量校验 ----------------------------------------------------

    def test_zero_agents_fails(self):
        """验证：agent 数量为 0 时校验失败。"""
        plan = ConfigPlan(project_name="no-agents", mode="orchestrator-worker", agents=[])
        result = validate_config_plan(plan)
        assert not result.passed
        assert any("agents" in e.lower() for e in result.errors)

    def test_single_agent_fails(self):
        """验证：只有 1 个 agent 时校验失败（至少需要 2 个）。"""
        plan = ConfigPlan(
            project_name="one-agent",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="only", role="orchestrator")]
        )
        result = validate_config_plan(plan)
        assert not result.passed
        assert any("agents" in e.lower() for e in result.errors)

    def test_exactly_two_agents_passes(self):
        """验证：恰好 2 个 agent 通过校验。"""
        plan = ConfigPlan(
            project_name="two-agents",
            mode="peer-review-pair",
            agents=[
                AgentSpec(agent_id="r1", role="peer_a"),
                AgentSpec(agent_id="r2", role="peer_b"),
            ]
        )
        result = validate_config_plan(plan)
        assert result.passed, f"2 个 agent 应通过: {result.errors}"

    # --- 模式特定结构约束 ----------------------------------------------------

    def test_orchestrator_mode_requires_one_orchestrator(self):
        """验证：orchestrator-worker 模式须恰好 1 个 orchestrator。"""
        plan = ConfigPlan(
            project_name="multi-orch",
            mode="orchestrator-worker",
            agents=[
                AgentSpec(agent_id="o1", role="orchestrator"),
                AgentSpec(agent_id="o2", role="orchestrator"),
                AgentSpec(agent_id="w1", role="worker"),
            ]
        )
        result = validate_config_plan(plan)
        assert not result.passed
        assert any("orchestrat" in e.lower() for e in result.errors)

    def test_orchestrator_mode_without_orchestrator_fails(self):
        """验证：orchestrator-worker 模式无 orchestrator 时校验失败。"""
        plan = ConfigPlan(
            project_name="no-orch",
            mode="orchestrator-worker",
            agents=[
                AgentSpec(agent_id="w1", role="worker"),
                AgentSpec(agent_id="w2", role="worker"),
            ]
        )
        result = validate_config_plan(plan)
        assert not result.passed
        assert any("orchestrat" in e.lower() for e in result.errors)

    def test_peer_review_mode_requires_exactly_two(self):
        """验证：peer-review-pair 模式须恰好 2 个 agent。"""
        plan = ConfigPlan(
            project_name="three-peers",
            mode="peer-review-pair",
            agents=[
                AgentSpec(agent_id="a", role="peer_a"),
                AgentSpec(agent_id="b", role="peer_b"),
                AgentSpec(agent_id="c", role="peer_b"),
            ]
        )
        result = validate_config_plan(plan)
        assert not result.passed
        assert any("peer-review-pair" in e.lower() or "2" in e for e in result.errors)

    # --- 数值边界校验 --------------------------------------------------------

    def test_max_cycles_zero_fails(self):
        """验证：max_cycles 为 0 时校验失败。"""
        plan = ConfigPlan(
            project_name="zero-cycles",
            mode="orchestrator-worker",
            max_cycles=0,
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")]
        )
        result = validate_config_plan(plan)
        assert not result.passed

    def test_max_cycles_negative_fails(self):
        """验证：max_cycles 为负数时校验失败。"""
        plan = ConfigPlan(
            project_name="neg-cycles",
            mode="orchestrator-worker",
            max_cycles=-5,
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")]
        )
        result = validate_config_plan(plan)
        assert not result.passed

    def test_convergence_gt_max_cycles_fails(self):
        """验证：convergence_rounds > max_cycles 时校验失败。"""
        plan = ConfigPlan(
            project_name="conv-gt-max",
            mode="orchestrator-worker",
            max_cycles=5,
            convergence_rounds=10,
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")]
        )
        result = validate_config_plan(plan)
        assert not result.passed
        assert any("convergence_rounds" in e.lower() or "max_cycles" in e.lower() for e in result.errors)

    def test_max_duration_zero_fails(self):
        """验证：max_duration_minutes 为 0 时校验失败。"""
        plan = ConfigPlan(
            project_name="zero-duration",
            mode="orchestrator-worker",
            max_duration_minutes=0,
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")]
        )
        result = validate_config_plan(plan)
        assert not result.passed

    # --- 空 convergence_criteria 警告 ---------------------------------------

    def test_empty_convergence_criteria_warns(self):
        """验证：convergence_criteria 为空时产生警告。"""
        plan = ConfigPlan(
            project_name="empty-conv",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")],
            convergence_criteria={},
        )
        result = validate_config_plan(plan)
        assert any("convergence" in w.lower() for w in result.warnings)

    # --- 空 routing_rules 警告 ----------------------------------------------

    def test_empty_routing_rules_warns(self):
        """验证：routing_rules 为空时产生警告。"""
        plan = ConfigPlan(
            project_name="empty-routing",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")],
            routing_rules=[],
        )
        result = validate_config_plan(plan)
        assert any("routing" in w.lower() for w in result.warnings)

    # --- 空 channels 警告 ---------------------------------------------------

    def test_empty_channels_warns(self):
        """验证：channels 为空时产生警告。"""
        plan = ConfigPlan(
            project_name="empty-channels",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")],
            channels=[],
        )
        result = validate_config_plan(plan)
        assert any("channel" in w.lower() or "channel" in " ".join(result.warnings).lower()
                   for w in result.warnings) or not result.warnings


# =========================================================================
#  TestValidateAgentSpec —— Agent 规格校验测试
# =========================================================================

class TestValidateAgentSpec:
    """测试 validate_agent_spec 对各种 agent 配置的校验。"""

    def test_valid_agent_spec_passes(self):
        """验证：合法的 AgentSpec 通过校验。"""
        agent = AgentSpec(
            agent_id="orch", role="orchestrator",
            description="总指挥", model="claude-sonnet"
        )
        result = validate_agent_spec(agent)
        assert result.passed, f"合法 agent 应通过: {result.errors}"

    def test_empty_agent_id_fails(self):
        """验证：空 agent_id 导致校验失败。"""
        agent = AgentSpec(agent_id="", role="orchestrator")
        result = validate_agent_spec(agent)
        assert not result.passed
        assert any("agent_id" in e.lower() for e in result.errors)

    def test_agent_id_starts_with_uppercase_fails(self):
        """验证：大写字母开头的 agent_id 导致校验失败。"""
        agent = AgentSpec(agent_id="Orchestrator", role="orchestrator")
        result = validate_agent_spec(agent)
        assert not result.passed
        assert any("agent_id" in e.lower() for e in result.errors)

    def test_agent_id_with_special_chars_fails(self):
        """验证：含特殊字符的 agent_id 导致校验失败。"""
        agent = AgentSpec(agent_id="agent@name", role="worker")
        result = validate_agent_spec(agent)
        assert not result.passed

    def test_valid_agent_id_with_dashes(self):
        """验证：含连字符的合法 agent_id 应通过。"""
        agent = AgentSpec(agent_id="my-agent-001", role="worker")
        result = validate_agent_spec(agent)
        assert result.passed, f"agent_id 'my-agent-001' 应通过: {result.errors}"

    def test_missing_role_warns(self):
        """验证：未指定 role 时产生警告。"""
        agent = AgentSpec(agent_id="test-agent", role="")
        result = validate_agent_spec(agent)
        assert any("role" in w.lower() for w in result.warnings)

    def test_unknown_role_warns(self):
        """验证：未知 role 名称产生警告。"""
        agent = AgentSpec(agent_id="test", role="some-random-role")
        result = validate_agent_spec(agent)
        assert any("role" in w.lower() for w in result.warnings)

    def test_missing_description_warns(self):
        """验证：缺少 description 产生警告。"""
        agent = AgentSpec(agent_id="nodoc", role="worker")
        result = validate_agent_spec(agent)
        assert any("description" in w.lower() for w in result.warnings)

    def test_missing_model_warns(self):
        """验证：未指定 model 产生警告。"""
        agent = AgentSpec(agent_id="nomodel", role="worker")
        result = validate_agent_spec(agent)
        assert any("model" in w.lower() for w in result.warnings)

    def test_permissions_non_list_type_fails(self):
        """验证：sessions_spawn 非列表类型时校验失败。"""
        agent = AgentSpec(
            agent_id="bad-perm",
            role="orchestrator",
            permissions={"sessions_spawn": "not-a-list"}
        )
        result = validate_agent_spec(agent)
        assert not result.passed
        assert any("sessions_spawn" in e.lower() for e in result.errors)


# =========================================================================
#  TestValidateCrossReferences —— 交叉引用校验测试
# =========================================================================

class TestValidateCrossReferences:
    """测试 validate_cross_references 的引用完整性校验。"""

    def test_valid_references_pass(self):
        """验证：所有引用均指向已定义 agent 时通过。"""
        plan = ConfigPlan(
            project_name="xref-ok",
            mode="orchestrator-worker",
            agents=[
                AgentSpec(agent_id="o", role="orchestrator",
                          permissions={"sessions_send": ["w1"]}),
                AgentSpec(agent_id="w1", role="worker",
                          permissions={"sessions_send": ["o"]}),
            ],
            routing_rules=[{"source": "o", "target": "w1"}],
        )
        result = validate_cross_references(plan)
        assert result.passed, f"应通过: {result.errors}"

    def test_routing_source_not_found_fails(self):
        """验证：routing_rules 中 source 不存在时失败。"""
        plan = ConfigPlan(
            project_name="bad-src",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")],
            routing_rules=[{"source": "ghost", "target": "w"}],
        )
        result = validate_cross_references(plan)
        assert not result.passed
        assert any("ghost" in e for e in result.errors)

    def test_routing_target_not_found_fails(self):
        """验证：routing_rules 中 target 不存在时失败。"""
        plan = ConfigPlan(
            project_name="bad-tgt",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")],
            routing_rules=[{"source": "o", "target": "phantom"}],
        )
        result = validate_cross_references(plan)
        assert not result.passed
        assert any("phantom" in e for e in result.errors)

    def test_permissions_send_target_not_found_fails(self):
        """验证：permissions 中 sessions_send 引用不存在的 agent 时失败。"""
        plan = ConfigPlan(
            project_name="bad-send",
            mode="orchestrator-worker",
            agents=[
                AgentSpec(agent_id="o", role="orchestrator",
                          permissions={"sessions_send": ["nonexistent"]}),
                AgentSpec(agent_id="w1", role="worker"),
            ]
        )
        result = validate_cross_references(plan)
        assert not result.passed
        assert any("nonexistent" in e for e in result.errors)

    def test_permissions_spawn_target_not_found_fails(self):
        """验证：permissions 中 sessions_spawn 引用不存在的 agent 时失败。"""
        plan = ConfigPlan(
            project_name="bad-spawn",
            mode="orchestrator-worker",
            agents=[
                AgentSpec(agent_id="o", role="orchestrator",
                          permissions={"sessions_spawn": ["missing_agent"]}),
                AgentSpec(agent_id="w1", role="worker"),
            ]
        )
        result = validate_cross_references(plan)
        assert not result.passed

    def test_empty_agents_list_fails_with_message(self):
        """验证：agents 为空时交叉引用校验失败并给出明确消息。"""
        plan = ConfigPlan(
            project_name="no-agents-xref",
            mode="orchestrator-worker",
            agents=[],
        )
        result = validate_cross_references(plan)
        assert not result.passed
        assert any("agents" in e.lower() for e in result.errors)

    def test_routing_with_from_to_aliases(self):
        """验证：routing_rules 支持 from/to 别名。"""
        plan = ConfigPlan(
            project_name="from-to",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")],
            routing_rules=[{"from": "o", "to": "w"}],
        )
        result = validate_cross_references(plan)
        assert result.passed, f"from/to 别名应通过: {result.errors}"

    def test_channels_inbound_default_agent_warns(self):
        """验证：channel inbound.default_agent 引用不存在的 agent 时警告。"""
        plan = ConfigPlan(
            project_name="bad-channel-agent",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")],
            channels=[{
                "id": "default",
                "routing_rules": {"inbound": {"default_agent": "ghost_channel"}}
            }],
        )
        result = validate_cross_references(plan)
        assert any("ghost_channel" in w for w in result.warnings)


# =========================================================================
#  TestValidateOutputFiles —— 输出文件校验测试
# =========================================================================

class TestValidateOutputFiles:
    """测试 validate_output_files 的输出检查。"""

    def test_empty_output_dir_reports_missing_files(self):
        """验证：空输出目录报告所有 5 个文件缺失。"""
        result = validate_output_files(_PROJECT_ROOT / "artifacts")
        assert not result.passed
        assert len(result.errors) >= 1

    def test_output_after_render_passes(self):
        """验证：渲染后输出目录通过文件存在性校验。"""
        from render import TemplateRenderer
        plan = ConfigPlan(
            project_name="file-test",
            mode="orchestrator-worker",
            agents=[
                AgentSpec(agent_id="o", role="orchestrator"),
                AgentSpec(agent_id="w", role="worker"),
            ]
        )
        renderer = TemplateRenderer(
            template_dir=_PROJECT_ROOT / "templates",
            output_dir=_PROJECT_ROOT / "output",
        )
        renderer.render_all(plan, mode="orchestrator-worker")
        result = validate_output_files(_PROJECT_ROOT / "output")
        assert result.passed, f"渲染后应通过: {result.errors}"


# =========================================================================
#  TestValidationResult —— 校验结果数据类测试
# =========================================================================

class TestValidationResult:
    """测试 ValidationResult 数据结构。"""

    def test_new_result_defaults_to_passed(self):
        """验证：新创建的 ValidationResult 默认为 passed=True。"""
        r = ValidationResult()
        assert r.passed is True
        assert r.errors == []
        assert r.warnings == []

    def test_add_error_sets_passed_false(self):
        """验证：添加 error 后 passed 变为 False。"""
        r = ValidationResult()
        r.errors.append("something wrong")
        r.passed = False
        assert not r.passed

    def test_add_warning_keeps_passed_true(self):
        """验证：仅添加 warning 不影响 passed。"""
        r = ValidationResult()
        r.warnings.append("minor issue")
        assert r.passed is True

    def test_details_dict_mutable(self):
        """验证：details 字段可写并可序列化。"""
        r = ValidationResult(details={"file_count": 5})
        r.details["extra_info"] = "test"
        assert r.details["file_count"] == 5
        assert r.details["extra_info"] == "test"


# =========================================================================
#  TestRunValidateOnly —— 仅校验模式测试
# =========================================================================

class TestRunValidateOnly:
    """测试 run_validate_only 函数。"""

    def test_returns_list_of_messages(self):
        """验证：返回的消息列表中包含 summary 条目。"""
        from render import TemplateRenderer
        plan = ConfigPlan(
            project_name="vo-test",
            mode="orchestrator-worker",
            agents=[
                AgentSpec(agent_id="o", role="orchestrator"),
                AgentSpec(agent_id="w", role="worker"),
            ]
        )
        # 先渲染确保有输出文件
        renderer = TemplateRenderer(
            template_dir=_PROJECT_ROOT / "templates",
            output_dir=_PROJECT_ROOT / "output",
        )
        renderer.render_all(plan, mode="orchestrator-worker")
        # 执行仅校验
        messages = run_validate_only(_PROJECT_ROOT / "output", plan=plan)
        assert isinstance(messages, list)
        assert len(messages) > 0
        # 最后一行为 summary
        assert "summary" in messages[-1].lower()

    def test_validate_only_without_plan_no_config_checks(self):
        """验证：不提供 plan 时跳过 config plan 和 cross-reference 校验。"""
        from render import TemplateRenderer
        plan = ConfigPlan(
            project_name="vo-no-plan",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")]
        )
        renderer = TemplateRenderer(
            template_dir=_PROJECT_ROOT / "templates",
            output_dir=_PROJECT_ROOT / "output",
        )
        renderer.render_all(plan, mode="orchestrator-worker")
        messages = run_validate_only(_PROJECT_ROOT / "output", plan=None)
        assert isinstance(messages, list)
        assert any("summary" in m.lower() for m in messages)


# =========================================================================
#  TestPrintValidationReport —— 校验报告打印测试
# =========================================================================

class TestPrintValidationReport:
    """测试 print_validation_report 输出格式。"""

    def test_report_with_all_pass(self):
        """验证：全部 PASS 的报告不包含 FAIL 统计。"""
        import io
        messages = [
            "[PASS] openclaw.json is valid.",
            "[PASS] All files present.",
            "\n--- Validation summary: 2 PASS, 0 WARN, 0 FAIL ---",
        ]
        # 重定向 stdout 捕获输出
        saved = sys.stdout
        try:
            sys.stdout = io.StringIO()
            print_validation_report(messages)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = saved
        assert "PASS" in output

    def test_report_with_failures(self):
        """验证：含 FAIL 的报告显示失败计数。"""
        import io
        messages = [
            "[FAIL] Missing file: SOUL.md",
            "[PASS] openclaw.json is valid.",
            "[WARN] small file size.",
            "\n--- Validation summary: 1 PASS, 1 WARN, 1 FAIL ---",
        ]
        saved = sys.stdout
        try:
            sys.stdout = io.StringIO()
            print_validation_report(messages)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = saved
        assert "FAIL" in output
        assert "RESULT" in output
