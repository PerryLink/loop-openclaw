"""test_e2e_sequential.py —— Sequential-Pipeline 模式端到端测试。

测试场景：设计->实施->测试流水线（designer + builder + tester）。
验证链式 handoff、回退路由、末尾收敛判定。
"""
from tests import load_plan_from_json, _PROJECT_ROOT as ROOT
from render import (  # noqa: E402
    TemplateRenderer,
    validate_config_plan,
    validate_cross_references,
    validate_output_files,
)


class TestE2ESequentialPipeline:
    """Sequential Pipeline 模式端到端测试套件。"""

    @classmethod
    def setup_class(cls):
        """加载配置计划并执行渲染。"""
        cls.plan = load_plan_from_json("03-config-plan-example-c.json")
        cls.out = ROOT / "output"
        renderer = TemplateRenderer(template_dir=ROOT / "templates", output_dir=cls.out)
        cls.rendered = renderer.render_all(cls.plan, mode="sequential-pipeline")

    def test_plan_validates(self):
        """verify: validate_config_plan 返回 passed=True。"""
        r = validate_config_plan(self.plan)
        assert r.passed, f"校验失败: {r.errors}"

    def test_three_agents(self):
        """verify: 流水线包含 3 个阶段 agent。"""
        assert len(self.plan.agents) == 3
        assert {a.agent_id for a in self.plan.agents} == {"designer", "builder", "tester"}

    def test_chain_routing(self):
        """verify: 链式 handoff——每个 agent 向下一个发送。"""
        d = next(a for a in self.plan.agents if a.agent_id == "designer")
        b = next(a for a in self.plan.agents if a.agent_id == "builder")
        t = next(a for a in self.plan.agents if a.agent_id == "tester")
        assert "builder" in d.permissions.get("sessions_send", [])
        assert "tester" in b.permissions.get("sessions_send", [])
        assert "designer" in t.permissions.get("sessions_send", [])

    def test_fallback_routing(self):
        """verify: routing_rules 包含 P0 回退至 designer 的规则。"""
        fallback = [r for r in self.plan.routing_rules
                    if r.get("target") == "designer" or "P0" in r.get("condition", "")]
        assert len(fallback) > 0, "缺少回退路由"

    def test_cross_references(self):
        """verify: 所有引用指向已定义 agent。"""
        r = validate_cross_references(self.plan)
        assert r.passed, f"交叉引用校验失败: {r.errors}"

    def test_output_files(self):
        """verify: 5 个输出文件均存在。"""
        r = validate_output_files(self.out)
        assert r.passed, f"输出文件校验失败: {r.errors}"

    def test_mode_defaults(self):
        """verify: pipeline 模式默认 max_cycles=5, convergence_rounds=1。"""
        assert self.plan.max_cycles == 5
        assert self.plan.convergence_rounds == 1

    def test_pipeline_text(self):
        """verify: AGENTS.md 包含流水线/handoff 描述。"""
        text = (self.out / "AGENTS.md").read_text(encoding="utf-8")
        assert "pipeline" in text.lower() or "handoff" in text.lower() or "流水线" in text

    def test_soul_md_contains_persona_traits(self):
        """verify: SOUL.md 模板渲染输出包含 config plan 中定义的 persona traits。"""
        text = (self.out / "SOUL.md").read_text(encoding="utf-8")
        for agent in self.plan.agents:
            if agent.persona_traits:
                for trait in agent.persona_traits:
                    assert trait in text, (
                        f"SOUL.md 缺少 agent '{agent.agent_id}' trait: {trait}"
                    )

    def test_identity_md_contains_agent_descriptions(self):
        """verify: IDENTITY.md 模板渲染输出包含 agent 描述/职责。"""
        text = (self.out / "IDENTITY.md").read_text(encoding="utf-8")
        for agent in self.plan.agents:
            assert agent.agent_id in text, (
                f"IDENTITY.md 缺少 agent ID: {agent.agent_id}"
            )

    def test_tools_md_contains_tool_declarations(self):
        """verify: TOOLS.md 模板渲染输出包含 agent 工具声明。"""
        text = (self.out / "TOOLS.md").read_text(encoding="utf-8")
        for agent in self.plan.agents:
            assert agent.agent_id in text, (
                f"TOOLS.md 缺少 agent ID: {agent.agent_id}"
            )
            if agent.tools:
                for tool in agent.tools:
                    assert tool in text, (
                        f"TOOLS.md 缺少 agent '{agent.agent_id}' 的工具: {tool}"
                    )

    def test_openclaw_json_has_pipeline_agents(self):
        """verify: openclaw.json 输出包含流水线 agent 引用。"""
        raw = (self.out / "openclaw.json").read_text(encoding="utf-8")
        assert "designer" in raw
        assert "builder" in raw
        assert "tester" in raw
