# Spec043 Task04 前端集中复审报告

## 范围与复审方式

- 角色：`frontend-reviewer`；日期：2026-10-20。
- 只读核对：`frontend/literature-maps.js`、`frontend/literature-maps.css`、`frontend/index.html`，`tests/frontend/test_frontend_literature_map_expansion.py`、既有前端契约测试与 `literature_map_component.html` fixture，以及 Task04 扩展/恢复计划、增量合同和前端交接报告。
- 未修改业务代码、测试代码或 fixture；未运行后端 pytest、全量回归、真实 provider、部署或提交。
- 按要求用提升权限运行精准 Chromium 测试；fixture 是 mock API，只验证 DOM/API 接线，不是生产 API E2E。

## 结论

**GO（前端 Task04 窄范围）**。本轮独立复审确认 indexed+tombstone 恢复缺口已修复；提升权限真实 Chromium 精准套件 `8 passed`、无 skip，既有地图可行性回归 `3 passed`。未发现 P0/P1。仍不替代生产 API E2E、后端验收或部署验证。

### 初审结果修正（按主会话合同裁定，不计为缺陷）

- 初审 `6 passed、2 failed` 的 partial stop 失败已撤回：Task03 冻结合同将 `partial/failed/stopped/completed` 视为终态，stop 为 no-op；当前 `renderJobActions()` 隐藏终态 stop、仅显示 retryable retry 是正确行为。修正后的 fixture 明确覆盖 `partial → retry` 与 `running → stop → retry`。
- 初审 remove 后隐藏 references/citations 的失败已撤回：墓碑在显式 restore 前不属于可扩展节点，节点归属门禁要求先恢复再扩展；当前测试已改为断言移除后无 references，点击“显式恢复”后再进入 references preview。

### P1-3 修复复审：indexed+tombstone 同时保留文档入口与显式恢复

- 修复位置：`frontend/literature-maps.js:1679-1715`。
- 当前逻辑先计算 `indexed` 与 `removed`；indexed 节点保留“已加入知识库/在知识库中查看”，removed/tombstone 无论是否 indexed 均追加“显式恢复”；仅未移除且未 indexed 时显示“加入知识库/移出地图”。恢复后 `removed=false`，references/citations 入口重新出现。
- 动态覆盖：fixture `?indexed-tombstone` 将 indexed `node-b` 标为 tombstone；测试断言不显示重复 import、同时显示 KB 导航和显式恢复，点击恢复后再点击 references 并打开 preview。
- 结果：提升权限 Chromium 通过；restore 请求仍携带当前 `map_id`、`node_id`、`expected_revision` 与幂等键，未发现 owner/间接 map ID 回归。

## 已核对通过项

- 预览/确认合同：`openPreview()` 使用当前服务端 `map_id`，对 map/node/preview ID 做 URL 编码；POST body 包含 `kind`、必要的 `node_id`、topic 的 `query` 和幂等键。GET 候选来自服务端；apply 使用 `expected_revision`、服务端 `candidate_id` 和幂等键，不把客户端 paper 快照当身份。
- refresh 空选择：有差异时允许 `selected_candidate_ids: []` 并显示“确认刷新”，不会伪造新增节点；无差异时不显示确认按钮，并明确显示“没有字段或关系差异；地图无需更新。”。
- owner/间接 map ID：所有预览、apply、job、node remove/restore 请求均从当前 `state.map.map_id` 构造路径并 `encodeURIComponent`；异步回写同时校验 `selectedMapId`、map ID、active 状态与请求代次，未发现可由节点/候选字段绕过地图范围的前端路径。服务端 owner 校验不由本报告替代。
- async 竞态：`previewRequest`、`previewPollGeneration`、`jobActionRequest`、`nodeActionRequest` 与既有 graph/map/job/view/node/import 门禁覆盖切图、离开视图和旧 preview/job 回调；409 apply 只展示冲突并提供“重新读取并预览”，没有自动重放或覆盖用户变化。
- 容量：前端常量为每批 20、地图 200；勾选时按当前 graph 数量阻止超额，apply 按同一规则禁用。服务端事务复核仍是最终边界，不能把前端按钮当安全校验。
- indexed 正常路径：普通 indexed 节点不渲染“加入知识库”，显示 document ID，并复用既有 `window.jumpToKnowledgeBase(documentId)` 或 `[data-view="kb"]` 导航；fixture 对重复 import 禁用和导航入口有覆盖。
- XSS/资源：`literature-maps.js` 无 `innerHTML`/动态 HTML 拼接，动态文本使用 `textContent`/DOM API；原文 URL 仅接受 `http:`/`https:` 且拒绝凭据和 `javascript:`。`frontend/index.html` 与 fixture/契约均同步使用 `literature-maps.js?v=6`、`literature-maps.css?v=4`。

### 最新真实 refresh diff formatter 窄复审（2026-10-20）

- 以交接报告、增量合同补记及 `api-evidence.json` 的真实 producer shape 为准：`preview.diff` 是数组，数组项为 `{node_id, changes}`；字段变化使用 `{from,to}`，关系变化使用 `{added,removed}`，不是 `diff.metadata`，也不是展示字符串。
- 当前 formatter 按 `node_id` 从当前 graph 解析论文标题并保留 ID；字段映射为中文，逐项显示 `from → to`；关系分别显示新增/移除；`null`、空字符串、空列表和缺失键分别输出 `null`、`空字符串`、`空列表`、`字段缺失`。旧 object diff 仍有兼容 fallback，不影响真实数组 shape。
- 差异值经 `createElement(...).textContent` 写入，没有 `innerHTML`/`insertAdjacentHTML`/`outerHTML`/`eval`；XSS fixture 的 `<img src=x onerror=alert(1)>` 只作为文本显示，DOM 中无 `img[onerror]`。无差异 refresh 明确显示无需更新且不渲染确认按钮。
- 资源版本已同步为 `literature-maps.js?v=6`；fixture 使用同一真实 shape，8 项差异覆盖字段前后值、关系增减、XSS、null/empty/missing 语义。
- 本次独立提升权限 Chromium 精准复跑 `8 passed`、无 skip；既有地图可行性复跑 `3 passed`。未发现 P0/P1/P2；GO 仍仅适用于前端 fixture 契约，不外推生产 API E2E 或部署结果。

## 验证记录

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py`（提升权限、真实 Chromium） | 退出码 0；`8 passed`；无 skip，包含 partial/retry、running/stop/retry、先 restore 后 references、indexed+tombstone |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_feasibility.py`（提升权限、真实 Chromium） | 退出码 0；`3 passed`；既有地图交互回归通过 |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0；`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；未发现 spec/task 编号测试名 |
| `git diff --check -- frontend tests/frontend` | 退出码 0 |
| `rg innerHTML/insertAdjacentHTML/outerHTML/eval frontend/literature-maps.js` | 无命中 |

## 交接与下一步

- 当前 verdict：**GO（前端窄范围）**；partial 终态 stop 与未恢复墓碑禁扩展均按冻结合同通过，indexed+tombstone 修复及回归通过。
- 不得将本 fixture GO 外推为生产 API E2E；主会话仍需完成真实 preview→apply/refresh/stop-retry/remove-restore/reopen 证据及部署门禁。
- 本报告不启动暂停中的 8000 服务。

复审进度日志：`.codebuddy/agent-logs/spec-043/task-04/frontend-reviewer/20261020-023607.md`
