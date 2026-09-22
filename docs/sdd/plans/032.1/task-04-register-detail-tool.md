# Task 04：注册 `fetch_paper_detail` Tool

> 关联：[spec-032.1](../../specs/032.1-usenix-skill-decoupling.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03；当前状态：`已完成（待本规格收口复核）`

## 一句话目标

把「抓取 USENIX presentation 详情页并提取摘要」注册为 Agent 可调用的 Tool
`fetch_paper_detail`，纳入既有 Tool 注册表与白名单校验体系。

## 背景与前置条件

- 任务 02 完成：`parse_usenix_detail()` 可解析摘要。
- 任务 03 完成：`UsenixAcceptedSource` 已具备详情页抓取阶段（`_fetch_detail` / `_sync_detail_unit` /
  `_fill_abstract` 等），但这些都是**内部方法**，不能直接作为 Tool 入口。
- 既有 Tool 注册表：`backend/app/skills/registry.py`（**唯一事实源＝代码**），
  已注册 `search_paper_catalog` / `download_and_import_paper` / `kb_search` / `kb_ask` 四个 Tool。
- 执行体系：Tool 名必须在注册表内且 `enabled=true`；参数过白名单后才可执行
  （见 spec-023 的 `tool_dispatch` / `tool_executor`）。

## 实施步骤与文件边界

1. 在 `UsenixAcceptedSource` 上新增**公开稳定入口**（例如 `fetch_paper_detail(...)`），
   内部复用任务 03 已有的 `_fetch_detail` + `parse_usenix_detail`，
   **避免与同步路径双写逻辑**。返回标题 / 作者 / 摘要 / 关键词 / 官方 PDF 链接等字段。
2. 在 `backend/app/skills/registry.py` 注册 ToolEntry：
   - `name`: `fetch_paper_detail`
   - `description`: 必须能引导模型正确传参（说明用途、参数含义、不接受任意 URL）
   - `entry`: 指向上述**真实可定位**的入口（`模块.类.方法`）
   - `parameters`: JSON Schema；必填字段必须写进 `required`
3. 安全：URL 必须过既有白名单（`_detail_url_ok` / `validate_url`），
   非法 URL 返回可读错误，**不发起网络请求**。

**只允许改动**：`usenix_publication_source.py`（新增公开入口）、`registry.py`（注册）、新增/更新测试。

## 子代理分派

角色 `backend-dev`（模型 `qwen3.8:27b-mlx`）。本地模型约束：单次最多 2 个代码文件、约 150 行。
回传：公开入口签名、ToolEntry 定义、测试命令/退出码/结果、风险。

## 边界与明确不做

- **不新增第二套抓取/解析实现**：必须复用任务 02/03 的既有能力。
- 不改 `search_paper_catalog` 等既有 Tool 的定义与行为。
- 不改 `/api/papers/searches` 契约，不新增 HTTP 路由。
- 不在本任务创建新 Skill（属任务 05），因此**不改任何 SKILL.md**。
- 搜索/目录同步阶段仍禁 PDF；本 Tool 只取 HTML 详情页摘要，不下载 PDF。

## 验收（每条都要有测试）

1. `build_default_tool_registry()` 返回的 Tool 列表中包含 `fetch_paper_detail`，且 `entry` 指向真实可导入的符号（可 import 成功）。
2. 用 fixture / fake client 调用该入口能返回正确摘要（不依赖真实网络）。
3. 非法 URL（其它域名 / 带 query / 非 presentation 路径）返回可读错误且**不发起网络请求**。
4. 未注册 / 已禁用的 Tool 名在既有执行体系中仍被拒绝（回归保护，确认未破坏 spec-023 的 `tool_dispatch`）。
5. 既有 `tests/test_tool_registry.py`、`tests/test_tool_executor.py`、`tests/test_skill_intent.py`、
   `tests/test_usenix_publication_source.py` 全绿。
6. `.venv/bin/ruff check` 对改动文件干净。

## 产出物、执行结果与变更日志

### 执行结果（2026-09-20 对账）

- 改动文件：`backend/app/paper_discovery/infrastructure/usenix_publication_source.py`、
  `backend/app/skills/registry.py`、`backend/app/skills/tool_dispatch.py`、
  `tests/test_usenix_detail_tool.py`、`tests/test_fetch_paper_detail_dispatch.py`。
- 定向验证：`.venv/bin/python -m pytest tests/test_usenix_detail_tool.py tests/test_fetch_paper_detail_dispatch.py -q` → **24 passed，exit 0**。
- 复核结论：`fetch_paper_detail` 已注册并接入分派器；入口可导入、非法 URL 不触网、未注册/禁用工具仍拒绝；Tool 路径复用共享 USENIX source 实例以保持缓存/限流。
- 规格收口仍待 032.1 Task07 的独立需求/验收评审。
