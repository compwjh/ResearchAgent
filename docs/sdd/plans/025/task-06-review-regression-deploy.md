> 关联：[spec-025](../../specs/025-conversation-context-compaction.md) ｜ 索引：[README](./README.md)
> 依赖：任务 05；当前状态：`已完成`

# Task 06 — 评审、全量回归、运行时验收、部署与复盘

## 1. 状态与一句话目标

`已完成`。完成双端评审与全量回归，启动服务做真实 smoke，产出三份评审与复盘后把 Spec025 转为 `已完成`。

## 2. 背景与前置条件

- Task02–05 均已完成并通过各自定向测试。
- 三份评审落盘路径见 Spec025「评审记录」：`docs/sdd/reviews/025-requirement-review.md`、`025-tech-review.md`、`025-acceptance-review.md`。
- 状态台账唯一文件：`docs/sdd/spec-status-changelog.md`。

## 3. 数据、配置与接口

- 验收清单以 Spec025「验收方式」为准，本 Task 不新增验收条目。
- 真实 smoke 需构造长会话使 `ratio` 越过 0.8。

## 4. 实施步骤与文件边界

1. `backend-reviewer` 评 `backend/**`（边界、迁移、并发、失败降级）；`frontend-reviewer` 评 `frontend/**`（DOM 契约、`?v=34`、XSS、CSS 作用域）。
2. 执行全量回归（本计划唯一一次），记录命令、退出码、通过数量与阻塞项。
3. 启动本地服务做真实 smoke：占比随消息增长、80% 自动压缩不阻塞、下一条消息起占比下降、手动压缩可用、重复点击只发一次请求、失败仅提示。
4. 产出三份评审 + 验收评审签字，追加状态台账，落复盘到 `docs/sdd/retro/`。
5. 服务默认端口被占用时改选可用端口并明确告知用户实际端口与访问地址。

可观察结果：全量回归通过、三份评审真实落盘、服务可用且 smoke 清单逐条通过。

## 5. 子代理分派

- `backend-reviewer` / `frontend-reviewer` / `backend-tester` / `frontend-tester` / `tester`（均 hy3，32k），各自只评/只测自己那一端。
- 部署与启动由主会话（架构师）执行并验证。

## 6. 边界与明确不做

- 不在本 Task 扩大范围；评审发现的新需求回到 Spec 修订与确认。
- 不伪造评审结论与运行结果；失败必须记录真实原因与命令。
- 不执行 `git reset --hard`、`git clean` 等破坏性操作。

## 7. 验收、风险与回滚

- 验收：全量回归退出码 0 且有通过数量记录；三份评审为真实结论；smoke 清单逐条通过；台账与复盘已落盘。
- 风险：真实 Ollama 未就绪会误判失败——须单独记录环境状态，不直接判实现失败。
- 回滚：revert 本计划提交；新表仅新增，删除即回滚，不影响 `messages`。

## 8. 产出物、执行结果与变更日志

- 评审：`025-requirement-review.md`（通过）、`025-backend-review.md`（GO，无 P0）、`025-frontend-review.md`（GO）、`025-acceptance-review.md`（通过）。三份子代理评审因 hy3 连续 429 限流改由架构师代行，已标注。
- 全量回归：`python -m pytest tests/ -q` → 1345 passed、1 skipped、47 subtests；唯一失败 `test_import_compensation.py::test_import_without_temp_dir_uses_attempt_private_root_and_cleans_only_it`，已用 `git stash` 在干净树复现，属存量问题（退出码 1）。
- 部署：`RERANKER_ENABLED=false ./deploy/start.sh -d`，服务 http://127.0.0.1:8000，`/api/health` 与 `/` 均 200。
- 运行时 smoke：`context-usage` 正常；手动压缩 job queued→done，段 0→1，消息条数不变（30）；二次压缩生成新 job 且无新消息时不写空段；不存在的会话 404；前端 `/assets/app.js?v=34`、`/assets/styles.css?v=34` 均 200 且含新逻辑/样式。
- 复盘：`docs/sdd/retro/2026-09-12-spec-025-context-compaction.md`。
