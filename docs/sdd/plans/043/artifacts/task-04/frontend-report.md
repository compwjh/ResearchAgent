# Spec043 Task04 前端交接报告

## 状态

**前端实现可交独立复审（PASS_WITH_LIMITATIONS）**。Task04 的扩展/刷新/恢复 UI 与冻结增量合同已接线；复审发现的 P1 前端问题已修复，并由授权真实 Chromium 精准套件复跑通过。仍未启动生产服务、未调用真实 provider、未运行后端 pytest，也未提交代码。

## 实际改动

- `frontend/literature-maps.js`
  - 增加“继续搜索”“刷新预览”、预览状态持久化/重开、候选列表和服务端候选 ID 提交。
  - 显示已有节点、移除墓碑、新候选和 20/200 容量；已有节点禁选，墓碑只提供显式恢复，不把客户端数据当成候选身份。
  - 增加 refresh 字段/关系差异展示与“确认刷新”路径；刷新允许空 `selected_candidate_ids` 仅提交服务端差异，不虚构新增节点。
  - apply 使用 `expected_revision` 与幂等 key；409 只提示重新读取并预览，不自动覆盖或重放。
  - 增加停止/可重试失败单元入口、partial/限流/空候选提示、请求代次与地图 ID 守卫，避免旧 preview/job 回写当前地图。
  - 增加 remove/explicit restore；indexed 节点显示真实 `document_id` 与已有知识库导航，不再显示重复“加入知识库”按钮；import 仍提交空 payload，身份由服务端节点决定。
  - 所有动态文本继续使用 DOM API/textContent；模块无 `innerHTML`。
- `frontend/literature-maps.css`：增加预览、候选、差异、job 操作和已入库文档状态的 scoped 样式。
- `frontend/index.html`：地图资源版本升至 `literature-maps.js?v=5`、`literature-maps.css?v=4`。
- `tests/frontend/fixtures/literature_map_component.html`：扩展显式 mock API fixture，覆盖 preview/apply、refresh 空选择、CAS 409、stop/retry、墓碑恢复和 indexed 文档入口；fixture 不作为生产证据。
- `tests/frontend/test_frontend_literature_map_expansion.py`：新增能力命名契约/组件测试，断言 preview kind/node/query、候选禁选、容量、refresh 空选择、CAS 不自动重放、停止/有限重试、墓碑恢复及 indexed 不重复 import。
- `tests/frontend/test_frontend_literature_map_contract.py`：同步资源版本断言。

## 与冻结合同的核对

- `POST /previews` body 按 `kind`、必要 `node_id`、topic 默认 `map.topic`、`idempotency_key` 构造；不接受客户端任意 paper/source 快照。
- `GET /previews/{preview_id}` 的 `candidates/diff/warnings/job` 仅由服务端响应渲染；候选 `candidate_id` 原样作为本预览句柄提交。
- 新候选 apply 最多 20 个并显示地图 200 容量；refresh 差异使用空选择确认，避免把已有节点误当新增候选。
- apply/remove/restore 均携带当前地图 `expected_revision` 与幂等 key；409、部分失败、限流和空结果均有明确下一步。
- stop/retry 只由服务端 job 状态和 retryable 单元控制；成功结果不自动重抓，离开地图/切图/关闭视图会停止前端轮询。
- 预览 session 按 map ID 写入 `sessionStorage`，重开地图读取持久 preview/job；异步响应同时检查 request generation、selected map 和 active 状态。

