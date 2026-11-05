# 三个在途 worktree 研究与收尾记录（2026-11-05）

> 主会话纯文档落盘。本次是**工作区运维与状态判定**，不涉及业务代码改动，
> 也不改变任何 spec 状态；Spec044 的结论仅供后续范围决策，不启动实施。

## 1. 背景

用户指出三个 worktree 有大量未提交文件（`architecture-boundary-guards` 188 个、
`memory-management-recovery` 17 个、`paper-login-recovery` 10 个），要求研究用途、
判断能否收尾，并「先挑好收尾的收」。

基准：`main` @ `320320a9`（已与 `origin/main` 同步，分叉 `0 / 0`）。

## 2. 逐个判定

### 2.1 `memory-management-recovery` — **冗余过时快照，已收尾**

| 项 | 值 |
|---|---|
| 分支 / HEAD | `codex/fix-file-memory-management` @ `70b1af1f`（2026-10-26 `docs(recovery): record memory and login repair plans`） |
| 相对 main | 落后 65、**0 个独有提交** |
| 改动构成 | 10 M + 7 ?? |
| 主题 | Spec038 记忆层改造：管理页面复接补充 |

判定依据（逐文件 `cmp -s` 与内容比对）：

- 5 个后端代码（`routes_conversations.py`、`schemas.py`、`conversation_service.py`、
  `markdown_store.py`、`repository.py`）与 2 个测试
  （`test_memory_analysis_repair.py`、`test_memory_block_fixes.py`）**与 main 逐字节相同**。
- 7 个 untracked 文档（4 份 `docs/sdd/plans/038/2026-10-26-management-*.md`、
  `038-requirement-review.md`、`038-tech-review.md`、`test_memory_document_store.py`）
  **全部已存在于 main**。
- 3 个差异文档是 **10-26 的中间态**：worktree 里 spec038 写「管理复接补充已确认…
  待实施」、plan 写「待分端实施」；而 main 里 spec038 已是
  「`P1/P2/P3 历史阶段已实现；2026-10-26 管理复接补充已完成（含 hidden 可见性复验，
  验收/架构师 GO）`」，plan 结论为「管理复接补充已完成」，backend/frontend 的
  review/test 均为 GO / PASS / READY_FOR_USER。
- 台账：worktree 仅 2 条 `2026-10-26` 记录，main 有 14 条（含后续完成记录）。

→ 全部实质成果已在 main，无独有内容，**收尾方式 = 备份后丢弃未提交改动**。

### 2.2 `paper-login-recovery` — **冗余过时快照，已收尾**

| 项 | 值 |
|---|---|
| 分支 / HEAD | `codex/fix-paper-login-recovery` @ `1a963015`（2026-10-26 `fix(maps): explain unavailable analysis actions`） |
| 相对 main | 落后 66、**0 个独有提交** |
| 改动构成 | 6 M + 4 ?? |
| 主题 | Spec032 数据源扩展：已有批次登录恢复窄修 |

判定依据：

- 2 个后端（`routes_paper.py`、`paper_import_batch_service.py`）与 2 个测试
  （`test_paper_browser.py`、`test_paper_import_batch_service.py`）**与 main 逐字节相同**。
- 4 个 untracked 文档（`docs/sdd/plans/032/2026-10-26-login-recovery-{plan,implementation,review,test}.md`）
  **全部已存在于 main**，且 main 版本结论已是
  「本次登录/继续窄修已完成（tester READY_FOR_USER、architect GO）」「Task11 窄修评审已完成并 GO」。
- 2 个差异文档是中间态：worktree 的 spec032 写「已有批次登录恢复窄修（已确认，实施中）」，
  main 的 spec032 仍为「暂停，待下次继续」（窄修作为独立闭环已完成，不撤销整体暂停结论）；
  台账 main 有对应完成记录。

→ 同样无任何独有内容，**收尾方式 = 备份后丢弃未提交改动**。

### 2.3 `architecture-boundary-guards` — **真实在途重构，本次不收**

