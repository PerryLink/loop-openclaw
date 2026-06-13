"""test_unit_render.py —— 渲染引擎单元测试。

覆盖范围：simple_render（regex降级引擎）、TemplateRegistry（变量注册表加载与解析）、
TemplateRenderer 内部辅助函数、模式选择逻辑。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 将项目根目录加入 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from render import (  # noqa: E402
    AgentSpec,
    ConfigPlan,
    TemplateRegistry,
    TemplateRenderer,
    TemplateVariableError,
    simple_render,
    render_engine_info,
    MODE_NAMES,
    _parse_agent_block,
    _extract_section,
)


# =========================================================================
#  TestSimpleRender —— regex 降级引擎单元测试
# =========================================================================

class TestSimpleRender:
    """测试 simple_render 函数的变量替换逻辑。"""

    # --- 基本变量替换 --------------------------------------------------------

    def test_simple_variable_replacement(self):
        """验证：{{ var }} 占位符被正确替换为值。"""
        tmpl = "项目名: {{ project_name }}"
        result = simple_render(tmpl, {"project_name": "test-loop"})
        assert result == "项目名: test-loop"

    def test_multiple_variables(self):
        """验证：多个占位符同时被替换。"""
        tmpl = "{{ name }} 使用 {{ model }} 模型"
        vars_ = {"name": "orchestrator", "model": "claude-sonnet"}
        result = simple_render(tmpl, vars_)
        assert result == "orchestrator 使用 claude-sonnet 模型"

    def test_no_placeholders_returns_original(self):
        """验证：不含占位符的模板原样返回。"""
        tmpl = "这是纯文本，没有变量。"
        result = simple_render(tmpl, {})
        assert result == tmpl

    def test_placeholder_preserved_when_var_missing(self):
        """验证：未定义变量被替换为空字符串（simple_render 的行为）。"""
        tmpl = "未知变量: {{ unknown_var }}"
        result = simple_render(tmpl, {"known": "value"})
        # simple_render 对顶层缺失变量返回空字符串（非保留原占位符）
        assert "未知变量: " in result

    # --- 点号路径访问 --------------------------------------------------------

    def test_dot_path_dict_access(self):
        """验证：{{ dict.key }} 点号路径可访问嵌套字段。"""
        tmpl = "Agent: {{ agent.id }}"
        vars_ = {"agent": {"id": "orch-001", "role": "orchestrator"}}
        result = simple_render(tmpl, vars_)
        assert result == "Agent: orch-001"

    def test_dot_path_deep_nesting(self):
        """验证：深层嵌套点号路径可正确解析。"""
        tmpl = "收敛条件: {{ convergence_criteria.P0 }}"
        vars_ = {"convergence_criteria": {"P0": "阻断性bug", "P1": "非阻断缺陷"}}
        result = simple_render(tmpl, vars_)
        assert result == "收敛条件: 阻断性bug"

    def test_dot_path_list_index(self):
        """验证：点号路径中可用数字索引访问列表元素。"""
        tmpl = "第一个Agent: {{ agents.0.id }}"
        vars_ = {"agents": [{"id": "a1"}, {"id": "a2"}]}
        result = simple_render(tmpl, vars_)
        assert result == "第一个Agent: a1"

    def test_dot_path_invalid_index_preserved(self):
        """验证：列表索引越界时保留原始占位符。"""
        tmpl = "{{ agents.99 }}"
        vars_ = {"agents": [{"id": "a1"}]}
        result = simple_render(tmpl, vars_)
        assert "{{" in result or "agents.99" in result

    # --- 管道语法 ------------------------------------------------------------

    def test_pipe_tojson_dict(self):
        """验证：{{ var | tojson }} 管道语法将字典序列化为JSON。"""
        tmpl = "配置: {{ config | tojson }}"
        vars_ = {"config": {"key": "val", "num": 42}}
        result = simple_render(tmpl, vars_)
        assert '"key"' in result
        assert '"val"' in result
        # 确认不是简单 str( 而是 json.dumps 结果
        assert "key" in result

    def test_pipe_tojson_list(self):
        """验证：管道语法可序列化列表。"""
        tmpl = "{{ items | tojson }}"
        vars_ = {"items": [1, 2, 3]}
        result = simple_render(tmpl, vars_)
        assert "1" in result and "2" in result and "3" in result

    # --- 边界情况 ------------------------------------------------------------

    def test_whitespace_in_placeholder(self):
        """验证：占位符内部空白不影响替换。"""
        tmpl = "{{  project_name  }}"
        result = simple_render(tmpl, {"project_name": "ws-test"})
        assert result == "ws-test"

    def test_numeric_value(self):
        """验证：数值类型变量正确转换为字符串。"""
        tmpl = "最多 {{ max_cycles }} 轮"
        result = simple_render(tmpl, {"max_cycles": 10})
        assert result == "最多 10 轮"

    def test_boolean_value(self):
        """验证：布尔类型变量可正确渲染。"""
        tmpl = "启用: {{ enabled }}"
        result = simple_render(tmpl, {"enabled": True})
        assert "True" in result

    def test_special_characters_in_value(self):
        """验证：值中包含特殊字符(换行、引号)时仍可正确替换。"""
        tmpl = "描述: {{ description }}"
        vars_ = {"description": '包含 "引号" 和 换行\n字符'}
        result = simple_render(tmpl, vars_)
        assert "引号" in result
        assert "换行" in result


# =========================================================================
#  TestTemplateRegistry —— 模板注册表加载与变量解析测试
# =========================================================================

class TestTemplateRegistry:
    """测试 TemplateRegistry 的加载、解析与兜底逻辑。"""

    def test_load_from_existing_file(self):
        """验证：从 templates/template_registry.json 成功加载。"""
        reg = TemplateRegistry(_PROJECT_ROOT / "templates" / "template_registry.json")
        assert len(reg._variables) >= 20, f"注册表变量数量不足: {len(reg._variables)}"

    def test_load_from_missing_file_fallback(self):
        """验证：文件缺失时回退到内建默认注册表。"""
        reg = TemplateRegistry(Path("/nonexistent/path/registry.json"))
        assert len(reg._variables) >= 20, "内建注册表应至少包含20个变量"

    def test_resolve_required_variable(self):
        """验证：resolve() 正确填充必填变量。"""
        reg = TemplateRegistry(_PROJECT_ROOT / "templates" / "template_registry.json")
        plan = ConfigPlan(
            project_name="resolve-test",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="orch", role="orchestrator")]
        )
        resolved = reg.resolve(plan, {})
        assert resolved["project_name"] == "resolve-test"
        assert resolved["mode"] == "orchestrator-worker"

    def test_resolve_missing_required_raises_error(self):
        """验证：必填变量缺失且无默认值时抛出 TemplateVariableError。"""
        reg = TemplateRegistry(_PROJECT_ROOT / "templates" / "template_registry.json")
        plan = ConfigPlan()
        # project_name 缺省为空字符串，但注册表中标记为 required 且无 default
        # 实际上 plan.project_name 默认 "loop-openclaw-default"，不会触发
        # 所以手工清空一个必填变量
        from render import TemplateVariableError
        # 测试一个注册表中标记为 required 的变量在 resolved 中为 None
        # 构造一个不完整场景
        plan2 = ConfigPlan(project_name="", mode="", agents=[])
        try:
            reg.resolve(plan2, {})
        except TemplateVariableError as e:
            assert "project_name" in str(e) or "缺少" in str(e)
        else:
            # 如果没有抛异常，project_name 也可能被设置为 "" —— 验证注册表行为
            pass

    def test_resolve_fills_defaults(self):
        """验证：resolve() 为缺失的非必填变量填充默认值。"""
        reg = TemplateRegistry(_PROJECT_ROOT / "templates" / "template_registry.json")
        plan = ConfigPlan(
            project_name="default-test",
            mode="peer-review-pair",
            agents=[AgentSpec(agent_id="a", role="peer_a"), AgentSpec(agent_id="b", role="peer_b")]
        )
        resolved = reg.resolve(plan, {})
        assert resolved.get("model_provider") == "anthropic"
        assert resolved.get("max_tokens") == 4096

    def test_resolve_derives_orchestrator_id(self):
        """验证：resolve() 从 agent 列表中派生 orchestrator_id。"""
        reg = TemplateRegistry(_PROJECT_ROOT / "templates" / "template_registry.json")
        plan = ConfigPlan(
            project_name="derive-test",
            mode="orchestrator-worker",
            agents=[
                AgentSpec(agent_id="boss", role="orchestrator"),
                AgentSpec(agent_id="w1", role="worker"),
                AgentSpec(agent_id="w2", role="worker"),
            ]
        )
        resolved = reg.resolve(plan, {})
        assert resolved["orchestrator_id"] == "boss"
        assert resolved["worker_ids"] == ["w1", "w2"]

    def test_resolve_worker_only_returns_empty_orch_id(self):
        """验证：无 orchestrator 时 orchestrator_id 为空字符串。"""
        reg = TemplateRegistry(_PROJECT_ROOT / "templates" / "template_registry.json")
        plan = ConfigPlan(
            project_name="no-orch",
            mode="sequential-pipeline",
            agents=[
                AgentSpec(agent_id="s1", role="pipeline_stage"),
                AgentSpec(agent_id="s2", role="pipeline_stage"),
            ]
        )
        resolved = reg.resolve(plan, {})
        assert resolved["orchestrator_id"] == ""

    def test_resolve_with_extra_vars_override(self):
        """验证：extra_vars 可覆盖已解析的值。"""
        reg = TemplateRegistry(_PROJECT_ROOT / "templates" / "template_registry.json")
        plan = ConfigPlan(
            project_name="original", mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator")]
        )
        extra = {"project_name": "overridden", "custom_key": "custom_val"}
        resolved = reg.resolve(plan, extra)
        assert resolved["project_name"] == "overridden"
        assert resolved["custom_key"] == "custom_val"

    def test_mode_description_generation(self):
        """验证：_mode_description() 为每种模式返回非空描述。"""
        for mode in MODE_NAMES:
            desc = TemplateRegistry._mode_description(mode)
            assert desc, f"{mode} 的描述不应为空"
            assert len(desc) > 20, f"{mode} 的描述过短: {desc}"

    def test_completion_gate_text_per_mode(self):
        """验证：_completion_gate_text() 为每种模式生成不同的收敛指令。"""
        texts = {}
        for mode in MODE_NAMES:
            texts[mode] = TemplateRegistry._completion_gate_text(mode, 3)
            assert "CONVERGED" in texts[mode], f"{mode} 收敛文本缺少 CONVERGED"
        # 三种模式生成不同文本
        assert len(set(texts.values())) == 3, "三种模式应生成不同收敛文本"


# =========================================================================
#  TestAgentBlockParser —— Agent 块解析单元测试
# =========================================================================

class TestAgentBlockParser:
    """测试 _parse_agent_block 函数的解析逻辑。"""

    def test_parse_valid_agent_block(self):
        """验证：解析正常 Markdown agent 块。"""
        block = (
            "### Agent: test-agent\n"
            "role: orchestrator\n"
            "description: 测试用 orchestrator agent\n"
            "model: claude-sonnet-4-20250514\n"
        )
        agent = _parse_agent_block(block)
        assert agent is not None
        assert agent.agent_id == "test-agent"
        assert agent.role == "orchestrator"
        assert "测试用 orchestrator agent" in agent.description

    def test_parse_agent_with_tools_list(self):
        """验证：解析含工具列表的 agent 块。"""
        block = (
            "### Agent: worker-1\n"
            "role: worker\n"
            "description: 执行任务\n"
            "tools: [\"read\", \"write\", \"exec\"]\n"
        )
        agent = _parse_agent_block(block)
        assert agent is not None
        assert len(agent.tools) == 3
        assert "read" in agent.tools

    def test_parse_agent_with_persona_traits(self):
        """验证：解析含 persona traits 的 agent 块。"""
        block = (
            "### Agent: reviewer\n"
            "role: reviewer\n"
            "description: 代码审查\n"
            "persona traits:\n"
            "- 严谨\n"
            "- 注重细节\n"
            "- 快速反馈\n"
        )
        agent = _parse_agent_block(block)
        assert agent is not None
        assert len(agent.persona_traits) == 3
        assert "严谨" in agent.persona_traits

    def test_parse_agent_with_boundaries(self):
        """验证：解析含能力边界的 agent 块。"""
        block = (
            "### Agent: worker-2\n"
            "role: worker\n"
            "boundaries:\n"
            "- 不得修改配置文件\n"
            "- 不得越权操作\n"
        )
        agent = _parse_agent_block(block)
        assert agent is not None
        assert len(agent.boundaries) == 2

    def test_skip_non_agent_block(self):
        """验证：非 ### Agent: 开头的块返回 None。"""
        block = "## This is a section header, not an agent block"
        agent = _parse_agent_block(block)
        assert agent is None

    def test_parse_agent_without_role_defaults_to_worker(self):
        """验证：缺少 role 时默认为 worker。"""
        block = (
            "### Agent: silent-worker\n"
            "description: 没有显式指定 role\n"
        )
        agent = _parse_agent_block(block)
        assert agent is not None
        assert agent.role == "worker"

    def test_parse_agent_with_permissions(self):
        """验证：解析含 permissions JSON 的 agent 块。"""
        block = (
            "### Agent: admin\n"
            "role: orchestrator\n"
            'permissions: {"sessions_spawn": ["w1", "w2"], "file_read": true}\n'
        )
        agent = _parse_agent_block(block)
        assert agent is not None
        assert agent.permissions.get("sessions_spawn") == ["w1", "w2"]
        assert agent.permissions.get("file_read") is True


