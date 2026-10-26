# Spec 038 管理复接 B01–B03 后端复审

> 当前收口状态：B01–B03 后端窄范围已完成；初审 BLOCK、修复复审 GO 与环境边界均保留。

## 范围与依据

- 复审对象：`backend/app/memory/markdown_store.py`、`backend/app/memory/repository.py`、`backend/app/chat/application/conversation_service.py`、`backend/app/api/schemas.py`、`backend/app/api/routes_conversations.py`。
- 依据：`docs/sdd/plans/038/2026-10-26-management-contract.md` §1–§3、`2026-10-26-management-backend.md`，以及 backend-patterns / regression-guard / test-naming 约束。
- 未修改业务代码或测试；未访问真实 `data/memory/`，复现均使用临时目录。

## 定向验证

命令（使用主目录解释器；测试数据由 pytest `tmp_path` 隔离）：

```text
PYTHONPATH=/Users/wjh/.codex/worktrees/memory-management-recovery/ResearchAgent \
PYTHON_DOTENV_DISABLED=1 LANGFUSE_ENABLED=false \
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q \
  tests/memory/test_memory_document_store.py \
  tests/memory/test_memory_markdown_store.py \
  tests/memory/test_memory_block_fixes.py \
  tests/memory/test_memory_analysis_repair.py \
  tests/conversation/test_conversations_api.py
```

- 退出码：0
- 结果：83 passed；仅 pytest cache 因 managed worktree 只读产生 warning。
- 覆盖：固定文档缺失/原文 Unicode/OCC/65,536 上限/symlink 项目路径、pending 稳定 ID/幂等/append 失败保留、旧 audit-only `PENDING_UNLINKED`、save/ignore 决策与受影响聊天 API。

## 发现

### [P1] 待确认保存把损坏/解码失败的目标文件当成空文件覆盖并消费 PENDING

- 文件：`backend/app/memory/markdown_store.py:422–429`、`588–644`；路由调用点 `backend/app/api/routes_conversations.py:2394–2405`。
- 事实：`resolve_pending(save)` 调用 `append_memory()`，其 `_append_entry()` 通过旧的 `_read_text()` 读取目标；`_read_text()` 会把 `UnicodeDecodeError`、`OSError`、权限/目录错误统一降级为 `""`。随后 `_atomic_write()` 写入新条目并删除 PENDING，路由再把审计标为 `auto_saved`。
- 复现（临时目录）：先写入 `MEMORY.md` 原始字节 `b"\\xff"`，再调用 `add_pending(..., item_id="item-1")` 和 `resolve_pending("item-1", scope="global", project_id=None)`。调用无异常，PENDING 消失，原始不可解码内容被替换为 `- 保留我\n`。
- 违反：合同 §2.2/§2.3 及 §3.3 要求真实读取/解码/写入失败返回 503、不得伪装为空；append 失败必须保留 PENDING，不能报告 `auto_saved`。这是可见数据丢失与错误成功状态。
- 建议：为管理/待确认写入路径增加严格读（仅 `FileNotFoundError` 视为空；解码、权限、目录和其他 I/O 均抛 `MemoryDocumentUnavailableError`），让 `resolve_pending` 在 append 失败时不删除 PENDING；补充损坏 UTF-8、读取 OSError、目标目录故障注入测试。

### [P1] global 固定文件未做 realpath/symlink 边界校验，可把 `/api/memory-documents` 写到 MEMORY_DIR 外

- 文件：`backend/app/memory/markdown_store.py:254–268`、`308–343`。
- 事实：`document_path(scope="project")` 经过 `_project_path()` 的 realpath 检查；但 global 直接返回 `self.memory_path`。若 `MEMORY.md` 是指向 memory 根目录外的符号链接，`read_document` 会读取目标，`write_document` 会在 OCC 成功后经 `os.replace()` 替换该外部目标。
- 复现（临时目录）：创建 `memory/MEMORY.md -> outside.md`，GET 返回 `outside.md` 内容；用对应 SHA-256 PUT 后，外部 `outside.md` 被改写，返回 200。
- 违反：固定文件映射/不增加任意路径读写及“符号链接越界不得写入”的边界；虽然客户端不能直接传 path，但 API 仍能越过受控 memory 根写入。
- 建议：对 global 固定文件也执行 canonical parent/target 校验；目标存在且为 symlink 或解析后不在 memory root 时返回稳定 `MEMORY_DOCUMENT_PATH_INVALID` 400，并在校验失败前不创建/替换文件。补充 global symlink read/write API 测试。

