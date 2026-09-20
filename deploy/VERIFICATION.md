# 部署后确认流程

本文件是每次合并远程分支、重建运行时数据或切换部署端口后的固定确认清单。确认顺序不能跳过；任何一项失败都不能把服务声明为“可用”。

## 1. Git 与远程分支核对

```bash
git fetch origin --prune
git status --short --branch
git rev-list --left-right --count origin/main...HEAD
git branch -r
```

对每个候选 PR 分支执行：

```bash
git merge-base --is-ancestor origin/<branch> HEAD
```

退出码为 `0` 才表示该分支已经包含在当前提交中。不能只根据分支名称或 PR 页面判断“已合并”。合并后必须再次执行 `git diff --check` 和 `git status`。

## 2. SQLite 运行库确认

先停止服务，再读取版本和文件状态：

```bash
./deploy/stop.sh
sqlite3 data/memory/memory.sqlite3 'SELECT MAX(version) FROM schema_version;'
ls -l data/memory/memory.sqlite3*
```

当前内存库基线为 **schema v8**。发现 v1–v7 时，不在旧库上强行迁移；按以下顺序保留可恢复备份并重建：

```bash
backup_dir="data/memory/legacy-backups/<timestamp>-v<old-version>"
mkdir -p "$backup_dir"
mv data/memory/memory.sqlite3 "$backup_dir/memory.sqlite3"
mv data/memory/memory.sqlite3-shm "$backup_dir/memory.sqlite3-shm" 2>/dev/null || true
mv data/memory/memory.sqlite3-wal "$backup_dir/memory.sqlite3-wal" 2>/dev/null || true
```

启动后确认新库：

```bash
sqlite3 data/memory/memory.sqlite3 'SELECT MAX(version) FROM schema_version;'
sqlite3 data/memory/memory.sqlite3 "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
```

必须得到版本 `8`，并包含 `conversation_segments`、`conversation_compaction_jobs`、`messages`、`conversations` 等新基线表。旧库只允许留在 `legacy-backups/`，不得删除或覆盖。

## 3. 服务启动与依赖确认

端口被占用时选择空闲端口；知识库本地 Qdrant 只能单进程打开：

```bash
PORT=8500 RERANKER_ENABLED=false ./deploy/start.sh -d
```

如果后台启动受到宿主机/沙箱限制，改用前台启动并保持终端进程存活：

```bash
PORT=8500 RERANKER_ENABLED=false ./deploy/start.sh
```

确认：

```bash
curl -fsS -w '\nhealth:%{http_code}\n' http://127.0.0.1:8500/api/health
curl -fsS -o /tmp/researchagent-home.html -w 'home:%{http_code} bytes:%{size_download}\n' http://127.0.0.1:8500/
curl -fsS http://127.0.0.1:8500/api/models
```

健康接口和首页必须返回 `200`。Reranker 被禁用时只能记录为 RRF 降级，不能伪称已启用精排。

## 4. Ollama 确认

`OLLAMA_HOST=0.0.0.0:11434` 是服务监听地址，不应作为客户端的唯一语义依据；客户端应使用本机回环地址或实际局域网 IP。部署机必须先确认标签接口和最小对话：

```bash
curl -fsS --max-time 10 http://127.0.0.1:11434/api/tags
curl -fsS --max-time 60 -X POST http://127.0.0.1:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.5:9b","messages":[{"role":"user","content":"只回复1"}],"stream":false,"think":false,"options":{"num_predict":8}}'
```

标签和最小对话均成功，才可继续做应用层对话验证。标签成功但对话超时，应记录为模型加载/推理性能问题，不归因于 Web 服务连接失败。

## 5. 前端资源版本确认

```bash
curl -fsS http://127.0.0.1:8500/ > /tmp/researchagent-home.html
rg -o 'assets/(app|styles)\.js?\?v=[0-9]+' /tmp/researchagent-home.html
test -s frontend/app.js
test -s frontend/styles.css
```

页面引用的版本号必须与本次提交的静态资源契约一致；不能只看浏览器缓存页面。

## 6. 会话与上下文压缩确认

至少验证以下接口，而不是只验证 `/api/health`：

```bash
curl -fsS http://127.0.0.1:8500/api/conversations
curl -fsS http://127.0.0.1:8500/api/health
```

创建测试会话后确认：

```bash
curl -fsS http://127.0.0.1:8500/api/conversations/<conversation_id>/context-usage
curl -fsS -X POST http://127.0.0.1:8500/api/conversations/<conversation_id>/compactions
```

`context-usage` 必须返回预算、占用和 `compaction_status`；手动压缩必须返回任务状态，而不是 `500 memory schema migration failed`。验证结束后删除测试会话或在验收记录中注明测试数据。

## 7. 回归与证据

- Task 开发只跑受影响领域测试。
- Spec 收口才跑唯一一次全量回归。
- 记录命令、退出码、通过/失败数量、端口、Git 提交、数据库版本、Ollama 模型和已知降级。
- 失败时先保留日志和数据库备份，不使用 `reset`、`stash`、`clean` 或覆盖用户修改。

