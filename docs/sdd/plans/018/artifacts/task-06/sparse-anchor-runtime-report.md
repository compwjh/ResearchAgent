# Spec018 Task06E-D 稀疏来源锚点运行时验收报告

## 固定回传字段

- 任务：`Spec018 Task06E-D`
- 角色：`tester`
- 模型：临时 `Luna xhigh`
- 结果状态：`PASS（本报告覆盖的运行时验收项）`
- 验收范围：只读 HTTP API、既有版本门禁测试、真实浏览器检查器、双向点击定位；未执行 manifest rebuild、embedding、下载、Qdrant 写入/切换/删除或 Git 操作。
- 服务：已有本地服务 `http://127.0.0.1:8000/`，浏览器连接成功；服务监听证据为 Python PID `22967` 的 `127.0.0.1:8000 (LISTEN)`。
- 文档：`d4dfd2a620384ad5bece27320661f8f0`
- 原件：`How to Peel a Million- Validating and Expanding Bitcoin Clusters.pdf`
- 产物：`docs/sdd/plans/018/artifacts/task-06/sparse-anchor-runtime-report.md`
- 进度日志：`.codebuddy/agent-logs/spec-018/task-06e/tester/20260910-runtime.md`

## 1. API 运行证据

### 1.1 文档列表

只读请求：

```text
curl -sS -i --max-time 10 http://127.0.0.1:8000/api/kb/documents
```

结果：HTTP `200`；返回 1 个文档，`document_id=d4dfd2a620384ad5bece27320661f8f0`，PDF 页数 18，v1/v2 均为 indexed、progress 100；无服务写入。

### 1.2 inspection 版本与分页

以 `page_size=200` 对 v1、v2 逐页 GET，持续使用服务返回的 opaque `next_cursor`，直到 `next_cursor=null`。两种版本所有页面均返回 HTTP `200` 且 `manifest.mapping_algorithm_version=source-anchor-v2`。

| chunker | 页数 | 每页 `(blocks,chunks,anchors)` | 汇总 received | API total | 唯一性 | manifest status |
|---|---:|---|---|---|---|---|
| v1 | 3 | `(200,107,200)`, `(200,0,200)`, `(104,0,166)` | `504,107,566` | `504,107,566` | 0 duplicates | `ready` |
| v2 | 3 | `(200,200,200)`, `(200,108,200)`, `(104,0,60)` | `504,308,460` | `504,308,460` | 0 duplicates | `partial` |

v2 manifest 同时返回 `mapped_count=290`、`unmapped_count=18`、`unmapped_reasons.SOURCE_RANGE_UNRESOLVED=18`；未映射项没有被伪造为 anchor。分页验收命令退出码为 `0`。

补充的 `page_size=500` 只读分页也得到 v1 `504/107/566`、v2 `504/308/460`，两者均 2 页完整结束，作为最大页大小的交叉证据。

### 1.3 旧 v1 manifest/fixture 版本门禁

当前线上 v1 chunker 清单本身已标记为 `source-anchor-v2`，因此 live API 对该清单按设计返回 200；旧 `source-anchor-v1` 清单必须通过测试夹具验证 fail-closed。执行：

```text
./.venv/bin/python -m pytest -q \
  tests/test_kb_document_routes.py::test_inspection_legacy_mapping_version_is_rebuild_gate \
  tests/test_kb_document_foundation.py::test_inspection_rejects_legacy_source_anchor_bundle \
  tests/test_kb_document_foundation.py::test_inspection_rejects_legacy_payload_without_source_hash
```

结果：退出码 `0`，`3 passed`。重复执行 route 门禁：

```text
./.venv/bin/python -m pytest -q tests/test_kb_document_routes.py::test_inspection_legacy_mapping_version_is_rebuild_gate
```

结果：退出码 `0`，`1 passed`。测试断言旧 mapping 版本最终转换为 HTTP `409`、`error_code=INDEX_REBUILD_REQUIRED`、`details.cause=MAPPING_VERSION_MISMATCH`；临时 fixture 使用 `tmp_path`，未修改真实 `data/kb`、Qdrant 或用户 manifest。

## 2. 真实浏览器验收

浏览器通过检查器选择上述 PDF 后，v1 初始页显示 `v1 · 107 个切片`、`ready · 已加载`、`504 个原文块`。

- v1 点击“加载更多切片”后：DOM 中 107/107 个 chunk cards，`chunk_index=0..106` 连续，卡片 `anchorCount` 总和为 566，加载按钮消失。
- 原文面板滚动到文档末尾时，AX 状态可观察到“原文块 504”。原文区采用滚动窗口增量渲染，采样时 DOM 只保留可见窗口，不将此误判为 API 数据缺失。
- 切换 v2 后状态显示 `partial · 已映射 290/308 · 未映射 18 · 原因 SOURCE_RANGE_UNRESOLVED`；连续点击“加载更多切片”三次后得到 308/308 cards，`chunk_index=0..307` 连续，`anchorCount` 总和为 460，加载按钮消失。
- 浏览器运行时错误/警告日志：空数组 `[]`。

