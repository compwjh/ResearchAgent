# Spec032 Task11 登录恢复后端测试报告（backend-tester）

> 当前收口状态：Task11 窄修精确测试与主目录集成已完成；认证后下载/入库未验证，Spec032 整体仍暂停。

> 范围：`codex/fix-paper-login-recovery` 隔离 worktree `/Users/wjh/.codex/worktrees/paper-login-recovery/ResearchAgent` 的登录/恢复窄修复。
>
> 结论：**Task11 后端候选精确范围 PASS，窄修已完成**。可写临时导出和主目录集成中的候选三文件集合均为 `64 passed`、`0 failed`、`0 skipped`；managed worktree 的单个既有 storage-lock 节点仍受默认 `data/articles` 不可写环境阻塞，单独记录为环境证据，不把它混入候选通过数。Spec032 全量及认证后下载/入库不在本窄修范围，整体仍暂停。

## 1. 测试边界与基线指纹

- 角色：`backend-tester`；只验证 `backend/**` 与 `tests/paper_discovery/**` 的后端切片。
- 精确测试文件：
  - `tests/paper_discovery/test_paper_import_batch_service.py`
  - `tests/paper_discovery/test_paper_browser.py`
  - `tests/paper_discovery/test_paper_import_batch_api.py`
- 候选生产文件：
  - `backend/app/paper_discovery/application/paper_import_batch_service.py`
  - `backend/app/api/routes_paper.py`
- 候选测试文件 diff：上述 service/browser 两个文件；API 文件保留既有 storage-lock 节点作为受影响集合的一部分。
- 分支：`codex/fix-paper-login-recovery`
- HEAD：`1a96301558864e12bf1f4080aa736474c180d792`
- 当前四文件 patch SHA-256：`2ea2d246c00688a795a000a8d1341aa73d654169018a3c9b765ae54bcfd7d19a`
- 候选四文件 SHA-256（临时导出与源 worktree 一致）：

```text
1525df74f0da9de1f9cb71e5304cad3414a4b52701da0b0e20c837ca99f4333f  backend/app/api/routes_paper.py
041a686d4b7d64cb0734b1d3c7e8b4743eb01d97ea61907c4f646cd42294bfb5  backend/app/paper_discovery/application/paper_import_batch_service.py
276bf3d99d53bf295c8bbb020f90bf22e75f1bfb013dca9238217ff570542d02  tests/paper_discovery/test_paper_browser.py
c9bfa8c7ca75fc42fcd372a0942b80f1ed8b7db5fa0507405de5d3d7c7f2bfbb  tests/paper_discovery/test_paper_import_batch_service.py
```

运行解释器固定为 `/Users/wjh/ResearchAgent/.venv/bin/python`，环境固定包含 `PYTHON_DOTENV_DISABLED=1`、`LANGFUSE_ENABLED=false`、`PYTHONDONTWRITEBYTECODE=1`。候选通过证据来自 `git archive HEAD` 加当前四个 tracked 文件 diff 的可写临时导出 `/private/tmp/spec032-login-recovery-candidate.NB3c1y`；其 KB、文章下载、browser profile、paper-search DB 和 pytest 临时目录均在该临时导出内。pristine 对照导出为 `/private/tmp/spec032-login-recovery-pristine.syr9h7`。

## 2. 精确测试结果

### 候选三文件集合（当前最终 diff）

命令（在候选临时导出中）：

```text
PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
KB_DIR=/private/tmp/spec032-login-recovery-candidate.NB3c1y/data/kb \
QDRANT_PATH=/private/tmp/spec032-login-recovery-candidate.NB3c1y/data/kb/qdrant \
ARTICLE_DOWNLOAD_DIR=/private/tmp/spec032-login-recovery-candidate.NB3c1y/data/articles \
PAPER_DISCOVERY_BROWSER_PROFILE_DIR=/private/tmp/spec032-login-recovery-candidate.NB3c1y/data/browser-profile/security-papers \
PAPER_DISCOVERY_DB_PATH=/private/tmp/spec032-login-recovery-candidate.NB3c1y/data/paper_search/state.sqlite3 \
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider \
  --basetemp=/private/tmp/spec032-login-recovery-candidate.NB3c1y/.pytest-tmp \
  tests/paper_discovery/test_paper_import_batch_service.py \
  tests/paper_discovery/test_paper_browser.py \
  tests/paper_discovery/test_paper_import_batch_api.py
```

