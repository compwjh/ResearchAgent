# Spec029 Task06 运行时探针报告

## 结果状态

```text
result=BLOCKED_RUNTIME_BRIDGE
safe_indexed_documents=1 (strict; 3 legacy manifests remain readable by manifest rules but metadata is legacy_unknown; 2 documents lack a current manifest)
catalog_snapshot=AVAILABLE_BUT_NOT_ACQUISITION_READY
evidence_upgrade_real_manifest=PASS_WITH_EXPLICIT_GENERATION_READER
evidence_upgrade_default_constructor=BLOCKED
get_acquisitions_projection=404_NO_APPROVAL
task_detail_search_id=ABSENT
network_or_real_download=false
user_kb_or_qdrant_write=false
```

本轮只读检查本地 `data/research`、`data/paper_search`、`data/kb`，并运行既有定向 pytest；没有下载公网 PDF、登录浏览器、提交导入、删除/重建数据或修改业务代码。

## 观察事实

### 1. 本地 KB 文档与 manifest

- `data/kb/papers.json` 有 6 个 `status=indexed` 的文档，所有对应 PDF 文件存在，逐个 SHA-256 与 metadata `source_sha256` 一致。
- 严格按“metadata 也必须是当前验证态”筛选，只有 `d4dfd2a620384ad5bece27320661f8f0` 可作为当前已索引样本：
  - 文件：`data/kb/papers/d4dfd2a620384ad5bece27320661f8f0.pdf`，762149 bytes；
  - manifest：`data/kb/manifests/d4dfd2a620384ad5bece27320661f8f0/v1.json`；
  - manifest `status=ready`、`source_hash_state=verified`、`source_sha256 == indexed_source_sha256`、107 chunks、页码 1–18；
  - generation marker `run_id=38efa91a33154fd097c61d1c745d408f`，且 `data/kb/index-generation.json` 存在。
- 另外 3 个文档（`f3227d...`、`891dc8...`、`388ff1...`）的 v1/v2 manifest 具有 verified hash 和 chunks，但 `papers.json` 仍为 `source_hash_state=legacy_unknown`、`indexed_source_sha256=null`；`ca08f5...` 与 `dd1e53...` 没有当前 v1/v2 manifest。因而本报告不把这些文档列为“严格安全样本”，只记为“manifest 层可读候选”或“无 manifest”。

### 2. Catalog candidate / search snapshot

- 当前最新 `search_jobs` 行为：`search_id=dd5c47aa0cb541188b884c27fa233e67`，query=`软件供应链攻击 软件供应链攻击`，`status=partial`、`degraded=1`、`total_results=894`，expires=`2026-09-16T13:23:03Z`。
- 该 search_id 在 `search_results` 有 894 条快照，但在 `paper_candidates` 没有行；快照样本含 `catalog_paper_id`、title、abstract、`source_page_url`，未包含 `pdf_url`/`pdf_access`。因此它是可读 catalog snapshot，但当前不能直接作为 acquisition-preview 的 public PDF candidate。
- 旧 `paper_candidates` 表确有 public 候选，例如 `search_id=084d7b57491d4812ae4eb505326a6414` 的 `f11a606c713386db`（`{Back-Propagating} System Dependency Impact for Attack Investigation`，`pdf_access=public`），但该 search session 已于 2026-09-15 22:43:19Z 过期；本轮不把过期 snapshot 当作可安全复用候选。

### 3. EvidenceUpgradeService 真实 manifest/store 接缝

- 使用真实 `data/kb/manifests/.../v1.json` 和真实 generation reader（`FinalizeBundleStore(...).require_generation`），仅用内存 probe store 保存结果、用 manifest 的首个真实 chunk 构造检索命中，未触碰真实 Research SQLite/Qdrant。
- 结果为 `status=upgraded`、`to_level=fulltext`、`document_id=d4dfd2a620384ad5bece27320661f8f0`、`chunk_ids=[0d70f374-678b-542e-aff5-7f43b4038097]`、`page=1/page_end=1`、`source_sha256=71f8829f...a14a1`、`manifest_generation=38efa91a...d408f`、`manifest_fingerprint=b3594ce9...43e9`、`chunker=v1`。这证明实际 manifest 校验、generation 读取和 locator 投影接缝可工作。
- 但用生产默认构造 `EvidenceUpgradeService(store, search=...)` 时立即失败：`AttributeError: 'InspectionManifestStore' object has no attribute 'require_generation'`（退出码 1）。`create_manifest_store()` 返回 `InspectionManifestStore`，而 `require_generation()` 只在 `FinalizeBundleStore` 上；当前测试通过显式注入 `generation_reader` 绕过了这个生产默认接缝。该问题需主 Agent 修复或明确装配方式后，才能宣称默认运行时 evidence upgrade 可用。

