"""test_e2e_orchestrator.py —— Orchestrator-Worker 模式端到端测试。

测试场景：bug 修复工作流（orchestrator + implementer + tester）。
验证完整渲染 + validate_config_plan + validate_cross_references。
"""
from tests import load_plan_from_json, _PROJECT_ROOT as ROOT
from render import (  # noqa: E402
    TemplateRenderer,
    validate_config_plan,
    validate_cross_references,
    validate_output_files,
)


class TestE2EOrchestratorWorker:
    """Orchestrator-Worker 模式端到端测试套件。"""

    @classmethod
    def setup_class(cls):
        """加载配置计划并执行渲染。"""
        cls.plan = load_plan_from_json("03-config-plan-example-a.json")
        cls.out = ROOT / "output"
        renderer = TemplateRenderer(template_dir=ROOT / "templates", output_dir=cls.out)
        cls.rendered = renderer.render_all(cls.plan, mode="orchestrator-worker")

    def test_plan_validates(self):
        """verify: validate_config_plan 返回 passed=True。"""
        r = validate_config_plan(self.plan)
        assert r.passed, f"校验失败: {r.errors}"

    def test_output_files(self):
        """verify: 5 个输出文件均存在且体积达标。"""
        r = validate_output_files(self.out)
        assert r.passed, f"输出文件校验失败: {r.errors}"

    def test_cross_references(self):
        """verify: routing_rules 和 permissions 引用均指向已定义 agent。"""
        r = validate_cross_references(self.plan)
        assert r.passed, f"交叉引用校验失败: {r.errors}"

    def test_agent_count_and_ids(self):
        """verify: 包含 3 个 agent (orchestrator/implementer/tester)。"""
        assert len(self.plan.agents) == 3
        assert {a.agent_id for a in self.plan.agents} == {"orchestrator", "implementer", "tester"}

    def test_orch_permissions(self):
        """verify: orchestrator 拥有 sessions_spawn 权限指向两个 worker。"""
        orch = next(a for a in self.plan.agents if a.agent_id == "orchestrator")
        spawns = orch.permissions.get("sessions_spawn", [])
        assert "implementer" in spawns
        assert "tester" in spawns

    def test_workers_no_spawn(self):
        """verify: implementer 和 tester 不允许 sessions_spawn。"""
        for aid in ("implementer", "tester"):
            a = next(x for x in self.plan.agents if x.agent_id == aid)
            assert not a.permissions.get("sessions_spawn", []), f"{aid} 不应有 sessions_spawn"

    def test_agents_md_has_convergence(self):
        """verify: AGENTS.md 包含收敛条件。"""
        text = (self.out / "AGENTS.md").read_text(encoding="utf-8")
        assert "收敛" in text or "CONVERGED" in text or "convergence" in text.lower()

    def test_openclaw_json_has_agents(self):
        """verify: openclaw.json 输出包含 agent 引用。"""
        raw = (self.out / "openclaw.json").read_text(encoding="utf-8")
        assert "orchestrator" in raw

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
            if agent.description:
                assert agent.description in text, (
                    f"IDENTITY.md 缺少 agent '{agent.agent_id}' 的 description"
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
