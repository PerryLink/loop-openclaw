{# ============================================================ #}
{# TOOLS.md.j2 — Agent 可用工具申明模板                        #}
{# 定义每个 agent 可用的工具列表及使用约束                     #}
{# 限制 agent 只能使用列出的工具，避免权限漂移                 #}
{# ============================================================ #}

# TOOLS.md — Agent 工具声明

> 本文档定义了 {{ project_name }} 项目中所有 agent 可用的工具。
> **每个 agent 只能使用本文档中为其列出的工具。**
> 使用未列出的工具即为权限越界——见 AGENTS.md 第 6.4 节。

---

## 工具使用总则

以下规则适用于所有 agent 的所有工具使用：

1. **白名单原则：** 只能使用下文"你的工具"节中列出的工具。未列出的工具禁止使用。
2. **按需使用：** 不要为了"试试看"而调用工具——每次工具调用必须有明确的业务目的。
3. **最小权限：** 在满足需求的前提下，优先使用权限最小的工具（如：能用 read 就不用 execute）。
4. **使用记录：** 关键工具调用（文件写入、代码执行、网络请求）在使用后记录到 LOOP STATE 状态块中。
5. **错误处理：** 工具调用失败时，报告错误信息并根据严重度分类（P0=工具不可用导致核心路径阻塞，P1=工具部分失败可降级，P2=非关键工具失败）。

---

{% for agent in agents %}
## {{ agent.id }} — {{ agent.name }}

### 角色工具需求概述

{{ agent.tools.overview | default(agent.role_display + ' agent。仅需 ' + (agent.tools.list | default([]) | length | string) + ' 个工具即可完成其职责。') }}

### 你的工具

{% if agent.tools.list %}
| 工具名 | 用途 | 调用频率 | 注意事项 |
|--------|------|----------|----------|
{% for tool in agent.tools.list %}
| `{{ tool.name }}` | {{ tool.purpose }} | {{ tool.frequency | default('按需') }} | {{ tool.notes | default('无特殊注意事项') }} |
{% endfor %}
{% else %}
| 工具名 | 用途 | 调用频率 | 注意事项 |
|--------|------|----------|----------|
| _此 agent 当前未分配工具_ | — | — | 若这不符合预期，请检查 openclaw.json 中的 permissions 配置。 |
{% endif %}

### 工具使用约束

{% for constraint in agent.tools.constraints | default([]) %}
{{ loop.index }}. {{ constraint }}
{% endfor %}

### 禁止使用的工具

{% if agent.tools.blocked | default([]) | length > 0 %}
以下工具**严禁使用**。若因业务需要确实需要使用，向 Orchestrator/上游 agent 提出请求，由具备权限的 agent 代为执行：

| 禁止工具 | 原因 | 替代方案 |
|----------|------|----------|
{% for blocked in agent.tools.blocked %}
| `{{ blocked.name }}` | {{ blocked.reason }} | {{ blocked.alternative | default('向上游 agent 请求代为执行') }} |
{% endfor %}
{% else %}
_此 agent 无非标准工具禁令。标准禁令（修改 openclaw.json、权限提升等）见 AGENTS.md 第 6.4 节。_
{% endif %}

{% if not loop.last %}
---
{% endif %}
{% endfor %}

---

## 工具权限对照表（交叉校验用）

对照 openclaw.json 中的 permissions 字段验证以下映射是否正确：

| Agent ID | File Read | File Write | Code Execute | Network | sessions_send | sessions_spawn |
|----------|-----------|------------|--------------|---------|---------------|----------------|
{% for agent in agents %}
| `{{ agent.id }}` | {{ agent.capabilities.can_read_files | default(true) }} | {{ agent.capabilities.can_write_files | default(false) }} | {{ agent.capabilities.can_execute_code | default(false) }} | {{ agent.capabilities.can_search_web | default(false) }} | {{ (agent.permissions.sessions_send if agent.permissions is defined else []) | length }} targets | {{ (agent.permissions.sessions_spawn if agent.permissions is defined else []) | length }} targets |
{% endfor %}

> **交叉校验说明：** 此表应与 openclaw.json 中的 `agents.<id>.permissions` 和 `agents.<id>.capabilities` 字段完全一致。
> 若发现不一致，以 openclaw.json 中的技术强制限制为准——TOOLS.md 是声明性的，openclaw.json 是强制性的。
