"""loop-openclaw 端到端测试包。提供共享的配置计划加载工具。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from render import AgentSpec, ConfigPlan  # noqa: E402


def load_plan_from_json(filename: str) -> ConfigPlan:
    """从 artifacts/ 目录加载 JSON 配置计划文件并转为 ConfigPlan。

    Args:
        filename: JSON 文件名（不含路径），如 "03-config-plan-example-a.json"。

    Returns:
        包含所有 agent、routing rules、convergence criteria 的 ConfigPlan。
    """
    data = json.loads(
        (_PROJECT_ROOT / "artifacts" / filename).read_text(encoding="utf-8")
    )
    agents = [
        AgentSpec(
            agent_id=a["agent_id"], role=a["role"],
            description=a.get("description", ""), model=a.get("model", ""),
            permissions=a.get("permissions", {}), tools=a.get("tools", []),
            persona_traits=a.get("persona_traits", []),
            boundaries=a.get("boundaries", []),
        )
        for a in data["agents"]
    ]
    return ConfigPlan(
        project_name=data["project_name"], mode=data["mode"],
        agents=agents, channels=data.get("channels", []),
        convergence_criteria=data.get("convergence_criteria", {}),
        routing_rules=data.get("routing_rules", []),
        max_cycles=data.get("max_cycles", 10),
        max_duration_minutes=data.get("max_duration_minutes", 60),
        convergence_rounds=data.get("convergence_rounds", 3),
        extra=data.get("extra", {}),
    )