### 4. Research SQLite 与 GET 投影

- 只读 SQLite 查询结果：`research_paper_selections=0`、`research_selection_versions=0`、`research_acquisition_approvals=0`、`research_document_links=0`、`research_acquisition_events=0`、`research_evidence_upgrades=0`、`preliminary_reports=0`。
- 直接调用现有 `get_research_task("319542120c064dc3848a19a3b51fceaf")` 返回任务详情（`status=interrupted`、plan_version=2），但返回对象没有 `search_id` 字段；其 plan/work_items 也未提供服务端 catalog snapshot handle。
- 直接调用现有 `get_research_acquisition("319542120c064dc3848a19a3b51fceaf")` 返回 HTTP 404，稳定错误体为 `{"error":{"code":"BATCH_NOT_FOUND","message":"研究任务尚未确认全文获取"}}`。这与当前无 approval/link 行一致，证明“未确认时 GET 投影”能 fail closed，但没有真实 batch/link 可用于验证逐篇 projection。
- 另一已完成任务 `929d24e696935fd0b6188796814a7ab9` 的详情同样没有 `search_id`；其 acquisitions GET 同样为 404 `BATCH_NOT_FOUND`。

## 命令 / 退出码

| 命令 | 退出码 | 真实结果 |
|---|---:|---|
| `.venv/bin/python` 只读脚本：枚举 KB PDF、校验 SHA-256、读取 manifest/generation | 0 | 6 个 PDF 存在；1 个严格 metadata+manifest 样本；generation `38efa91a...d408f` 有效 |
| `.venv/bin/python` 真实 manifest 接缝 probe，默认 `EvidenceUpgradeService` 构造 | 1 | 生产默认构造失败：`InspectionManifestStore.require_generation` 不存在 |
| `.venv/bin/python` 真实 manifest 接缝 probe，显式注入 `FinalizeBundleStore.require_generation` | 0 | 真实 manifest locator 成功升级为 `fulltext`；仅内存保存结果 |
| `.venv/bin/python` 直接调用 `get_research_task` / `get_research_acquisition`（先导入 `backend.app.main` 注册 provider） | 0 | detail 无 `search_id`；acquisitions 返回 404 `BATCH_NOT_FOUND` |
| `.venv/bin/python -m pytest -q tests/test_spec029_fulltext_evidence.py tests/test_spec029_acquisition_bridge.py tests/test_spec029_reuse_gate.py tests/test_spec029_frontend_acquisition_progress.py` | 0 | `16 passed in 0.74s` |
| `git status --short --branch` | 0 | 仅报告新增前工作树为 `main...origin/main [ahead 5]`，无业务代码改动 |

## 产物路径

- 本报告：`docs/sdd/plans/029/artifacts/task-06/runtime-probe-report.md`
- 未新增探针脚本；探针均为一次性只读内联 Python。

## 风险阻塞

1. **P0：EvidenceUpgradeService 默认构造接缝断裂。** 生产默认 reader 绑定了没有 `require_generation` 的 `InspectionManifestStore`；必须修正装配，或在组合根统一传入 `FinalizeBundleStore.require_generation`，并补一个不依赖 fake reader 的回归测试。
2. **P0：任务详情没有 `search_id`。** 当前 `ResearchTask`/`_task_summary`/detail projection 没有稳定返回服务端 search snapshot handle；确认 acquisitions 只能依赖用户保留的外部句柄，任务刷新后无法从详情恢复。已有前端报告也把此列为阻塞。
3. **P0：当前真实 Research 数据没有 selection/approval/link/evidence 行。** 因而无法安全执行真实确认、下载、导入、全文升级或验证有数据时的 GET acquisitions 逐篇投影；不能把 404 或合同测试写成真实成功。
4. **P1：最新有效 search snapshot 只有 `search_results` 快照，没有 `pdf_url`/`pdf_access`。** acquisition-preview 的候选 fallback 会将 dict 的 access 视为 unknown，无法证明 public PDF 路径；旧 public candidates 已过期。
5. **P1：3 个已有 manifest 虽可按 manifest 规则通过，但 metadata 仍是 legacy_unknown；另有 2 个文档没有当前 manifest。** 若要使用这些文档作为真实证据样本，应先由既有索引/元数据流程完成验证，而非在探针中猜测其 provenance。

