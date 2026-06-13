#!/usr/bin/env python3
"""
render.py  --  Loop-OpenClaw 配置渲染器
============================================

**Architectural Philosophy — Single-File by Design**

loop-openclaw is a pure configuration generator, not a runtime loop engine.
The entire codebase lives in this single file by deliberate architectural choice:

  1. **One input**: a Markdown config plan (artifacts/03-config-plan.md) or JSON plan
  2. **One engine**: Jinja2 template rendering (with zero-dependency regex fallback)
  3. **One output**: 5 Gateway-ready configuration files written to output/
  4. **One responsibility**: generate configs and stop — the Gateway runs the actual loop

This "single-file architecture" ensures:
  - **Full auditability**: every line of logic is in one place, reviewable in one pass
  - **Zero orchestration overhead**: no state machine, no hook system, no runtime driver
  - **Minimal supply-chain surface**: only Python stdlib + optional Jinja2
  - **Clear separation of concerns**: config generation and loop execution are distinct phases

**Loop behavior emerges downstream**: the generated configs embed natural-language
convergence conditions (Completion Gates) as plain text inside agent instructions.
When deployed to OpenClaw Gateway, agents self-evaluate convergence — the loop is
emergent from agent self-governance, not from a central loop driver.

读取配置计划 (artifacts/03-config-plan.md) 与模板注册表
(templates/template_registry.json)，解析全部模板变量，使用 Jinja2（主引擎）
或简单字符串替换（降级）渲染 5 个 OpenClaw Gateway 输出文件，写入 output/ 目录，
并执行渲染后校验检查清单。

**Validation Levels:**
  - basic: file existence, JSON syntax, agent count (always run)
  - strict (--strict): adds cross-references, convergence observability, routing validation

用法:
    python render.py [--mode orchestrator-worker|peer-review-pair|sequential-pipeline]
                     [--plan artifacts/03-config-plan.md]
                     [--templates templates/]
                     [--output output/]
                     [--validate]
                     [--strict]

可选依赖（推荐安装）:
    pip install jinja2>=3.0

若 Jinja2 不可用，渲染器自动降级为 {{ variable }} 纯字符串替换。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# 可选 Jinja2 导入 —— 若不可用则优雅降级
# ---------------------------------------------------------------------------

try:
    from jinja2 import (Environment, FileSystemLoader, StrictUndefined,
                        Template, TemplateNotFound, UndefinedError)
    HAS_JINJA2: bool = True
except ImportError:
    HAS_JINJA2: bool = False

# =========================================================================
#  常量定义
# =========================================================================

MODE_NAMES: Tuple[str, ...] = (
    "orchestrator-worker",
    "peer-review-pair",
    "sequential-pipeline",
)

OUTPUT_FILES: Tuple[str, ...] = (
    "openclaw.json",
    "SOUL.md",
    "AGENTS.md",
    "IDENTITY.md",
    "TOOLS.md",
)

# 输出文件最小体积阈值（字节）
MIN_FILE_SIZES: Dict[str, int] = {
    "openclaw.json": 200,   # 至少包含骨架结构
    "SOUL.md":      50,     # 至少一个段落
    "AGENTS.md":    200,    # 收敛条件 + 路由规则
    "IDENTITY.md":  40,     # 身份声明
    "TOOLS.md":     40,     # 工具声明
}

# 每种模式的默认最大循环轮次
DEFAULT_MAX_CYCLES: Dict[str, int] = {
    "orchestrator-worker": 10,
    "peer-review-pair":     8,
    "sequential-pipeline":  5,
}

# 每种模式的默认收敛轮次
DEFAULT_CONVERGENCE_ROUNDS: Dict[str, int] = {
    "orchestrator-worker": 3,
    "peer-review-pair":     2,
    "sequential-pipeline":  1,   # 流水线由末尾 agent 判定收敛
}

DEFAULT_MAX_DURATION_MINUTES: int = 60


# =========================================================================
#  自定义异常
# =========================================================================

class RenderError(Exception):
    """渲染致命错误 —— 输出不可用。"""


class TemplateVariableError(RenderError):
    """必填模板变量缺失且无默认值。"""

    def __init__(self, var_name: str, context: str = ""):
        ctx = f" (在 {context} 中)" if context else ""
        super().__init__(f"缺少必填模板变量: {var_name}{ctx}")


class ValidationError(RenderError):
    """渲染后校验失败。"""


# =========================================================================
#  数据类（Dataclasses）
# =========================================================================

@dataclass
class AgentSpec:
    """从配置计划中提取的单个 agent 规格。

    Attributes:
        agent_id: Agent 唯一标识符。
        role: Agent 角色名（orchestrator / worker / reviewer / ...）。
        description: 职责描述。
        model: 使用的模型名。
        permissions: 权限配置（sessions_spawn, file_read 等）。
        tools: 可用工具列表。
        persona_traits: 人格特征列表。
        boundaries: 能力边界声明列表。
    """
    agent_id: str
    role: str
    description: str = ""
    model: str = ""
    permissions: Dict[str, Any] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    persona_traits: List[str] = field(default_factory=list)
    boundaries: List[str] = field(default_factory=list)


@dataclass
class ConfigPlan:
    """配置计划的结构化表示 (artifacts/03-config-plan.md)。

    Attributes:
        project_name: 项目名称。
        mode: Loop 拓扑模式。
        agents: Agent 规格列表。
        channels: OpenClaw Gateway 频道配置。
        convergence_criteria: 收敛条件结构。
        routing_rules: Agent 间路由规则。
        max_cycles: 最大循环轮次。
        max_duration_minutes: 最大运行时长（分钟）。
        convergence_rounds: 无新发现即收敛所需连续轮次。
        extra: 额外变量（透传自 --extra-vars）。
    """
    project_name: str = "loop-openclaw-default"
    mode: str = "orchestrator-worker"
    agents: List[AgentSpec] = field(default_factory=list)
    channels: List[Dict[str, Any]] = field(default_factory=list)
    convergence_criteria: Dict[str, Any] = field(default_factory=dict)
    routing_rules: List[Dict[str, Any]] = field(default_factory=list)
    max_cycles: int = 10
    max_duration_minutes: int = 60
    convergence_rounds: int = 3
    extra: Dict[str, Any] = field(default_factory=dict)


# =========================================================================
#  TemplateRegistry —— 模板变量注册表
# =========================================================================

class TemplateRegistry:
    """加载并解析模板变量注册表。

    注册表 (templates/template_registry.json) 定义了模板期望的每个变量
    —— 其类型、是否必填以及降级默认值。
    """

    def __init__(self, registry_path: Path):
        """初始化注册表并从 JSON 文件加载变量定义。

        Args:
            registry_path: template_registry.json 的文件路径。
        """
        self._path = registry_path
        self._raw: Dict[str, Any] = {}
        self._variables: Dict[str, Dict[str, Any]] = {}
        self._load()

    # -- 加载 ------------------------------------------------------------

    def _load(self) -> None:
        """从 JSON 文件加载变量注册表；若文件缺失则使用内建默认注册表。"""
        if not self._path.exists():
            # 文件缺失时构建内建注册表，保障渲染不被阻塞
            self._raw = self._builtin_registry()
        else:
            with open(self._path, "r", encoding="utf-8") as fh:
                self._raw = json.load(fh)
        self._variables = self._raw.get("variables", {})

    @staticmethod
    def _builtin_registry() -> Dict[str, Any]:
        """返回内建默认注册表，当 template_registry.json 未部署时使用。

        Returns:
            包含 20 个变量定义的字典。
        """
        return {
            "variables": {
                "project_name":           {"type": "str",  "required": True,  "default": None},
                "mode":                   {"type": "str",  "required": True,  "default": "orchestrator-worker"},
                "mode_description":       {"type": "str",  "required": True,  "default": ""},
                "agent_topology":         {"type": "list", "required": True,  "default": []},
                "agents":                 {"type": "list", "required": True,  "default": []},
                "channels":               {"type": "list", "required": True,  "default": [{"id": "default", "type": "console"}]},
                "convergence_criteria":   {"type": "dict", "required": True,  "default": {}},
                "convergence_rounds":     {"type": "int",  "required": False, "default": 3},
                "max_cycles":             {"type": "int",  "required": False, "default": 10},
                "max_duration_minutes":   {"type": "int",  "required": False, "default": 60},
                "routing_rules":          {"type": "list", "required": False, "default": []},
                "hard_stop_instructions": {"type": "str",  "required": False, "default": ""},
                "generated_at":           {"type": "str",  "required": False, "default": ""},
                "generator_version":      {"type": "str",  "required": False, "default": "1.0.0"},
                "orchestrator_id":        {"type": "str",  "required": False, "default": ""},
                "worker_ids":             {"type": "list", "required": False, "default": []},
                "completion_gate_text":   {"type": "str",  "required": False, "default": ""},
                "escape_detection_text":  {"type": "str",  "required": False, "default": ""},
                "model_provider":         {"type": "str",  "required": False, "default": "anthropic"},
                "model_name":             {"type": "str",  "required": False, "default": "claude-sonnet-4-20250514"},
                "temperature":            {"type": "num",  "required": False, "default": 0.7},
                "max_tokens":             {"type": "int",  "required": False, "default": 4096},
            }
        }

    # -- 解析变量 --------------------------------------------------------

    def resolve(self, plan: ConfigPlan, plan_vars: Dict[str, Any]) -> Dict[str, Any]:
        """将配置计划数据与额外变量合并为完整的变量字典，填充缺失默认值。

        若必填变量无法解析，抛出 ``TemplateVariableError``。

        Args:
            plan: 解析后的 ConfigPlan 实例。
            plan_vars: 来自 --extra-vars 的额外变量字典。

        Returns:
            合并后的完整变量字典，供模板渲染使用。

        Raises:
            TemplateVariableError: 当必填变量缺失且无默认值时。
        """
        resolved: Dict[str, Any] = {}

        # 从 plan 对象提取一切可用数据
        resolved["project_name"]       = plan.project_name
        resolved["mode"]               = plan.mode
        resolved["agents"]             = [self._agent_to_dict(a) for a in plan.agents]
        resolved["agent_topology"]     = resolved["agents"]
        resolved["channels"]           = plan.channels
        resolved["convergence_criteria"] = plan.convergence_criteria
        resolved["convergence_rounds"] = plan.convergence_rounds
        resolved["max_cycles"]         = plan.max_cycles
        resolved["max_duration_minutes"] = plan.max_duration_minutes
        resolved["routing_rules"]      = plan.routing_rules
        resolved["extra"]              = plan.extra
        resolved["generated_at"]       = datetime.now(timezone.utc).isoformat()

        # 模式感知默认值
        resolved.setdefault("mode_description", self._mode_description(plan.mode))
        resolved.setdefault("completion_gate_text",
                            self._completion_gate_text(plan.mode, plan.convergence_rounds))
        resolved.setdefault("escape_detection_text", self._escape_detection_text())
        resolved.setdefault("hard_stop_instructions",
                            self._hard_stop_text(plan.max_cycles, plan.max_duration_minutes))

        # 从 agent 列表派生 orchestrator / worker id
        orchestrator = next((a for a in plan.agents if "orchestrat" in a.role.lower()), None)
        resolved["orchestrator_id"] = orchestrator.agent_id if orchestrator else ""
        resolved["worker_ids"] = [
            a.agent_id for a in plan.agents
            if "orchestrat" not in a.role.lower()
        ]

        # 叠加额外变量
        resolved.update(plan_vars)

        # 从注册表填充仍缺失的键
        for var_name, spec in self._variables.items():
            if var_name not in resolved or resolved[var_name] is None:
                if spec.get("required"):
                    raise TemplateVariableError(var_name)
                resolved[var_name] = spec.get("default")

        # 最终兜底默认值
        resolved.setdefault("model_provider", "anthropic")
        resolved.setdefault("model_name", "claude-sonnet-4-20250514")
        resolved.setdefault("temperature", 0.7)
        resolved.setdefault("max_tokens", 4096)

        return resolved

    # -- 辅助方法 --------------------------------------------------------

    @staticmethod
    def _agent_to_dict(agent: AgentSpec) -> Dict[str, Any]:
        """将 AgentSpec 转换为字典。"""
        return {
            "id": agent.agent_id,
            "role": agent.role,
            "description": agent.description,
            "model": agent.model,
            "permissions": agent.permissions,
            "tools": agent.tools,
            "persona_traits": agent.persona_traits,
            "boundaries": agent.boundaries,
        }

    @staticmethod
    def _mode_description(mode: str) -> str:
        """返回指定模式的中文描述文本。"""
        descriptions = {
            "orchestrator-worker": (
                "Hub-and-spoke 拓扑：一个 Orchestrator agent 向 N 个 Worker agent "
                "分配任务，收集结果并判定收敛。"
            ),
            "peer-review-pair": (
                "双向审查拓扑：两个对等 agent 交替生产和审查，"
                "直到双方一致认为输出完整。"
            ),
            "sequential-pipeline": (
                "链式 Handoff 拓扑：N 个 agent 顺序执行阶段。"
                "末尾的质量检查 agent 决定收敛或回退到起点。"
            ),
        }
        return descriptions.get(mode, descriptions["orchestrator-worker"])

    @staticmethod
    def _completion_gate_text(mode: str, rounds: int) -> str:
        """根据模式和收敛轮次生成 Completion Gate 自然语言指令文本。

        Args:
            mode: Loop 拓扑模式。
            rounds: 收敛所需连续轮次。

        Returns:
            模式专属的收敛条件文本。
        """
        if mode == "orchestrator-worker":
            return (
                f"若连续 {rounds} 轮（即连续 {rounds} 次你分配任务并收集结果后）"
                "未发现任何新 P0/P1/P2 问题，且所有已知问题状态为\"已修复\""
                "或\"已验证\"，则判断任务完成。回复 "
                "\"CONVERGED: 任务完成。最终状态：[摘要]\""
            )
        elif mode == "peer-review-pair":
            return (
                f"若你在本轮审查中未发现任何 P0/P1/P2 问题，且上一轮对方的审查"
                "同样未发现任何问题（查看 history），则回复 "
                "\"CONVERGED: 双方审查一致通过。\""
            )
        else:  # sequential-pipeline
            return (
                "你是流水线末尾的质量检查 agent。在收到上一个 agent 的 handoff "
                "后：执行全面验证。若未发现任何 P0/P1/P2 问题 → 回复 "
                "\"CONVERGED: 流水线完成。所有阶段产出均通过验证。\""
            )

    @staticmethod
    def _escape_detection_text() -> str:
        """返回统一的逃逸检测自然语言指令。"""
        return (
            "如果你发现自己在重复执行相同的操作而没有进展"
            "（例如连续 2 轮的任务分配内容几乎相同），立即停止并回复："
            "\"ESCAPE_DETECTED: 检测到循环无进展。最近 2 轮的操作内容"
            "高度重复。建议人工介入。\""
        )

    @staticmethod
    def _hard_stop_text(max_cycles: int, max_duration: int) -> str:
        """生成硬止损 Markdown 文本。

        Args:
            max_cycles: 最大循环轮次。
            max_duration: 最大运行时长（分钟）。

        Returns:
            硬止损 Markdown 格式文本。
        """
        return (
            f"## 硬止损 (Hard Stop)\n\n"
            f"本章节的指令优先级最高。\n\n"
            f"1. **最大轮次：** 在第 {max_cycles} 轮结束时必须停止循环。\n"
            f"2. **最大时间：** 如果距离任务开始已超过 {max_duration} 分钟，"
            f"立即停止所有进行中的子任务。\n"
            f"3. **逃逸检测：** 连续 2 轮操作高度重复→停止。\n"
            f"4. **权限越界阻断：** 任何 agent 不得尝试提升自己的权限。\n"
        )


# =========================================================================
#  simple_render —— Jinja2 降级引擎（零依赖字符串替换）
# =========================================================================

def simple_render(template_text: str, variables: Dict[str, Any]) -> str:
    """将 ``{{ varname }}`` 占位符（及其点号访问变体如 ``{{ agent.id }}``、
    ``{{ convergence_criteria.key }}``）替换为 *variables* 中的值。

    这是 Jinja2 未安装时的零依赖降级方案。它**不**支持循环、条件渲染或过滤器
    —— 仅做纯变量替换。

    Args:
        template_text: 包含 ``{{ var }}`` 占位符的模板文本。
        variables: 变量名到值的映射字典。

    Returns:
        替换后的文本。
    """

    # -- 辅助函数：解析点号路径  -----------------------------------------
    def _resolve(path: str, scope: Dict[str, Any]) -> str:
        parts = path.strip().split(".")
        current: Any = scope
        for p in parts:
            if isinstance(current, dict):
                current = current.get(p, "")
            elif isinstance(current, list):
                try:
                    idx = int(p)
                    current = current[idx]
                except (ValueError, IndexError):
                    return f"{{{{ {path} }}}}"
            else:
                return f"{{{{ {path} }}}}"
        if isinstance(current, (dict, list)):
            try:
                return json.dumps(current, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                return str(current)
        return str(current) if current is not None else ""

    def _replacer(match: re.Match) -> str:
        inner = match.group(1).strip()
        # 处理 {{ var | tojson }} 管道语法
        if "|" in inner:
            varname = inner.split("|")[0].strip()
            return _resolve(varname, variables)
        return _resolve(inner, variables)

    return re.sub(r"\{\{\s*(.*?)\s*\}\}", _replacer, template_text)


# =========================================================================
#  TemplateRenderer —— 模板渲染主引擎
# =========================================================================

class TemplateRenderer:
    """读取模板，解析变量，写入渲染输出。

    Attributes:
        template_dir: 包含 *.j2 模板文件和 template_registry.json 的目录。
        output_dir: 渲染输出文件写入目录。
        registry: TemplateRegistry 实例。
    """

    def __init__(
        self,
        template_dir: Union[str, Path],
        output_dir: Union[str, Path],
        registry_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """初始化渲染器。

        Args:
            template_dir: 模板文件目录路径。
            output_dir: 输出目录路径。
            registry_path: template_registry.json 的显式路径。
                           默认为 ``template_dir / "template_registry.json"``。
        """
        self.template_dir = Path(template_dir)
        self.output_dir = Path(output_dir)
        self._registry_path = (
            Path(registry_path)
            if registry_path
            else self.template_dir / "template_registry.json"
        )
        self.registry = TemplateRegistry(self._registry_path)

        # Jinja2 环境（None => 使用 simple_render 降级）
        self._jinja_env: Optional[Environment] = None
        if HAS_JINJA2:
            self._jinja_env = Environment(
                loader=FileSystemLoader(str(self.template_dir)),
                undefined=StrictUndefined,
                trim_blocks=True,
                lstrip_blocks=True,
            )
            # 注册 tojson 过滤器，使模板可使用 {{ var | tojson }}
            self._jinja_env.filters["tojson"] = lambda v: json.dumps(
                v, ensure_ascii=False, indent=2
            )

        self._vars: Dict[str, Any] = {}
        self._mode: str = "orchestrator-worker"
        self._rendered: Dict[str, str] = {}

    # -- 公开 API --------------------------------------------------------

    def render_all(
        self,
        config_plan: ConfigPlan,
        mode: str = "orchestrator-worker",
        extra_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """渲染全部 5 个输出文件。

        Args:
            config_plan: 配置计划数据。
            mode: Loop 拓扑模式。
            extra_vars: 额外变量字典（覆盖默认值）。

        Returns:
            文件名 -> 渲染内容 的映射字典。
        """
        self._mode = self._validate_mode(mode)
        self._vars = self.registry.resolve(config_plan, extra_vars or {})
        self._ensure_output_dir()

        rendered: Dict[str, str] = {}

        rendered["openclaw.json"] = self.render_openclaw_json(config_plan, self._mode)
        rendered["SOUL.md"]       = self.render_soul_md(config_plan)
        rendered["AGENTS.md"]     = self.render_agents_md(
            config_plan, self._mode
        )
        rendered["IDENTITY.md"]   = self.render_identity_md(config_plan)
        rendered["TOOLS.md"]      = self.render_tools_md(config_plan)

        # 写入文件
        for filename, content in rendered.items():
            out_path = self.output_dir / filename
            out_path.write_text(content, encoding="utf-8")

        self._rendered = rendered
        return rendered

    def render_openclaw_json(self, plan: ConfigPlan, mode: str) -> str:
        """渲染 **openclaw.json** —— Gateway 主配置（JSON5 格式）。

        优先使用模板 ``openclaw.json.j2``。若模板缺失，则程序化构建 JSON。

        Args:
            plan: 配置计划。
            mode: Loop 模式。

        Returns:
            渲染后的 JSON5 文本。
        """
        template_name = "openclaw.json.j2"
        content = self._load_template_or_none(template_name)
        if content is not None:
            return self._render(content, template_name)

        # --- 降级：程序化构建 openclaw.json -----------------------------
        agents_list: List[Dict[str, Any]] = []
        for agent in plan.agents:
            agents_list.append({
                "id": agent.agent_id,
                "role": agent.role,
                "model": agent.model or self._vars.get("model_name", ""),
                "system_prompt": f"See SOUL.md, IDENTITY.md, TOOLS.md for {agent.agent_id}",
                "permissions": agent.permissions or {},
            })

        channels_list = plan.channels or [
            {"id": "default", "type": "console", "enabled": True}
        ]

        config = {
            "$schema": "https://openclaw.ai/schemas/gateway-config.json",
            "version": "1.0",
            "project": plan.project_name,
            "description": f"Loop configuration – mode: {mode}",
            "generated_by": "loop-openclaw render.py",
            "generated_at": self._vars.get("generated_at", ""),
            "agents": agents_list,
            "channels": channels_list,
            "routing": plan.routing_rules,
            "settings": {
                "max_cycles": plan.max_cycles,
                "convergence_rounds": plan.convergence_rounds,
                "max_duration_minutes": plan.max_duration_minutes,
            },
        }
        return (
            "// OpenClaw Gateway Configuration\n"
            "// Generated by loop-openclaw render.py\n"
            "// Mode: " + mode + "\n"
            "// Project: " + plan.project_name + "\n\n"
            + json.dumps(config, ensure_ascii=False, indent=2) + "\n"
        )

    def render_soul_md(self, plan: ConfigPlan) -> str:
        """渲染 **SOUL.md** —— agent 人格/灵魂定义文件。

        优先使用模板 ``SOUL.md.j2``。若模板缺失，则从 agent persona_traits 构建。

        Args:
            plan: 配置计划。

        Returns:
            渲染后的 Markdown 文本。
        """
        template_name = "SOUL.md.j2"
        content = self._load_template_or_none(template_name)
        if content is not None:
            return self._render(content, template_name)

        # --- 降级 -------------------------------------------------------
        lines: List[str] = [
            f"# SOUL.md – Agent Personas for {plan.project_name}",
            "",
            f"*Generated by loop-openclaw render.py*",
            f"*Mode: {self._mode}*",
            f"*Date: {self._vars.get('generated_at', '')}*",
            "",
            "---",
            "",
        ]
        for agent in plan.agents:
            lines.append(f"## Agent: {agent.agent_id} ({agent.role})")
            lines.append("")
            lines.append(f"**Description:** {agent.description or 'No description provided.'}")
            lines.append("")
            if agent.persona_traits:
                lines.append("**Persona Traits:**")
                for trait in agent.persona_traits:
                    lines.append(f"- {trait}")
                lines.append("")
            lines.append("**Tone & Behavior:**")
            lines.append("- Professional, precise, and focused on the assigned role.")
            lines.append("- Do not exceed the boundaries declared in IDENTITY.md.")
            lines.append("- Communicate clearly via the established routing rules.")
            lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines)

    def render_agents_md(
        self,
        plan: ConfigPlan,
        mode: str,
    ) -> str:
        """渲染 **AGENTS.md** —— 多 agent 编排指令文件（核心 loop 逻辑载体）。

        优先使用模板 ``AGENTS.md.j2``。若模板缺失，则程序化构建。

        Args:
            plan: 配置计划。
            mode: Loop 模式。

        Returns:
            渲染后的 Markdown 文本。
        """
        template_name = "AGENTS.md.j2"
        content = self._load_template_or_none(template_name)
        if content is not None:
            return self._render(content, template_name)

        # --- 降级 -------------------------------------------------------
        return self._build_agents_md(plan, mode)

    def render_identity_md(self, plan: ConfigPlan) -> str:
        """渲染 **IDENTITY.md** —— agent 身份声明文件。

        优先使用模板 ``IDENTITY.md.j2``。

        Args:
            plan: 配置计划。

        Returns:
            渲染后的 Markdown 文本。
        """
        template_name = "IDENTITY.md.j2"
        content = self._load_template_or_none(template_name)
        if content is not None:
            return self._render(content, template_name)

        # --- 降级 -------------------------------------------------------
        lines: List[str] = [
            f"# IDENTITY.md – Agent Identity Declarations for {plan.project_name}",
            "",
            "*Generated by loop-openclaw render.py*",
            "",
        ]
        for agent in plan.agents:
            lines.append(f"## {agent.agent_id}")
            lines.append("")
            lines.append(f"You are **{agent.agent_id}**, the **{agent.role}**.")
            lines.append(f"Your responsibility: {agent.description or 'Execute assigned tasks within your role boundary.'}")
            lines.append("")
            if agent.boundaries:
                lines.append("**Boundaries:**")
                for b in agent.boundaries:
                    lines.append(f"- {b}")
                lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines)

    def render_tools_md(self, plan: ConfigPlan) -> str:
        """渲染 **TOOLS.md** —— agent 工具声明文件。

        优先使用模板 ``TOOLS.md.j2``。

        Args:
            plan: 配置计划。

        Returns:
            渲染后的 Markdown 文本。
        """
        template_name = "TOOLS.md.j2"
        content = self._load_template_or_none(template_name)
        if content is not None:
            return self._render(content, template_name)

        # --- 降级 -------------------------------------------------------
        lines: List[str] = [
            f"# TOOLS.md – Agent Tool Declarations for {plan.project_name}",
            "",
            "*Generated by loop-openclaw render.py*",
            "",
        ]
        for agent in plan.agents:
            lines.append(f"## {agent.agent_id} – {agent.role}")
            lines.append("")
            if agent.tools:
                lines.append("**Permitted Tools:**")
                for tool in agent.tools:
                    lines.append(f"- `{tool}`")
                lines.append("")
            else:
                # 从 permissions 派生工具列表
                perms = agent.permissions
                if perms:
                    if perms.get("sessions_spawn"):
                        lines.append("- `sessions_spawn` – spawn sub-agent sessions")
                    if perms.get("sessions_send"):
                        lines.append("- `sessions_send` – send messages to other agents")
                    if perms.get("file_read"):
                        lines.append("- File system read")
                    if perms.get("file_write"):
                        lines.append("- File system write")
                    if perms.get("command_exec"):
                        lines.append("- Command execution")
                    lines.append("")
                else:
                    lines.append("*(No tools declared – check openclaw.json permissions)*")
                    lines.append("")
            lines.append("**Constraints:**")
            lines.append("- Use only the tools listed above.")
            lines.append("- Do not attempt to elevate permissions.")
            lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines)

    def validate_output(self) -> List[str]:
        """执行渲染后校验检查清单。

        执行 6 项校验:
          1. 全部 5 个输出文件存在且非空。
          2. ``openclaw.json`` 是合法的 JSON（或 JSON5 兼容解析）。
          3. Agent 拓扑一致性（AGENTS.md 中的 agent 在 openclaw.json 中均存在）。
          4. ``openclaw config validate`` CLI 命令（若可用）。
          5. 收敛条件被编码为可观测的指令。
          6. 路由规则引用的 agent id 均存在。

        Returns:
            校验消息列表（PASS/WARN/FAIL/SKIP 前缀）。
        """
        messages: List[str] = []
        output = self.output_dir

        # --- 1. 文件存在性与最小体积检查 ---------------------------------
        for filename in OUTPUT_FILES:
            fpath = output / filename
            if not fpath.exists():
                messages.append(f"[FAIL] Missing output file: {filename}")
                continue
            size = fpath.stat().st_size
            min_size = MIN_FILE_SIZES.get(filename, 40)
            if size < min_size:
                messages.append(
                    f"[WARN] {filename} is suspiciously small "
                    f"({size} bytes, expected >= {min_size})"
                )

        # --- 2. JSON 语法校验 --------------------------------------------
        json_path = output / "openclaw.json"
        if json_path.exists():
            raw = json_path.read_text(encoding="utf-8")
            # 去掉 JSON5 特性以兼容 stdlib json 解析器
            clean = self._strip_json5_features(raw)
            try:
                json.loads(clean)
                messages.append("[PASS] openclaw.json is valid JSON/JSON5.")
            except json.JSONDecodeError as exc:
                messages.append(f"[FAIL] openclaw.json JSON parse error: {exc}")

        # --- 3. Agent 拓扑一致性 -----------------------------------------
        if json_path.exists():
            config = self._load_json5(json_path)
            config_agents = {a.get("id", "") for a in config.get("agents", [])}
            for doc_name in ("SOUL.md", "AGENTS.md", "IDENTITY.md", "TOOLS.md"):
                doc_path = output / doc_name
                if not doc_path.exists():
                    continue
                doc_text = doc_path.read_text(encoding="utf-8")
                for agent_id in config_agents:
                    if agent_id and agent_id not in doc_text:
                        messages.append(
                            f"[WARN] Agent '{agent_id}' (in openclaw.json) "
                            f"not mentioned in {doc_name}"
                        )

        # --- 4. openclaw config validate（外部 CLI）----------------------
        try:
            result = subprocess.run(
                ["openclaw", "config", "validate", "--path", str(json_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                messages.append("[PASS] openclaw config validate succeeded.")
            else:
                messages.append(
                    f"[FAIL] openclaw config validate failed:\n{result.stderr.strip()}"
                )
        except FileNotFoundError:
            messages.append(
                "[SKIP] openclaw CLI not found – skipping external validation."
            )
        except subprocess.TimeoutExpired:
            messages.append("[WARN] openclaw config validate timed out.")

        # --- 5. 收敛条件可观测性 -----------------------------------------
        agents_md_path = output / "AGENTS.md"
        if agents_md_path.exists():
            agents_text = agents_md_path.read_text(encoding="utf-8")
            # 检查是否包含至少一种可观测模式
            observable_patterns = [
                r"连续\s*\d+\s*轮",
                r"consecutive\s*\d+\s*round",
                r"CONVERGED",
                r"P0.*P1.*P2",
                r"Completion Gate",
                r"convergence",
            ]
            found_any = any(
                re.search(pat, agents_text, re.IGNORECASE)
                for pat in observable_patterns
            )
            if found_any:
                messages.append(
                    "[PASS] AGENTS.md contains observable convergence criteria."
                )
            else:
                messages.append(
                    "[WARN] AGENTS.md may lack observable convergence criteria."
                )

        # --- 6. 路由规则交叉校验 -----------------------------------------
        if json_path.exists():
            config = self._load_json5(json_path)
            agent_ids = {a.get("id", "") for a in config.get("agents", [])}
            routing = config.get("routing", [])
            if isinstance(routing, list):
                for rule in routing:
                    src = rule.get("source", rule.get("from", ""))
                    tgt = rule.get("target", rule.get("to", ""))
                    if src and src not in agent_ids:
                        messages.append(
                            f"[FAIL] Routing source '{src}' is not a defined agent."
                        )
                    if tgt and tgt not in agent_ids:
                        messages.append(
                            f"[FAIL] Routing target '{tgt}' is not a defined agent."
                        )
            messages.append("[PASS] Routing rules cross-checked against agent list.")

        # 汇总统计
        fail_count = sum(1 for m in messages if m.startswith("[FAIL]"))
        warn_count = sum(1 for m in messages if m.startswith("[WARN]"))
        pass_count = sum(1 for m in messages if m.startswith("[PASS]"))
        messages.append(
            f"\n--- Validation summary: {pass_count} PASS, "
            f"{warn_count} WARN, {fail_count} FAIL ---"
        )

        return messages

    # -- 内部辅助方法 ----------------------------------------------------

    def _validate_mode(self, mode: str) -> str:
        """验证模式名；无效时回退到 orchestrator-worker。"""
        if mode not in MODE_NAMES:
            print(
                f"[WARN] Unknown mode '{mode}'. "
                f"Falling back to 'orchestrator-worker'.",
                file=sys.stderr,
            )
            return "orchestrator-worker"
        return mode

    def _ensure_output_dir(self) -> None:
        """确保输出目录存在。"""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _load_template_or_none(self, name: str) -> Optional[str]:
        """返回模板文本，若文件缺失则返回 None。"""
        path = self.template_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def _render(self, template_text: str, context_hint: str = "") -> str:
        """使用最佳可用引擎渲染模板文本。"""
        if self._jinja_env is not None:
            return self._render_jinja2(template_text, context_hint)
        return simple_render(template_text, self._vars)

    def _render_jinja2(self, template_text: str, context_hint: str = "") -> str:
        """用 Jinja2 编译并渲染模板。

        两阶段渲染策略：
        1. 先用 StrictUndefined 严格渲染，捕获模板中未定义的变量访问
        2. 若 StrictUndefined 抛出 UndefinedError，回退为宽容模式重试，
           未定义变量渲染为空字符串，同时输出警告供模板作者修复。
        """
        try:
            tmpl = self._jinja_env.from_string(template_text)  # type: ignore[union-attr]
            return tmpl.render(**self._vars)
        except UndefinedError as exc:
            # 严格模式失败 -> 以宽容 undefined 处理重试
            var_name = str(exc).split("'")[1] if "'" in str(exc) else str(exc)
            print(
                f"[WARN] StrictUndefined raised for '{var_name}' in "
                f"'{context_hint}'; retrying with forgiving undefined handling.",
                file=sys.stderr,
            )
            try:
                # 构建一个不设置 undefined 的临时环境（默认 Undefined 对
                # 未定义变量返回空字符串而非抛出异常）
                forgiving_env = Environment(
                    loader=self._jinja_env.loader,
                    trim_blocks=True,
                    lstrip_blocks=True,
                )
                forgiving_env.filters["tojson"] = self._jinja_env.filters["tojson"]
                tmpl = forgiving_env.from_string(template_text)
                return tmpl.render(**self._vars)
            except UndefinedError as exc2:
                var_name = str(exc2).split("'")[1] if "'" in str(exc2) else str(exc2)
                raise TemplateVariableError(var_name, context=context_hint) from exc2
        except Exception as exc:
            raise RenderError(
                f"Jinja2 render failed ({context_hint}): {exc}"
            ) from exc

    def _build_agents_md(self, plan: ConfigPlan, mode: str) -> str:
        """当模板缺失时，程序化构建 AGENTS.md。

        按三种模式分支生成不同的拓扑描述和通信协议。

        Args:
            plan: 配置计划。
            mode: Loop 模式。

        Returns:
            渲染后的 Markdown 文本。
        """
        sections: List[str] = [
            f"# AGENTS.md – Multi-Agent Orchestration for {plan.project_name}",
            "",
            f"*Generated by loop-openclaw render.py*",
            f"*Mode: {mode}*",
            f"*Date: {self._vars.get('generated_at', '')}*",
            "",
            "---",
            "",
            "## Agent Communication Protocol",
            "",
        ]

        # 按模式描述拓扑
        if mode == "orchestrator-worker":
            orchestrator = next(
                (a for a in plan.agents if "orchestrat" in a.role.lower()),
                plan.agents[0] if plan.agents else None,
            )
            workers = [a for a in plan.agents if a != orchestrator]
            oid = orchestrator.agent_id if orchestrator else "orchestrator"
            sections.append(
                f"**Topology:** Hub-and-spoke.  **{oid}** is the Orchestrator; "
            )
            sections.append(
                f"**Workers:** " + ", ".join(w.agent_id for w in workers) + "."
            )
            sections.append("")
            sections.append("- Orchestrator -> Worker: `sessions_spawn(worker_id, task_prompt)`")
            sections.append("- Worker -> Orchestrator: `sessions_send(orchestrator_id, result)`")
            sections.append("- Workers do NOT communicate directly.")
        elif mode == "peer-review-pair":
            if len(plan.agents) >= 2:
                a, b = plan.agents[0], plan.agents[1]
                sections.append(
                    f"**Topology:** Bidirectional review pair.  "
                    f"**{a.agent_id}** <-> **{b.agent_id}**."
                )
            else:
                sections.append("**Topology:** Bidirectional review pair (2 agents required).")
            sections.append("")
            sections.append("- Peer A produces -> `sessions_send(Peer_B, review_request)`")
            sections.append("- Peer B reviews -> `sessions_send(Peer_A, review_result)`")
        else:  # sequential-pipeline
            ids = [a.agent_id for a in plan.agents]
            sections.append(f"**Topology:** Chain handoff: {' -> '.join(ids)}.")
            sections.append("")
            sections.append("- Agent-N completes stage -> `sessions_send(Agent-N+1, handoff)`")
            sections.append("- Last agent detects issues -> `sessions_send(Agent-1, fallback)`")

        sections.extend([
            "",
            "---",
            "",
            "## Completion Gate (收敛条件)",
            "",
            self._vars.get("completion_gate_text", "*(No completion gate defined)*"),
            "",
            "## 硬止损 (Hard Stop)",
            "",
            self._vars.get("hard_stop_instructions", "*(No hard stop defined)*"),
            "",
            "## 逃逸检测 (Escape Detection)",
            "",
            self._vars.get("escape_detection_text", ""),
            "",
        ])

        return "\n".join(sections)

    @staticmethod
    def _strip_json5_features(text: str) -> str:
        """去除 JSON5 特性使 stdlib json 可解析。

        处理: // 和 /* */ 注释、尾部逗号、Windows 回车符。
        """
        # 统一换行符为 \n（去除 \r 避免 JSON 非法控制字符）
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        # 去除 /* */ 块注释
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        # 去除 // 行注释（注意避开 URL 中的 :// 和 JSON 字符串内的 //）
        lines = []
        for line in text.split('\n'):
            # 找到不在字符串内的第一个 //
            in_string = False
            comment_idx = -1
            i = 0
            while i < len(line):
                ch = line[i]
                if ch == '"' and (i == 0 or line[i-1] != '\\'):
                    in_string = not in_string
                elif ch == '/' and i+1 < len(line) and line[i+1] == '/' and not in_string:
                    # 确保不是 URL 中的 ://
                    if i == 0 or line[i-1] != ':':
                        comment_idx = i
                        break
                i += 1
            if comment_idx >= 0:
                lines.append(line[:comment_idx].rstrip())
            else:
                lines.append(line)
        text = '\n'.join(lines)
        # 去除 ] 或 } 前的尾部逗号
        text = re.sub(r',\s*([}\]])', r'\1', text)
        return text

    @staticmethod
    def _load_json5(path: Path) -> Dict[str, Any]:
        """加载 JSON5 文件并返回字典。"""
        raw = path.read_text(encoding="utf-8")
        clean = TemplateRenderer._strip_json5_features(raw)
        return json.loads(clean)


# =========================================================================
#  配置计划解析器 —— 读取 artifacts/03-config-plan.md
# =========================================================================

def parse_config_plan(plan_path: Union[str, Path]) -> ConfigPlan:
    """解析配置计划 Markdown 文件为结构化 ``ConfigPlan``。

    解析器查找已知的章节标题和键值对。若文件缺失或无法解析，
    返回带有默认值的最小 ConfigPlan，确保渲染器仍能产出可用的输出
    供下游手动编辑。

    Args:
        plan_path: 03-config-plan.md 的文件路径。

    Returns:
        解析后的 ConfigPlan 实例。
    """
    plan_path = Path(plan_path)
    plan = ConfigPlan()

    if not plan_path.exists():
        print(f"[WARN] Config plan not found: {plan_path}. Using defaults.",
              file=sys.stderr)
        return plan

    text = plan_path.read_text(encoding="utf-8")

    # --- 提取简单 key: value 键值对 -------------------------------------
    patterns = {
        "project_name":        r"project[_ ]name\s*[:=]\s*(.+?)(?:\n|$)",
        "mode":                r"(?:loop\s*)?mode\s*[:=]\s*(.+?)(?:\n|$)",
        "max_cycles":          r"max[_ ]cycles\s*[:=]\s*(\d+)",
        "max_duration_minutes": r"max[_ ]duration[_ ]minutes\s*[:=]\s*(\d+)",
        "convergence_rounds":   r"convergence[_ ]rounds\s*[:=]\s*(\d+)",
    }
    for attr, regex in patterns.items():
        m = re.search(regex, text, re.IGNORECASE)
        if m:
            value = m.group(1).strip()
            if attr in ("max_cycles", "max_duration_minutes", "convergence_rounds"):
                setattr(plan, attr, int(value))
            else:
                setattr(plan, attr, value)

    # 模式感知默认值
    if plan.mode in DEFAULT_MAX_CYCLES:
        plan.max_cycles = DEFAULT_MAX_CYCLES.get(plan.mode, plan.max_cycles)
    if plan.mode in DEFAULT_CONVERGENCE_ROUNDS:
        plan.convergence_rounds = DEFAULT_CONVERGENCE_ROUNDS.get(plan.mode, plan.convergence_rounds)

    # --- 提取 agent 块 --------------------------------------------------
    # 每个 agent 块以 "### Agent:" 或类似标题开头
    agent_blocks = re.split(r"\n(?=###\s+Agent\b)", text)
    for block in agent_blocks:
        agent = _parse_agent_block(block)
        if agent is not None:
            plan.agents.append(agent)

    # --- 提取 channels --------------------------------------------------
    channel_match = re.search(r"channels?\s*[:=]\s*(\[.*?\])", text, re.DOTALL | re.IGNORECASE)
    if channel_match:
        try:
            plan.channels = json.loads(channel_match.group(1))
        except json.JSONDecodeError:
            plan.channels = [{"id": "default", "type": "console"}]

    # --- 提取 convergence criteria --------------------------------------
    criteria: Dict[str, Any] = {}
    cc_section = _extract_section(text, "Convergence Criteria", "Convergence Gate")
    if cc_section:
        criteria["raw"] = cc_section.strip()
        for problem_level in ("P0", "P1", "P2"):
            if problem_level in cc_section:
                criteria[f"has_{problem_level}"] = True
    plan.convergence_criteria = criteria

    # --- 提取 routing rules ---------------------------------------------
    routing_section = _extract_section(text, "Routing", "Communication")
    if routing_section:
        for line in routing_section.splitlines():
            line = line.strip()
            if "->" in line or "→" in line:  # -> 或 →
                sep = "->" if "->" in line else "→"
                parts = line.split(sep)
                if len(parts) >= 2:
                    plan.routing_rules.append({
                        "source": parts[0].strip(),
                        "target": parts[1].strip(),
                    })

    return plan


def _parse_agent_block(block: str) -> Optional[AgentSpec]:
    """解析单个 agent 块并返回 AgentSpec，若无效则返回 None。

    从 Markdown agent 块中提取 agent_id、role、description、model、
    tools、permissions、persona_traits 和 boundaries。

    Args:
        block: agent 块的文本内容。

    Returns:
        解析后的 AgentSpec 实例，或 None（若块无法解析）。
    """
    if not block.strip().startswith("###"):
        return None

    # 提取 agent_id
    id_match = re.search(r"Agent\s*[:=]?\s*(\S+)", block)
    if not id_match:
        return None
    agent_id = id_match.group(1).rstrip(":")

    # 提取 role
    role_match = re.search(r"role\s*[:=]\s*(.+?)(?:\n|$)", block, re.IGNORECASE)
    role = role_match.group(1).strip() if role_match else "worker"

    # 提取 description
    desc_match = re.search(r"description\s*[:=]\s*(.+?)(?:\n|$)", block, re.IGNORECASE)
    description = desc_match.group(1).strip() if desc_match else ""

    # 提取 model
    model_match = re.search(r"model\s*[:=]\s*(.+?)(?:\n|$)", block, re.IGNORECASE)
    model = model_match.group(1).strip() if model_match else ""

    # 提取 tools（列表）
    tools_match = re.search(r"tools?\s*[:=]\s*\[(.*?)\]", block, re.DOTALL | re.IGNORECASE)
    tools: List[str] = []
    if tools_match:
        raw_tools = tools_match.group(1)
        tools = [t.strip().strip('"').strip("'") for t in raw_tools.split(",") if t.strip()]

    # 提取 persona traits（破折号列表）
    persona_match = re.search(
        r"(?:persona traits|traits)\s*[:=]?\s*\n((?:\s*-\s*.+\n?)+)",
        block, re.IGNORECASE,
    )
    traits: List[str] = []
    if persona_match:
        traits = [
            re.sub(r"^\s*-\s*", "", line).strip()
            for line in persona_match.group(1).splitlines()
            if line.strip().startswith("-")
        ]

    # 提取 boundaries
    boundaries_match = re.search(
        r"boundar(?:y|ies)\s*[:=]?\s*\n((?:\s*-\s*.+\n?)+)",
        block, re.IGNORECASE,
    )
    boundaries: List[str] = []
    if boundaries_match:
        boundaries = [
            re.sub(r"^\s*-\s*", "", line).strip()
            for line in boundaries_match.group(1).splitlines()
            if line.strip().startswith("-")
        ]

    # 提取 permissions
    perms: Dict[str, Any] = {}
    perm_match = re.search(r"permissions?\s*[:=]\s*(\{.*?\})", block, re.DOTALL | re.IGNORECASE)
    if perm_match:
        try:
            perms = json.loads(perm_match.group(1))
        except json.JSONDecodeError:
            pass

    return AgentSpec(
        agent_id=agent_id,
        role=role,
        description=description,
        model=model,
        tools=tools,
        persona_traits=traits,
        boundaries=boundaries,
        permissions=perms,
    )


def _extract_section(text: str, *keywords: str) -> str:
    """返回第一个 Markdown 标题包含任一关键词的章节内容，若无匹配则返回空字符串。

    Args:
        text: 完整的 Markdown 文档文本。
        *keywords: 用于匹配标题的关键词列表。

    Returns:
        匹配到的章节内容，去除首尾空白。
    """
    for kw in keywords:
        pattern = rf"##\s+[^\n]*{re.escape(kw)}[^\n]*\n(.*?)(?=\n##\s|\Z)"
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


# =========================================================================
#  渲染后校验报告（可打印格式）
# =========================================================================

def print_validation_report(messages: List[str]) -> None:
    """将校验报告以格式化方式打印到 stdout。

    Args:
        messages: validate_output() 返回的消息列表。
    """
    print()
    print("=" * 68)
    print("  POST-RENDER VALIDATION CHECKLIST")
    print("=" * 68)
    for msg in messages:
        if msg.startswith("[FAIL]"):
            prefix = "  FAIL "
        elif msg.startswith("[WARN]"):
            prefix = "  WARN "
        elif msg.startswith("[PASS]"):
            prefix = "  PASS "
        elif msg.startswith("[SKIP]"):
            prefix = "  SKIP "
        else:
            prefix = "       "
        print(f"{prefix}  {msg.removeprefix('[FAIL] ').removeprefix('[WARN] ').removeprefix('[PASS] ').removeprefix('[SKIP] ')}")
    print("=" * 68)

    fail_count = sum(1 for m in messages if m.startswith("[FAIL]"))
    if fail_count > 0:
        print(f"  RESULT: {fail_count} check(s) FAILED – review output before deployment.")
    else:
        print("  RESULT: All checks passed. Output is ready for deployment.")
    print()


# =========================================================================
#  独立校验函数 —— 不依赖 TemplateRenderer，可从模块级直接调用
# =========================================================================

@dataclass
class ValidationResult:
    """校验结果结构体。

    Attributes:
        passed: 是否通过校验。
        errors: 错误消息列表（阻断性问题）。
        warnings: 警告消息列表（非阻断性问题）。
        details: 额外详情字典。
    """
    passed: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


def validate_config_plan(plan: ConfigPlan) -> ValidationResult:
    """校验 ConfigPlan 的全部 10 个字段。

    检查 project_name、mode、agents、channels、convergence_criteria、
    routing_rules、max_cycles、max_duration_minutes、convergence_rounds
    和 extra 的合法性与完整性。

    Args:
        plan: 待校验的 ConfigPlan 实例。

    Returns:
        包含 passed/errors/warnings 的 ValidationResult。
    """
    result = ValidationResult()

    # 1. project_name
    if not plan.project_name or not plan.project_name.strip():
        result.errors.append("project_name 为空或缺失")
        result.passed = False
    elif not re.match(r'^[a-zA-Z0-9_-]+$', plan.project_name):
        result.warnings.append(
            f"project_name '{plan.project_name}' 包含非标准字符，建议仅用字母数字下划线连字符"
        )

    # 2. mode
    if plan.mode not in MODE_NAMES:
        result.errors.append(f"mode '{plan.mode}' 不在有效值 {MODE_NAMES} 中")
        result.passed = False

    # 3. agents
    if not plan.agents or len(plan.agents) < 2:
        result.errors.append(
            f"agents 数量不足（需要 >= 2，当前 {len(plan.agents)}）"
        )
        result.passed = False
    else:
        for agent in plan.agents:
            ar = validate_agent_spec(agent)
            if not ar.passed:
                result.errors.extend(ar.errors)
                result.passed = False
            result.warnings.extend(ar.warnings)

    # 4. channels
    if not plan.channels:
        result.warnings.append("channels 为空，将使用默认 console 频道")

    # 5. convergence_criteria
    if not plan.convergence_criteria:
        result.warnings.append("convergence_criteria 为空，收敛判定可能无法正确执行")

    # 6. routing_rules
    if not plan.routing_rules:
        result.warnings.append("routing_rules 为空，agent 间缺少显式路由规则")

    # 7-9. 数值边界
    for attr, label, vmin in [
        ("max_cycles", "max_cycles", 1),
        ("max_duration_minutes", "最大运行时长（分钟）", 1),
        ("convergence_rounds", "收敛轮次", 1),
    ]:
        val = getattr(plan, attr)
        if val < vmin:
            result.errors.append(f"{label} 必须 >= {vmin}（当前 {val}）")
            result.passed = False

    if plan.convergence_rounds > plan.max_cycles:
        result.errors.append(
            f"convergence_rounds ({plan.convergence_rounds}) 不能超过 max_cycles ({plan.max_cycles})"
        )
        result.passed = False

    # 10. 模式特定结构约束
    if plan.mode == "orchestrator-worker":
        orch_count = sum(
            1 for a in plan.agents if "orchestrat" in a.role.lower()
        )
        if orch_count != 1:
            result.errors.append(
                f"orchestrator-worker 模式需恰好 1 个 orchestrator（当前 {orch_count}）"
            )
            result.passed = False
    elif plan.mode == "peer-review-pair":
        if len(plan.agents) != 2:
            result.errors.append(
                f"peer-review-pair 模式需恰好 2 个 agent（当前 {len(plan.agents)}）"
            )
            result.passed = False

    return result


def validate_output_files(output_dir: Union[str, Path]) -> ValidationResult:
    """校验输出目录下的 5 个文件是否满足最小体积要求。

    逐文件检查存在性和字节数是否 >= MIN_FILE_SIZES 阈值。

    Args:
        output_dir: 包含渲染输出文件的目录路径。

    Returns:
        ValidationResult，每个文件标记 PASS/WARN/FAIL。
    """
    result = ValidationResult()
    output = Path(output_dir)

    for filename in OUTPUT_FILES:
        fpath = output / filename
        if not fpath.exists():
            result.errors.append(f"[FAIL] 输出文件缺失: {filename}")
            result.passed = False
            continue
        size = fpath.stat().st_size
        min_size = MIN_FILE_SIZES.get(filename, 40)
        if size < min_size:
            result.warnings.append(
                f"[WARN] {filename} 文件过小 ({size} bytes, 预期 >= {min_size})"
            )
        else:
            result.details[filename] = {"size": size, "min_size": min_size, "ok": True}

    return result


def validate_agent_spec(agent: AgentSpec) -> ValidationResult:
    """校验单个 AgentSpec 的所有字段。

    检查 agent_id 格式、role 合法性、permissions 一致性、
    model 非空等。

    Args:
        agent: 待校验的 AgentSpec 实例。

    Returns:
        ValidationResult，包含字段级别的错误和警告。
    """
    result = ValidationResult()

    # agent_id 校验
    if not agent.agent_id or not agent.agent_id.strip():
        result.errors.append("AgentSpec 缺少 agent_id")
        result.passed = False
    elif not re.match(r'^[a-z][a-z0-9_-]*$', agent.agent_id):
        result.errors.append(
            f"agent_id '{agent.agent_id}' 格式非法（须以小写字母开头，仅含字母数字下划线连字符）"
        )
        result.passed = False

    # role 校验
    known_roles = {"orchestrator", "worker", "reviewer",
                   "peer_a", "peer_b", "pipeline_stage"}
    if not agent.role:
        result.warnings.append(f"agent '{agent.agent_id}' 未指定 role")
    elif (agent.role.lower() not in known_roles
          and "orchestrat" not in agent.role.lower()):
        result.warnings.append(
            f"agent '{agent.agent_id}' role '{agent.role}' 不在已知角色列表中"
        )

    # description 校验
    if not agent.description:
        result.warnings.append(f"agent '{agent.agent_id}' 缺少 description")

    # model 校验
    if not agent.model:
        result.warnings.append(
            f"agent '{agent.agent_id}' 未指定 model，将使用全局默认值"
        )

    # permissions 类型校验
    perms = agent.permissions
    if isinstance(perms, dict):
        for key in ("sessions_spawn", "sessions_send"):
            targets = perms.get(key, [])
            if targets and not isinstance(targets, list):
                result.errors.append(
                    f"agent '{agent.agent_id}' {key} 须为数组类型"
                )
                result.passed = False

    return result


def validate_cross_references(plan: ConfigPlan) -> ValidationResult:
    """校验 routing_rules 和 permissions 中引用的 agent_id 确实存在。

    检查 routing_rules 中的 source/from 和 target/to 是否对应已定义的 agent，
    以及 sessions_send/sessions_spawn 目标是否均为已知 agent。

    Args:
        plan: 包含 agents 和 routing_rules 的 ConfigPlan 实例。

    Returns:
        ValidationResult，缺失引用记录为 errors。
    """
    result = ValidationResult()
    agent_ids = {a.agent_id for a in plan.agents}

    if not agent_ids:
        result.errors.append("agents 列表为空，无法执行交叉引用校验")
        result.passed = False
        return result

    # 校验 routing_rules 中的引用
    for i, rule in enumerate(plan.routing_rules):
        if isinstance(rule, dict):
            src = rule.get("source", rule.get("from", ""))
            tgt = rule.get("target", rule.get("to", ""))
            if src and src not in agent_ids:
                result.errors.append(
                    f"routing_rules[{i}]: source '{src}' 未在 agents 中定义"
                )
                result.passed = False
            if tgt and tgt not in agent_ids:
                result.errors.append(
                    f"routing_rules[{i}]: target '{tgt}' 未在 agents 中定义"
                )
                result.passed = False

    # 校验每个 agent 的 permissions 引用
    for agent in plan.agents:
        perms = agent.permissions
        if isinstance(perms, dict):
            for key in ("sessions_send", "sessions_spawn"):
                targets = perms.get(key, [])
                if isinstance(targets, list):
                    for target in targets:
                        if target and target not in agent_ids:
                            result.errors.append(
                                f"agent '{agent.agent_id}' {key} 引用不存在的 '{target}'"
                            )
                            result.passed = False

    # 校验 channels inbound.default_agent
    for ch in plan.channels:
        if isinstance(ch, dict):
            routing = ch.get("routing_rules", {})
            if isinstance(routing, dict):
                inbound = routing.get("inbound", {})
                if isinstance(inbound, dict):
                    default_agent = inbound.get("default_agent", "")
                    if default_agent and default_agent not in agent_ids:
                        result.warnings.append(
                            f"channel inbound.default_agent '{default_agent}' 未在 agents 中定义"
                        )

    return result


def run_validate_only(
    output_dir: Union[str, Path],
    plan: Optional[ConfigPlan] = None,
) -> List[str]:
    """执行仅校验模式：跳过渲染，直接校验已有输出文件。

    此函数专为 --validate-only CLI 标志设计。

    Args:
        output_dir: 输出文件目录。
        plan: 可选的 ConfigPlan（用于 agent 和交叉引用校验）。

    Returns:
        标准格式的校验消息列表（PASS/WARN/FAIL/SKIP 前缀）。
    """
    messages: List[str] = []
    output = Path(output_dir)

    # 输出文件存在性与体积校验
    file_result = validate_output_files(output)
    for err in file_result.errors:
        messages.append(err)
    for warn in file_result.warnings:
        messages.append(warn)

    # JSON 语法校验
    json_path = output / "openclaw.json"
    if json_path.exists():
        raw = json_path.read_text(encoding="utf-8")
        clean = TemplateRenderer._strip_json5_features(raw)
        try:
            json.loads(clean)
            messages.append("[PASS] openclaw.json 是合法 JSON/JSON5")
        except json.JSONDecodeError as exc:
            messages.append(f"[FAIL] openclaw.json JSON 解析错误: {exc}")

    # ConfigPlan 校验（若提供）
    if plan is not None:
        plan_result = validate_config_plan(plan)
        for err in plan_result.errors:
            messages.append(f"[FAIL] {err}")
        for warn in plan_result.warnings:
            messages.append(f"[WARN] {warn}")

        # 交叉引用校验
        xref_result = validate_cross_references(plan)
        for err in xref_result.errors:
            messages.append(f"[FAIL] {err}")
        for warn in xref_result.warnings:
            messages.append(f"[WARN] {warn}")

    # 汇总
    fail_count = sum(1 for m in messages if m.startswith("[FAIL]"))
    pass_count = sum(1 for m in messages if m.startswith("[PASS]"))
    warn_count = sum(1 for m in messages if m.startswith("[WARN]"))
    messages.append(
        f"\n--- Validate-only summary: {pass_count} PASS, "
        f"{warn_count} WARN, {fail_count} FAIL ---"
    )

    return messages


# =========================================================================
#  main() —— CLI 入口
# =========================================================================

def main(argv: Optional[List[str]] = None) -> int:
    """独立 CLI 入口。

    用法::

        python render.py \\
            --mode orchestrator-worker \\
            --plan artifacts/03-config-plan.md \\
            --templates templates/ \\
            --output output/ \\
            --validate

    Args:
        argv: 命令行参数列表（默认 sys.argv[1:]）。

    Returns:
        进程退出码: 0=成功, 1=CLI参数错误, 2=模板变量缺失, 3=渲染错误, 4=校验失败。
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Loop-OpenClaw Configuration Renderer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              python render.py --mode orchestrator-worker
              python render.py --plan artifacts/03-config-plan.md --validate
              python render.py --templates templates/ --output output/ --mode peer-review-pair
        """),
    )
    parser.add_argument(
        "--mode", "-m",
        choices=MODE_NAMES,
        default="orchestrator-worker",
        help="Loop 模式 (默认: orchestrator-worker)",
    )
    parser.add_argument(
        "--plan", "-p",
        default="artifacts/03-config-plan.md",
        help="配置计划 Markdown 文件路径 (默认: artifacts/03-config-plan.md)",
    )
    parser.add_argument(
        "--templates", "-t",
        default="templates/",
        help="包含 .j2 模板文件的目录 (默认: templates/)",
    )
    parser.add_argument(
        "--output", "-o",
        default="output/",
        help="渲染文件输出目录 (默认: output/)",
    )
    parser.add_argument(
        "--registry", "-r",
        default=None,
        help="template_registry.json 路径 (默认: <templates>/template_registry.json)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="执行渲染后校验检查清单 (默认: True)",
    )
    parser.add_argument(
        "--no-validate",
        action="store_false",
        dest="validate",
        help="跳过渲染后校验",
    )
    parser.add_argument(
        "--extra-vars",
        default=None,
        help="额外模板变量的 JSON 字符串 (如 '{\"key\":\"val\"}')",
    )
    parser.add_argument(
        "--extra-vars-file",
        default=None,
        help="包含额外模板变量的 JSON 文件路径",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        default=False,
        help="跳过渲染，仅执行输出目录及配置计划校验（不调用 render_all）",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="严格校验模式：额外检查模板变量完整性、输出文件内容质量、agent 权限深度等",
    )

    args = parser.parse_args(argv)

    # 解析路径（相对于项目根目录，即 Creative.txt 所在目录）
    template_dir = Path(args.templates)
    output_dir = Path(args.output)
    plan_path = Path(args.plan)
    registry_path = Path(args.registry) if args.registry else None

    # --- 仅校验模式：跳过渲染 -------------------------------------------
    if args.validate_only:
        print(f"Validate-only mode: checking {output_dir.resolve()}")
        plan = parse_config_plan(plan_path) if plan_path.exists() else None
        if plan and plan.agents:
            print(f"  Plan loaded: mode={plan.mode}, agents={len(plan.agents)}")
        else:
            plan = None
        messages = run_validate_only(output_dir, plan=plan)
        print_validation_report(messages)
        fail_count = sum(1 for m in messages if m.startswith("[FAIL]"))
        return 4 if fail_count > 0 else 0

    # --- 解析额外变量 ---------------------------------------------------
    extra_vars: Dict[str, Any] = {}
    if args.extra_vars:
        try:
            extra_vars.update(json.loads(args.extra_vars))
        except json.JSONDecodeError as exc:
            print(f"[ERROR] Invalid --extra-vars JSON: {exc}", file=sys.stderr)
            return 1
    if args.extra_vars_file:
        try:
            extra_vars.update(
                json.loads(Path(args.extra_vars_file).read_text(encoding="utf-8"))
            )
        except (json.JSONDecodeError, FileNotFoundError) as exc:
            print(f"[ERROR] --extra-vars-file: {exc}", file=sys.stderr)
            return 1

    # --- 解析配置计划 ---------------------------------------------------
    print(f"Reading config plan: {plan_path.resolve()}")
    plan = parse_config_plan(plan_path)
    print(f"  Mode:            {plan.mode}")
    print(f"  Agents:          {len(plan.agents)}")
    print(f"  Max cycles:      {plan.max_cycles}")
    print(f"  Conv. rounds:    {plan.convergence_rounds}")

    # --- 渲染 -----------------------------------------------------------
    print(f"\nRendering with{' ' if HAS_JINJA2 else 'out '}Jinja2...")
    if HAS_JINJA2:
        try:
            import jinja2 as _j2
            engine_str = f"Jinja2 {getattr(_j2, '__version__', '')}"
        except Exception:
            engine_str = "Jinja2"
    else:
        engine_str = "simple string replacement (fallback)"
    print(f"  Template engine: {engine_str}")

    renderer = TemplateRenderer(
        template_dir=template_dir,
        output_dir=output_dir,
        registry_path=registry_path,
    )

    try:
        results = renderer.render_all(plan, mode=args.mode, extra_vars=extra_vars)
    except TemplateVariableError as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        return 2
    except RenderError as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        return 3

    print(f"\nRendered {len(results)} file(s):")
    for fname in sorted(results):
        fpath = output_dir / fname
        size = fpath.stat().st_size if fpath.exists() else 0
        print(f"  {fname:<20s}  {size:>6d} bytes")

    # --- 校验 -----------------------------------------------------------
    if args.validate:
        print("\nRunning validation checklist...")
        messages = renderer.validate_output()
        print_validation_report(messages)

        fail_count = sum(1 for m in messages if m.startswith("[FAIL]"))
        if fail_count > 0:
            return 4

    # --- 严格校验模式 (--strict) ----------------------------------------
    if args.strict:
        print("\n" + "=" * 68)
        print("  STRICT VALIDATION (enhanced checks)")
        print("=" * 68)

        strict_issues = 0

        # 1. 未解析占位符检测：扫描所有输出文件，查找残留的 {{ }} 模板标记
        for fname in sorted(results):
            content = results[fname]
            unresolved = re.findall(r'\{\{\s*\w+(?:\.\w+)*\s*\}\}', content)
            if unresolved:
                unique = sorted(set(unresolved))
                print(f"  [WARN] {fname}: 发现 {len(unresolved)} 处未解析占位符 "
                      f"({len(unique)} 种): {', '.join(unique[:5])}"
                      f"{'...' if len(unique) > 5 else ''}")
                strict_issues += 1

        # 2. 模板变量使用率检测：registry 中定义的变量是否在至少一个 .j2 模板中被引用
        template_files = list(Path(args.templates).glob("*.j2"))
        if template_files and hasattr(renderer.registry, '_variables'):
            all_template_text = ""
            for tf in template_files:
                all_template_text += tf.read_text(encoding="utf-8")
            unused_vars = []
            for var_name in renderer.registry._variables:
                if f"{{{{ {var_name} }}}}" not in all_template_text and \
                   f"{{{{ {var_name}." not in all_template_text and \
                   f"{{{{ {var_name}|" not in all_template_text:
                    unused_vars.append(var_name)
            if unused_vars:
                print(f"  [INFO] registry 中有 {len(unused_vars)} 个变量未在任何 .j2 模板中使用: "
                      f"{', '.join(unused_vars[:10])}"
                      f"{'...' if len(unused_vars) > 10 else ''}")
            else:
                print(f"  [PASS] 所有 {len(renderer.registry._variables)} 个 registry 变量均在模板中被引用")

        # 3. 输出文件内容完整性：AGENTS.md 和 openclaw.json 关键 content 检查
        agents_md = results.get("AGENTS.md", "")
        if agents_md:
            if "Completion Gate" not in agents_md and "收敛条件" not in agents_md:
                print("  [WARN] AGENTS.md 缺少 Completion Gate / 收敛条件 章节")
                strict_issues += 1
            if "Hard Stop" not in agents_md and "硬止损" not in agents_md:
                print("  [WARN] AGENTS.md 缺少 Hard Stop / 硬止损 章节")
                strict_issues += 1

        openclaw_json = results.get("openclaw.json", "")
        if openclaw_json:
            if '"agents"' not in openclaw_json and '"agents"' not in openclaw_json:
                print("  [FAIL] openclaw.json 不包含 agents 数组")
                strict_issues += 1
            if '"routing"' not in openclaw_json and '"routing"' not in openclaw_json:
                print("  [WARN] openclaw.json 缺少 routing 配置")
                strict_issues += 1

        # 4. Agent 权限深度检查：验证每个 worker agent 没有 sessions_spawn 权限
        for agent in plan.agents:
            if "orchestrat" not in agent.role.lower():
                spawns = agent.permissions.get("sessions_spawn", [])
                if spawns:
                    print(f"  [WARN] Worker agent '{agent.agent_id}' 拥有 sessions_spawn 权限 "
                          f"-> {spawns}（在 orchestrator-worker 模式中不应存在）")
                    strict_issues += 1

        if strict_issues == 0:
            print("  RESULT: All strict checks passed.")
        else:
            print(f"  RESULT: {strict_issues} strict warning(s) found. "
                  f"Review before production deployment.")
        print("=" * 68)

    print("Done.")
    return 0


# =========================================================================
#  Jinja2 可用性辅助函数（供外部使用）
# =========================================================================

def render_engine_info() -> Dict[str, Any]:
    """返回描述当前渲染引擎的字典。

    Returns:
        包含 jinja2_available、engine、fallback 等键的字典。
    """
    info: Dict[str, Any] = {
        "jinja2_available": HAS_JINJA2,
        "fallback": "simple-string-replacement",
    }
    if HAS_JINJA2:
        try:
            import jinja2 as _j2
            info["jinja2_version"] = getattr(_j2, "__version__", "unknown")
            info["engine"] = "jinja2"
        except Exception:
            info["engine"] = "simple-string-replacement"
    else:
        info["engine"] = "simple-string-replacement"
    return info


# =========================================================================
#  __main__ 守护
# =========================================================================

if __name__ == "__main__":
    sys.exit(main())
