# loop-openclaw — Multi-Agent Loop Config Generator for OpenClaw Gateway

**This is a pure configuration generator — one Python renderer + Jinja2 templates. It produces OpenClaw Gateway configs; the Gateway runs the actual loop. 'Single file' architecture is by design.**

> **loop-openclaw 是 loop-* 系列中最轻量的项目 —— 纯配置生成器 + Jinja2 模板引擎，非运行时 loop 驱动。**
> 读取用户需求，经过需求分析、架构选择和模板渲染，输出一套部署到 OpenClaw Gateway 的多 agent 闭环配置文件。
>
> **This is the lightest project in the loop-* family — a pure config generator + Jinja2 template engine, not a runtime loop driver.**
> Read user requirements, perform topology selection and template rendering, output a set of multi-agent loop configuration files ready for deployment to OpenClaw Gateway.

[![Version](https://img.shields.io/badge/version-0.1.0-blue)]()
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-≥3.10-blue?logo=python)](https://python.org)


[English](#english) | [中文](#chinese)

<a id="english"></a>

**This project is a configuration generator, not a runtime engine.** It generates OpenClaw Gateway config files that embed natural-language convergence conditions (Completion Gates). When deployed to the Gateway, agents self-evaluate convergence — the loop behavior emerges from agent self-governance, not from a central driver.

## Features

- Three loop topologies — Orchestrator+Worker (hub-and-spoke), Peer Review Pair (bidirectional), Sequential Pipeline (chain handoff)
- 8 output artifacts — gateway config (JSON5), agent personality (SOUL.md), multi-agent orchestration (AGENTS.md), identity (IDENTITY.md), tools (TOOLS.md), sessions config, routing rules, worker prompts
- Natural-language convergence conditions — Completion Gates expressed as plain English criteria, evaluated by agents themselves
- Jinja2 template engine — type-safe variable substitution with JSON Schema validation via `template_registry.json`
- Mode selection decision tree — automatic topology recommendation based on project structure and requirements
- External cron watchdog guidance — deployment docs include cron-based external supervision patterns for Gateway environments
- Zero runtime dependencies beyond Python stdlib + Jinja2 — lightweight, auditable, single-file render.py

## Quick Start

```bash
# Prerequisites: Python >= 3.10
git clone https://github.com/PerryLink/loop-openclaw.git
cd loop-openclaw
pip install -r requirements.txt

# Render configuration for a project
python render.py --project-dir /path/to/your/project --mode orchestrator

# Output files are written to ./output/
ls output/
# AGENTS.md  IDENTITY.md  SOUL.md  TOOLS.md  openclaw.json

# Validate templates completeness
python render.py --validate-only

# Deploy to OpenClaw Gateway
cp output/* /etc/openclaw/gateway/configs/
```

Requirements: Python >= 3.10, Jinja2 >= 3.0 (optional, falls back to built-in string substitution).

## FAQ

### Q: loop-openclaw doesn't run a loop itself — how does the loop happen?
A: Correct. loop-openclaw is a config generator, not a runtime. It outputs configuration files that embed natural-language convergence conditions (Completion Gates) inside agent instructions. When deployed to OpenClaw Gateway, the agents read these conditions and self-evaluate whether they've met them. If not, they route back to the appropriate phase — creating a loop behavior without a central loop driver. An external cron watchdog (recommended in deployment docs) provides an additional safety net.

### Q: Which topology should I choose for my project?
A: **Orchestrator+Worker** — best for structured projects with clear sub-tasks (most projects). **Peer Review Pair** — best when output quality is critical and you want two agents cross-checking each other (security reviews, production code). **Sequential Pipeline** — best for linear workflows with clear stage gates (design -> implement -> test). Use `python render.py --list-modes` to run the decision tree interactively.

### Q: Can I customize the generated configurations after rendering?
A: Yes. The output files are plain text (Markdown, JSON5, YAML). Edit them directly before deploying to Gateway. The templates in `templates/` are Jinja2 `.j2` files — modify those to change the generation logic for all future runs.

### Q: Is this the lightest loop-* project? Why?
A: Yes. loop-openclaw is deliberately minimal — a single `render.py` file with no state machine, no hook system, no runtime loop driver. It generates configuration and stops. The "loop" comes from the Gateway agents themselves reading convergence conditions embedded in the output. This design prioritizes auditability, simplicity, and zero runtime overhead.

## Related Projects

- [loop-superpowers](https://github.com/PerryLink/loop-superpowers) — pure Skill mini-loops for Claude Code
- [loop-opencode](https://github.com/PerryLink/loop-opencode) — closed-loop driver for OpenCode CLI
- [loop-codex](https://github.com/PerryLink/loop-codex) — dual-channel (JSON-RPC + CDP) driver for Codex Desktop
- [loop-copilot](https://github.com/PerryLink/loop-copilot) — closed-loop driver for GitHub Copilot SDK
- [loop-cursor](https://github.com/PerryLink/loop-cursor) — closed-loop driver for Cursor IDE SDK
- [loop-deepseek](https://github.com/PerryLink/loop-deepseek) — self-built ReAct agent loop for DeepSeek API
- [loop-ollama](https://github.com/PerryLink/loop-ollama) — self-built ReAct agent loop for local Ollama models
- [loop-antigravity](https://github.com/PerryLink/loop-antigravity) — closed-loop driver for Google Antigravity / Gemini

## License

Apache License 2.0 — see [LICENSE](./LICENSE) for full text.

Copyright 2026 Perry Link

---

<a id="chinese"></a>

## 中文

[English](#english) | **中文**

# loop-openclaw —— OpenClaw Gateway 多代理循环配置生成器

> **loop-openclaw 是 loop-* 系列中最轻量的项目 —— 纯配置生成器 + Jinja2 模板引擎，非运行时 loop 驱动。**
> 读取用户需求，经过需求分析、架构选择和模板渲染，输出一套部署到 OpenClaw Gateway 的多 agent 闭环配置文件。

**本项目是配置生成器，非运行引擎。** 它生成内嵌自然语言收敛条件（Completion Gates）的 OpenClaw Gateway 配置文件。部署到 Gateway 后，agents 自主评估收敛状态 —— 循环行为源自 agent 自我治理，而非中央驱动。

## 特性

- **三种循环拓扑** —— Orchestrator+Worker（中心辐射型）、Peer Review Pair（双向互审型）、Sequential Pipeline（链式传递型）
- **8 个输出构件** —— gateway 配置（JSON5）、agent 人格（SOUL.md）、多 agent 编排（AGENTS.md）、身份声明（IDENTITY.md）、工具声明（TOOLS.md）、会话配置、路由规则、工作 agent 提示词
- **自然语言收敛条件** —— Completion Gates 以自然语言表述，由 agents 自身评估
- **Jinja2 模板引擎** —— 类型安全的变量替换，通过 `template_registry.json` 进行 JSON Schema 校验
- **模式选择决策树** —— 基于项目结构和需求自动推荐拓扑模式
- **外部 cron 监控指导** —— 部署文档包含 cron 外部监督模式
- **零运行时依赖（除 Python 标准库 + Jinja2 外）** —— 轻量、可审计、单文件 render.py

## 快速开始

```bash
# 前置条件：Python >= 3.10
git clone https://github.com/PerryLink/loop-openclaw.git
cd loop-openclaw
pip install -r requirements.txt

# 为项目渲染配置
python render.py --project-dir /path/to/your/project --mode orchestrator

# 输出文件写入 ./output/
ls output/
# AGENTS.md  IDENTITY.md  SOUL.md  TOOLS.md  openclaw.json

# 验证模板完整性
python render.py --validate-only

# 部署到 OpenClaw Gateway
cp output/* /etc/openclaw/gateway/configs/
```

依赖要求：Python >= 3.10，Jinja2 >= 3.0（可选，未安装时降级为内置字符串替换）。

## 常见问题

### Q：loop-openclaw 自身不运行 loop —— 循环如何发生？
A：正确。loop-openclaw 是配置生成器，不是运行时。它输出内嵌自然语言收敛条件（Completion Gates）的配置文件。部署到 OpenClaw Gateway 后，agents 会读取这些条件并自行评估是否满足。如果不满足，它们会路由回相应阶段 —— 在没有中央 loop 驱动器的情况下产生循环行为。部署文档中推荐的外部 cron 监控提供了额外的安全网。

### Q：我应该为项目选择哪种拓扑？
A：**Orchestrator+Worker** —— 最适合具有明确子任务的结构化项目（大多数项目）。**Peer Review Pair** —— 最适合输出质量至关重要且希望两个 agent 交叉检查的场景（安全审查、生产代码）。**Sequential Pipeline** —— 最适合具有明确阶段门槛的线性工作流（设计 -> 实施 -> 测试）。使用 `python render.py --list-modes` 交互式运行决策树。

### Q：渲染后可以自定义生成的配置吗？
A：可以。输出文件是纯文本（Markdown、JSON5、YAML）。在部署到 Gateway 之前直接编辑即可。`templates/` 中的模板是 Jinja2 `.j2` 文件 —— 修改它们可以改变所有未来运行的生成逻辑。

### Q：这是最轻量的 loop-* 项目吗？为什么？
A：是的。loop-openclaw 刻意保持极简 —— 单个 `render.py` 文件，没有状态机，没有钩子系统，没有运行时 loop 驱动器。它生成配置后即停止。 "Loop" 来自于 Gateway agents 自身读取输出中嵌入的收敛条件。这种设计优先考虑可审计性、简单性和零运行时开销。

## 相关项目

- [loop-superpowers](https://github.com/PerryLink/loop-superpowers) —— 面向 Claude Code 的纯 Skill 迷你循环
- [loop-opencode](https://github.com/PerryLink/loop-opencode) —— OpenCode CLI 闭环驱动
- [loop-codex](https://github.com/PerryLink/loop-codex) —— Codex Desktop 双通道（JSON-RPC + CDP）驱动
- [loop-copilot](https://github.com/PerryLink/loop-copilot) —— GitHub Copilot SDK 闭环驱动
- [loop-cursor](https://github.com/PerryLink/loop-cursor) —— Cursor IDE SDK 闭环驱动
- [loop-deepseek](https://github.com/PerryLink/loop-deepseek) —— 面向 DeepSeek API 的自建 ReAct 代理循环
- [loop-ollama](https://github.com/PerryLink/loop-ollama) —— 面向本地 Ollama 模型的自建 ReAct 代理循环
- [loop-antigravity](https://github.com/PerryLink/loop-antigravity) —— Google Antigravity / Gemini 闭环驱动

## 许可证

Apache License 2.0 —— 详见 [LICENSE](./LICENSE) 文件。

Copyright 2026 Perry Link
