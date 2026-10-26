# Spec032 登录恢复修复后端评审

> 当前收口状态：Task11 窄修评审已完成并 GO；managed worktree 环境阻塞与历史 BLOCK 保留，Spec032 整体仍暂停。

> 角色：backend-reviewer；范围：Task11 登录/恢复窄修复的两个后端文件及其两个后端测试文件。
> 评审基线：`codex/fix-paper-login-recovery` 工作树当前实际 diff；未修改业务代码、测试代码或生产数据库。
> 首轮结论：BLOCK（已修复并复审）；本次窄修当前结论：**GO（范围完成；managed worktree 环境性测试阻塞已隔离）**。Spec032 整体仍暂停。

## 范围与核对结论

已审查：

- `backend/app/paper_discovery/application/paper_import_batch_service.py`
- `backend/app/api/routes_paper.py`
- `tests/paper_discovery/test_paper_import_batch_service.py`
- `tests/paper_discovery/test_paper_browser.py`

实现的 durable-first 顺序、目标 item/batch/candidate/search 身份检查、整批快照检查，以及缺失快照时保留 live-search fallback 的边界与计划一致。`_paper_item_browser_target` 仍负责受控 ACM/IEEE origin 校验；本轮未发现客户端 URL 进入恢复链、私有方法被路由直接暴露、SSRF/allowlist、CAS 或浏览器 session TTL 被放宽。

## 首轮发现与复审

### [HIGH] 持久快照完整性错误未转换为服务错误，API 丢失 `SNAPSHOT_REBUILD_REQUIRED`（已修复）

- **首轮位置**：`backend/app/paper_discovery/application/paper_import_batch_service.py:523-524`；路由兜底见 `backend/app/api/routes_paper.py:1149-1155` 和 `1191-1200`。
- **首轮证据**：`PaperImportBatchStore.get_snapshot()` 在 hash 不匹配、JSON 无法解析或快照字段不完整时抛出 `PaperImportBatchStoreError(SNAPSHOT_REBUILD_REQUIRED, ...)`（`paper_import_batch_store.py:568-576`），而 wrapper 未转换，真实 login 曾返回 `BROWSER_UNAVAILABLE`，resume 曾返回 `IMPORT_BATCH_ERROR`。
- **修复核对**：当前实现 `paper_import_batch_service.py:524-532` 已将 `SNAPSHOT_REBUILD_REQUIRED` 转换为 `PaperImportBatchServiceError`；新增 `test_login_and_resume_sqlite_corrupt_snapshot_map_to_rebuild_required` 用真实 SQLite 快照损坏覆盖 login/resume，断言均为 503 `SNAPSHOT_REBUILD_REQUIRED` 且 browser 未调用。
- **复审结论**：通过，首轮 HIGH 已关闭；未再发现 P0/P1 或安全边界退化。

## 验证证据

### 当前候选定向回归与基线核对

命令：

```text
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/paper_discovery/test_paper_import_batch_service.py \
  tests/paper_discovery/test_paper_browser.py \
  tests/paper_discovery/test_paper_import_batch_api.py
```

从原始 managed worktree 运行三文件命令曾退出码 `1`，显示 `62 passed, 1 failed`；唯一失败是 `test_storage_locked_import_sets_item_error_code_via_api`。该工作树受权限限制，生产默认 `BASE_DIR/data/articles` 不可创建，底层真实异常为 `paper_import.py:506` 的 `PermissionError`，随后被导入器按环境故障归类为 `KB_IMPORT_FAILED`。这不是本轮快照代码路径，也不能直接把该结果标为“基线失败”。

为得到可比证据，使用同一 `/Users/wjh/ResearchAgent/.venv/bin/python`：

1. **pristine HEAD，干净可写 `git archive` 临时副本，精确 failing node**：`1 passed`，退出码 `0`。
2. **当前候选代码，`git archive HEAD` 临时副本再应用当前 tracked diff，精确相同 failing node**：`1 passed`，退出码 `0`。
3. **当前候选代码，同一可写临时副本的三个完整测试文件**：`64 passed`，退出码 `0`。
4. **pristine HEAD，同一三个测试文件**：`55 passed`，退出码 `0`。

因此当前 managed worktree 的单测失败已被精确定位为工作树写权限/默认下载目录环境阻塞；在可写、代码内容等同的当前候选副本中，存量失败与新增测试均通过。根会话如需保留原工作树命令的退出码，应记录环境阻塞，不伪造成产品回归。

### 静态与命名门禁

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/ruff check --no-cache`（2 后端文件 + 2 测试文件） | 0 | `All checks passed!` |
| `.venv/bin/python -m py_compile`（2 后端文件） | 0 | 通过 |
| `.venv/bin/python scripts/check_test_naming.py` | 0 | `test naming check passed` |
| `.venv/bin/python -m pytest --collect-only -q`（3 个相关测试文件） | 0 | `64 tests collected`，无 collection error |
| `git diff --check` | 0 | 通过 |

新增测试及既有相关测试在当前候选中均可收集；SQLite 损坏快照 login/resume 回归在原工作树为 `2 passed`。

## Verdict

**GO（代码评审通过，环境备注）**：durable-first、整批/目标身份门禁、legacy fallback、allowlist/SSRF、CAS 与 session TTL 边界均符合范围；首轮快照错误转换缺陷已修复并由真实 SQLite login/resume 回归覆盖。当前 managed worktree 的 `KB_STORAGE_LOCKED` 精确节点失败是默认 `data/articles` 不可写导致的环境阻塞；同一解释器下 pristine HEAD 与当前候选的可写临时副本均通过。该窄修已由验收报告追加栏签收，认证后 resume/download/import 仍不在本次范围。

## 2026-10-26 窄修收口

主目录集成定向回归为 `64 passed, 0 failed, 0 skipped`，真实 login 为 `200/opened/acm`；本报告评审范围完成。原始 BLOCK 与环境阻塞证据保留，Spec032 整体仍保持暂停。