结果：

```text
64 passed in 2.48s
exit 0; failed 0; skipped 0
```

此集合实际覆盖了 durable-first 快照在 search TTL 过期后的 item/service 解析、重启恢复、缺失快照的 legacy live-search fallback、candidate/search 身份篡改、部分元数据和损坏 SQLite 快照的 fail-closed；login/resume 使用服务端持久快照、受控 ACM/IEEE allowlist、session 过期和精确 session 清理；API 批次创建/状态/resume/retry/duplicate/storage-lock 既有契约及受影响生命周期。没有 real browser、外部网络、模型调用或产品 HTTP POST。

### pristine HEAD 对照

同一解释器、同一三文件集合和同类临时隔离，仅不应用当前四文件 diff：

```text
55 passed in 2.48s
exit 0; failed 0; skipped 0
```

该数值仅作为当前候选与 pristine HEAD 的受影响集合对照，不是全仓测试总数，也不替代候选 `64/64` 结果。

## 3. managed worktree 环境阻塞证据

在原 managed worktree 运行同一解释器、关闭 dotenv/Langfuse、使用 pytest 临时目录，仅执行该既有节点：

```text
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q -p no:cacheprovider \
  --basetemp=/private/tmp/spec032-managed-pytest.x2pjVT \
  tests/paper_discovery/test_paper_import_batch_api.py::test_storage_locked_import_sets_item_error_code_via_api
```

结果：`1 failed in 1.33s`，退出码 1；实际断言值为 `KB_IMPORT_FAILED`，期望 `KB_STORAGE_LOCKED`。这是 managed worktree 的环境路径问题，不是本轮新增 durable snapshot/login 测试失败：

- `ArticleSettings()` 的类默认 `article_download_dir` 指向 `/Users/wjh/.codex/worktrees/paper-login-recovery/ResearchAgent/data/articles`。
- 无写入探针诊断显示该目录和父目录均不存在，父目录 `os.access(..., os.W_OK)` 为 `False`。
- `PaperImportBatchService` 的该测试没有注入 settings，`import_candidate` 因而在到达被 monkeypatch 的 `paper_import_port` 前，先尝试在 worktree 默认文章目录创建临时导入根（`paper_import.py` 约 505 行），环境异常被稳定映射为 `KB_IMPORT_FAILED`。
- 即使把 `KB_DIR`、`ARTICLE_DOWNLOAD_DIR`、profile 和 DB 环境变量指向 `/private/tmp`，该节点仍保持相同结果，因为此调用路径使用 `ArticleSettings()` 类默认值；可写临时导出把 `BASE_DIR` 本身移到可写临时目录后，候选三文件集合全部通过。

因此不得把 managed 的 `1 failed` 写成候选代码回归，也不得把它改写为 `64 passed`；最终候选证据明确来自可写临时导出，managed 原路径失败作为需要根会话保留的环境备注。

## 4. 静态、收集和安全门禁

| 检查 | 结果 |
|---|---:|
| `pytest --collect-only -q`（同三文件） | `64 tests collected`，退出码 0，无 collection error |
| `ruff check --no-cache`（2 后端生产 + 2 后端测试文件） | `All checks passed!`，退出码 0 |
| `python -m py_compile`（2 后端生产文件） | 退出码 0 |
| `scripts/check_test_layout.py` | `test layout: ok`，退出码 0 |
| `scripts/check_test_naming.py` | `test naming check passed: no spec/task numbers under tests`，退出码 0 |
| `git diff --check`（4 个候选 tracked 文件） | 退出码 0 |
| scoped secret/console scan | 无硬编码 `sk-<token>` 或 `console.log` 命中；退出码 1 表示 grep 无结果 |

## 5. Verification report

