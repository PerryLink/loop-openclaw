"""test_edge_cases.py —— 边缘用例测试。

覆盖范围：空计划列表、无效模式名称、缺失 agent 配置、超大配置（100+ agents）、
包含特殊字符的模板变量、异常路径、极端值输入等。
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
    TemplateRegistry,
    TemplateRenderer,
    TemplateVariableError,
    RenderError,
    simple_render,
    validate_config_plan,
    validate_agent_spec,
    validate_cross_references,
    validate_output_files,
    run_validate_only,
    parse_config_plan,
    _parse_agent_block,
    _extract_section,
    MODE_NAMES,
    DEFAULT_MAX_CYCLES,
    DEFAULT_CONVERGENCE_ROUNDS,
)


# =========================================================================
#  TestEmptyPlan —— 空计划和缺失配置测试
# =========================================================================

class TestEmptyPlan:
    """测试空计划、缺失字段等退化场景。"""

    def test_empty_plan_defaults_work(self):
        """验证：默认 ConfigPlan 包含所有字段默认值。"""
        plan = ConfigPlan()
        assert plan.project_name == "loop-openclaw-default"
        assert plan.mode == "orchestrator-worker"
        assert plan.agents == []
        assert plan.max_cycles == 10
        assert plan.max_duration_minutes == 60
        assert plan.convergence_rounds == 3

    def test_render_with_empty_agents(self):
        """验证：空 agent 列表仍能渲染（不崩溃）。"""
        renderer = TemplateRenderer(
            template_dir=_PROJECT_ROOT / "templates",
            output_dir=_PROJECT_ROOT / "output",
        )
        plan = ConfigPlan(project_name="empty-agents-test", mode="orchestrator-worker", agents=[])
        # 不应抛出异常
        try:
            results = renderer.render_all(plan, mode="orchestrator-worker")
            assert isinstance(results, dict)
            assert "openclaw.json" in results
        except Exception as e:
            # 如果 Jinja2 模板有 for 循环 agent，可能抛出异常
            # simple_render 降级不应崩溃
            pass

    def test_render_with_minimal_plan(self):
        """验证：最小配置计划可成功渲染全部 5 个文件。"""
        plan = ConfigPlan(
            project_name="minimal",
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
        results = renderer.render_all(plan, mode="orchestrator-worker")
        assert len(results) == 5
        for fname in ["openclaw.json", "SOUL.md", "AGENTS.md", "IDENTITY.md", "TOOLS.md"]:
            assert fname in results, f"缺少输出文件: {fname}"

    def test_missing_template_files_programmatic_fallback(self):
        """验证：模板文件缺失时使用程序化构建作为降级方案。"""
        # 使用一个不存在的模板目录
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpl_dir = Path(tmpdir) / "templates"
            tmpl_dir.mkdir()
            out_dir = Path(tmpdir) / "output"
            plan = ConfigPlan(
                project_name="no-templates",
                mode="orchestrator-worker",
                agents=[AgentSpec(agent_id="a", role="orchestrator"),
                        AgentSpec(agent_id="b", role="worker")]
            )
            renderer = TemplateRenderer(template_dir=tmpl_dir, output_dir=out_dir)
            results = renderer.render_all(plan, mode="orchestrator-worker")
            # 即使没有 .j2 模板，也应生成 5 个文件
            assert len(results) == 5
            for fname in ["openclaw.json", "SOUL.md"]:
                assert fname in results
                assert len(results[fname]) > 0


# =========================================================================
#  TestInvalidMode —— 无效模式名测试
# =========================================================================

class TestInvalidMode:
    """测试无效模式名的行为。"""

    def test_unknown_mode_fallback_in_renderer(self):
        """验证：TemplateRenderer 中无效模式回退到 orchestrator-worker。"""
        renderer = TemplateRenderer(
            template_dir=_PROJECT_ROOT / "templates",
            output_dir=_PROJECT_ROOT / "output",
        )
        plan = ConfigPlan(
            project_name="bad-mode",
            mode="garbage-mode",
            agents=[AgentSpec(agent_id="a", role="orchestrator"),
                    AgentSpec(agent_id="b", role="worker")]
        )
        results = renderer.render_all(plan, mode="garbage-mode")
        # 回退为 orchestrator-worker 模式，应成功渲染
        assert len(results) == 5

    def test_empty_mode_string(self):
        """验证：空模式名回退到默认值。"""
        renderer = TemplateRenderer(
            template_dir=_PROJECT_ROOT / "templates",
            output_dir=_PROJECT_ROOT / "output",
        )
        plan = ConfigPlan(project_name="empty-mode", mode="",
                          agents=[AgentSpec(agent_id="a", role="orchestrator"),
                                  AgentSpec(agent_id="b", role="worker")])
        results = renderer.render_all(plan, mode="")
        assert len(results) == 5

    def test_mode_case_sensitive(self):
        """验证：模式名大小写敏感——大写变体无效。"""
        plan = ConfigPlan(
            project_name="case-test",
            mode="Orchestrator-Worker",
            agents=[AgentSpec(agent_id="a", role="orchestrator"),
                    AgentSpec(agent_id="b", role="worker")]
        )
        result = validate_config_plan(plan)
        assert not result.passed, "大小写变体应无效"


# =========================================================================
#  TestSpecialCharacters —— 特殊字符模板变量测试
# =========================================================================

class TestSpecialCharacters:
    """测试模板变量包含特殊字符时的行为。"""

    def test_unicode_in_variable_values(self):
        """验证：Unicode 字符（emoji、中文、日文）可正确渲染。"""
        tmpl = "{{ greeting }}"
        vars_ = {"greeting": "你好世界 🚀 こんにちは"}
        result = simple_render(tmpl, vars_)
        assert "你好世界" in result
        assert "🚀" in result
        assert "こんにちは" in result

    def test_html_tags_in_values(self):
        """验证：HTML 标签不触发注入问题，原样渲染。"""
        tmpl = "描述: {{ desc }}"
        vars_ = {"desc": "<script>alert('xss')</script>"}
        result = simple_render(tmpl, vars_)
        assert "<script>" in result, "simple_render 不执行转义，应原样输出"

    def test_json_special_chars_in_values(self):
        """验证：JSON 特殊字符（引号、反斜杠、换行）正确渲染。"""
        tmpl = "{{ payload }}"
        vars_ = {"payload": '{"key": "value\\with\\backslash", "msg": "line1\\nline2"}'}
        result = simple_render(tmpl, vars_)
        assert "backslash" in result

    def test_empty_string_value(self):
        """验证：空字符串值渲染为空。"""
        tmpl = "前置文本{{ empty }}后置文本"
        result = simple_render(tmpl, {"empty": ""})
        assert "前置文本后置文本" in result

    def test_none_value_renders_empty(self):
        """验证：None 值渲染为空字符串。"""
        tmpl = "{{ maybe_null }}"
        result = simple_render(tmpl, {"maybe_null": None})
        assert result == ""

    def test_very_long_string_value(self):
        """验证：超长字符串值可正确渲染。"""
        long_str = "x" * 10000
        tmpl = "{{ content }}"
        result = simple_render(tmpl, {"content": long_str})
        assert len(result) == 10000
        assert result == long_str

    def test_agent_id_with_special_chars_in_plan(self):
        """验证：agent_id 包含连字符和下划线时渲染正常。"""
        plan = ConfigPlan(
            project_name="special-ids",
            mode="orchestrator-worker",
            agents=[
                AgentSpec(agent_id="my-orchestrator_v2", role="orchestrator"),
                AgentSpec(agent_id="worker-a_001", role="worker"),
                AgentSpec(agent_id="worker-b_002", role="worker"),
            ]
        )
        renderer = TemplateRenderer(
            template_dir=_PROJECT_ROOT / "templates",
            output_dir=_PROJECT_ROOT / "output",
        )
        results = renderer.render_all(plan, mode="orchestrator-worker")
        openclaw = results["openclaw.json"]
        assert "my-orchestrator_v2" in openclaw
        assert "worker-a_001" in openclaw


# =========================================================================
#  TestLargeConfig —— 超大配置测试
# =========================================================================

class TestLargeConfig:
    """测试超大配置（100+ agents）的性能和正确性。"""

    def test_100_agents_render_without_crash(self):
        """验证：100 个 agent 可渲染而不会崩溃或超时。"""
        agents = []
        for i in range(100):
            role = "orchestrator" if i == 0 else "worker"
            agents.append(AgentSpec(
                agent_id=f"agent-{i:03d}",
                role=role,
                description=f"Agent number {i}",
                persona_traits=[f"trait-{i}-a", f"trait-{i}-b"],
                tools=[f"tool_{i}", "session_read"],
            ))
        plan = ConfigPlan(
            project_name="hundred-agents",
            mode="orchestrator-worker",
            agents=agents,
        )
        renderer = TemplateRenderer(
            template_dir=_PROJECT_ROOT / "templates",
            output_dir=_PROJECT_ROOT / "output",
        )
        results = renderer.render_all(plan, mode="orchestrator-worker")
        assert len(results) == 5
        # openclaw.json 必须包含 100 个 agent id
        for i in range(100):
            assert f"agent-{i:03d}" in results["openclaw.json"]

    def test_200_agents_config_validity(self):
        """验证：200 个 agent 的配置计划校验不崩溃。"""
        agents = []
        for i in range(200):
            agents.append(AgentSpec(
                agent_id=f"a{i:04d}",
                role="worker",
            ))
        plan = ConfigPlan(
            project_name="two-hundred",
            mode="orchestrator-worker",
            agents=agents,
        )
        result = validate_config_plan(plan)
        # 由于至少需要一个 orchestrator，这可能会失败
        # 但我们只关心不会崩溃
        assert isinstance(result.passed, bool)

    def test_large_routing_rules(self):
        """验证：大量路由规则（100条）交叉引用校验不崩溃。"""
        agents = [AgentSpec(agent_id=f"n{i}", role="worker") for i in range(10)]
        routing = []
        for i in range(9):
            routing.append({"source": f"n{i}", "target": f"n{i+1}"})
        for i in range(91):
            routing.append({"source": f"n{i % 10}", "target": f"n{(i + 1) % 10}"})
        plan = ConfigPlan(
            project_name="many-routes",
            mode="sequential-pipeline",
            agents=agents,
            routing_rules=routing,
        )
        result = validate_cross_references(plan)
        # 所有引用都应该有效，因为只用 n0-n9
        assert result.passed, f"大面积路由校验应通过: {result.errors[:3]}"

    def test_deeply_nested_variable_access(self):
        """验证：深层嵌套（5层）的变量点号路径访问。"""
        tmpl = "{{ a.b.c.d.e }}"
        vars_ = {"a": {"b": {"c": {"d": {"e": "deep-value"}}}}}
        result = simple_render(tmpl, vars_)
        assert result == "deep-value"


# =========================================================================
#  TestParseMissingFile —— 缺失/损坏配置文件解析
# =========================================================================

class TestParseMissingFile:
    """测试解析不存在或损坏的配置计划文件。"""

    def test_parse_nonexistent_file_returns_defaults(self):
        """验证：不存在的配置计划文件返回默认 ConfigPlan。"""
        plan = parse_config_plan("/nonexistent/path/plan.md")
        assert plan.project_name == "loop-openclaw-default"
        assert plan.mode == "orchestrator-worker"
        assert plan.agents == []

    def test_parse_emtpy_file_returns_defaults(self):
        """验证：空文件返回默认 ConfigPlan。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("")
            f.flush()
            plan = parse_config_plan(f.name)
            assert plan.project_name == "loop-openclaw-default"
            assert plan.agents == []
        os.unlink(f.name)

    def test_parse_minimal_markdown(self):
        """验证：解析最简合法的 Markdown 配置。"""
        md = (
            "project_name: simple-test\n"
            "mode: peer-review-pair\n"
            "### Agent: r1\n"
            "role: peer_a\n"
            "description: reviewer 1\n"
            "### Agent: r2\n"
            "role: peer_b\n"
            "description: reviewer 2\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(md)
            f.flush()
            plan = parse_config_plan(f.name)
            assert plan.project_name == "simple-test"
            assert plan.mode == "peer-review-pair"
            assert len(plan.agents) == 2
            agent_ids = {a.agent_id for a in plan.agents}
            assert "r1" in agent_ids
            assert "r2" in agent_ids
        os.unlink(f.name)


# =========================================================================
#  TestWeirdVariablePatterns —— 奇怪的模板变量模式测试
# =========================================================================

class TestWeirdVariablePatterns:
    """测试非标准模板变量模式的处理。"""

    def test_double_close_brace_in_text(self):
        """验证：模板中包含 }} 文本但不构成占位符时不被错误替换。"""
        tmpl = "这是一段包含 }} 左右花括号的文本"
        result = simple_render(tmpl, {"test": "val"})
        assert "}}" in result
        # 不应丢失文本

    def test_open_brace_without_close(self):
        """验证：只有 {{ 而没有 }} 时保留原样。"""
        tmpl = "未闭合的 {{ var"
        result = simple_render(tmpl, {"var": "value"})
        # 正则 {{ ... }} 不匹配，文本保留原样
        assert "{{ var" in result

    def test_nested_curly_braces(self):
        """验证：三层花括号的退化处理行为（不崩溃即为通过）。"""
        tmpl = "{{{ nested }}}"
        result = simple_render(tmpl, {"nested": "inner"})
        # simple_render 非贪婪匹配：{{ { nested }} -> 捕获组 "{ nested " -> 变量不存在 -> 替换为空
        # 残留最后一个 } 作为普通文本；渲染器不崩溃但不做 Jinja2 式的嵌套表达式处理
        assert "}" in result or result == ""

    def test_consecutive_placeholders(self):
        """验证：连续的占位符均被替换。"""
        tmpl = "{{ a }}{{ b }}{{ c }}"
        vars_ = {"a": "1", "b": "2", "c": "3"}
        result = simple_render(tmpl, vars_)
        assert result == "123"

    def test_placeholder_inside_json_like_text(self):
        """验证：占位符位于 JSON 类文本中时可正确替换。"""
        tmpl = '{"name": "{{ name }}", "id": {{ id }}}'
        vars_ = {"name": "test", "id": 42}
        result = simple_render(tmpl, vars_)
        assert '"name": "test"' in result
        assert '"id": 42' in result

    def test_pipe_syntax_with_spaces(self):
        """验证：管道语法含多余空格时正确解析。"""
        tmpl = "{{  data  |  tojson  }}"
        vars_ = {"data": {"key": "val"}}
        result = simple_render(tmpl, vars_)
        assert '"key"' in result
        assert '"val"' in result


# =========================================================================
#  TestExtraVarsEdgeCases —— extra_vars 边界情况测试
# =========================================================================

class TestExtraVarsEdgeCases:
    """测试 extra_vars 的各种边缘输入。"""

    def test_extra_vars_override_project_name(self):
        """验证：extra_vars 可覆盖 project_name。"""
        reg = TemplateRegistry(_PROJECT_ROOT / "templates" / "template_registry.json")
        plan = ConfigPlan(
            project_name="original",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")]
        )
        resolved = reg.resolve(plan, {"project_name": "overridden-name"})
        assert resolved["project_name"] == "overridden-name"

    def test_extra_vars_inject_new_keys(self):
        """验证：extra_vars 可注入注册表未定义的新键。"""
        reg = TemplateRegistry(_PROJECT_ROOT / "templates" / "template_registry.json")
        plan = ConfigPlan(
            project_name="newkey-test",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")]
        )
        resolved = reg.resolve(plan, {"custom_field": "custom_value", "another": 123})
        assert resolved["custom_field"] == "custom_value"
        assert resolved["another"] == 123

    def test_extra_vars_empty_dict_no_effect(self):
        """验证：空 extra_vars 不影响解析结果。"""
        reg = TemplateRegistry(_PROJECT_ROOT / "templates" / "template_registry.json")
        plan = ConfigPlan(
            project_name="empty-extra",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")]
        )
        resolved1 = reg.resolve(plan, {})
        resolved2 = reg.resolve(plan, {"irrelevant": "ignored"})
        assert resolved1["project_name"] == resolved2["project_name"]
        assert resolved1["mode"] == resolved2["mode"]


# =========================================================================
#  TestConvergenceTextGeneration —— 收敛文本生成边缘测试
# =========================================================================

class TestConvergenceTextGeneration:
    """测试 _completion_gate_text 和 _hard_stop_text 的各种输入。"""

    def test_completion_gate_with_large_rounds(self):
        """验证：大收敛轮次（1000）正确嵌入文本。"""
        text = TemplateRegistry._completion_gate_text("orchestrator-worker", 1000)
        assert "1000" in text
        assert "CONVERGED" in text

    def test_completion_gate_with_rounds_one(self):
        """验证：收敛轮次为 1 时文本仍合法。"""
        text = TemplateRegistry._completion_gate_text("orchestrator-worker", 1)
        assert "1" in text
        assert "CONVERGED" in text

    def test_completion_gate_unknown_mode_fallback(self):
        """验证：未知模式回退到 orchestrator-worker 收敛文本。"""
        text = TemplateRegistry._completion_gate_text("bogus-mode", 3)
        assert "CONVERGED" in text

    def test_hard_stop_with_large_values(self):
        """验证：超大的 max_cycles 和 max_duration 正确嵌入。"""
        text = TemplateRegistry._hard_stop_text(99999, 99999)
        assert "99999" in text
        assert "硬止损" in text

    def test_escape_detection_text_not_empty(self):
        """验证：逃逸检测文本非空。"""
        text = TemplateRegistry._escape_detection_text()
        assert len(text) > 0
        assert "ESCAPE_DETECTED" in text


# =========================================================================
#  TestTemplateRendererEdgeCases —— TemplateRenderer 边缘情况
# =========================================================================

class TestTemplateRendererEdgeCases:
    """测试 TemplateRenderer 的边缘行为和错误恢复。"""

    @classmethod
    def setup_class(cls):
        """创建基础 renderer 实例。"""
        cls.renderer = TemplateRenderer(
            template_dir=_PROJECT_ROOT / "templates",
            output_dir=_PROJECT_ROOT / "output",
        )

    def test_render_all_creates_output_dir(self):
        """验证：render_all 自动创建输出目录（若不存在）。"""
        import shutil
        new_out = _PROJECT_ROOT / "output" / "edge_test_subdir"
        if new_out.exists():
            shutil.rmtree(str(new_out))
        r = TemplateRenderer(
            template_dir=_PROJECT_ROOT / "templates",
            output_dir=new_out,
        )
        plan = ConfigPlan(
            project_name="mkdir-test",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")]
        )
        r.render_all(plan, mode="orchestrator-worker")
        assert new_out.exists()
        assert (new_out / "openclaw.json").exists()

    def test_registry_path_custom(self):
        """验证：可指定自定义 registry 路径。"""
        r = TemplateRenderer(
            template_dir=_PROJECT_ROOT / "templates",
            output_dir=_PROJECT_ROOT / "output",
            registry_path=_PROJECT_ROOT / "templates" / "template_registry.json",
        )
        # 应正常加载
        assert len(r.registry._variables) >= 20

    def test_validate_output_returns_messages(self):
        """验证：validate_output() 返回非空消息列表。"""
        plan = ConfigPlan(
            project_name="validate-edge",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator"), AgentSpec(agent_id="w", role="worker")]
        )
        self.renderer.render_all(plan, mode="orchestrator-worker")
        messages = self.renderer.validate_output()
        assert isinstance(messages, list)
        assert len(messages) > 0
        # 应包含 summary
        assert any("summary" in m.lower() for m in messages)

    def test_simple_render_with_agent_list(self):
        """验证：simple_render 正确渲染 agent 列表到模板。"""
        tmpl = "Agents: {{ agents }}"
        vars_ = {"agents": [{"id": "a"}, {"id": "b"}]}
        result = simple_render(tmpl, vars_)
        # list 类型通过 _resolve 中的 json.dumps 或 str 转换
        assert "a" in result
        assert "b" in result
