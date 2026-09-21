# 交接文档：主服务重部署 + Langfuse 部署与追踪启用

> 生成时间：2026-09-21（原执行 agent 额度用尽，移交另一 agent 继续执行）
> 仓库：`/Users/wjh/ResearchAgent_codebuddy`，分支 `main`
> 关联 spec：`docs/sdd/specs/037-startup-readiness-gap-and-ux-bugs.md`（已完成，Bug 1-10 已修复提交）
> 关联部署说明：`deploy/langfuse/README.md`

---

## 0. 本次要完成的目标（用户最终指令）

1. **重部署主服务（端口 8400）**，使其加载 spec-037 全部修复（含 Bug 1-10 与「已批准」文案统一）。
2. **部署/确认 Langfuse 可用**（用户原话"这次部署要部署好 langfuse"）。
3. 启用**后端 → Langfuse 追踪**（让观测真正产生数据，否则 Langfuse 只是空跑）。

> 注意：代码 `git push` **已经完成**（见下方状态核验），无需再 push 代码；只有文档改动可选提交。

---

## 1. 当前已确认状态（执行前务必先核对）

| 项 | 状态 | 证据 |
|---|---|---|
| `main` 与 `origin/main` | **已同步，无未推送提交** | `git log origin/main..HEAD` 为空 |
| 最新提交 | `74a2aa5 fix(spec-037): 统一审批成功文案为「已批准」` | `git log --oneline -3` |
| spec-037 Bug 1-10 修复 | 已提交（`7d36051`）+ 合并冲突修复（`705aae4`） | `git log` 对应文件 |
| 主服务运行进程 | **PID 72405**，端口 8400，启动于 09-21 02:53 | `lsof -iTCP:8400` / `ps` |
| Langfuse 基础设施 | **已在运行**：ClickHouse 8123 / PostgreSQL 5432 / Redis 6379 / MinIO 9002 均 LISTEN | `lsof` 端口检查 |
| Langfuse web/worker | **已在运行**：web 3000 / worker 3030 均 LISTEN | `lsof` 端口检查 |
| `backend/.env` | **不存在**（观测默认 `LANGFUSE_ENABLED=false`，即后端当前**未**向 Langfuse 发追踪） | `ls backend/.env` → 无此文件 |
| 未提交改动 | `M docs/sdd/spec-status-changelog.md`、`?? docs/sdd/specs/041-langfuse-trace-detail-and-waterfall.md` | `git status --short` |

### 关键事实（避免踩坑）
- **Langfuse 用非 Docker 脚本部署**（`deploy/langfuse/start-infra.sh`、`start-langfuse.sh`），**本机不需要 docker**。此前误以为需要 docker 是误判——实际依赖是 ClickHouse/PostgreSQL/Redis/MinIO 命令行常驻进程 + nvm Node v24.20.0。
- `start-langfuse.sh` 硬编码 `LANG_FUSE_DIR="/Users/wjh/ResearchAgent/vendor/langfuse"`（注意是 `ResearchAgent`，非本仓库 `ResearchAgent_codebuddy`）。**两条路径都存在且可用**，无需改动。
- ClickHouse 二进制不在 `PATH`（位于 `~/opt/clickhouse/clickhouse`），但已在运行，端口 8123 UP。
- nvm Node v24.20.0 已安装：`/Users/wjh/.nvm/versions/node/v24.20.0/bin`。

---

## 2. 执行步骤（按顺序）

### Task A — 重部署主服务（端口 8400）

```bash
cd /Users/wjh/ResearchAgent_codebuddy

# A1. 复核最新代码已提交（应看到 74a2aa5 在最上方）
git log --oneline -3

# A2. 停止旧进程（deploy/stop.sh 读取 deploy/run.pid）
bash deploy/stop.sh
# 若 8400 仍被占用（stop 失败或 pid 不匹配），手动清理：
lsof -nP -iTCP:8400 -sTCP:LISTEN -t | xargs -r kill -TERM
sleep 2

# A3. 启动（保持单 worker！start.sh 已禁止 --workers>1，勿加）
PORT=8400 bash deploy/start.sh -d

# A4. 验证启动成功
sleep 3
curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:8400/   # 期望 200
tail -n 30 deploy/run.log
```

> 说明：`start.sh` 默认会尝试启动 reranker（`RERANKER_ENABLED=true`）。若 reranker 启动失败仅降级为 RRF，**不会阻塞主服务**，日志有警告即可忽略。

---

### Task B — 验证 Langfuse 可用（大概率已就绪，仅确认）