```text
Build:    PASS（本后端切片无独立构建产物；py_compile 通过）
Types:    N/A（本 Task 未配置独立类型检查；未扩大范围运行全仓工具）
Lint:     PASS（Ruff 4 个受影响文件）
Tests:    PASS（候选 exact 64/64，0 failed，0 skipped；pristine 对照 55/55）
Security: PASS（受影响文件 scoped secret/console scan 无命中；持久快照/allowlist 边界由测试覆盖）
Diff:     PASS（四文件 diff-check 通过；仅候选四文件为本 Task 代码范围）

Overall:  READY for scoped Task11 backend review/acceptance
```

限制与后续：

1. 本报告不代表 Spec032 全量回归、部署验证或最终验收评审通过。
2. 未发送生产 HTTP POST，未打开 headed browser，未触碰生产 SQLite/KB/profile，未调用网络或模型。
3. 根会话仍需按 Spec032 门禁执行授权的真实单论文 login/resume/API E2E，并保存请求、响应、实体 ID、最终状态和产物路径；该动作不由本 backend-tester 代行。
4. managed `data/articles` 权限问题应作为环境前置条件处理；在可写工作树或等价临时导出中复跑候选结果即可，不应修改本 Task 测试断言来掩盖它。

## 6. 交接日志

- 进展日志：`.codebuddy/agent-logs/spec-032/task-11/backend-tester/20261026-020001.md`
- 当前报告：`docs/sdd/plans/032/2026-10-26-login-recovery-test.md`

## 7. 集成主目录复核（2026-10-26，backend-tester）

根会话已将登录/恢复窄修复整合到主目录 `/Users/wjh/ResearchAgent`。本节只核对四个候选文件的集成版本，不把同一工作树中的其他 Spec018/KB/frontend 改动纳入结论。

运行环境：`/Users/wjh/ResearchAgent/.venv/bin/python`；`PYTHON_DOTENV_DISABLED=1`、`LANGFUSE_ENABLED=false`、`PYTHONDONTWRITEBYTECODE=1`；KB、Qdrant、browser profile、paper-search DB 和 pytest 临时目录均指向 `/private/tmp/spec032-login-recovery-integrated.ojrRFP` 下的隔离路径。未发送产品 HTTP POST、未打开 headed browser、未部署、未触碰生产 SQLite/KB/profile。

| 检查 | 命令/范围 | 结果 |
|---|---|---|
| 精确 pytest | `python -m pytest -q -p no:cacheprovider --basetemp=/private/tmp/spec032-login-recovery-integrated.ojrRFP/pytest-tmp tests/paper_discovery/test_paper_import_batch_service.py tests/paper_discovery/test_paper_browser.py tests/paper_discovery/test_paper_import_batch_api.py` | 退出码 `0`；`64 passed`、`0 failed`、`0 skipped`（2.29s） |
| Ruff | `ruff check --no-cache`：`backend/app/api/routes_paper.py`、`backend/app/paper_discovery/application/paper_import_batch_service.py`、`tests/paper_discovery/test_paper_browser.py`、`tests/paper_discovery/test_paper_import_batch_service.py` | 退出码 `0`；`All checks passed!` |
| Diff check | `git diff --check`（上述四个候选文件） | 退出码 `0` |

**集成版本结论：PASS。** 主目录整合后的登录/恢复三文件精确集合仍为 `64/64` 通过，四个受影响文件 Ruff 与 diff-check 均通过；未发现整合回归。该结论仅覆盖 Task11 后端窄范围；随后主目录真实 login `200/opened/acm` 与验收报告架构师 GO 已完成本窄修收口，不代表 Spec032 全量回归、认证后 resume、下载/入库、部署或整体 Spec 完成。

## 8. 窄修收口（2026-10-26）

验收范围为过期 search TTL 下既有 item 的 durable snapshot 优先 login/resume 路由。定向 `64/64`、真实 login API `200/opened/acm`、独立 review GO 与验收报告 `READY_FOR_USER` 均已落盘；认证后 publisher resume、PDF 下载/校验与 KB 入库未验证，仍按 Spec032 整体暂停边界保留。