## 主 Agent 后续动作

- 修复并测试 `EvidenceUpgradeService` 默认 generation reader 接线，优先复用 `FinalizeBundleStore`，然后重跑真实 manifest probe。
- 在任务详情或持久化桥接中补齐稳定、服务端拥有的 `search_id`（或确认等价的持久化 snapshot handle），再重跑 detail/read-after-refresh 验证；范围变化需先更新 Spec029/spec status。
- 准备一个用户已确认、可复验且未过期的 public catalog snapshot，使 `paper_candidates`/`search_results` 能提供完整服务端 candidate payload；仅在显式确认后才允许进入既有 batch。
- 真实运行时验收前先产生 selection→approval→batch→document link 的合法数据链，再读取 GET acquisitions，记录逐篇 status/document_id/import_item_id/error_code；随后才可执行真实 PDF/索引/evidence locator 和删除/重建降级验证。
- 本轮不应将 Spec029 标记为 `已完成`，也不应宣称真实全文导入或部署验收通过。

## 开始 / 结束 / 总耗时

```text
开始：2026-09-16T04:45:00+08:00（约）
结束：2026-09-16T04:53:47+08:00
总耗时：约 8 分 47 秒
```

## 后续修复复验（2026-09-16）

本报告第 3 节记录的是修复前的历史事实，不回写为虚假的成功结果。随后已将生产默认装配改为：逐文档 manifest 继续由
`InspectionManifestStore` 读取，发布代次改由 `FinalizeBundleStore.require_generation` 读取；新增回归测试覆盖默认构造路径。

- 默认 `EvidenceUpgradeService` 的真实构造与 generation 读取已通过：当前本地代次为
  `38efa91a33154fd097c61d1c745d408f`。
- 定向 Spec029 回归：`17 passed in 1.28s`。
- 该修复只消除了 generation reader 的 P0；任务详情缺少稳定 `search_id`、真实确认/导入链和真实浏览器交互验收仍保持未完成，不能据此把 Spec029 标记为完成。

随后又完成了 `search_id` 桥接修复：`ResearchTask` 增加可选服务端快照句柄，研究仓储做加性迁移并采用首个有效句柄优先写入；搜索 worker、编排器、任务摘要和 worker 事件均传递该句柄。既有历史任务没有对应搜索快照时仍安全返回 `null`，不会猜测或伪造句柄。相关定向回归为 `63 passed`；真实 acquisition 链、公开 PDF 和浏览器确认仍未执行。

## 运行时复核补充（2026-09-16 06:00）

- 只读网络探针确认固定公开样本
  `https://www.usenix.org/system/files/usenixsecurity26-peng-jiaqian.pdf` 返回 `200`、
  `application/pdf`、`1094158` bytes。
- 在临时复制的知识库目录中调用既有 `import_candidate`、安全下载器和
  `KnowledgeBasePaperImportAdapter`，补齐完整 v1/v2 chunker 状态后成功返回
  `status=indexed` 和临时 `document_id`；临时目录随后由进程清理。
- Research 侧选集→确认→批次→document link 的持久化桥接仍以现有定向合同为准；本次没有把
  真实 PDF 写入用户当前知识库，也没有把隔离探针冒充生产端到端成功。
- 结论仍为 **NO-GO**：生产知识库/向量代次的真实写入需要用户明确允许一次可回滚的测试导入，
  并在导入后验证补偿或由用户选择保留测试论文。该门禁未通过前，Spec029 不标记为已完成。

## Intake 入口修复复验（2026-09-16）

- 截图会话 `eedf7efb96a74932b619115672d134c0` 曾处于 `intake_pending`，助手消息为空且没有
  `research_task_id`；健康接口仍返回 200，故阻塞不是 Ollama 不可用。
- 根因是 Intake SSE 沿用了不带 `event_seq` 的 `stream_event`，而前端对首个 `meta` 和后续帧要求
  连续序号，导致浏览器把已成功落库的 Intake 显示为 `STREAM_INTERRUPTED`。
- 另外，研究表单没有提交必填 `time_range`，创建出的助手占位消息不会自动得到 Intake 投影。
- 修复后：统一 Intake 投影构造/持久化；表单增加起止年份；表单创建的助手占位消息写入安全 Intake
  投影并收口；Intake SSE 改用 `EventSequencer`。定向测试 `74 passed`，8500 服务重启后
  `/api/health` 返回 200。
- 该修复只打通入口与 SSE 协议，不代表真实公开 PDF 导入、全文索引或证据升级已经通过。