### 2.1 Introduction 正向与反向定位

API 找到标题原文块：

```text
block_id=d4dfd2a620384ad5bece27320661f8f0:p2:b8
text=1 Introduction
anchor=(chunker=v1, chunk_index=3, coverage=0.014042, is_primary=false)
```

真实点击结果：

1. 点击标题块 `p2:b8` 后，仅激活真实关联切片 `v1:3`；没有激活 `v1:0` 或其它无交集切片。
2. 点击 `v1:3` 后，激活其全部真实来源块 `p2:b5`、`p2:b8`、`p2:b10`；`p2:b10` 是该 chunk 的 primary block。

### 2.2 第三页来源块正向与反向定位

1. 点击第三页块 `d4dfd2a620384ad5bece27320661f8f0:p3:b0`，激活 `v1:7`、`v1:8`，且 `zeroActive=false`，没有错误跳转到 `#0`。
2. 反向点击 `v1:7`，只激活来源块 `p3:b0`，且 `zeroActive=false`。

上述点击均通过浏览器 DOM 的 `data-block-id`、`data-chunk-index`、`data-active` 和 `data-primary-block-id` 复核；不是只依据可见文本猜测。

## 3. 定向前端/后端回归

```text
node --check frontend/kb-inspection.js
node tests/test_frontend_kb_inspection_runtime.js
node tests/test_frontend_kb_inspection_interaction.js
node tests/test_frontend_kb_inspection_renderer.js
node tests/test_frontend_kb_inspection_pdf.js
```

结果：全部退出码 `0`。

- runtime contract：PASS（tabs、分页、状态、取消、GET-only、304 cache）
- interaction contract：PASS（overlap/cross-page、click-keyboard、窄屏滚动、批量显示）
- renderer contract：PASS（pipeline、hostile HTML/image、fallback、DTO validation）
- PDF renderer contract：PASS（本地 module、worker/options、lazy canvas/text/bbox、error/cancel、GET allowlist）
- `node --check`：PASS

后端版本/inspection 定向测试（含重复门禁）退出码均为 `0`；另运行 `tests/test_kb_upload_closure_matrix.py` 得 `2 passed`、退出码 `0`。首次一次 `-k` 表达式拼写错误导致 pytest 退出码 `4`、未执行测试，修正后没有复现，该失败属于命令输入错误而非产品失败。

## 4. 决策依据

1. Spec018 要求 inspection 成功体使用 `source-anchor-v2`；live v1/v2 两个 chunker 清单的每一页均满足该版本字段。
2. API 分页逐页汇总与 `total` 完全相等，且 block/chunk/anchor 复合键均无重复，证明没有首批截断或 cursor 丢失。
3. 旧 v1 清单由 manifest store/route 测试稳定 fail-closed 为 `409 INDEX_REBUILD_REQUIRED`，不将旧 anchors 交给前端。
4. 浏览器在手动加载完分页后，v1/v2 的 cards 与 anchorCount 均与 API 汇总一致；点击证据显示标题和第三页块只到真实 anchor，不再错误跳转 `#0`。
5. 本轮只读 GET、浏览器点击/滚动和隔离测试；没有执行 manifest rebuild 或任何 Qdrant/embedding/下载/原件写入。

## 5. 风险与阻塞

- **运行时验收阻塞：无。** 请求的 API、版本门禁、分页、浏览器完整 anchors 和双向定位均有通过证据。
- **需主 Agent 收口的证据差异：** 既有 `sparse-anchor-backend-report.md` 的离线 v2 bundle 记录 497 条 anchors，而当前 live v2 inspection `total.anchors=460`；当前 live 状态仍自洽（290/308 mapped、18 unresolved，分页无重复），本 tester 不擅自判断哪一个是权威，也未执行重建。Task06E-E 应在 fingerprint 门禁下解释/复核该差异后再决定是否重建 manifest。
- **流程边界：** 本报告不授予真实 Qdrant Collection 切换、删除或全库收口资格；这些动作仍属于 Task06E-E/Task07 的独立门禁。

## 6. 主 Agent 后续动作

1. 保留本报告和进度日志作为 Task06E-D 运行证据。
2. 复核 live v2 `460` 与离线报告 `497` 的 fingerprint/manifest 生成差异；未解释前不要把两者混写成同一事实。
3. 按 Task06E-E 的受控门禁决定是否执行单文档 manifest rebuild；继续保持 Qdrant/原件/metadata 零写入约束，直至证据闭合。

## 7. 时间与工具统计

- 开始：2026-09-10 约 20:45（Asia/Shanghai）
- 结束：2026-09-10 20:56（Asia/Shanghai）
- 总耗时：约 11 分钟
- 模型：临时 Luna xhigh
- token 统计：当前工具环境未提供可靠精确值
- 工具统计：约 25 次只读命令/浏览器状态、点击、滚动与定向验证调用