## 验证记录

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py` | 退出码 0；4 passed、4 skipped；skip 为 Chromium 在宿主启动时的 `MachPortRendezvousServer`/`TargetClosedError` 权限阻塞，不计成功 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_feasibility.py` | 退出码 0；3 passed；未改写 tracked evidence |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0；`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；未发现 spec/task 编号测试名 |
| `git diff --check -- frontend tests/frontend` | 退出码 0 |
| 新增 CSS/JS class 对照及 `rg innerHTML frontend/literature-maps.js` | 通过；新增类均有 scoped CSS，模块无 `innerHTML` |

## 未验证、限制与下一步

- 当前没有真实生产 API/Chromium E2E；mock fixture 只证明 DOM/API 接线，不能替代真实 preview→apply、refresh、stop/retry、remove/restore 或重启恢复验收。
- 未启动暂停中的 8000 服务，未调用真实 provider，未下载文件，未运行后端 pytest；由 backend-reviewer/backend-tester 和主会话负责后端/真实 API 门禁。
- 移除候选的显式恢复按钮要求服务端候选携带已验证的 `node_id` 或 `existing_node_id`；若缺失，前端只显示“需显式恢复”而不会把 `candidate_id` 冒充节点 ID，避免误恢复。
- “在知识库中查看”只复用现有 `window.jumpToKnowledgeBase` 或既有 KB 导航，不创建新的文档查看器；真实 indexed 文档导航需在生产浏览器确认。
- 下一步：独立 frontend-reviewer 复核当前 diff 与 DOM/XSS/版本门禁；服务可用后由主会话复用既有真实地图完成 Task04 生产 preview/apply/恢复案例。

## 交接产物

- 本报告：`docs/sdd/plans/043/artifacts/task-04/frontend-report.md`
- 前端开发日志：`.codebuddy/agent-logs/spec-043/task-04/frontend-dev/20261019-230252.md`
- 组件 fixture：`tests/frontend/fixtures/literature_map_component.html`

## 复审修复追加（2026-10-20）

- 修复 indexed+tombstone 分支优先级：已入库墓碑同时显示真实 document ID/“在知识库中查看”和“显式恢复”；恢复前不显示 references/citations，恢复后才重新提供扩展入口，保持“显式恢复才清墓碑”。fixture 新增 `?indexed-tombstone` 场景并验证查看不触发 import、恢复请求可达、恢复后可继续打开 references 预览。
- 修正复审测试预期而未放宽业务边界：`partial` 是终态，停止入口保持隐藏，仅对 retryable failed units 显示“重试失败单元”；新增 `?running` fixture 验证 running 才显示停止入口，停止后保留成果并可重试。墓碑测试先断言恢复前不可扩展，点击显式恢复后再验证 references 预览。

### 授权 Chromium 复跑

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py`（`require_escalated`） | 退出码 0；8 passed；无 skip（含 indexed+tombstone 恢复后 references 手势） |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_feasibility.py`（`require_escalated`） | 退出码 0；3 passed |
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python scripts/check_test_layout.py` / `check_test_naming.py` | 均退出码 0 |
| `git diff --check -- frontend tests/frontend` | 退出码 0 |

本追加仍只涉及前端组件、fixture、前端精准测试和交接文档；backend、部署、真实 provider 与提交均未改动。等待独立 frontend-reviewer 复核后再裁定 Task04 前端窄验收。

## 真实 refresh diff formatter 修复追加（2026-10-20）

### 生产者 shape 交接片段（供主会话补入 `interface-contract.md`）

本轮不修改公共接口，只冻结真实 API tester 已落盘的字段形状：

```json
{
  "diff": [
    {"node_id": "21041260a5394f42891b020128fa60fa", "changes": {"citation_count": {"from": 29000, "to": 29014}}},
    {"node_id": "...", "changes": {"relations": {"added": ["identity-key"], "removed": []}}}
  ]
}
```

`diff` 是数组；每项以服务端 `node_id` 标识论文，`changes` 的键是字段名。字段值通常是 `{from,to}`；关系差异使用 `{added,removed}` 数组。`null`、空字符串、空数组和缺失键均有不同含义，前端不能把对象整体降级为“未提供”。

### 实际改动

- `frontend/literature-maps.js` 新增安全 diff formatter：优先显示图中论文标题并保留 node ID；字段名映射为中文；显示 citation `from → to`；关系 added/removed 显示可读内容；`null`、空字符串、空列表、缺字段分别标记。
- `frontend/index.html` 与组件 fixture 的地图脚本资源版本同步升至 `literature-maps.js?v=6`，避免生产浏览器继续使用旧 formatter 缓存。
- 仍只通过 `textContent`/DOM API 写入，`<img ...>` 等差异值按纯文本显示，不生成 HTML；refresh 无差异时显示“没有字段或关系差异；地图无需更新。”。
- `tests/frontend/fixtures/literature_map_component.html` 使用上述真实对象 shape，加入 8 项差异、citation 实值、关系增减、XSS 文本、null/空/缺失和无差异场景。
- `tests/frontend/test_frontend_literature_map_expansion.py` 增加 8 项可见性、XSS 无执行/无 `img[onerror]`、关系与空值语义、无差异提示断言。

