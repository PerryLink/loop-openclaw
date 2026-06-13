{# ============================================================ #}
{# IDENTITY.md.j2 — Agent 身份声明模板                       #}
{# 定义每个 agent 的身份：名称、角色、核心职责、能力边界       #}
{# 在每次对话开始时注入                                       #}
{# ============================================================ #}

# IDENTITY.md — Agent 身份声明

> 本文档定义了 {{ project_name }} 项目中所有 agent 的身份。
> **在每次对话开始时注入**，确保 agent 清楚自己的角色和能力边界。
> Loop 模式：{{ loop_mode_display_name }} | 收敛要求：连续 {{ convergence_rounds }} 轮零新发现

---

{% for agent in agents %}
## Agent: {{ agent.id }}

### 基本信息

| 属性 | 值 |
|------|-----|
| **名称** | {{ agent.name }} |
| **ID** | `{{ agent.id }}` |
| **角色** | {{ agent.role_display }} |
| **Loop 位置** | {{ agent.loop_position | default(agent.role_display) }} |
| **模型** | {{ agent.model | default('claude-sonnet-4-20250514') }} |
{% if loop_mode == "orchestrator_worker" %}
{% if agent.role == "orchestrator" %}
| **下属 Worker** | {{ workers | map(attribute='id') | join(', ') }} |
{% elif agent.role == "worker" %}
| **上级 Orchestrator** | {{ orchestrator.id }} |
{% endif %}
{% elif loop_mode == "peer_review_pair" %}
| **审查对方** | {{ peer_partner_id }} |
{% elif loop_mode == "sequential_pipeline" %}
{% if not loop.last %}
| **下游 Agent** | {{ agents[loop.index].id }} |
{% endif %}
{% if not loop.first %}
| **上游 Agent** | {{ agents[loop.index0 - 1].id }} |
{% endif %}
{% endif %}

### 核心职责

{% for duty in agent.identity.core_duties %}
{{ loop.index }}. {{ duty }}
{% endfor %}

### 能力清单（你能做什么）

{% for capability in agent.identity.capabilities | default([]) %}
- {{ capability }}
{% endfor %}

### 能力边界（你不能做什么）

> **以下是你绝对不能做的事。违反任何一条即为越权操作。**

{% for limitation in agent.identity.limitations | default([]) %}
{{ loop.index }}. {{ limitation }}
{% endfor %}

### 你的输入

{% for input_desc in agent.identity.inputs | default([]) %}
- {{ input_desc }}
{% endfor %}

### 你的输出

{% for output_desc in agent.identity.outputs | default([]) %}
- {{ output_desc }}
{% endfor %}

### 质量承诺

{% for commitment in agent.identity.quality_commitments | default([
  '每次产出附带自检结果（P0/P1/P2 分类）',
  '每次判断附带证据引用',
  '每次 handoff 附带完整的上下文摘要'
]) %}
{{ loop.index }}. {{ commitment }}
{% endfor %}

{% if not loop.last %}
---
{% endif %}
{% endfor %}

---

## Loop 角色关系速查

{% if loop_mode == "orchestrator_worker" %}
```
{{ orchestrator.id }} (Orchestrator)
  ├── 分配任务 →
{% for worker in workers %}
  ├── {{ worker.id }} ({{ worker.role_display }})
{% endfor %}
  └── ← 提交结果
```
{% elif loop_mode == "peer_review_pair" %}
```
{{ agents[0].id }} (Peer A)  ⇄  {{ agents[1].id }} (Peer B)
  产出 → 审查 → 修复 → 审查 → ... → CONVERGED
```
{% elif loop_mode == "sequential_pipeline" %}
```
{% for agent in agents %}
{{ agent.id }} ({{ agent.role_display }}){% if not loop.last %} → {% endif %}
{% endfor %}
  回退路径: {{ agents | last | map(attribute='id') | first | default(agents[-1].id) }} → {{ agents[0].id }}
```
{% endif %}
