# Security Policy / 安全策略

> **loop-openclaw** -- Configuration Generator & Template Renderer for OpenClaw Gateway
> Copyright (c) 2026 Perry Link. Licensed under Apache License 2.0.

---

## Supported Versions / 支持的版本

We release patches for security vulnerabilities in the following versions. / 我们为以下版本发布安全漏洞补丁。

| Version / 版本 | Supported / 支持状态          |
|----------------|-------------------------------|
| 1.x.x          | :white_check_mark: Supported  |
| < 1.0          | :x: End of life               |

Only the latest minor release within the current major version receives security
fixes. Users are strongly encouraged to upgrade to the most recent release
before reporting a vulnerability -- the issue may already be resolved.

只有当前主版本的最新次要版本会收到安全修复。强烈建议用户在报告漏洞之前升级到最新版本 -- 该问题可能已经被修复。

---

## Reporting a Vulnerability / 报告漏洞

**We take security seriously.** If you discover a security vulnerability in
loop-openclaw, please report it responsibly. / 如果您在 loop-openclaw 中发现
安全漏洞，请负责任地报告。

### Primary Contact / 主要联系方式

| Channel / 渠道       | Details / 详情                        |
|-----------------------|----------------------------------------|
| Email / 电子邮件      | **novelnexusai@outlook.com**           |
| GitHub Maintainer     | **PerryLink**                          |

### What to Include / 报告内容

- A detailed description of the vulnerability and its potential impact.
- Steps to reproduce the issue, including a minimal proof-of-concept if possible.
- The affected version(s) of loop-openclaw.
- Any suggested mitigations or fixes you may have.

- 漏洞的详细描述及其潜在影响。
- 复现步骤，如可能请附上最小化的概念验证。
- 受影响的 loop-openclaw 版本。
- 您认为可行的缓解措施或修复建议（如有）。

### Response Timeline / 响应时间

| Phase / 阶段                         | Target / 目标时间 |
|--------------------------------------|---------------------|
| Initial acknowledgment / 初步确认    | Within 48 hours     |
| Triage & severity assessment / 评估  | Within 5 business days |
| Patch development / 补丁开发         | Within 15 business days (severity-dependent) |
| Public disclosure / 公开披露         | After patch is released and users have had a reasonable upgrade window |

Please do **not** publicly disclose the vulnerability before we have had an
opportunity to investigate and release a fix. We follow coordinated disclosure
practices and will credit reporters in the release notes unless you request
anonymity.

请**不要**在我们有机会调查并发布修复之前公开披露漏洞。我们遵循协调披露实践，
并将在发行说明中致谢报告者（除非您要求匿名）。

---

## Security Model / 安全模型

### Overview / 概述

loop-openclaw is a **configuration generator** -- it reads a configuration plan
(Markdown or JSON), renders Jinja2 templates, and writes output files. It is
**not** a runtime loop engine, does **not** expose network services, and does
**not** accept unsanitized user input at runtime. This architectural choice
minimizes the attack surface.

loop-openclaw 是一个**配置生成器** -- 它读取配置计划（Markdown 或 JSON），渲染
Jinja2 模板，并写入输出文件。它**不是**运行时循环引擎，**不**暴露网络服务，
也**不**在运行时接受未净化的用户输入。这一架构选择最小化了攻击面。

### Template Injection Protection / 模板注入防护

The primary security mechanism for template rendering is Jinja2's
**`StrictUndefined`**, enforced at multiple levels:

模板渲染的主要安全机制是 Jinja2 的 **`StrictUndefined`**，在多个层面强制执行：

1. **Environment-level enforcement / 环境级别执行**

   The Jinja2 `Environment` is constructed with `undefined=StrictUndefined`,
   ensuring that **every** template rendering raises an `UndefinedError` when
   an undefined variable is accessed -- rather than silently substituting an
   empty string, which could mask injection or misconfiguration.

   Jinja2 `Environment` 使用 `undefined=StrictUndefined` 构建，确保**每次**
   模板渲染在访问未定义变量时都会抛出 `UndefinedError` -- 而不是静默替换为空
   字符串，避免掩盖注入或配置错误。

