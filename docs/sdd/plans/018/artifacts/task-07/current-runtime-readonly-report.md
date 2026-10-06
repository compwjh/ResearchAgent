# BLOCKED — Spec018 当前运行时只读验收报告

## 1. 范围、运行标识与结论

- **Spec / Task**：Spec018 / Task07 当前运行时复核（tester，只读）
- **run_id**：`spec018-runtime-readonly-20261006T133052Z`
- **服务**：`http://127.0.0.1:8000`（本次所有请求均为 `GET` 或 `HEAD`）
- **运行时间**：2026-10-06 13:30:52Z–13:33:03Z
- **工作树身份（只读观察）**：分支 `codex/integrate-current-code-to-main`，HEAD `cb7bf56381f5ad18891b69f1c0289218f5f4ae97`；工作树当时有 63 个状态条目、其中 8 个未合并条目。本报告没有产生这些状态。
- **禁止/未执行**：没有 `POST`、`DELETE`、reindex、manifest rebuild、resume/cleanup、Qdrant 写入或切换、embedding、下载、上传、删除、Git 写入；响应正文没有写入项目产物，只保留脱敏统计。

当前服务的 API 读路径可复核，但本轮不能对 Spec018 重新签署 `READY_FOR_USER`：v2 离线 bundle 与当前 live manifest 不是同一 chunk 快照，差异尚未在同一输入/fingerprint 下解释；另外两个固定交接物缺失，closure matrix 仍含冲突标记。最终结论为 **`BLOCKED`**。

## 2. API E2E Artifact（只读）

### 2.1 探活与依赖状态

| 请求 | 结果 | 脱敏关键字段 |
|---|---:|---|
| `GET /api/health` | `200` | `status=ok` |
| `GET /api/kb/health` | `200` | `generation.ready=true`、`generation.error_code=null`、`qdrant=true`、`embedding=false`、`papers=40`、`chunks=8568`、`reranker.enabled=false`、`v2_llm.available=true` |
| `GET /api/kb/documents?limit=10` | `200` | 当前页 10 条、`total=40`、返回 opaque `next_cursor`、`ETag` 存在 |

`embedding=false` 是本次健康响应的观察值；本次没有以此推断冷加载完成时间，也没有发起会触发 embedding 的请求。generation 与 Qdrant 已达到读路径所需的健康条件。

### 2.2 已知完整 manifest 文档的 inspection 分页

样本为既有文档 `d4dfd2a620384ad5bece27320661f8f0`。每页继续使用服务返回的 opaque `next_cursor`，不手写或改写 cursor；所有页面 HTTP `200`。唯一键检查使用：block=`block_id`，chunk=`(chunker,chunk_index)`，anchor=`(block_id,chunker,chunk_index)`。

| chunker | 页级 `(blocks,chunks,anchors)` | 页数 | API `total` | 实际汇总 | 唯一键重复 | manifest |
|---|---|---:|---|---|---:|---|
| v1 | `(200,107,200)`, `(200,0,200)`, `(104,0,166)` | 3 | `504/107/566` | `504/107/566` | 0 | `ready` |
| v2 | `(200,200,200)`, `(200,108,200)`, `(104,0,60)` | 3 | `504/308/460` | `504/308/460` | 0 | `partial` |

两版本每页的 `total` 均一致，分页汇总与 API 声明完全相等，没有首批截断或 cursor 重复。两版本均返回 `mapping_algorithm_version=source-anchor-v2`。

稀疏映射统计（不保存正文）：

| chunker | chunks | blocks | anchors | manifest mapped/unmapped | 有 anchor 的 blocks/chunks | 可能 block×chunk 对 | anchor 密度 |
|---|---:|---:|---:|---:|---:|---:|---:|
| v1 | 107 | 504 | 566 | 107/0 | 504/107 | 53,928 | 1.049548% |
| v2 | 308 | 504 | 460 | 290/18 | 460/290 | 155,232 | 0.296331% |

v2 的 18 个 unmapped 均由 manifest 归因 `SOURCE_RANGE_UNRESOLVED`；没有把它们伪造为 anchor。当前 live manifest 与 API 汇总相互一致。

### 2.3 Source 与错误契约

| 请求 | 结果 | 脱敏关键 headers/body |
|---|---:|---|
| `HEAD /api/kb/documents/d4dfd2a620384ad5bece27320661f8f0/source` | `200` | `Content-Type=application/pdf`、`Content-Length=762149`、`Accept-Ranges=bytes`、`ETag` 存在；无 body |
| `GET .../source`，`Range: bytes=0-15` | `206` | `Content-Length=16`、`Content-Range=bytes 0-15/762149`、`Accept-Ranges=bytes`、`ETag` 存在；仅验证 16 字节长度，不记录字节内容 |
| `GET /api/kb/documents/00000000000000000000000000000000/inspection?chunker=v1` | `404` | `error_code=DOCUMENT_NOT_FOUND`、`retryable=false`；错误体不含 `/Users/`、`/private/`、`/tmp/` 或 `/var/` 绝对路径 |

