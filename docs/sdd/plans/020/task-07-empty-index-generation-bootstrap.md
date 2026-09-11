> 关联：[spec-020](../../specs/020-misc-bug-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`
>
> **⚠️ 主模型代行（原因）**：本会话 `Task` 工具无法解析项目自定义子代理 `backend-dev`
> （`.codebuddy/agents/backend-dev.md` 存在但调用报 `Subagent "backend-dev" not found`，加 `subagent_path` 重试仍失败，
> 该工具仅暴露内置只读的 `code-explorer`）。用户于 2026-09-11 明确**豁免代行**，由主会话（架构师）实现。
> 按门禁硬规则 #3 完成三处留痕：① 本文件头部标注；② spec-020 评审记录标注 `（代行，非独立评审）`；③ spec-020 变更日志登记。

# Task07 空库首次部署代际自动初始化（BUG-05）

## 1. 状态与一句话目标

目标：让**空库/首次部署**自动完成索引代际初始化，使上传不再被 `INDEX_REBUILD_REQUIRED` 拦截；
同时保证**非空库**在 marker 缺失时仍然 fail-closed 返回 409。

只改 `backend/**`。

## 2. 背景与前置条件

- spec-020 第 3 批 BUG-05（已由用户确认「按这个执行，不需要全量回归」）。
- 现象：全新机器首次部署后上传即报
  `上传失败：索引尚未完成全库重建，请先执行 python -m backend.app.knowledge_base.rebuild_index --confirm-replace（INDEX_REBUILD_REQUIRED）`。
- 实测：`data/kb` 目录**完全不存在**（无 `papers.json`、无 `index-generation.json`、无 `rebuild-runs`）。

## 3. 根因（已定位，勿重复排查）

- `backend/app/knowledge_base/infrastructure/manifest_store.py:599-614`
  `FinalizeBundleStore.require_generation()`：
  ```python
  marker_path = self.live_root / "index-generation.json"
  if not marker_path.exists():
      code = "INDEX_FINALIZE_REQUIRED" if finalize_pending else "INDEX_REBUILD_REQUIRED"
      raise ManifestStoreError(code, status=503 if finalize_pending else 409)
  ```
  只判 marker 是否存在，把两种状态混为一谈：
  - (a) **空库/首次部署**：从未有过索引 → 无东西可重建 → 应自动 bootstrap
  - (b) **已有旧索引但代际不符** → 才需停服全库重建 → 才该报 409
- 调用方：`backend/app/api/routes_kb.py:310-324` `_require_generation()`，上传等接口统一过这道门。
- 启动侧：`backend/app/main.py:34-40` 仅 `print("[kb] index generation gate not ready: ...")`，不做初始化。
- 佐证：同一函数内 `papers.json` 缺失走的是 503 `INDEX_FINALIZE_REQUIRED`（606-613 行），
  说明"文件缺失"本就被区别对待，唯独 marker 缺失被一律当成"需全库重建"。

## 4. 数据、配置与接口

- 目标 marker 路径：`data/kb/index-generation.json`，schema `index-generation-v1`。
- 字段（参照同文件 `commit()` 约 581-594 行的构造方式）：
  `schema_version` / `run_id` / `alias_name` / `alias_target` / `bundle_sha256` /
  `collection_fingerprint` / `metadata_sha256` / `manifests_digest` / `committed_at`。
- 空库 bootstrap 时 `alias_target` 复用既有 `papers` collection。
- 必须通过 `_validate("index-generation.schema.json", ...)`。

## 5. 实施步骤与文件边界

### 步骤 1 — `manifest_store.py`：`require_generation()` 增加空库 bootstrap

在读取 marker 之前插入判定：当 `papers.json` **不存在或为空数组** 且 marker **不存在**时，
调用一个新的内部方法（如 `_bootstrap_empty_generation()`）创建初始 marker 后继续正常流程，不再抛错。

**关键约束（不做则 bootstrap 完立刻仍 503）**：
- `metadata_sha256` 必须等于 `data/kb/papers.json` **实际字节**的 sha256 →
  若 `papers.json` 不存在，需先创建为空数组 `[]`（若项目别处已有创建逻辑则复用，勿造第二套）。
- `manifests_digest` 必须等于 `_live_manifests_digest()` 的返回值。
- 写入沿用文件内既有的 `_atomic_bytes`，保证原子；函数需**幂等**（重复调用不报错、不改写已存在 marker）。

### 步骤 2 — `main.py`：启动自检

把 `main.py:34-40` 那段"只 print"的 gate 改为：空库时触发同一次 bootstrap，
使首次启动即就绪；非空库仍保持原行为（只 print，不自动重建）。

### 步骤 3 — 定向测试

新增两组用例（放 `tests/` 下与 KB 相关的既有测试文件旁，或新建专测文件）：
- 空库 bootstrap：无 `papers.json` + 无 marker → `require_generation()` **成功返回**，且后续调用仍成功（幂等）。
- 非空库 fail-closed：`papers.json` 有内容 + 无 marker → **仍抛 409 `INDEX_REBUILD_REQUIRED`**。

## 6. 子代理分派

- 角色：`backend-dev`；只改 `backend/**`。
- 最小上下文：本文件 + `manifest_store.py:540-614` + `main.py:28-45` + `routes_kb.py:302-325`。
- 单次范围：≤2 个代码文件（本项目本地模型约束）。

## 7. 边界与明确不做

- **不改**全库重建协议与 `--confirm-replace` 语义；**不改** `finalize` / `INDEX_FINALIZE_REQUIRED` 语义。
- **绝不**对非空库自动触发 embedding 或重建（严防"启动即重建"）。
- 不改前端；不改 `routes_kb.py` 的错误文案语义。
- 做**最小增量**改动，不重写/重构 `manifest_store.py` 其它部分。

## 8. 验收、风险与回滚

| # | 验收标准 |
|---|---|
| 1 | 全新环境（把 `data/kb` 改名备份模拟首次部署）→ 启动服务 → 上传 → **200 成功**，不再 409 |
| 2 | 已有文档数据但 marker 缺失 → **仍返回 409 `INDEX_REBUILD_REQUIRED`**（回归保护） |
| 3 | `routes_kb.py:83` `kb_component_status()` 的 `generation.ready` 在空库初始化后为 `true` |
| 4 | 新增两组定向测试通过（**只跑定向测试，不做全量回归**——用户明确要求） |
| 5 | 空库首次启动日志**不再出现** `[kb] index generation gate not ready` |

- 风险：bootstrap 时若 `papers.json` 未同步创建，会因 `metadata_sha256` 不匹配立刻转 503 → 步骤 1 的约束必须落实。
- 回滚：改动集中在 `manifest_store.py` 与 `main.py`，回退这两个文件即可恢复原行为（空库仍报 409，无数据破坏）。

## 9. 产出物、执行结果与变更日志

### 改动文件（3 个）

| 文件 | 改动 |
|---|---|
| `backend/app/knowledge_base/infrastructure/manifest_store.py` | 新增 `_is_empty_library()` / `_bootstrap_empty_generation()`；`require_generation()` 增加 `allow_bootstrap` 参数（默认 `False`，保持读路径零副作用） |
| `backend/app/api/routes_kb.py` | `_require_generation()` 透传 `allow_bootstrap`；**上传端点**显式传 `allow_bootstrap=True`（唯一 opt-in 点） |
| `tests/test_kb_empty_generation_bootstrap.py` | 新增 5 条定向测试（空库 bootstrap + 幂等 / 默认 fail-closed / 非空库绝不自动重建 / `finalize_pending` 仍 503 / 启动不自举） |

> **未改 `main.py`**：bootstrap 设计为显式 opt-in，启动路径默认 `allow_bootstrap=False`，
> 因此 `main.py` 既有调用天然保持只读，满足 `tests/test_kb_startup_generation_gate.py:71` 的 `assert not kb_dir.exists()`。

### 冻结清单同步（授权变更）

`tests/test_kb_upload_closure_matrix.py` 是冻结清单守卫，`routes_kb.py` 在其中。改动后按授权同步：
`docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json`
- `routes_kb.py` 单文件 sha256：`7674ee49…7c59` → `c24322d1…3c90`
- `inventory_digest`：`879b606a…ab2a` → `e03d6c84…1256`

### 执行结果（真实命令与输出）

```
# 定向测试（第 1 轮，仅新用例 + 启动门禁）
.venv/bin/python -m pytest tests/test_kb_empty_generation_bootstrap.py tests/test_kb_startup_generation_gate.py -q
→ 8 passed in 2.89s

# 定向测试（第 2 轮，含冻结清单守卫）
→ 1 failed（inventory_digest 未同步），86 passed

# 同步冻结清单后重跑（10 个 KB 相关测试文件）
.venv/bin/python -m pytest tests/test_kb_empty_generation_bootstrap.py \
  tests/test_kb_startup_generation_gate.py tests/test_kb_document_routes.py \
  tests/test_kb_document_foundation.py tests/test_kb_document_boundary.py \
  tests/test_kb_upload_closure_matrix.py tests/test_kb_document_delete.py \
  tests/test_kb_document_reindex.py tests/test_legacy_kb_integration.py \
  tests/test_kb_candidate_rebuild.py -q
→ 157 passed in 40.19s
```

### 运行时验收（模拟首次部署，真实服务）

| # | 验收 | 结果 |
|---|---|---|
| 1 | 全新环境（移走 `data/kb`）启动后上传 | **HTTP 201**，返回 `document_id` 与 `status: indexing`，**不再是 409** ✅ |
| 2 | 启动保持只读 | 启动后 `data/kb` **未创建** ✅（满足既有测试约束） |
| 3 | 第二次上传（`papers.json` 已变更） | **HTTP 201**，未出现 503 `INDEX_FINALIZE_REQUIRED`（`store.upsert_paper` 的 `refresh_live_digests` 生效）✅ |
| 4 | 文档列表接口 | 正常返回，无代际错误 ✅ |
| 5 | 生成的 marker | `data/kb/index-generation.json` 通过 schema 校验，`alias_target=papers_rebuild_empty_bootstrap` ✅ |
| 6 | 清理 | 两个测试文档 `DELETE` 均 200，`papers.json` 回到 0 条 ✅ |

> 非空库 fail-closed、默认参数 fail-closed、`finalize_pending` 仍 503 三项由定向测试覆盖（无需真实数据破坏）。
> **未执行全量回归**（用户明确要求）。

## 阻塞记录（2026-09-11）

用户已确认执行，但分派 `backend-dev` **失败 2 次**：当前会话的 `Task` 工具报
`Subagent "backend-dev" not found`（`.codebuddy/agents/backend-dev.md` 文件确实存在，
加 `subagent_path` 显式指定仍失败；该工具在本会话仅暴露内置只读的 `code-explorer`）。

按 `AGENTS.md` 门禁硬规则 #3，改动涉及 `.py` 时**禁止主会话代行**，因此未自行实现。
待用户明确豁免代行，或换到可调用项目子代理的环境后，按本文件执行。