2. **Two-phase rendering strategy / 两阶段渲染策略**

   - **Phase 1 (strict) / 第一阶段（严格）**: Render with `StrictUndefined`.
     Any undefined variable raises `UndefinedError` immediately.
     使用 `StrictUndefined` 渲染。任何未定义变量立即抛出 `UndefinedError`。

   - **Phase 2 (forgiving fallback) / 第二阶段（宽容回退）**: If phase 1 fails,
     the renderer retries with `Undefined` (default forgiving mode) and logs a
     warning to stderr. This ensures graceful degradation while alerting the
     operator that the template references variables not present in the config
     plan -- a potential misconfiguration or injection indicator.
     如果第一阶段失败，渲染器使用 `Undefined`（默认宽容模式）重试，并向 stderr
     输出警告。这确保了优雅降级，同时提醒操作员模板引用了配置计划中不存在的
     变量 -- 这可能是配置错误或注入的信号。

3. **Variable registry validation (`validate_templates.py`) / 变量注册表验证**

   A standalone validator cross-references every variable reference in `.j2`
   templates against the canonical `template_registry.json`. Any variable
   referenced in a template but not declared in the registry is flagged as an
   error -- preventing template authors from introducing unvetted variable
   paths.

   独立的验证脚本将 `.j2` 模板中的每个变量引用与权威的
   `template_registry.json` 进行交叉验证。模板中引用但未在注册表中声明的任何
   变量都会被标记为错误 -- 防止模板作者引入未经审查的变量路径。

4. **Output validation checklist / 输出验证检查清单**

   Post-render validation (basic and strict levels) ensures generated output
   files are syntactically valid, structurally coherent, and free of
   injection artifacts before they are deployed to the Gateway.

   渲染后验证（基本级别和严格级别）确保生成的输出文件在部署到 Gateway 之前
   语法有效、结构一致且无注入痕迹。

### Input Sanitization / 输入净化

- All config-plan input is parsed through structured Markdown/JSON parsers with
  explicit section-matching; free-form text is never interpolated into code
  contexts without escaping.
- The project enforces a strict **allowlist model**: only variables declared in
  `template_registry.json` are recognized during rendering. Unknown keys are
  rejected at validation time, not at runtime.

- 所有配置计划输入通过结构化的 Markdown/JSON 解析器处理，具有明确的章节匹配；
  自由格式文本不会在未转义的情况下插入到代码上下文中。
- 项目强制执行严格的**白名单模型**：只有 `template_registry.json` 中声明的
  变量在渲染期间被识别。未知键在验证时即被拒绝，而非在运行时。

### Architecture-Level Mitigations / 架构层面缓解

| Principle / 原则                    | Implementation / 实现 |
|--------------------------------------|------------------------|
| Single-file codebase / 单文件代码库  | All logic in `render.py` -- full audit in one pass |
| No runtime network exposure / 无运行时网络暴露 | No HTTP server, no sockets, no external listeners |
| Read-only output / 只读输出模式      | Writes only to `output/`; never modifies source templates or config |
| Graceful degradation / 优雅降级      | If Jinja2 is unavailable, falls back to regex-based string substitution (zero dependency) |
| No `eval` / 不使用 eval              | No dynamic code execution; all parsing is declarative |

---

## Dependency Security / 依赖安全

### Runtime Dependencies / 运行时依赖

| Package / 包 | Required / 必需 | Version / 版本 | Purpose / 用途 |
|---------------|-------------------|-----------------|-----------------|
| Python        | Yes / 是         | >= 3.10         | Runtime / 运行时 |
| Jinja2        | **Optional** / 可选 | >= 3.0          | Template engine (primary) / 模板引擎（主要） |

### Dependency Policy / 依赖策略

1. **Minimal dependency footprint / 最小依赖足迹**

   The project has exactly **one** optional third-party dependency: Jinja2.
   This is a deliberate design decision to minimize supply-chain risk. When
   Jinja2 is not installed, the renderer falls back to zero-dependency regex
   string substitution.

   项目仅有一个可选第三方依赖：Jinja2。这是刻意为之的设计决策，旨在最小化
   供应链风险。当 Jinja2 未安装时，渲染器回退到零依赖的正则字符串替换。