```bash
# B1. web 是否返回 200
curl -s -o /dev/null -w 'HTTP %{http_code}\n' --max-time 10 http://127.0.0.1:3000   # 期望 200

# B2. 若非 200，按 deploy/langfuse/README.md 顺序拉起（已运行的服务会 [SKIP]，可重复执行）：
#   bash deploy/langfuse/start-infra.sh
#   # 仅当 /Users/wjh/ResearchAgent/vendor/langfuse/.env 不存在时：
#   cp deploy/langfuse/env.example /Users/wjh/ResearchAgent/vendor/langfuse/.env
#   bash deploy/langfuse/start-langfuse.sh
```

- **登录地址**：http://127.0.0.1:3000
- **账号**：`admin@local.dev` / `langfuse_dev`（见 `deploy/langfuse/env.example` `LANGFUSE_INIT_USER_*`）
- **常见故障**：若 web 报 ClickHouse 权限错误（`Not enough privileges ... grant TABLE ENGINE ON`），需执行 `deploy/langfuse/clickhouse-grants.sql`（README 常见问题 3）。迁移（`--migrate`）**只需首次**；当前已运行说明已迁移，**勿重复加 `--migrate`** 除非数据被清空。

---

### Task C — 启用后端 → Langfuse 追踪（让"部署好 langfuse"真正生效）

后端观测由 `backend/.env`（`load_dotenv()` 加载，且**不覆盖**已有环境变量）控制，当前缺该文件故默认关闭。创建它即可开启：

```bash
cd /Users/wjh/ResearchAgent_codebuddy

# C1. 创建 backend/.env（当前不存在，安全新建）
cat > backend/.env <<'EOF'
LANGFUSE_ENABLED=true
LANGFUSE_HOST=http://127.0.0.1:3000
LANGFUSE_PUBLIC_KEY=pk-lf-local-dev-0001
LANGFUSE_SECRET_KEY=sk-lf-local-dev-0001
LANGFUSE_SAMPLE_RATE=1.0
EOF
```

> 变量来源：key 取自 `deploy/langfuse/env.example` 的 `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` / `SECRET_KEY`；`LANGFUSE_HOST` 默认即 `http://127.0.0.1:3000`。

```bash
# C2. 重新执行 Task A 重部署，使新进程加载 .env（必须，否则不生效）
# （回到 A2~A4）

# C3. 验证追踪真正发出
#   触发一次后端动作（如发起一次对话/检索），然后：
grep -i langfuse deploy/run.log | tail -20        # 应无报错；若有异常见下方回退
#   再到 Langfuse Web → Project "Local Dev" → Tracing，应能看到本次产生的 trace
```

---

### Task D —（可选，SDD 卫生）提交并推送文档改动

```bash
cd /Users/wjh/ResearchAgent_codebuddy
git add docs/sdd/spec-status-changelog.md
git add docs/sdd/specs/041-langfuse-trace-detail-and-waterfall.md
git commit -m "docs(spec-037): 更新状态台账；新增 041 langfuse 追踪详情(待确认)"
git push origin main
```

> **重要约束**：`041-langfuse-trace-detail-and-waterfall.md` 当前状态应为 **`待确认`**。执行 agent **不得**将其改为 `已确认` 或开始实现——spec 确认需用户明确表态（见 `AGENTS.md` 强制流程）。仅做落盘跟踪即可。

---

## 3. 验收标准（完成判据）

- [ ] 主服务 8400 返回 HTTP 200；`git log` 顶部 `74a2aa5` 对应代码已生效（审批成功文案显示「已批准」）。
- [ ] Langfuse web:3000 可登录；Tracing 页面能看到后端产生的 trace（证明 Task C 生效）。
- [ ] `backend/.env` 存在且 `LANGFUSE_ENABLED=true`；主服务重启后 `deploy/run.log` 无观测相关异常。

---

## 4. 回退与风险

- **不想启用后端追踪**：删除 `backend/.env` 或设 `LANGFUSE_ENABLED=false`，再重部署（Task A）。观测设计上失败不影响业务（见 `backend/app/platform/observability/config.py` 的 fail-open 原则）。
- **主服务代码回退**：代码已全部提交，无法回退到"未提交"状态；如需回退提交用 `git revert <commit>` 后重部署。
- **Langfuse 进程管理**：停基础设施 `bash deploy/langfuse/stop-infra.sh`；日常重启 `start-infra.sh` + `start-langfuse.sh`。
- **重复 `--migrate` 风险**：已迁移环境再次 `--migrate` 一般幂等，但清空数据后才需要；当前环境已运行，跳过即可。
- **端口冲突**：主服务固定 8400；若被其它进程占用，先停占用进程再启动（见 A2）。
