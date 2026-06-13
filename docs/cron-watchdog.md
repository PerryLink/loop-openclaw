# External Cron Watchdog 文档

> 适用: loop-openclaw 生成的 OpenClaw Gateway 部署

---

## 1. 背景

OpenClaw Gateway 缺少内置 loop 驱动 —— agent 完成回答后停止，不会自动触发下一轮。loop-openclaw 通过 AGENTS.md 中的自然语言指令引导 agent 自主循环，但这属于"软性"机制。外部 cron watchdog 作为补充安全网，监控循环健康。

---

## 2. Cron 调度

推荐每 5 分钟执行一次健康检查：

```bash
crontab -e
*/5 * * * * /opt/loop-openclaw/scripts/watchdog.sh >> /var/log/loop-watchdog.log 2>&1
```

---

## 3. Watchdog 脚本

```bash
#!/bin/bash
# watchdog.sh — loop-openclaw 外部健康监控
set -euo pipefail
OUTPUT_DIR="/opt/loop-openclaw/output"
MAX_IDLE_MINUTES=30
DISK_PCT_CRIT=90

# 检查 1: 输出文件新鲜度
NOW=$(date +%s)
for f in openclaw.json SOUL.md AGENTS.md IDENTITY.md TOOLS.md; do
    FP="$OUTPUT_DIR/$f"
    if [ ! -f "$FP" ]; then
        echo "[ALERT] 输出文件缺失: $FP"; continue
    fi
    AGE=$(( (NOW - $(stat -c %Y "$FP")) / 60 ))
    if [ "$AGE" -gt "$MAX_IDLE_MINUTES" ]; then
        echo "[ALERT] $f 已 $AGE 分钟未更新（阈值: ${MAX_IDLE_MINUTES}min）"
    fi
done

# 检查 2: render.py 日志错误
GOT_ERR=$(grep -c "\[ERROR\]" /var/log/loop-openclaw/render.log 2>/dev/null || echo 0)
if [ "$GOT_ERR" -gt 5 ]; then
    echo "[ALERT] render.py 错误数异常: $GOT_ERR"
fi

# 检查 3: 磁盘使用率
DISK=$(df -h "$OUTPUT_DIR" | awk 'NR==2 {gsub(/%/,""); print $5}')
if [ "${DISK:-0}" -ge "$DISK_PCT_CRIT" ]; then
    echo "[CRITICAL] 磁盘使用率 ${DISK}% >= ${DISK_PCT_CRIT}%"
fi

echo "[OK] Watchdog @ $(date -Iseconds)"
```

---

## 4. 告警阈值与升级

| 级别 | 条件 | 动作 |
|------|------|------|
| WARN | 输出文件 > 30min 未更新 | 记录日志，Slack 通知 |
| ALERT | render.py 错误 > 5 条 | Slack/邮件告警 |
| CRITICAL | 磁盘使用率 >= 90% | PagerDuty/短信，建议清理 |
| EMERGENCY | 连续 3 次 CRITICAL | 暂停新任务，通知 on-call |

升级路径: WARN (30min) -> ALERT (60min) -> CRITICAL (120min) -> EMERGENCY (人工)。

---

## 5. 日志轮转

```bash
# /etc/logrotate.d/loop-openclaw
/var/log/loop-openclaw/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    maxsize 50M
}
```

保留 14 天，按天轮转，超过 50MB 强制轮转。

---

## 6. 恢复流程

### 场景 A: 输出过期（loop 停滞）

1. 检查 Gateway 健康: `curl -s $GATEWAY_URL/api/health`
2. 检查 agent 会话: `curl -s $GATEWAY_URL/api/sessions`
3. 若 Gateway 正常: 检查 AGENTS.md 收敛条件是否过严
4. 手动触发新一轮: 向 Gateway 发送入站消息

### 场景 B: 磁盘不足

1. 清理旧日志: `find /var/log/loop-openclaw -mtime +7 -delete`
2. 删除旧渲染输出: 仅保留最近 3 个版本
3. 扩容或迁移日志分区

### 场景 C: render.py 频繁报错

1. 检查 template_registry.json 完整性
2. 检查 artifacts/03-config-plan.md 格式
3. `python render.py --validate-only` 定位问题
4. 重新生成配置

---

## 7. 注意事项

- Watchdog 不修改配置、不重启 Gateway、不注入消息
- Watchdog 是补充安全网，核心 loop 驱动依赖 AGENTS.md 指令
- 建议在 Gateway 运维文档中记录 watchdog 安装步骤
