# Spec044 合并 main 部署后确认（2026-11-08 11:38 CST）

> 依据 `deploy/VERIFICATION.md` 第 1–7 节的可适用项逐项确认。仅记录脱敏的状态、版本与结果摘要。
> **未执行项如实说明**：未执行「创建测试会话 → 手动 `POST /compactions`」，以免改动用户真实会话数据；本 spec 不涉及上下文压缩链路，全量回归已覆盖该领域测试。其余接口均为真实只读确认。
> 服务：`http://127.0.0.1:8000`（`launchctl` 托管 `com.researchagent.recovery8000`，PID 88588）。
> 分支：`feature/spec-044-conversation-answer-display-and-provenance` @ `74573d7d`，合并前 `main` @ `715a2d7b`。

## 1. Git 与远程分支核对

```
git fetch origin --prune                      → exit 0（清理了已删除的 origin/codex/spec042-offline-evaluation）
git status --short --branch                   → 分支上仅 2 个无关未跟踪项（.playwright-cli/、artifacts/jd-agent-infra-capability-map.md）
git rev-list --left-right --count origin/main...HEAD → 0  1
git rev-list --left-right --count main...origin/main  → 0  0
git merge-base --is-ancestor main HEAD        → exit 0（线性，可 fast-forward / squash）
git diff --check                              → OK: clean
gh pr list --head feature/spec-044-...        → []（无 PR）
gh api repos/compwjh/ResearchAgent/branches/main/protection → 404 "Branch not protected"
```

## 2. SQLite 运行库（只读）

```
SELECT MAX(version) FROM schema_version; → 8（符合基线 v8）
```

基线表均存在：`conversation_compaction_jobs`、`conversation_segments`、`conversations`、`messages`。
本次合并**不涉及 schema 变更**，未停止服务、未重建数据库、未触碰 `legacy-backups/`。

## 3. 服务与接口

| 接口 | 状态 |
|---|---|
| `GET /` | 200 |
| `GET /api/health` | 200 |
| `GET /api/kb/health` | 200 |
| `GET /api/models` | 200 |
| `GET /api/conversations` | 200 |
| `GET /api/conversations/cc9f02f3d8184943bee35b4a23aa9481/context-usage` | 200，返回 `used_tokens=2199 / budget_tokens=20000 / ratio=0.10995 / compaction_status=idle` 与 `breakdown` |

## 4. Ollama

```
GET  http://127.0.0.1:11434/api/tags → 200
POST http://127.0.0.1:11434/api/chat {"model":"qwen3.5:9b",...} → 200，message.content="1"，done=true
```

## 5. 前端静态资源版本（来自活服务首页的真实标签，非缓存页）

```
app.js?v=72                      conversation-research.js?v=2
kb-inspection.js?v=24            processing-tree.js?v=2
styles.css?v=70                  literature-maps.css?v=31
literature-maps.js?v=45          research-session-ui.js?v=2
research-tasks.js?v=21           marked.min.js?v=13
purify.min.js?v=13               vendor/katex/katex.min.css?v=1
vendor/katex/katex.min.js?v=1
```

与本次提交的前端版本契约一致；本地 KaTeX vendor 全部 200，无 CDN。

## 6. 回归与验收

- Spec 收口全量回归：`4030 passed, 2 skipped, 67 subtests passed`，`EXIT=0`（`artifacts/spec044-full-regression.log`）。
- 真实 API E2E 与真实 Chromium B 域 E2E：`artifacts/spec-044-api-sample.md`、`artifacts/spec044-b-domain-e2e.json`。
- Gate 5 验收：`docs/sdd/reviews/044-acceptance-review.md`，30/30 通过、准备度 10/10、`architect` 已签字。
- 用户 2026-11-08 明确反馈「人工验收成功可以收尾了」，人工验收环节已完成。

## 7. 合并门禁真实状态（按 `docs/github.md:23` 如实落盘）

| 门禁 | 规范 | 真实状态 |
|---|---|---|
| CI 全绿 | ① 必须 | **不可验证**：仓库无 `.github/workflows/`（文件数 0），无 CI 运行记录 |
| 测试覆盖率 ≥ 80% | ② 必须 | **不可验证**：无 `pyproject.toml` / `setup.cfg` / `.coveragerc` 覆盖率阈值配置，未采集覆盖率数据 |
| 至少 1 个 approval | ③ 必须 | **不满足**：无 PR（`gh pr list` 返回 `[]`），无 approval 产生 |

**结论：三项门禁均不满足/不可验证，按 `docs/github.md:13` 本应阻断。** 本次合并系仓库所有者于 2026-11-08 明确授权「该分支可以合并到main然后push了」，沿用 Spec043 的处置先例（见 `docs/sdd/spec-status-changelog.md` 2026-11-07 条目）：执行合并与推送，但**不声称 CI 全绿、不声称覆盖率达标、不声称存在 approval**；已在合并 commit message、`spec-status-changelog.md` 与本文同步披露。合并方式为 squash，主干保持线性；远端 `main` 未启用分支保护（非 force push）。

## 8. 已知降级（非 P0/P1）

- Reranker 模型文件缺失 → 服务以 RRF 降级模式运行，**未声称已启用精排**。
- SSE `progress` 帧按设计不携带 `detail_json`，证据明细经历史接口水合。
- 全量回归有 OTel 导出到 `127.0.0.1:3000` 连接被拒的非阻塞告警；浏览器 4 条 404 来自历史会话列表已删除会话的 GET。

## 9. 合并与推送结果（2026-11-08 补录）

```
git checkout main                                            → Switched to branch 'main'
git merge --squash feature/spec-044-...                       → 100 files staged，无冲突标记
git commit -F <msg>                                          → ce47ee16（1 个 squash 提交）
git diff --quiet HEAD feature/spec-044-...                    → exit 0（tree 与 feature 完全一致）
git diff --check                                             → OK
git push origin main                                         → 715a2d7b..ce47ee16  main -> main（非 force）
git fetch origin --prune && git rev-list --left-right --count main...origin/main → 0  0
git merge-base --is-ancestor 715a2d7b origin/main             → exit 0（上一版 main 保留，可回滚）
```

- 远端 `origin/main` HEAD = `ce47ee16`，与本地 `main` 完全一致；远端 spec-044 分支本就不存在（从未 push 该分支），故无需删除远端分支。
- 本地源分支采用 `git branch -D` 删除：squash 合并不产生 merge 关系，`git branch -d` 会报「not fully merged」；删除前已用 tree 一致性 + 远端已推送 + 上一版 main 可回滚三点确认内容零丢失。
- 服务未重启（代码与合并前运行版本完全相同）。**合并后在工作树已切到 `main` 的情况下再次真实探活**：`/`、`/api/health`、`/api/kb/health`、`/api/models`、`/api/conversations` 全部 200；首页真实标签仍为 `app.js?v=72`、`styles.css?v=70`、`processing-tree.js?v=2`、`katex.min.css?v=1`、`katex.min.js?v=1`。
- 本地源分支已用 `git branch -D` 删除并确认 `git branch --list 'feature/spec-044*'` 为空；远端 `origin/main` 已含全部内容（`ce47ee16`），上一版 `715a2d7b` 保留可回滚。