建议证据目录：`deploy/evidence/<YYYYMMDD-HHMM>/`。该目录只保存脱敏的状态、版本和结果摘要，不保存密码、Cookie、Token、完整 Prompt 或论文正文。

## 8. 回滚

```bash
./deploy/stop.sh
mv data/memory/memory.sqlite3 data/memory/failed-v8.sqlite3
mv data/memory/legacy-backups/<timestamp>-v7/memory.sqlite3 data/memory/memory.sqlite3
```

回滚后重新执行第 2–6 节。旧库仍可能被当前代码拒绝，这是预期的 fail-closed 行为；此时应恢复代码与数据库的匹配版本，而不是绕过 schema 检查。

## 9. 2026-09-16 部署复盘

- 远程分支审计确认：`feature/spec-035-online-model-provider` 的提交 `6fe3523` 已包含在本地 `main` 和 `origin/main`；`feature/spec-027-research-task-mvp` 的额外提交也已在本地合并。不能仅凭分支名称判断功能是否遗漏，必须使用 `merge-base --is-ancestor`。
- 故障表现：健康接口可用，但 `/api/conversations` 和上下文压缩接口返回 500；启动日志为 `memory schema migration failed; startup is fail-closed`。
- 根因：工作树中的 Spec038 代码要求 memory schema v8，运行目录仍是历史 v7 数据库。代码按设计拒绝在旧库上半迁移。
- 处置：停止服务，将旧库及 `-shm`/`-wal` sidecar 保存在 `data/memory/legacy-backups/20260916-v7/`，启动时创建全新 v8 库；旧库未删除。
- 验证：schema version `8`；`/api/health`、`/api/conversations`、`/api/models`、首页和静态资源均 HTTP 200；临时会话的 `context-usage` 和手动 `compactions` 均 HTTP 200；Ollama `/api/tags` 和最小 9B 对话均成功。
- 回归：受控环境全量 `2407 passed, 1 failed, 1 skipped, 67 subtests`；唯一失败 `test_available_models_bypasses_system_proxy` 在全套顺序运行中受 Ollama 负缓存与沙箱网络限制影响，单独运行通过，不能据此宣称所有外部环境均可用。内存基线、上下文使用/压缩定向测试另行 `5 passed`。

### 9.1 历史上下文恢复记录

如果 v8 数据库能够启动但界面没有历史会话或上下文占用，先区分“前端指标隐藏”与“数据库确实没有历史数据”：

1. 保留当前 v8 快照，不覆盖现有库；本次快照为 `data/memory/legacy-backups/20260916-v8-before-restore/`。
2. 从 `data/memory/legacy-backups/20260916-v7/memory.sqlite3` 读取旧库，只对共有业务表执行 `INSERT OR IGNORE`，不把旧 schema 直接替换回运行目录。
3. 本次恢复结果为：`projects=1`、`conversations=57`、`messages=148`、`processing_steps=259`；旧库中的 56 条会话和 146 条消息被保留，临时测试会话未被覆盖。
4. 将仍然有效的旧记忆迁移到 Markdown 记忆层，再重建 FTS 索引：消息索引 148 条、记忆文档 3 条。删除的旧记忆不恢复。
5. 重启后必须同时验证：会话列表能返回历史记录、具体会话的 `context-usage` 返回 200、浏览器打开该会话后出现上下文百分比和“压缩”按钮。

空白新会话仍按设计隐藏上下文占用条；这不表示历史数据丢失。只有打开已有会话，或新会话发送第一条消息后，才展示实际占用值。

### 9.2 2026-09-16 Spec034 收口部署

- 本地 `main` 已合并 `origin/main`（远程已合并的认证 PDF、深链刷新和内存基线修复）以及 Spec034 修复分支；当前提交：`7970aa0`。
- SQLite 检查：`data/memory/memory.sqlite3` 为 schema v8，包含 `conversations`、`messages`、`conversation_segments`、`conversation_compaction_jobs` 等表。
- 全量回归：`COMPACTION_SUMMARY_MODE=rule .venv/bin/python -m pytest -q`，退出码 0，`2478 passed, 1 skipped, 67 subtests passed`。
- 运行时：前台 `PORT=8500 RERANKER_ENABLED=false ./deploy/start.sh`；`/api/health`、`/api/models`、首页、`/c/{conversation_id}` 深链、`/api/conversations`、已有会话 `context-usage` 和手动 `compactions` 均返回 200；未知 `/api/*` 返回 404。
- 静态资源：页面引用 `app.js?v=53`、`styles.css?v=53` 和 `research-session-ui.js?v=2`；Reranker 未启用，按 RRF 降级运行。
- Ollama：健康接口检测到本机模型列表；本次未把模型推理作为部署门禁，真实模型可用性仍以部署机 Ollama 状态为准。
