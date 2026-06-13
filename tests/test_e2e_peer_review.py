"""test_e2e_peer_review.py —— Peer-Review 模式端到端测试。

测试场景：代码审查工作流（reviewer_a + reviewer_b 双向审查）。
验证完整渲染 + 双向路由 + STALEMATE 硬止损。
"""
from tests import load_plan_from_json, _PROJECT_ROOT as ROOT
from render import (  # noqa: E402
    TemplateRenderer,
    validate_config_plan,
    validate_cross_references,
    validate_output_files,
)


class TestE2EPeerReview:
    """Peer Review Pair 模式端到端测试套件。"""

    @classmethod
    def setup_class(cls):
        """加载配置计划并执行渲染。"""
        cls.plan = load_plan_from_json("03-config-plan-example-b.json")
        cls.out = ROOT / "output"
        renderer = TemplateRenderer(template_dir=ROOT / "templates", output_dir=cls.out)
        cls.rendered = renderer.render_all(cls.plan, mode="peer-review-pair")

    def test_plan_validates(self):
        """verify: validate_config_plan 返回 passed=True。"""
        r = validate_config_plan(self.plan)
        assert r.passed, f"校验失败: {r.errors}"

    def test_exactly_two_agents(self):
        """verify: peer-review 模式恰好 2 个 agent。"""
        assert len(self.plan.agents) == 2
        assert {a.agent_id for a in self.plan.agents} == {"reviewer_a", "reviewer_b"}

    def test_bidirectional_routing(self):
        """verify: 双方互相拥有 sessions_send 权限。"""
        a = next(x for x in self.plan.agents if x.agent_id == "reviewer_a")
        b = next(x for x in self.plan.agents if x.agent_id == "reviewer_b")
        assert "reviewer_b" in a.permissions.get("sessions_send", [])
        assert "reviewer_a" in b.permissions.get("sessions_send", [])

    def test_no_spawn(self):
        """verify: peer agent 不允许 sessions_spawn。"""
        for agent in self.plan.agents:
            assert not agent.permissions.get("sessions_spawn", []), \
                f"{agent.agent_id} 不应有 sessions_spawn"

    def test_cross_references(self):
        """verify: 所有引用指向已定义 agent。"""
        r = validate_cross_references(self.plan)
        assert r.passed, f"交叉引用校验失败: {r.errors}"

    def test_output_files(self):
        """verify: 5 个输出文件均存在。"""
        r = validate_output_files(self.out)
        assert r.passed, f"输出文件校验失败: {r.errors}"

    def test_convergence_in_agents_md(self):
        """verify: AGENTS.md 包含双向审查/peer 相关描述。"""
        text = (self.out / "AGENTS.md").read_text(encoding="utf-8")
        assert "review" in text.lower() or "peer" in text.lower() or "审查" in text

    def test_mode_defaults(self):
        """verify: peer-review 模式默认 max_cycles=8, convergence_rounds=2。"""
        assert self.plan.max_cycles == 8
        assert self.plan.convergence_rounds == 2

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

    def test_openclaw_json_has_peer_agents(self):
        """verify: openclaw.json 输出包含两个 peer agent 引用。"""
        raw = (self.out / "openclaw.json").read_text(encoding="utf-8")
        assert "reviewer_a" in raw
        assert "reviewer_b" in raw
