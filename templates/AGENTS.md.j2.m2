{# ============================================================ #}
{# AGENTS.md.j2 — 多 Agent 编排指令模板                        #}
{# 包含 Completion Gate（收敛条件）、路由规则、硬止损指令        #}
{# 支持三种 loop 模式：orchestrator_worker / peer_review_pair    #}
{#   / sequential_pipeline                                      #}
{# ============================================================ #}
{# 顶层变量定义——确保在后续所有块中可用                        #}
{% if loop_mode == "sequential_pipeline" %}{% set last_agent = agents | last %}{% endif %}
{% if loop_mode == "orchestrator_worker" %}{% set orchestrator = agents | selectattr("role", "equalto", "orchestrator") | first %}{% set workers = agents | selectattr("role", "equalto", "worker") | list %}{% endif %}

# AGENTS.md — 多 Agent 编排指令

> 本文档定义了 {{ project_name }} 项目中所有 agent 的协作协议。
> 包括通信规范、收敛条件、回退路由、硬止损。
> **每个 agent 必须在每轮操作后阅读并执行本章节的收敛判定。**

---

## 1. 项目概述

**项目名称：** {{ project_name }}
**Loop 模式：** {{ loop_mode_display_name }}
**参与 Agent：** {{ agents | length }} 个
**收敛目标：** {{ convergence_goal }}
**最多轮次：** {{ max_cycles }}
**最多时长：** {{ max_duration_minutes }} 分钟

---

## 2. Agent 角色与职责

| Agent ID | 角色 | 职责 | 通信权限 |
|----------|------|------|----------|
{% for agent in agents %}
| `{{ agent.id }}` | {{ agent.role_display }} | {{ agent.responsibility }} | {% if agent.permissions is defined and agent.permissions.sessions_send %}发送至 {{ agent.permissions.sessions_send | join(', ') }}{% else %}无{% endif %}{% if agent.permissions is defined and agent.permissions.sessions_spawn %}；派生子任务至 {{ agent.permissions.sessions_spawn | join(', ') }}{% endif %} |
{% endfor %}

---

## 3. 通信协议

### 3.1 消息格式标准

所有 agent 间通信（sessions_send / sessions_spawn）必须使用以下 Markdown 标记块格式：

```markdown
:::agent-message
**FROM:** [agent_id]
**TO:** [agent_id]
**TYPE:** [TASK_ASSIGN | RESULT | REVIEW | HANDOFF | FALLBACK | CONVERGED | HARD_STOP]
**ROUND:** [round_number]
**PRIORITY:** [P0 | P1 | P2 | INFO]

[消息正文——结构化内容]

**EVIDENCE:** [支持结论的证据/引用]
:::
```

### 3.2 消息确认协议

- 接收方在收到消息后 {{ message_ack_timeout_seconds }} 秒内回复确认。
- 若发送方在超时后未收到确认，重试 1 次。
- 若重试后仍未收到确认，标记为 `COMMUNICATION_LOST` 并在下一轮报告中注明。

### 3.3 Handoff 协议

```
sessions_send(target_agent_id, "handoff: [阶段名] 完成。产出位于 [路径]。下一阶段：[阶段名]。")
```

接收方确认收到后开始执行。

### 3.4 回退协议

```
sessions_send(target_agent_id, "回退: 发现 P[X] 问题 [具体描述]。请从 [阶段名] 重新开始。\n问题详情：\n[清单]")
```

---

## 4. 严重度分级标准（P0/P1/P2）

所有 agent 在审查产出、评估结果、判定收敛时必须使用统一的分级标准：

| 级别 | 名称 | 判定标准 | 响应动作 |
|------|------|----------|----------|
| **P0** | 致命 | 需求理解错误、方案不可行、架构方向错误、安全漏洞导致数据泄露 | 触发回退——从需求分析或架构阶段重新开始 |
| **P1** | 严重 | 核心功能缺失、关键路径未实现、中等安全漏洞、性能严重不达标 | 触发定向修复——由对应 agent 修复后重新提交 |
| **P2** | 轻微 | 边界 case 遗漏、UI 瑕疵、代码风格问题、性能可优化但非阻塞 | 记录到问题列表——当前 phase 完成后统一处理 |

---

{% if loop_mode == "orchestrator_worker" %}
## 5. Completion Gate — Orchestrator+Worker 模式

### 5.1 你的角色

你是 **Orchestrator agent**（`{{ orchestrator.id }}`）。你的职责是：
- 将任务分解为子任务并分配给 Worker agent
- 收集 Worker 的返回结果
- **在每轮任务分发和结果收集后，执行收敛判定**
- 你**不直接操作代码**——代码操作由 Worker 执行

{% for worker in workers %}
- **{{ worker.id }}（{{ worker.role_display }}）：** {{ worker.responsibility }}
{% endfor %}

### 5.2 收敛判定流程（每轮必须执行）

在每轮任务分发和结果收集后，执行以下检查步骤：

**步骤 1 — 问题清单检查：**
- 阅读所有 Worker 返回的结果摘要。
- 识别其中提到的问题，按 P0/P1/P2 标准分类（见第 4 节）。
- 将问题记录到本轮问题清单中。

**步骤 2 — 新问题/已解决问题计数：**
- 对比本轮问题清单与上一轮问题清单。
- 统计：本轮新发现的问题数量、本轮已修复的问题数量、仍未修复的遗留问题数量。

**步骤 3 — 收敛判定：**
- 若 **连续 {{ convergence_rounds }} 轮**（即连续 {{ convergence_rounds }} 次你分配任务并收集结果后）未发现任何新 P0/P1/P2 问题，**且**所有已知问题状态为"已修复"或"已验证"，则判断任务完成。
- 回复格式：
  ```
  CONVERGED: 任务完成。
  连续未发现新问题轮次: {{ convergence_rounds }}/{{ convergence_rounds }}
  最终状态: [摘要]
  遗留 P2 问题（非阻塞）: [清单或无]
  ```

**步骤 4 — 未收敛时的动作：**
- 若未满足收敛条件，根据问题级别分派：
  - **P0 问题** → 重新分析需求，使用 sessions_spawn 启动"需求重分析"子任务，发送给对应 Worker。
  - **P1 问题** → 使用 sessions_send 将具体问题发给对应的 Worker，指令中附修复要求。
  - **P2 问题** → 累积到问题列表，不阻塞当前 phase 推进。在所有 P0/P1 清零后统一处理。

### 5.3 回退路由

```
P0 触发 → sessions_spawn(designer_id, "需求重分析: [P0 问题描述]。请从需求分析阶段重新开始。")
P1 触发 → sessions_send(target_worker_id, "定向修复: [P1 问题描述]。修复后重新提交给 Orchestrator。")
P2 触发 → 记录到问题列表: artifacts/p2-backlog.md（不触发回退）
```

### 5.4 Worker 职责

作为 Worker agent，你的职责是：
1. 接收 Orchestrator 分配的任务。
2. 执行任务（在 IDENTITY.md 和 TOOLS.md 限定的范围内）。
3. 完成后，使用 sessions_send 向 Orchestrator 提交结果。
4. **不要自行判断收敛**——收敛判定是 Orchestrator 的专属职责。
5. 若在执行中发现问题，在结果中附上问题描述和分类建议（P0/P1/P2），由 Orchestrator 最终分类。

{% elif loop_mode == "peer_review_pair" %}
## 5. Completion Gate — Peer Review Pair 模式

### 5.1 你的角色

你是 Peer Review Pair 中的一员。你的角色在每次 handoff 时切换：
- **当对方向你发送产出时** → 你是**审查者**。
- **当你向对方发送产出时** → 你是**生产者**。

{% for agent in agents %}
- **{{ agent.id }}（{{ agent.role_display }}）：** {{ agent.responsibility }}
{% endfor %}

### 5.2 收敛判定流程（每轮必须执行）

**当你是审查者时，执行以下步骤：**

**步骤 1 — 审查：**
- 收到对方产出的消息后，按 P0/P1/P2 标准（第 4 节）进行审查。
- 记录所有发现的问题，标注级别和具体位置。

**步骤 2 — 判定：**
- **场景 A：本轮无发现 + 上一轮也无发现**
  - 若你在本轮审查中**未发现任何 P0/P1/P2 问题**，且查阅对话历史确认**上一轮对方的审查同样未发现任何问题**，则回复：
    ```
    CONVERGED: 双方审查一致通过。
    本轮审查结果: P0=0, P1=0, P2=0
    上一轮审查结果: P0=0, P1=0, P2=0
    结论: 任务完成。
    ```

- **场景 B：本轮无发现 + 上一轮对方有发现**
  - 若你在本轮审查中未发现任何新问题，但对方上一轮有发现，则回复：
    ```
    APPROVED: 本轮无新发现。
    本轮审查结果: P0=0, P1=0, P2=0
    请对方确认其上一轮发现的问题是否已全部修复。
    ```

- **场景 C：本轮有发现**
  - 若发现 P0 问题 → 回复：
    ```
    BLOCKED: P0 问题。请重新从头开始。
    问题列表:
    - [P0] [问题描述]
    ```
  - 若发现 P1 问题 → 回复：
    ```
    REVISION_NEEDED: P1 问题。请修复后重新提交审查。
    问题列表:
    - [P1] [问题描述]
    ```
  - 若仅发现 P2 问题 → 回复：
    ```
    SUGGESTIONS: P2 问题。可在下轮一并修复。
    问题列表:
    - [P2] [问题描述]
    ```

### 5.3 回退路由

```
P0 触发 → 回复 BLOCKED，要求对方重新从头开始。回复格式见步骤 2 场景 C。
P1 触发 → 回复 REVISION_NEEDED，要求对方修复后重新提交。
P2 触发 → 回复 SUGGESTIONS，标记为可选修复。
```

{% elif loop_mode == "sequential_pipeline" %}
## 5. Completion Gate — Sequential Pipeline 模式

### 5.1 你的角色

你是 Sequential Pipeline 中的 **第 {{ agent.position }} 个 agent**（`{{ agent.id }}`）。
你的职责是 **{{ agent.responsibility }}**。
Pipeline 阶段顺序：
{% for a in agents %}
{{ loop.index }}. **{{ a.id }}** — {{ a.role_display }}: {{ a.responsibility }}
{% endfor %}

### 5.2 阶段完成与 Handoff

**当你完成你的阶段任务后：**
1. 确认产出符合本阶段的质量标准。
2. 将产出 handoff 给下一个 agent：
   ```
   sessions_send({{ next_agent_id }}, "handoff: [{{ agent.role_display }}] 完成。产出位于 [路径]。请继续下一阶段。")
   ```

### 5.3 收敛判定（仅最后一个 Agent 执行）

{% set last_agent = agents | last %}
**{{ last_agent.id }}（{{ last_agent.role_display }}）**是流水线末尾的质量检查 agent。在收到上一个 agent 的 handoff 后执行：

**步骤 1 — 全面验证：**
- 执行全流程验证（对照原始需求检查最终产出）。
- 按 P0/P1/P2 标准（第 4 节）分类所有发现的问题。

**步骤 2 — 判定：**
- **若未发现任何 P0/P1/P2 问题** → 回复：
  ```
  CONVERGED: 流水线完成。所有阶段产出均通过验证。
  验证轮次: {{ pipeline_cycle }}/{{ max_cycles }}
  ```

- **若发现问题** → 根据严重度决定回退目标，使用 sessions_send 触发回退：
  - **P0** → 回退到流水线第一个 agent（`{{ agents[0].id }}`）——从头修正。
  - **P1** → 回退到最早涉及该问题的 agent。
  - **P2** → 回退到当前 agent 的前一个 agent——就近修正。

### 5.4 回退消息格式

```
sessions_send({{ target_agent_id }}, "回退: 发现 P[X] 问题。
问题: [具体描述]
位置: [代码路径/文档位置]
修复建议: [可选]

本次验证发现的所有问题:
[完整清单]

请从你的阶段重新开始。")
```

### 5.5 中间阶段 Agent 职责

{% for agent in agents %}
{% if not loop.last %}
**{{ agent.id }}：**
- 收到来自上游的 handoff 后开始执行你的阶段任务。
- 完成后向下游 handoff。
- 若收到来自下游的回退请求，从你的阶段重新开始。
- **不要自行判断整体收敛**——收敛判定仅由末尾 agent（`{{ last_agent.id }}`）执行。

{% endif %}
{% endfor %}
{% endif %}

---

## 6. 硬止损 (Hard Stop)

> **本章节优先级最高**——即使与其他章节的收敛条件冲突，也以本章节为准。
> 所有 agent 必须遵守本章节的硬止损指令。

### 6.1 最大轮次

无论收敛条件是否满足，在第 **{{ max_cycles }}** 轮结束时必须停止循环。

回复格式：
```
HARD_STOP: 达到最大轮次 {{ max_cycles }}。
未解决问题:
[P0/P1/P2 清单]
遗留状态: [描述]
建议: MANUAL_INTERVENTION_NEEDED——请人工检查并决定是否继续。
```

### 6.2 最大时间

如果距离任务开始已超过 **{{ max_duration_minutes }}** 分钟，立即停止所有进行中的子任务并输出当前状态。

回复格式：
```
HARD_STOP: 达到最大时间限制 {{ max_duration_minutes }} 分钟。
当前进度: [描述]
未完成任务: [清单]
```

### 6.3 逃逸检测

如果你发现自己在重复执行**相同的操作**而没有进展（例如连续 2 轮的任务分配内容几乎相同、连续 2 轮的审查意见完全一致），立即停止并回复：

```
ESCAPE_DETECTED: 检测到循环无进展。
最近 2 轮的操作内容高度重复:
[列出重复的操作]
建议: 人工介入重新定义问题边界或调整收敛条件。
```

### 6.4 权限越界阻断

任何 agent 不得尝试：
- 修改 openclaw.json 配置文件
- 绕过 file_scope 限制访问非授权目录
- 提升自己的权限（如授予自己 sessions_spawn 权限）
- 修改其他 agent 的 SOUL.md / IDENTITY.md / TOOLS.md

若检测到上述行为，立即停止并回复：
```
SECURITY_BREACH_DETECTED: 检测到权限越界尝试。
越界行为: [描述]
执行者: [agent_id]
建议: 立即通知管理员并暂停所有 agent 活动。
```

---

## 7. 收敛状态追踪

每个 agent 在每轮操作后，在对话末尾附上以下状态块：

```markdown
## LOOP STATE — Round {{ '{{ round_number }}' }}

- **当前阶段：** {{ '{{ phase }}' }}
- **本轮发现：** P0={{ '{{ p0_count }}' }}, P1={{ '{{ p1_count }}' }}, P2={{ '{{ p2_count }}' }}
- **已修复：** P0={{ '{{ p0_fixed }}' }}, P1={{ '{{ p1_fixed }}' }}, P2={{ '{{ p2_fixed }}' }}
- **连续零新发现轮次：** {{ '{{ zero_new_finding_streak }}' }}/{{ convergence_rounds }}
- **累计轮次：** {{ '{{ current_round }}' }}/{{ max_cycles }}
- **距硬止损时间：** {{ '{{ remaining_minutes }}' }} 分钟
- **状态：** [IN_PROGRESS | WAITING_FOR_REVIEW | CONVERGED | HARD_STOP | ESCAPE_DETECTED]
```

---

## 8. 跨 Agent 通信路由速查表

{% if loop_mode == "orchestrator_worker" %}
| 从 | 到 | 方法 | 触发条件 |
|----|----|------|----------|
| Orchestrator | 任意 Worker | sessions_spawn | 分配任务 |
| Orchestrator | 任意 Worker | sessions_send | 发送指令/修复要求 |
| 任意 Worker | Orchestrator | sessions_send | 提交结果/报告问题 |
| Worker A | Worker B | **禁止** | Worker 间不直接通信 |
{% elif loop_mode == "peer_review_pair" %}
| 从 | 到 | 方法 | 触发条件 |
|----|----|------|----------|
| Peer A | Peer B | sessions_send | 提交产出供审查 |
| Peer B | Peer A | sessions_send | 提交审查结果 |
| Peer A | Peer B | sessions_send | 提交修复后的产出 |
| Peer B | Peer A | sessions_send | 提交二次审查结果 |
{% elif loop_mode == "sequential_pipeline" %}
| 从 | 到 | 方法 | 触发条件 |
|----|----|------|----------|
{% for agent in agents %}
{% if not loop.last %}
| {{ agent.id }} | {{ agents[loop.index].id }} | sessions_send | 阶段完成，handoff |
{% endif %}
{% endfor %}
| {{ last_agent.id }} | {{ agents[0].id }} | sessions_send | 回退——验证未通过（P0） |
| {{ last_agent.id }} | 最早涉及问题的 agent | sessions_send | 回退——P1 定向 |
| {{ last_agent.id }} | {{ agents[-2].id }} | sessions_send | 回退——P2 就近 |
{% endif %}

---

## 9. 模板渲染元数据

```
生成时间: {{ created_at }}
生成器版本: {{ generator_version }}
Loop 模式: {{ loop_mode }}
Agent 数量: {{ agents | length }}
收敛轮次要求: {{ convergence_rounds }}
最大轮次: {{ max_cycles }}
最大时长: {{ max_duration_minutes }} 分钟
```

---

> **本文件由 loop-openclaw 配置生成器自动生成。**
> **部署至 OpenClaw Gateway 前请人工审查 Completion Gate 的可执行性。**
> **如需修改收敛标准，编辑本文件后重启 Gateway。**