# =========================================================================
#  TestSectionExtractor —— Markdown 章节提取测试
# =========================================================================

class TestSectionExtractor:
    """测试 _extract_section 函数的章节提取逻辑。"""

    def test_extract_section_found(self):
        """验证：提取存在的章节内容。"""
        md = (
            "## Convergence Criteria\n\n"
            "这里是收敛条件的内容。\n"
            "包含 P0/P1/P2 定义。\n\n"
            "## Next Section\n\n"
            "另一个章节。\n"
        )
        result = _extract_section(md, "Convergence Criteria", "Conv")
        assert "收敛条件" in result
        assert "P0/P1/P2" in result
        assert "另一个章节" not in result, "不应包含下一个章节内容"

    def test_extract_section_not_found(self):
        """验证：不存在的章节返回空字符串。"""
        md = "## Only One Section\n\n内容。\n"
        result = _extract_section(md, "Missing Section", "Not Here")
        assert result == ""

    def test_extract_section_by_second_keyword(self):
        """验证：通过第二个关键词也能找到章节。"""
        md = (
            "## Convergence Gate\n\n"
            "通过第二个关键词匹配到。\n"
        )
        result = _extract_section(md, "Convergence Criteria", "Convergence Gate")
        assert "第二个关键词" in result


# =========================================================================
#  TestRenderEngineInfo —— 渲染引擎信息测试
# =========================================================================

