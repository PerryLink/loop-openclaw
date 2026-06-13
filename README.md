[![PyPI version](https://img.shields.io/pypi/v/loop-openclaw)](https://pypi.org/project/loop-openclaw/)

*A [**Loop Engineering**](https://github.com/PerryLink/loop-everything) autonomous coding loop engine — turn goals into production code.*
[![Python](https://img.shields.io/pypi/pyversions/loop-openclaw)](https://pypi.org/project/loop-openclaw/)
[![License](https://img.shields.io/pypi/l/loop-openclaw)](./LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/loop-openclaw)](https://pypi.org/project/loop-openclaw/)
[![CI](https://github.com/PerryLink/loop-openclaw/actions/workflows/ci.yml/badge.svg)](https://github.com/PerryLink/loop-openclaw/actions)

# loop-openclaw -- Jinja2 Template Renderer for Autonomous Agent Workspace Bootstrapping

**Alternative to static config generators -- dual-engine Jinja2 template rendering with regex fallback, StrictUndefined protection, and multi-mode topology generation. 15 templates across 3 topology modes, optimized for autonomous agent workspace bootstrapping.**

> **loop-openclaw 是 loop-* 系列中最轻量的项目 -- 纯配置生成器 + Jinja2 模板引擎，非运行时 loop 驱动。**
> 读取用户需求，经过需求分析、拓扑选择和模板渲染，输出一套部署到 OpenClaw Gateway 的多 agent 闭环配置文件。
>
> **This is the lightest project in the loop-* family -- a pure config generator + Jinja2 template engine, not a runtime loop driver.**
> Read user requirements, perform topology selection and template rendering, output a set of multi-agent loop configuration files ready for deployment to OpenClaw Gateway.

**English** | [中文](#中文)

**This project is a configuration generator, not a runtime engine.** It generates OpenClaw Gateway config files that embed natural-language convergence conditions (Completion Gates). When deployed to the Gateway, agents self-evaluate convergence -- the loop behavior emerges from agent self-governance, not from a central driver. See [sufficiency declaration](./docs/sufficiency-declaration.md) for scope details.

## Features

- **Dual-engine rendering** -- Jinja2 primary engine with regex fallback for zero-dependency environments; `StrictUndefined` protection catches missing variables at render time
- **15 templates (10 `.j2` + 5 `.j2.m2`)** -- two-tier template architecture: `.j2` Jinja2 templates for direct rendering, `.j2.m2` meta-templates for pre-processing pipelines
- **Three topology modes** -- Orchestrator+Worker (hub-and-spoke), Peer Review Pair (bidirectional), Sequential Pipeline (chain handoff)
- **`template_registry.json` single source of truth** -- JSON Schema-based variable registry defines all 20+ template variables with types, defaults, constraints, and cross-references; used by both the renderer and validator
- **Natural-language convergence conditions** -- Completion Gates expressed as plain English criteria, evaluated by agents themselves
- **Mode selection decision tree** -- automatic topology recommendation based on project structure and requirements (`schemas/mode-selection-decision-tree.yaml`)
- **Comprehensive validation** -- 6-check pipeline: plan structure, cross-references, output file integrity, agent spec compliance, StrictUndefined coverage, and convergence criteria completeness
- **External cron watchdog guidance** -- deployment docs include cron-based external supervision patterns for Gateway environments
- **Zero runtime dependencies beyond Python stdlib + Jinja2** -- lightweight, auditable, single-file `render.py`

## Architecture

loop-openclaw is a **single-file** project. The entire codebase lives in `render.py` (1853 lines):

| Component | Lines | Purpose |
|-----------|-------|---------|
| `AgentSpec` / `ConfigPlan` | ~60 | Pydantic-style data classes for configuration modeling |
| `TemplateRegistry` | ~80 | Loads and dispatches 20+ template variables from `template_registry.json` |
| `TemplateRenderer` | ~260 | Dual-engine renderer: Jinja2 primary + `re.sub()` regex fallback with `StrictUndefined` |
| `parse_config_plan()` | ~200 | Parses Markdown/JSON config plans into structured `ConfigPlan` |
| `validate_*()` functions | ~450 | 6-check validation: plan, cross-references, output files, agent specs |
| `simple_render()` | ~60 | Zero-dependency `{{ var }}` string replacement fallback (regex engine) |
| `main()` CLI | ~200 | Argument parsing, mode selection, render + validate pipeline |

### Templates (10 `.j2` + 5 `.j2.m2`)

| `.j2` Template | `.j2.m2` Meta | Output |
|----------------|---------------|--------|
| `openclaw.json.j2` | `openclaw.json.j2.m2` | Gateway main configuration (JSON5) |
| `SOUL.md.j2` | `SOUL.md.j2.m2` | Agent personality/soul definitions |
| `AGENTS.md.j2` | `AGENTS.md.j2.m2` | Multi-agent orchestration with convergence conditions |
| `IDENTITY.md.j2` | `IDENTITY.md.j2.m2` | Agent identity declarations |
| `TOOLS.md.j2` | `TOOLS.md.j2.m2` | Agent tool declarations |
| `worker_prompt.j2` | -- | Worker agent system prompt |
| `review_prompt.j2` | -- | Peer review agent system prompt |
| `routing_rules.yaml.j2` | -- | Inter-agent routing rules |
| `sessions_config.yaml.j2` | -- | Gateway session configuration |

### E2E Test Coverage (pytest)

| Test File | Mode | Assertions |
|-----------|------|------------|
| `tests/test_e2e_orchestrator.py` | Orchestrator+Worker | Plan validation, 5 output files, cross-references, agent permissions, convergence text |
| `tests/test_e2e_peer_review.py` | Peer Review Pair | Plan validation, bidirectional routing, 2-agent topology, STALEMATE handling |
| `tests/test_e2e_sequential.py` | Sequential Pipeline | Plan validation, chain handoff, fallback routing, pipeline convergence |
| `tests/test_edge_cases.py` | All modes | Empty config, malformed JSON, missing variables, circular references |
| `tests/test_unit_render.py` | Unit | `simple_render()` fallback, `TemplateRenderer` edge cases |
| `tests/test_unit_validation.py` | Unit | Each of 6 validation checks in isolation |

## Quick Start

```bash
# Install from PyPI
pip install loop-openclaw

# Or install from source
git clone https://github.com/PerryLink/loop-openclaw.git
cd loop-openclaw
pip install -r requirements.txt

# Render configuration with a specific mode and config plan
python render.py --mode orchestrator --config plan.json

# Alternatively, render for a project directory (auto-detects)
python render.py --project-dir /path/to/your/project --mode orchestrator

# Output files are written to ./output/
ls output/
# AGENTS.md  IDENTITY.md  SOUL.md  TOOLS.md  openclaw.json  routing_rules.yaml  sessions_config.yaml

# Validate templates completeness
python render.py --validate-only

# List available modes and run the decision tree
python render.py --list-modes

# Deploy to OpenClaw Gateway
cp output/* /etc/openclaw/gateway/configs/
```

Requirements: Python >= 3.10, Jinja2 >= 3.0 (optional -- falls back to built-in regex substitution when Jinja2 is unavailable).

## FAQ

### Q: loop-openclaw doesn't run a loop itself -- how does the loop happen?
A: Correct. loop-openclaw is a config generator, not a runtime. It outputs configuration files that embed natural-language convergence conditions (Completion Gates) inside agent instructions. When deployed to OpenClaw Gateway, the agents read these conditions and self-evaluate whether they've met them. If not, they route back to the appropriate phase -- creating a loop behavior without a central loop driver. An external cron watchdog (recommended in deployment docs) provides an additional safety net.

### Q: Which topology should I choose for my project?
A: **Orchestrator+Worker** -- best for structured projects with clear sub-tasks (most projects). **Peer Review Pair** -- best when output quality is critical and you want two agents cross-checking each other (security reviews, production code). **Sequential Pipeline** -- best for linear workflows with clear stage gates (design -> implement -> test). Use `python render.py --list-modes` to run the decision tree interactively.

### Q: Can I customize the generated configurations after rendering?
A: Yes. The output files are plain text (Markdown, JSON5, YAML). Edit them directly before deploying to Gateway. The templates in `templates/` are Jinja2 `.j2` files -- modify those to change the generation logic for all future runs. The `.j2.m2` meta-templates define pre-processing rules for variable derivation.

### Q: Is this the lightest loop-* project? Why?
A: Yes. loop-openclaw is deliberately minimal -- a single `render.py` file with no state machine, no hook system, no runtime loop driver. It generates configuration and stops. The "loop" comes from the Gateway agents themselves reading convergence conditions embedded in the output. This design prioritizes auditability, simplicity, and zero runtime overhead.

### Q: What happens if Jinja2 is not installed?
A: The renderer automatically falls back to a built-in `re.sub()` regex engine (`simple_render()`). It handles basic `{{ var }}` substitution and simple conditionals. For full Jinja2 features (loops, filters, macros), install Jinja2 >= 3.0. The `StrictUndefined` protection only applies in Jinja2 mode.

### Q: What is `template_registry.json`?
A: It is the **single source of truth** for all template variables. It defines every variable's type, whether it is required, its default value, allowed values (`enum`), and constraints. Both the `TemplateRenderer` and the `validate_*()` pipeline read from this registry, ensuring consistency between rendering and validation without duplicating variable definitions.

## Related Projects

- **[loop-everything](https://github.com/PerryLink/loop-everything)** -- Loop Engineering ecosystem hub (:star:)
- [loop-superpowers](https://github.com/PerryLink/loop-superpowers) -- pure Skill mini-loops for Claude Code
- [loop-opencode](https://github.com/PerryLink/loop-opencode) -- closed-loop driver for OpenCode CLI
- [loop-codex](https://github.com/PerryLink/loop-codex) -- dual-channel (JSON-RPC + CDP) driver for Codex Desktop
- [loop-copilot](https://github.com/PerryLink/loop-copilot) -- closed-loop driver for GitHub Copilot SDK
- [loop-cursor](https://github.com/PerryLink/loop-cursor) -- closed-loop driver for Cursor IDE SDK
- [loop-deepseek](https://github.com/PerryLink/loop-deepseek) -- self-built ReAct agent loop for DeepSeek API
- [loop-hermes](https://github.com/PerryLink/loop-hermes) -- closed-loop driver for Hermes SDK
- [loop-aider](https://github.com/PerryLink/loop-aider) -- closed-loop driver for Aider CLI
- [loop-ollama](https://github.com/PerryLink/loop-ollama) -- self-built ReAct agent loop for local Ollama models
- [loop-antigravity](https://github.com/PerryLink/loop-antigravity) -- closed-loop driver for Google Antigravity / Gemini
- [loop-claudecode](https://github.com/PerryLink/loop-claudecode) -- closed-loop driver for Claude Code CLI

## License

Apache License 2.0 -- see [LICENSE](./LICENSE) for full text. See [sufficiency declaration](./docs/sufficiency-declaration.md) for scope and known limitations.

Copyright 2026 Perry Link

---

## 中文

# loop-openclaw -- 面向自主 Agent 工作空间引导的 Jinja2 模板渲染引擎

**静态配置生成器的替代方案 -- 双引擎 Jinja2 模板渲染，支持正则降级、StrictUndefined 保护和多模式拓扑生成。15 个模板覆盖 3 种拓扑模式，专为自主 agent 工作空间引导优化。**

> **loop-openclaw 是 loop-* 系列中最轻量的项目 -- 纯配置生成器 + Jinja2 模板引擎，非运行时 loop 驱动。**
> 读取用户需求，经过需求分析、拓扑选择和模板渲染，输出一套部署到 OpenClaw Gateway 的多 agent 闭环配置文件。

**本项目是配置生成器，非运行引擎。** 它生成内嵌自然语言收敛条件（Completion Gates）的 OpenClaw Gateway 配置文件。部署到 Gateway 后，agents 自主评估收敛状态 -- 循环行为源自 agent 自我治理，而非中央驱动。详见[充分性声明](./docs/sufficiency-declaration.md)。

## 特性

- **双引擎渲染** -- Jinja2 主引擎 + 正则降级方案，适应零依赖环境；`StrictUndefined` 保护在渲染时捕获缺失变量
- **15 个模板（10 个 `.j2` + 5 个 `.j2.m2`）** -- 双层模板架构：`.j2` Jinja2 模板用于直接渲染，`.j2.m2` 元模板用于预处理流水线
- **三种拓扑模式** -- Orchestrator+Worker（中心辐射型）、Peer Review Pair（双向互审型）、Sequential Pipeline（链式传递型）
- **`template_registry.json` 单一变量真源** -- 基于 JSON Schema 的变量注册表，定义全部 20+ 模板变量的类型、是否必填、默认值、约束和交叉引用；渲染器和校验器均以此为准
- **自然语言收敛条件** -- Completion Gates 以自然语言表述，由 agents 自身评估
- **模式选择决策树** -- 基于项目结构和需求自动推荐拓扑模式（`schemas/mode-selection-decision-tree.yaml`）
- **全面校验流水线** -- 6 项校验：计划结构、交叉引用、输出文件完整性、agent 规格合规、StrictUndefined 覆盖、收敛条件完整性
- **外部 cron 监控指导** -- 部署文档包含 cron 外部监督模式
- **零运行时依赖（除 Python 标准库 + Jinja2 外）** -- 轻量、可审计、单文件 `render.py`

## 架构

loop-openclaw 是**单文件**项目。全部代码位于 `render.py`（1853 行）：

| 组件 | 行数 | 用途 |
|------|------|------|
| `AgentSpec` / `ConfigPlan` | ~60 | 配置建模的 Pydantic 风格数据类 |
| `TemplateRegistry` | ~80 | 从 `template_registry.json` 加载和分发 20+ 模板变量 |
| `TemplateRenderer` | ~260 | 双引擎渲染器：Jinja2 主引擎 + `re.sub()` 正则降级，含 `StrictUndefined` 保护 |
| `parse_config_plan()` | ~200 | 将 Markdown/JSON 配置计划解析为结构化 `ConfigPlan` |
| `validate_*()` 函数族 | ~450 | 6 项校验：计划、交叉引用、输出文件、agent 规格 |
| `simple_render()` | ~60 | 零依赖 `{{ var }}` 字符串替换降级方案（正则引擎） |
| `main()` CLI | ~200 | 参数解析、模式选择、渲染 + 校验流水线 |

### 模板（10 个 `.j2` + 5 个 `.j2.m2`）

| `.j2` 模板 | `.j2.m2` 元模板 | 输出 |
|------------|-----------------|------|
| `openclaw.json.j2` | `openclaw.json.j2.m2` | Gateway 主配置（JSON5） |
| `SOUL.md.j2` | `SOUL.md.j2.m2` | Agent 人格/灵魂定义 |
| `AGENTS.md.j2` | `AGENTS.md.j2.m2` | 多 agent 编排，内含收敛条件 |
| `IDENTITY.md.j2` | `IDENTITY.md.j2.m2` | Agent 身份声明 |
| `TOOLS.md.j2` | `TOOLS.md.j2.m2` | Agent 工具声明 |
| `worker_prompt.j2` | -- | 工作 agent 系统提示词 |
| `review_prompt.j2` | -- | 互审 agent 系统提示词 |
| `routing_rules.yaml.j2` | -- | Agent 间路由规则 |
| `sessions_config.yaml.j2` | -- | Gateway 会话配置 |

### E2E 测试覆盖（pytest）

| 测试文件 | 模式 | 断言要点 |
|----------|------|----------|
| `tests/test_e2e_orchestrator.py` | Orchestrator+Worker | 计划校验、5 个输出文件、交叉引用、agent 权限、收敛文本 |
| `tests/test_e2e_peer_review.py` | Peer Review Pair | 计划校验、双向路由、2-agent 拓扑、STALEMATE 处理 |
| `tests/test_e2e_sequential.py` | Sequential Pipeline | 计划校验、链式传递、回退路由、流水线收敛 |
| `tests/test_edge_cases.py` | 全模式 | 空配置、畸形 JSON、缺失变量、循环引用 |
| `tests/test_unit_render.py` | 单元 | `simple_render()` 降级方案、`TemplateRenderer` 边界情况 |
| `tests/test_unit_validation.py` | 单元 | 6 项校验各自独立验证 |

## 快速开始

```bash
# 从 PyPI 安装
pip install loop-openclaw

# 或从源码安装
git clone https://github.com/PerryLink/loop-openclaw.git
cd loop-openclaw
pip install -r requirements.txt

# 使用指定模式和配置计划渲染
python render.py --mode orchestrator --config plan.json

# 或为项目目录渲染（自动检测）
python render.py --project-dir /path/to/your/project --mode orchestrator

# 输出文件写入 ./output/
ls output/
# AGENTS.md  IDENTITY.md  SOUL.md  TOOLS.md  openclaw.json  routing_rules.yaml  sessions_config.yaml

# 验证模板完整性
python render.py --validate-only

# 列出可用模式并运行决策树
python render.py --list-modes

# 部署到 OpenClaw Gateway
cp output/* /etc/openclaw/gateway/configs/
```

依赖要求：Python >= 3.10，Jinja2 >= 3.0（可选，未安装时降级为内置正则替换）。

## 常见问题

### Q：loop-openclaw 自身不运行 loop -- 循环如何发生？
A：正确。loop-openclaw 是配置生成器，不是运行时。它输出内嵌自然语言收敛条件（Completion Gates）的配置文件。部署到 OpenClaw Gateway 后，agents 会读取这些条件并自行评估是否满足。如果不满足，它们会路由回相应阶段 -- 在没有中央 loop 驱动器的情况下产生循环行为。部署文档中推荐的外部 cron 监控提供了额外的安全网。

### Q：我应该为项目选择哪种拓扑？
A：**Orchestrator+Worker** -- 最适合具有明确子任务的结构化项目（大多数项目）。**Peer Review Pair** -- 最适合输出质量至关重要且希望两个 agent 交叉检查的场景（安全审查、生产代码）。**Sequential Pipeline** -- 最适合具有明确阶段门槛的线性工作流（设计 -> 实施 -> 测试）。使用 `python render.py --list-modes` 交互式运行决策树。

### Q：渲染后可以自定义生成的配置吗？
A：可以。输出文件是纯文本（Markdown、JSON5、YAML）。在部署到 Gateway 之前直接编辑即可。`templates/` 中的模板是 Jinja2 `.j2` 文件 -- 修改它们可以改变所有未来运行的生成逻辑。`.j2.m2` 元模板定义变量派生的预处理规则。

### Q：这是最轻量的 loop-* 项目吗？为什么？
A：是的。loop-openclaw 刻意保持极简 -- 单个 `render.py` 文件，没有状态机，没有钩子系统，没有运行时 loop 驱动器。它生成配置后即停止。"Loop" 来自于 Gateway agents 自身读取输出中嵌入的收敛条件。这种设计优先考虑可审计性、简单性和零运行时开销。

### Q：如果未安装 Jinja2 会怎样？
A：渲染器自动降级为内置 `re.sub()` 正则引擎（`simple_render()`）。它处理基本的 `{{ var }}` 替换和简单条件判断。如需完整的 Jinja2 功能（循环、过滤器、宏），请安装 Jinja2 >= 3.0。`StrictUndefined` 保护仅在 Jinja2 模式下生效。

### Q：什么是 `template_registry.json`？
A：它是所有模板变量的**单一真源**。它定义了每个变量的类型、是否必填、默认值、允许值（`enum`）和约束。`TemplateRenderer` 和 `validate_*()` 流水线均读取此注册表，确保渲染与校验的一致性，无需重复定义变量。

## 相关项目

- **[loop-everything](https://github.com/PerryLink/loop-everything)** -- Loop 工程生态枢纽（:star:）
- [loop-superpowers](https://github.com/PerryLink/loop-superpowers) -- 面向 Claude Code 的纯 Skill 迷你循环
- [loop-opencode](https://github.com/PerryLink/loop-opencode) -- OpenCode CLI 闭环驱动
- [loop-codex](https://github.com/PerryLink/loop-codex) -- Codex Desktop 双通道（JSON-RPC + CDP）驱动
- [loop-copilot](https://github.com/PerryLink/loop-copilot) -- GitHub Copilot SDK 闭环驱动
- [loop-cursor](https://github.com/PerryLink/loop-cursor) -- Cursor IDE SDK 闭环驱动
- [loop-deepseek](https://github.com/PerryLink/loop-deepseek) -- 面向 DeepSeek API 的自建 ReAct 代理循环
- [loop-hermes](https://github.com/PerryLink/loop-hermes) -- Hermes SDK 闭环驱动
- [loop-aider](https://github.com/PerryLink/loop-aider) -- Aider CLI 闭环驱动
- [loop-ollama](https://github.com/PerryLink/loop-ollama) -- 面向本地 Ollama 模型的自建 ReAct 代理循环
- [loop-antigravity](https://github.com/PerryLink/loop-antigravity) -- Google Antigravity / Gemini 闭环驱动
- [loop-claudecode](https://github.com/PerryLink/loop-claudecode) -- Claude Code CLI 闭环驱动

## 许可证

Apache License 2.0 -- 详见 [LICENSE](./LICENSE) 文件。详见[充分性声明](./docs/sufficiency-declaration.md)了解范围和已知限制。

Copyright 2026 Perry Link