### 定向验证

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py`（授权 Chromium） | 退出码 0；8 passed；无 skip |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0；`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `git diff --check -- frontend tests/frontend` | 退出码 0 |

本轮只改前端组件、fixture、精准测试和本交接报告；未修改 backend、公共接口、部署、环境或提交。生产浏览器报告中的 refresh P1 已有最小修复，待独立 frontend-reviewer 复审。

## 服务器持久预览重开追加（2026-10-20）

### 实际改动

- `frontend/literature-maps.js` 增加可见的“打开上次预览”入口。地图切换后先读取现有 `sessionStorage` 快路径；无本地状态时仅通过 `GET /{map_id}/events?after_seq=0` 找到 `preview_queued/preview_completed` 事件，再 `GET /{map_id}/jobs/{job_id}` 读取服务端 `cursor.preview_id`，只显示入口，不自动创建或触发 provider。
- 打开入口后仅 `GET /{map_id}/previews/{preview_id}` 恢复候选/差异；关闭预览会递增请求代次、停止轮询并清空当前面板，但保留入口以便再次只读打开。地图 ID、map request generation、preview request generation 和 active 状态均设守卫，迟到的旧地图/旧预览响应不会重开或写入当前面板。
- 事件恢复只筛选 `preview_*` 事件，最新 `restore` 作业不会遮蔽此前可恢复的 preview；已应用/冲突等旧 preview 仍按服务端状态只读展示。地图资源版本同步为 `literature-maps.js?v=7`、`literature-maps.css?v=5`，确保关闭态样式不被缓存旧资源覆盖。
- fixture 新增无 sessionStorage 的服务端事件→job cursor→preview 链路、latest restore 伴随事件、延迟关闭、切图竞态和 GET-only 请求日志；新增的差异断言仍使用真实 shape 中的 citation 值与关系字段。预览面板补充 `[hidden]` scoped 规则，避免通用 `display:grid` 覆盖关闭态。

### 定向验证

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py`（授权 Chromium） | 退出码 0；10 passed；无 skip。覆盖无存储重开、latest restore 不遮蔽、迟到响应关闭守卫、切图竞态和无 POST 请求 |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0；`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `git diff --check -- frontend/literature-maps.js frontend/literature-maps.css frontend/index.html tests/frontend` | 退出码 0 |

本追加只涉及前端组件、scoped CSS、fixture、精准测试和报告；未修改 backend、公共接口、部署、环境、真实 provider 或提交。组件 fixture 不是生产 E2E 证据，仍需独立 frontend-reviewer 复核及主会话真实浏览器验收。

## 持久预览事件分页 P1 修复追加（2026-10-20）

### 实际改动

- `discoverPersistedPreview()` 现在从 `after_seq=0` 开始，按服务端 `next_cursor` 严格递增读取既有事件页，直到收到空页；跨页汇总 `preview_*` 事件后，再按最新事件读取 `GET /{map_id}/jobs/{job_id}` 的 `cursor.preview_id`。没有新增接口或历史管理。
- 对非整数、未前进或倒退的游标立即终止，最多读取 50 页；异常或达到上限均显示明确的中文状态，不静默宣称“没有上次预览”。空页是正常终止条件。
- 每页以及 job 解析都复用地图 ID、map request generation 和 active 守卫；切图/停用视图时放弃迟到页，不创建 preview、不触发 provider。旧 job 解析失败会继续尝试更早的 preview 事件。
- fixture 增加真实分页形状：首页 200 个事件、第二页在 event 201+ 才出现 preview 并伴随最新 restore 作业、第三次读取为空；另覆盖游标停滞、停用中断、切图竞态和 GET-only 请求日志。

### 定向验证

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py`（授权 Chromium） | 退出码 0；13 passed；无 skip。覆盖 >200 事件分页至空页、latest restore、异常游标不循环、停用/切图中断和无 POST/provider |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0；`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `git diff --check -- frontend/literature-maps.js tests/frontend docs/sdd/plans/043/artifacts/task-04/frontend-report.md` | 退出码 0 |

本追加仍只涉及前端组件、fixture、精准测试和交接文档；未修改 backend、公共接口、部署、环境、真实 provider 或提交。分页 fixture 不是生产 E2E 证据，需独立复审及主会话真实浏览器验收。