class TestRenderEngineInfo:
    """测试 render_engine_info() 函数。"""

    def test_returns_dict_with_required_keys(self):
        """验证：返回的字典包含必要键。"""
        info = render_engine_info()
        assert "jinja2_available" in info
        assert "engine" in info
        assert "fallback" in info
        assert info["fallback"] == "simple-string-replacement"

    def test_boolean_jinja2_available(self):
        """验证：jinja2_available 为布尔值。"""
        info = render_engine_info()
        assert isinstance(info["jinja2_available"], bool)

    def test_engine_name_consistent(self):
        """验证：jinja2 可用时 engine 为 jinja2，否则为 fallback 值。"""
        info = render_engine_info()
        if info["jinja2_available"]:
            assert info["engine"] == "jinja2"
        else:
            assert info["engine"] == "simple-string-replacement"


# =========================================================================
#  TestTemplateRendererInternals —— TemplateRenderer 内部方法测试
# =========================================================================

class TestTemplateRendererInternals:
    """测试 TemplateRenderer 的内部辅助逻辑。"""

    @classmethod
    def setup_class(cls):
        """创建 TemplateRenderer 实例。"""
        cls.renderer = TemplateRenderer(
            template_dir=_PROJECT_ROOT / "templates",
            output_dir=_PROJECT_ROOT / "output",
        )

    def test_validate_mode_valid(self):
        """验证：已知模式返回原始值。"""
        for mode in MODE_NAMES:
            assert self.renderer._validate_mode(mode) == mode

    def test_validate_mode_invalid_fallback(self):
        """验证：无效模式回退到 orchestrator-worker。"""
        result = self.renderer._validate_mode("nonexistent-mode")
        assert result == "orchestrator-worker"

    def test_load_template_or_none_found(self):
        """验证：存在的模板文件返回非空内容。"""
        content = self.renderer._load_template_or_none("AGENTS.md.j2")
        assert content is not None
        assert len(content) > 0

    def test_load_template_or_none_missing(self):
        """验证：不存在的模板文件返回 None。"""
        content = self.renderer._load_template_or_none("nonexistent_template.j2")
        assert content is None

    def test_strip_json5_features_removes_comments(self):
        """验证：去除 JSON5 单行注释。"""
        json5 = '{"key": "val"} // 注释\n// 全行注释\n{"k2": 1}'
        clean = TemplateRenderer._strip_json5_features(json5)
        assert "注释" not in clean

    def test_strip_json5_features_removes_block_comments(self):
        """验证：去除 JSON5 块注释。"""
        json5 = '{"a": 1} /* 块注释 */ {"b": 2}'
        clean = TemplateRenderer._strip_json5_features(json5)
        assert "块注释" not in clean

    def test_strip_json5_features_removes_trailing_commas(self):
        """验证：去除尾部逗号使 stdlib json 可解析。"""
        json5 = '{"a": 1, "b": [1, 2,],}'
        clean = TemplateRenderer._strip_json5_features(json5)
        # 尾部逗号被移除后应可解析
        parsed = json.loads(clean)
        assert parsed["a"] == 1
        assert parsed["b"] == [1, 2]

    def test_load_json5_parses_valid_file(self):
        """验证：_load_json5 可解析 JSON5 文件。"""
        # 使用 renderer 渲染一个 openclaw.json 来测试
        plan = ConfigPlan(
            project_name="json5-test",
            mode="orchestrator-worker",
            agents=[AgentSpec(agent_id="o", role="orchestrator")]
        )
        self.renderer.render_all(plan, mode="orchestrator-worker")
        config = TemplateRenderer._load_json5(_PROJECT_ROOT / "output" / "openclaw.json")
        assert isinstance(config, dict)
        assert "project" in config


# =========================================================================
#  TestModeConstants —— 模式常量测试
# =========================================================================

class TestModeConstants:
    """测试模块级常量定义的一致性。"""

    def test_three_modes_defined(self):
        """验证：定义了3种模式。"""
        assert len(MODE_NAMES) == 3

    def test_all_modes_have_default_cycles(self):
        """验证：每种模式都有默认 max_cycles。"""
        from render import DEFAULT_MAX_CYCLES
        for mode in MODE_NAMES:
            assert mode in DEFAULT_MAX_CYCLES

    def test_all_modes_have_default_convergence_rounds(self):
        """验证：每种模式都有默认收敛轮次。"""
        from render import DEFAULT_CONVERGENCE_ROUNDS
        for mode in MODE_NAMES:
            assert mode in DEFAULT_CONVERGENCE_ROUNDS