### [P2] 非法 JSON 在 FastAPI body 解析阶段仍返回默认 422，未遵守 body 错误统一 400

- 文件：`backend/app/api/routes_conversations.py:687–703`、`backend/app/api/schemas.py:83–95`。
- 事实：对象、类型错误和 extra fields 会进入 `MemoryDocumentPutRequest.model_validate()` 并映射为 400；但 `Content-Type: application/json` 且 body 为非法 JSON 时，FastAPI 在进入路由前返回 `422 {detail: [...]}`，不会走该 `try/except`。
- 复现：对 `PUT /api/memory-documents?scope=global` 发送 `data="not-json"`，响应为 422，而合同 §2.3/代码 docstring 要求 `INVALID_MEMORY_DOCUMENT_REQUEST` 400。
- 建议：在该 API 的请求解析边界统一捕获 JSON decode/RequestValidationError，映射为 `{detail:{code:"INVALID_MEMORY_DOCUMENT_REQUEST", message, retryable:false}}` 400；补充非法 JSON 回归。

## 已核对的合同项

- SHA-256(UTF-8 bytes) 小写 revision、同路径 canonical RLock、原子临时文件 + fsync + replace：通过现有实现与测试核对。
- project_id 白名单/长度/realpath、owner + active project 查询、unknown/foreign/deleted 与 archived 的错误区分：通过现有实现与受影响 smoke 记录核对。
- 65,536 Unicode code points、原文保存、空文件 GET 不创建、坏 revision/extra body 字段稳定 400：通过现有定向测试/实现核对。
- worker 先 reserve audit item_id，再写 PENDING/正式 MD；PENDING 写失败为 `failed`；旧 audit-only 项返回 `PENDING_UNLINKED`，不按 statement 猜测：通过代码与现有测试核对。
- 同 ID pending 幂等、冲突拒绝、stale OCC 409、ignore 不写正式文件：通过现有定向测试核对。

## 结论

**Verdict: BLOCK — 2 个 P1 数据安全/一致性问题必须修复并复审；另有 1 个 P2 错误契约问题。**

修复后需重新运行上述定向集合，并新增/运行：损坏 UTF-8 或目标读取异常下 `resolve_pending` 返回 503 且 PENDING 与原文件保留；global `MEMORY.md` symlink 越界读写被拒绝；非法 JSON 返回稳定 400。当前不具备 backend review GO 条件。

## 最终复审（修复候选）

本节 supersede 上述初审 BLOCK 结论，针对三项发现逐项复核：

1. **损坏目标文件**：`resolve_pending(save)` 现在以 `strict_read=True` 调用 append；解码/I/O 异常传播为 `MemoryDocumentUnavailableError`，PENDING 不删除，正式文件字节不变。新增 store/API 回归覆盖项目文件与全局文件路径。
2. **global symlink**：`document_path(scope="global")` 现在拒绝 `MEMORY.md` symlink，并校验 realpath 位于 memory root；GET/PUT 与 pending save 均不会触碰越界目标，稳定返回 `MEMORY_DOCUMENT_PATH_INVALID`。
3. **非法 JSON**：PUT 改为手动 `Request.json()` 解析；JSON decode/Unicode 错误统一返回 400 `INVALID_MEMORY_DOCUMENT_REQUEST`，对象 schema 错误仍保持同一稳定错误码。

### 最终复核证据

- 精确后端集合：退出码 `0`，**104 passed, 0 failed**；仅 managed worktree `.pytest_cache` 写权限 warning。
- 独立临时目录边界 smoke：退出码 `0`；损坏目标保留原字节与 PENDING、global symlink GET/PUT 均 400 且外部文件不变、非法 JSON 为 400 `INVALID_MEMORY_DOCUMENT_REQUEST`。
- 验收报告 `docs/sdd/plans/038/2026-10-26-management-backend-test.md`：103 passed、三项 smoke、Ruff（受影响文件）与 test naming 均通过；宽 `repository.py` Ruff 仅报告既有债务。
- 未修改业务代码/测试，未访问真实记忆目录，未部署或联网。

## 最终结论

**Verdict: GO（backend B01–B03）。** 初审两项 P1 与一项 P2 已逐项修复并有回归/故障注入证据；本轮未发现新的 P0/P1 或超出 Spec038 合同的后端阻断项。可进入前端分派与后续跨端验收。