2. **Pinned versions / 版本锁定**

   We recommend pinning Jinja2 to a known-good version in your deployment
   environment (e.g., `jinja2==3.1.4`). Check the
   [Jinja2 changelog](https://github.com/pallets/jinja/releases) for
   security advisories before upgrading.

   我们建议在部署环境中将 Jinja2 锁定到已知良好版本（如
   `jinja2==3.1.4`）。升级前请查阅
   [Jinja2 更新日志](https://github.com/pallets/jinja/releases) 中的安全公告。

3. **Vulnerability monitoring / 漏洞监控**

   We monitor the following sources for dependency vulnerabilities:
   - [Jinja2 Security Advisories](https://github.com/pallets/jinja/security/advisories)
   - [Python Security Announcements](https://www.python.org/news/security/)
   - [GitHub Advisory Database](https://github.com/advisories)

   我们监控以下来源的依赖漏洞：
   - [Jinja2 安全公告](https://github.com/pallets/jinja/security/advisories)
   - [Python 安全公告](https://www.python.org/news/security/)
   - [GitHub 咨询数据库](https://github.com/advisories)

4. **Supply-chain integrity / 供应链完整性**

   All releases are signed and published exclusively through the official
   GitHub repository. We do not distribute packages through PyPI or other
   third-party registries. Verify the repository URL before cloning:

   所有发行版均经过签名，并仅通过官方 GitHub 仓库发布。我们不通过 PyPI 或
   其他第三方注册表分发软件包。克隆前请验证仓库 URL：

   ```
   https://github.com/PerryLink/loop-openclaw
   ```

---

## Disclosure Policy / 披露政策

### Coordinated Disclosure / 协调披露

We follow the **coordinated vulnerability disclosure** model:

1. Reporter submits vulnerability privately via email or GitHub.
2. Maintainer acknowledges receipt within 48 hours.
3. Maintainer investigates, reproduces, and develops a fix.
4. A security advisory (GitHub Security Advisory or CVE if warranted) is
   drafted.
5. The patch is released, and the advisory is published.
6. Reporter is credited (with consent).

我们遵循**协调漏洞披露**模型：

1. 报告者通过电子邮件或 GitHub 私下提交漏洞。
2. 维护者在 48 小时内确认收到。
3. 维护者调查、复现并开发修复方案。
4. 起草安全公告（如需要，通过 GitHub Security Advisory 或 CVE）。
5. 发布补丁和公告。
6. 在获得同意后致谢报告者。

### Scope / 范围

The following are **in scope** for security reports:

- Template injection vulnerabilities (e.g., bypassing `StrictUndefined`).
- Path traversal in template loading or output writing.
- Deserialization or injection through config-plan parsing.
- Vulnerabilities that allow arbitrary code execution through crafted input.

**In scope / 范围内：**

- 模板注入漏洞（例如绕过 `StrictUndefined`）。
- 模板加载或输出写入中的路径遍历。
- 通过配置计划解析的序列化漏洞或注入。
- 允许通过精心构造的输入执行任意代码的漏洞。

The following are **out of scope**:

- Vulnerabilities in the OpenClaw Gateway itself (report those to the Gateway
  maintainers).
- Vulnerabilities in generated output files that result from user-supplied
  configuration, not from loop-openclaw's rendering logic.
- Denial-of-service through resource exhaustion (Jinja2 loop/recursion limits
  are not enforced by this project -- users control their own templates).

**Out of scope / 范围外：**

- OpenClaw Gateway 本身的漏洞（请向 Gateway 维护者报告）。
- 由用户提供的配置（而非 loop-openclaw 渲染逻辑）导致的生成输出文件中的漏洞。
- 通过资源耗尽进行的拒绝服务攻击（本项目不强制执行 Jinja2 循环/递归限制 --
  用户控制自己的模板）。

### Safe Harbor / 安全港

We will not pursue legal action or file complaints against security researchers
who comply with this disclosure policy. We consider vulnerability research
conducted in accordance with this policy to be:

- Authorized under applicable anti-hacking laws.
- Exempt from restrictions in our Terms of Service that would otherwise
  interfere.

我们不会对遵守本披露政策的安全研究人员采取法律行动或提起投诉。我们认为按照
本政策进行的漏洞研究：

- 根据适用的反黑客法律是经授权的。
- 免于受我们服务条款中可能产生干扰的限制。

---

*This security policy was adopted on 2026-06-13. It may be revised from time to
time; the latest version is always available in the repository root.*

*本安全策略于 2026-06-13 生效。可能不时修订；最新版本始终可在仓库根目录找到。*