## 3. Generation、Qdrant meta 与 rebuild topology 解释

只读文件证据如下：

| 证据 | 观察值 |
|---|---|
| `data/kb/index-generation.json` | `run_id=38efa91a33154fd097c61d1c745d408f`；`papers → papers_rebuild_38efa91a33154fd097c61d1c745d408f`；commit marker 已写入 |
| `data/kb/qdrant/meta.json` | `aliases.papers` 同样指向 `papers_rebuild_38efa91a33154fd097c61d1c745d408f`；集合配置为 dense 1024 + sparse |
| `data/kb/rebuild-runs/38efa.../state.json` | `status=completed`、`progress=100`、`point_counts.total=415`（v1=107、v2=308）；`observed.outcome=ok`，fresh topology digest 与 expected digest 相等 |
| `data/kb/rebuild-runs/38efa.../commit.json` | commit candidate 与 generation marker 一致 |
| `data/kb/rebuild-runs/38efa.../topology.json` | 仍记录 `active_generation/alias=...fa5b...`、`state_status=switching`、`candidate_state=ambiguous`，并列出旧/新候选 |

解释：`topology.json` 是 38efa finalize/switch 过程中的旧 inventory 快照，保留了切换前的 alias 和 `switching` 状态，不能作为当前实时 topology 真相。当前 generation commit marker 与 Qdrant meta alias 均指向 38efa；live inspection 的 v1+v2 point 数 `107+308=415` 又与 38efa state 的总点数相符，API health/inspection 读路径也成功。因此本轮将 topology 文件解释为历史快照，而不是据此调用 resume、cleanup 或 rebuild。这里没有调用 Qdrant 管理接口，结论限于 marker、静态 meta 和真实 API 的只读交叉证据。

## 4. 离线 v2 `497` 与 live v2 `460` 的差异

历史离线报告 `docs/sdd/plans/018/artifacts/task-06/sparse-anchor-backend-report.md` 的 2026-09-10 内存 bundle 记录为：v2 `chunks=214`、`anchors=497`、`mapped=213`、`unmapped=1`，可能 block×chunk 对为 107,856。该报告明确为 `IMPLEMENTED-IN-ISOLATION`，未触碰真实 manifest、Qdrant 或用户数据。

本次 live API/manifest 记录为：v2 `chunks=308`、`anchors=460`、`mapped=290`、`unmapped=18`，可能 block×chunk 对为 155,232；当前 `index_fingerprint` 与 live manifest 自洽，分页无重复。

v1 两边均为 `504/107/566`，但 v2 的 chunk 数已经从 214 变成 308，故 `497` 与 `460` 不是同一输入或同一 chunker snapshot 的两个统计视图。现有材料没有给出离线 bundle 与 live manifest 的同一组 chunker/config/index fingerprint 对照，不能把差异归因于某一具体代码或数据变更，也不能把两者写成同一个事实。本轮不重建、不覆盖 manifest，保持该项为 **未解释差异（阻塞）**。

## 5. 固定交接物与已知阻塞

- `docs/sdd/plans/018/artifacts/task-06/full-index-rebuild-report.md`：**缺失**。
- `docs/sdd/plans/018/artifacts/task-06/sparse-anchor-backend-test-report.md`：**缺失**。
- `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json`：当前仍含 `<<<<<<<`、`=======`、`>>>>>>>` 冲突标记，不能作为有效 JSON 读取，也不能据此宣称 inventory digest/只读 allowlist 已验证。
- 200 页或 10,000 切片级长文档性能数据、当前部署 Markdown upload→index→inspection→UI 完整链路，在本轮没有新增证据；不把历史固定 fixture 证据冒充当前部署证据。
- 历史材料中的旧 PDF v2 `indexing/INSPECTION_BUILDING`、reranker disabled 等遗留继续按原报告披露；本轮没有调用任何会改变其状态的接口。

## 6. 待补的人工验收案例（本轮未执行，不构成 PASS）

以下步骤来自 Spec018 产品路径和历史运行报告；本次只做 HTTP GET/HEAD，没有打开浏览器，因此当前 UI 文案、等待提示和点击结果均标为“未验证”。在这些项补齐前不得交给用户人工验收。

入口：`http://127.0.0.1:8000`。前置：服务 health/kb health 为 200，选择已有完整 manifest 的 PDF `d4dfd2a620384ad5bece27320661f8f0`；禁止点击上传、删除或重建索引。

