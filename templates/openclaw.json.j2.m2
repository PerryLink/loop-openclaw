{# ============================================================ #}
{# openclaw.json.j2 — OpenClaw Gateway 主配置模板              #}
{# JSON5 格式：允许注释、尾逗号、裸键                          #}
{# Jinja2 渲染后输出为 output/openclaw.json                     #}
{# ============================================================ #}
{
  // ==========================================================
  // {{ project_name }} — OpenClaw Gateway 配置
  // 由 loop-openclaw 配置生成器自动生成
  // 生成时间: {{ created_at }}
  // 生成器版本: {{ generator_version }}
  // Loop 模式: {{ loop_mode }}
  // ==========================================================

  "gateway": {
    "name": "{{ project_name }}",
    "version": "1.0.0",
    "description": "{{ project_description }} — Loop mode: {{ loop_mode }}",
    "log_level": "{{ log_level | default('info') }}",
    "max_concurrent_sessions": {{ max_concurrent_sessions | default(agents | length * 2) }},
    "session_timeout_seconds": {{ session_timeout_seconds | default(3600) }}
  },

  // ==========================================================
  // Agent 定义
  // 每个 agent 有独立的模型、系统提示词、权限边界
  // ==========================================================
  "agents": {
    {% for agent in agents %}
    "{{ agent.id }}": {
      // {{ agent.role_display }} — {{ agent.responsibility }}
      "name": "{{ agent.name }}",
      "role": "{{ agent.role }}",
      "model": "{{ agent.model | default('claude-sonnet-4-20250514') }}",
      "system_prompt": "{{ agent.system_prompt | default(agent.role_display + ' agent for ' + project_name) }}",
      "persona_files": [
        "SOUL.md",
        "IDENTITY.md",
        "TOOLS.md",
        "AGENTS.md"
      ],
      "permissions": {
        // 文件系统访问范围
        "file_scope": [
          {% for path in agent.permissions.file_scope | default(['./workspace']) %}
          "{{ path }}"{% if not loop.last %},{% endif %}
          {% endfor %}
        ],
        // 网络访问控制
        "network": {
          "allow": [
            {% for host in agent.permissions.network.allow | default([]) %}
            "{{ host }}"{% if not loop.last %},{% endif %}
            {% endfor %}
          ],
          "deny": [
            {% for host in agent.permissions.network.deny | default([]) %}
            "{{ host }}"{% if not loop.last %},{% endif %}
            {% endfor %}
          ]
        },
        // 允许的命令
        "allowed_commands": [
          {% for cmd in agent.permissions.allowed_commands | default([]) %}
          "{{ cmd }}"{% if not loop.last %},{% endif %}
          {% endfor %}
        ],
        // 禁止的命令
        "blocked_commands": [
          {% for cmd in agent.permissions.blocked_commands | default([]) %}
          "{{ cmd }}"{% if not loop.last %},{% endif %}
          {% endfor %}
        ],
        // Agent 间通信 — 允许向哪些 agent 发送消息
        "sessions_send": [
          {% for target in agent.permissions.sessions_send | default([]) %}
          "{{ target }}"{% if not loop.last %},{% endif %}
          {% endfor %}
        ],
        // Agent 间通信 — 允许派生子任务给哪些 agent
        "sessions_spawn": [
          {% for target in agent.permissions.sessions_spawn | default([]) %}
          "{{ target }}"{% if not loop.last %},{% endif %}
          {% endfor %}
        ]
      },
      // Agent 能力声明
      "capabilities": {
        "can_read_files": {{ agent.capabilities.can_read_files | default(true) | lower }},
        "can_write_files": {{ agent.capabilities.can_write_files | default(false) | lower }},
        "can_execute_code": {{ agent.capabilities.can_execute_code | default(false) | lower }},
        "can_install_dependencies": {{ agent.capabilities.can_install_dependencies | default(false) | lower }},
        "can_search_web": {{ agent.capabilities.can_search_web | default(false) | lower }},
        "can_spawn_subagents": {{ (agent.permissions.sessions_spawn if agent.permissions is defined else []) | length > 0 | lower }}
      }
    }{% if not loop.last %},{% endif %}
    {% endfor %}
  },

  // ==========================================================
  // 频道配置
  // Agent 通过频道与外部用户交互
  // ==========================================================
  "channels": [
    {% for channel in channels %}
    {
      "id": "{{ channel.id }}",
      "type": "{{ channel.type }}",
      "config": {
        {% for key, value in channel.config.items() %}
        "{{ key }}": {{ value | tojson }}{% if not loop.last %},{% endif %}
        {% endfor %}
      },
      "routing_rules": {
        "inbound": {
          "default_agent": "{{ channel.routing_rules.inbound.default_agent | default(agents[0].id) }}"
        },
        "outbound": {
          "enabled": {{ channel.routing_rules.outbound.enabled | default(true) | lower }},
          "format": "{{ channel.routing_rules.outbound.format | default('markdown') }}"
        }
      }
    }{% if not loop.last %},{% endif %}
    {% endfor %}
  ],

  // ==========================================================
  // 路由规则
  // 定义 agent 间的消息路由和 handoff 逻辑
  // ==========================================================
  "routing": [
    {% for rule in routing_rules %}
    {
      "id": "{{ rule.id }}",
      "description": "{{ rule.description }}",
      "from": "{{ rule.from }}",
      "to": "{{ rule.to }}",
      "method": "{{ rule.method }}",
      "condition": "{{ rule.condition }}",
      "priority": "{{ rule.priority | default('normal') }}",
      "retry_on_failure": {{ rule.retry_on_failure | default(true) | lower }},
      "max_retries": {{ rule.max_retries | default(1) }}
    }{% if not loop.last %},{% endif %}
    {% endfor %}
  ],

  // ==========================================================
  // Loop 配置
  // loop-openclaw 特有的 loop 控制参数
  // ==========================================================
  "loop_config": {
    "mode": "{{ loop_mode }}",
    "convergence_rounds": {{ convergence_rounds }},
    "max_cycles": {{ max_cycles }},
    "max_duration_minutes": {{ max_duration_minutes }},
    "message_ack_timeout_seconds": {{ message_ack_timeout_seconds }},
    "hard_stop_enabled": true,
    "escape_detection_enabled": true,
    "escape_detection_similarity_rounds": 2
  },

  // ==========================================================
  // 日志与监控
  // ==========================================================
  "monitoring": {
    "enabled": {{ monitoring.enabled | default(true) | lower }},
    "log_agent_messages": {{ monitoring.log_agent_messages | default(true) | lower }},
    "log_convergence_checks": {{ monitoring.log_convergence_checks | default(true) | lower }},
    "alert_on_hard_stop": {{ monitoring.alert_on_hard_stop | default(true) | lower }},
    "alert_on_escape_detected": {{ monitoring.alert_on_escape_detected | default(true) | lower }},
    "alert_on_security_breach": {{ monitoring.alert_on_security_breach | default(true) | lower }}
  }
}
