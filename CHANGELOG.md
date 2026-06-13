# Changelog

All notable changes to loop-openclaw will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- Enhanced `.gitignore` coverage: Python bytecode (`*.pyc`, `*.pyo`), cache directories (`__pycache__/`, `.pytest_cache/`), build artifacts (`dist/`, `*.egg-info/`), IDE config, and environment files.

---

## [0.1.0] - 2026-06-13

### Added

- Initial release of loop-openclaw, a pure configuration generator for OpenClaw Gateway multi-agent loops.
- **Single-file architecture**: `render.py` (~1853 lines) serves as the sole Python runtime entry point.
- **Three loop topologies** with automatic mode selection decision tree:
  - Orchestrator+Worker (hub-and-spoke) — one orchestrator delegates tasks to multiple worker agents and synthesizes results.
  - Peer Review Pair (bidirectional review) — two agents exchange deliverables for mutual critique and iterative improvement.
  - Sequential Pipeline (chain handoff) — agents process output in a linear chain, each building on the predecessor's results.
- **Jinja2 template engine** with dual-mode rendering (Jinja2 primary + regex fallback when Jinja2 unavailable), ensuring portability across environments without mandatory dependency installation.
- **14 `.j2` template files** covering 8 output artifact types, each specialized per mode:
  - Gateway config (`openclaw.json`) — agent definitions, routing rules, and session parameters for the OpenClaw runtime.
  - Agent personality (`SOUL.md`) — per-agent behavioral guardrails, tone, and constraints.
  - Multi-agent orchestration (`AGENTS.md`) — convergence conditions, completion gates, and handoff protocols.
  - Identity (`IDENTITY.md`) — agent role, capabilities, and scope declarations.
  - Tools (`TOOLS.md`) — tool availability manifests per agent.
  - Sessions config — session lifecycle settings (timeouts, retry, concurrency).
  - Routing rules — message routing topology definitions.
  - Worker/review prompts — task-specific prompt templates for each agent role.
- **Template variable validation** via `template_registry.json` JSON Schema definitions with type checking and default values, preventing silent template rendering failures.
- **6-check output validation pipeline**:
  1. Plan validation (mode correctness, required fields present)
  2. Cross-reference checks (agent names resolve across artifacts)
  3. Output file existence (all expected artifacts generated)
  4. Agent spec integrity (required fields populated, types correct)
  5. Agent name uniqueness (no collisions across the generated topology)
  6. Routing rule completeness (every agent has inbound/outbound paths)
- **Natural-language convergence conditions** (Completion Gates) embedded in generated AGENTS.md, enabling agent self-governance without a central loop driver — agents autonomously detect completion criteria and signal termination.
- **Template variable schema** (`schemas/template-variables.yaml`) documenting all injectable variables across templates, their types, defaults, and which templates consume each variable.
- **Mode selection decision tree** (`schemas/mode-selection-decision-tree.yaml`) for topology recommendation based on task characteristics (complexity, collaboration needs, review requirements).
- **External cron watchdog guidance** in deployment docs for Gateway health supervision and automatic restart on stall detection.
- **Comprehensive project documentation**:
  - `DESIGN.md` — architectural decisions, data flow, and rationale.
  - `IMPLEMENTATION_PLAN.md` — phased development roadmap and milestones.
  - `ARCHITECTURE_RATIONALE.md` — "why this way" analysis of key design tradeoffs.
  - `runbook.md` — operational procedures for deployment, monitoring, and recovery.
  - `troubleshooting-guide.md` — common failure modes, diagnostic steps, and remediation.
  - `CLAUDE.md` — agent instruction set for AI-assisted development workflows.
- **E2E test suites** covering all three modes: orchestrator (task decomposition and synthesis), peer review (critique-iterate cycle), and sequential pipeline (chain integrity and handoff).
- **Template validation script** (`validate_templates.py`) for CI pipeline integration — verifies all 14 templates parse correctly against their schemas before deployment.
- Zero runtime dependencies beyond Python stdlib + optional Jinja2 (graceful fallback to regex-based rendering).
- **Automated changelog management** with Keep a Changelog format and Semantic Versioning compliance.

[Unreleased]: https://github.com/user/loop-openclaw/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/user/loop-openclaw/releases/tag/v0.1.0