| 项 | 值 |
|---|---|
| 分支 / HEAD | `chore/spec-017-architecture-boundary-guards` @ `48634e12` |
| 相对 main | **落后 30、领先 4** |
| 独有提交 | `f9f9eea7` 补齐七领域依赖门禁 / `703ec5fc` 记录 Spec030 快照兼容检查 / `71c96b55` 确认 Spec044 整批架构优化实施范围 / `48634e12` merge |
| 改动构成 | **117 M + 71 ??**；tracked diff `7503 insertions / 8830 deletions` |
| 主题 | **Spec017 后端限界上下文模块化 + Spec044 架构优化程序** |

改动分布（按目录）：`backend/app` 44 M + 20 untracked、`tests/research` 23 M + 6 untracked、
`tests/literature_maps` 10 M、`tests/frontend` 9 M、`frontend` 拆分出
`request-lifecycle.js` / `paper-search-api.js` / `literature-maps-state.js` /
`literature-maps-job-poller.js`、新增 `scripts/install_locked.sh`、
`requirements-dev.lock.txt`、`.github` 配置等。

**关键事实**：`docs/sdd/specs/044-architecture-optimization-program.md` 在 **main 里不存在**，
worktree 版本状态为「**实施中**（2026-10-30，需求／技术独立 GO，用户『继续工作』确认统一范围）」。
这不是冗余快照，而是一整套尚未进入主干的大规模重构。

**为什么本次不收**：
- 丢弃会损失 4 个独有提交与 188 个文件的真实在途工作；
- 直接合并风险高：分支落后 main 30 个提交（含本轮 FD 泄漏修复、`app.js?v=68`、
  Spec043 四轮修复等），且 `7503/8830` 的行级变化可能与 main 大量冲突；
- 按 SDD，Spec044 是否继续实施、是否收口属于**范围决策**，需用户确认，不能由主会话代决。

**建议后续二选一**（需用户明确指示）：
- **继续 Spec044**：先把 main 合入该分支并解决约 30 个提交的差距，跑七领域依赖门禁与
  锁定依赖安装，再由架构师评审后走 PR；
- **放弃**：明确授权后备份并清理 188 个改动、删除分支与 worktree。

## 3. 已执行的收尾动作

备份（先备份、后清理，可完整恢复）：

```
/tmp/worktree-cleanup-20261105/
├── memory-management-recovery/tracked.patch          (1143 行)
│   └── untracked/                                    (7 个文件，保留原相对路径)
└── paper-login-recovery/tracked.patch                (372 行)
    └── untracked/                                    (4 个文件，保留原相对路径)
```

清理命令（每个 worktree 内）：`git checkout -- .` + `git clean -fd`（不带 `-x`，
`.gitignore` 忽略的 `.venv` 等未受影响）。

清理后验证：

| worktree | `git status --short` | 分支 / HEAD |
|---|---|---|
| `memory-management-recovery` | 空 | `codex/fix-file-memory-management` @ `70b1af1f` |
| `paper-login-recovery` | 空 | `codex/fix-paper-login-recovery` @ `1a963015` |
| `map-usability`（上轮已清理） | 空 | `codex/spec030-report-quality` @ `6307d0db` |
| `architecture-boundary-guards` | **保留 188 个改动** | `chore/spec-017-…` @ `48634e12` |
| 主工作区 | 仅 2 个历史未跟踪文件 | `main` @ `320320a9` |

**未改动**：分支指针、worktree 目录、任何业务代码、`origin/main`。
两个被清理的分支仍是 main 历史里的旧节点，若确认无用可另行删除（需用户授权）。

## 4. 运行时验证

- `/api/health` 200；服务未重启（本次只动 worktree 工作区，主工作区文件零变化）。
- `main` 与 `origin/main` 状态见本报告提交后的同步记录。

## 5. 结论

- 好收尾的 2 个（`memory-management-recovery`、`paper-login-recovery`）**已收尾**：
  它们的工作早在 2026-10-26 就进入 main 并完成验收，worktree 只是残留的中间态快照。
- `architecture-boundary-guards` **不是残留，而是 Spec044 在途重构**，本次刻意不动；
  继续或放弃需要你给方向。