| 步骤 | 点击/输入（当前未验证） | 点击后提示（当前未验证） | 等待 | 等待中显示 | 下一步 | 失败恢复 |
|---|---|---|---|---|---|---|
| 1 | 打开知识库，点击二级 Tab“切片检查” | 应显示文档列表；本次未验证 | 等待列表请求完成 | 应显示加载/空状态；本次未验证 | 选择上述已有 PDF | 若列表失败，保留错误码与 request id，返回知识库，不触发重建 |
| 2 | 选择文档，选择 `v1` | 历史报告记录 `ready · 已加载` 与 107 个切片；本次未验证 | 等待 inspection 首页与后续 cursor 请求 | 应显示加载状态；本次未验证 | 点击“加载更多切片”直到按钮消失 | 遇 `409/202/503` 停止并记录稳定 `error_code`，不要轮询触发构建 |
| 3 | 切换 `v2` | 历史报告记录 `partial · 已映射 290/308 · 未映射 18`；本次未验证 | 等待每个 opaque cursor 页返回 | 应显示当前分页进度；本次未验证 | 加载到 308 个切片后检查 anchor 总数 460 | 若状态不是 `partial` 或计数不一致，停止人工验收并回传 run_id |
| 4 | 点击标题块/第三页块，再反向点击关联切片 | 历史报告记录真实关联且不跳到 `#0`；本次未验证 | 等待联动滚动结束 | 应保留两栏状态；本次未验证 | 检查高亮范围与 API anchor 关系 | 若跳到 `#0`、空高亮或控制台报错，记录 DOM/错误后退出，不修现场数据 |

成功判据应同时满足：API 汇总保持上述真实值、v2 18 个 unmapped 原因可见、双向定位不产生虚假 `#0`、没有 P0/P1、固定交接物与 closure matrix 补齐。当前这些人工步骤没有本轮证据。

## 7. Readiness Matrix

| # | 门项 | 结果 | 证据/原因 |
|---:|---|---|---|
| 1 | 服务已启动并可访问 | **PASS** | `/api/health`、`/api/kb/health` 均 200 |
| 2 | 真实 API 创建入口成功 | **FAIL** | 本次按只读边界禁止 POST，未创建新实体；不能用已有样本冒充创建入口成功 |
| 3 | 主路径参数被正确解析 | **PASS** | 两个 `chunker` inspection GET 均 200；document id、chunker、page_size 和服务返回 cursor 均被接受 |
| 4 | 任务/实体状态从初始态推进 | **FAIL** | 只观察到现有 `ready/partial` 终态/可用态，没有执行或观察状态转移 |
| 5 | 前端显示处理中提示 | **FAIL** | 本轮未打开浏览器；历史文案不能替代当前部署证据 |
| 6 | 用户知道何时点击或等待 | **FAIL** | 当前 UI 等待提示未验证 |
| 7 | 核心业务产物真实生成 | **PASS** | live inspection 返回真实分页 manifest、504 blocks、v1 107 chunks/566 anchors、v2 308 chunks/460 anchors |
| 8 | 失败状态有可操作恢复 | **FAIL** | 本轮未触发恢复路径；且 full rebuild/backend tester 固定交接物缺失 |
| 9 | 页面状态与 API 状态一致 | **FAIL** | API 自洽，但本轮没有当前浏览器 DOM/页面状态证据 |
| 10 | 步骤文档可由无上下文用户复现 | **FAIL** | 当前 UI 文案未验证，且存在 497/460 未解释差异、缺失交接物和冲突 matrix |

**计分：3/10 PASS。** 该分数、未解释差异、关键证据缺失和未解决冲突共同阻止 `READY_FOR_USER`。

## 8. Final Decision

**`BLOCKED`**

已完成：当前服务健康、documents 列表、d4df v1/v2 全量 opaque-cursor 分页、唯一键与稀疏映射统计、source HEAD、合法 Range 206、非法 ID 404，以及 generation/current Qdrant meta/run 状态的只读交叉核对。

仍阻塞：

1. 离线 v2 bundle（214 chunks/497 anchors）与 live v2 manifest（308 chunks/460 anchors）不是同一快照，缺少同输入/fingerprint 的解释；
2. `full-index-rebuild-report.md` 与 `sparse-anchor-backend-test-report.md` 缺失；
3. `upload-closure-matrix.json` 仍有冲突标记，inventory/allowlist 不能复核；
4. 当前部署的 UI 处理中提示、失败恢复、页面/API 一致性与人工步骤未由本轮验证；
5. 长文档性能和当前 Markdown 完整链路没有新增当前部署证据。

解除条件：由负责实现/架构角色补齐或明确豁免上述固定证据、在同一 chunk/config/index fingerprint 下解释 497/460、解决 closure matrix 冲突并重新验证；随后由 tester 在不改变运行数据的前提下重跑对应只读 API 与必要的当前 UI 人工案例。未解除前不建议用户开始人工验收。
