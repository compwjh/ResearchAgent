# Task04 production browser E2E

- **Run:** `task04-browser-e2e-20261020-refresh-r1`
- **Runtime:** real Google Chrome through CUA/Playwright, `http://127.0.0.1:8000/#literature-maps-view`
- **Candidate:** local commit `a54c119` (as supplied by the parent handoff); no code, test, deploy, or environment changes in this run.
- **Map reused:** `0baabeae7268429c9f7e4de8098ae1d0` (`API E2E graph attention networks r2`); no second map was created.
- **Provider budget:** reused the API tester's persisted references preview and refresh cache. After coordination, exactly one UI `刷新预览` request was sent; no retry or second provider request was issued.

## Verified browser paths

### Existing indexed document

1. Opened the 文献地图 entry and selected `API E2E graph attention networks r2`.
2. Activated the real `Graph Attention Networks` node with keyboard Enter (the SVG node responds reliably to Enter; a pointer click did not change the first selection in this browser run).
3. The right detail panel showed `indexed`, `已加入知识库 · 文档 ID：55afc3b8f01445429462fe78ed0d4c98`, and the button `在知识库中查看`.
4. Clicked that existing-document button once. The real knowledge-base view showed `2017-Conference-Graph-Attention-Networks.pdf`, `已索引`, and `v1 已索引 · 57 片段`; no import/download POST was made. Returned to 文献地图 through the main navigation.

**Result: PASS.** The persistent document ID and existing KB navigation are visible; no duplicate import affordance is exposed for this indexed node.

### Remove → explicit restore

- Selected the non-indexed `How Attentive are Graph Attention Networks?` node.
- `移出地图` changed the detail panel to only `显式恢复`; references/citations were not exposed while the tombstone was active, and the graph relation count temporarily dropped from 18 to 13.
- Clicking `显式恢复` returned the normal detail actions (`加入知识库`, `移出地图`, `参考文献`, `引用它的论文`), restored the 18 relations, and left the graph at 21 nodes.

**Result: PASS.** The operation was reversible and did not touch the indexed GAT document. SQLite read-only verification after the run retained the saved viewport `{x: 10, y: 20, scale: 1.1}`.

### One real refresh preview and apply

The existing API evidence recorded refresh preview `803a6aaefca740408d6296c23bbab8c7` (`completed`, base revision 3, 8 metadata diffs, warnings `SEMANTIC_SCHOLAR_INVALID_RESPONSE` and `SEMANTIC_SCHOLAR_RATE_LIMITED`). The browser could not expose that server preview in a new tab because the production UI has no preview-id route; it was read once through the real GET endpoint without mutation. Following the API tester coordination, I then used the visible `刷新预览` action exactly once. The resulting persisted preview was `ca1321d899eb4d6ca0ecdb3946a3a31b` (base revision 8, completed job `ac07705650474bac852f4add08a81410`, provider request count 7), and it was applied once.

Observed production UI:

- queued state: `预览状态：排队中，候选仍在读取。`
- terminal state: `预览状态：已完成`
- warning preserved: `SEMANTIC_SCHOLAR_INVALID_RESPONSE`
- capacity: `已选择 0/20；地图容量 21/200（还可加入 179）`
- all 21 returned candidates were marked `已在当前地图` with disabled checkboxes; no candidate was falsely selectable or added.
- the visible `确认刷新` action was enabled. Clicking it succeeded without a CAS conflict; the map remained 21 nodes / 18 relations and the indexed document ID remained unchanged. The UI status was `已确认加入，新增节点正在保存；原有布局不会被重排。`

**Result: PASS with a P1 UI defect below.** Refresh apply preserved graph size, relation count, saved layout, and document association. The inherited map remains explicitly partial/provider-limited; that is not attributed to this frontend run.

## P1 found: refresh diff values are lost in the production panel

The real refresh response contained concrete changes (for example GAT citation count `29000 → 29014`, plus seven other node changes). The production panel rendered `字段变更` followed by eight identical `未提供` bullets. The warning and candidate rows were visible, but none of the actual node IDs, fields, or from/to values was exposed to the user.

Minimal frontend fix recommendation: render the object-shaped diff entries (`{node_id, changes}`) as a safe node/title label plus each changed field's `from → to` value. Do not stringify untrusted metadata into HTML. Current rendering reaches `metadataText(entry)` in `frontend/literature-maps.js` and the helper falls back to `未提供` for this object shape.

This blocks a user from reviewing what a refresh would change, although the CAS/apply path itself completed correctly. No backend change is requested by this report.

## Not independently verified in the production panel

- The API tester's references preview `7fda3c448a7a4274be866ade62c39b19` was already applied before this browser run. The current UI has no visible persisted-preview list or preview-id route, so I did not create a duplicate `继续搜索` request merely to reproduce an already completed candidate panel.
- The API tester's stale refresh apply returned HTTP 409 without a write. This browser run applied a fresh preview successfully and therefore did not manufacture a second stale conflict. The UI 409 copy (`地图版本已变化；未自动覆盖你的操作，请重新读取后再次预览。`) remains covered by the component/fixture contract, but not by this production click path.
- The map/job still displayed the expected partial/degraded state and preserved the actionable provider warning; no retry or stop action was invoked on a terminal refresh.

## Screenshots

Two key screenshots were captured inline by the real CUA browser during this run:

1. Indexed GAT detail with the 21-node graph and `indexed` badge/document state (capture immediately before the refresh panel run).
2. Refresh preview panel showing `已完成`, the preserved warning, 21/200 capacity, all candidates disabled as already present, and the eight incorrect `未提供` diff bullets.

The CUA screenshot API returned inline image bytes but did not expose a writable local path; this report deliberately does not invent a screenshot filename. The second capture is the direct visual evidence for the P1 above.

## Verdict

**BLOCKED / P1.** Real Chrome verified indexed-document navigation, tombstone restore, refresh queue→completed→confirm, capacity/duplicate suppression, provider warning visibility, and layout/document preservation. Task04 frontend is not clear for user acceptance until refresh diff values are rendered instead of eight `未提供` placeholders. No code or deployment was changed by this tester.

## 3a99d5f narrow rerun: persisted refresh preview / indexed document (2026-10-20)

- **Run:** `task04-browser-e2e-20261020-refresh-r2`
- **Runtime:** real Google Chrome through CUA/Playwright, `http://127.0.0.1:8000/#literature-maps-view`
- **Candidate:** local commit `3a99d5f`; no code, test, deploy, environment, provider, import, or apply changes in this run.
- **Map reused:** `0baabeae7268429c9f7e4de8098ae1d0` (`API E2E graph attention networks r2`); the map list exposed `2/2` maps and this exact `data-map-id` was selected.
- **Request guard:** did not click `刷新预览`, `确认刷新`, `继续搜索`, import, download, stop, retry, remove, or restore. No new preview/provider call was initiated.

### Verified in the deployed UI

- The map reopened with `21 个节点 · 18 条关系 · 已完成 · 阶段：apply` and visible status `地图部分完成；已保留可用节点并标注失败阶段。` Both `引用关系` and `主题相似` layers remained enabled; the canvas legend still showed solid citation arrows and dashed similarity lines.
- The real node `21041260a5394f42891b020128fa60fa` (`Graph Attention Networks`) was activated with keyboard Enter. The detail panel showed `indexed`, citation count `29000`, and `已加入知识库 · 文档 ID：55afc3b8f01445429462fe78ed0d4c98`.
- The existing `在知识库中查看` action was clicked once. The knowledge-base view showed `2017-Conference-Graph-Attention-Networks.pdf`, `已索引`, `v1 已索引 · 57 片段`, and `v2 已索引 · 92 片段`; no duplicate import/download action occurred. Returning through the 文献地图 navigation preserved the same map state.
- A real Chrome screenshot was captured inline after returning to the map with the indexed GAT detail, 21-node/18-edge header, layer controls, and graph visible. CUA returned image bytes only; no invented filesystem screenshot path is recorded.

### Persisted refresh preview limitation

The current production UI exposes only `刷新预览`; it has no visible saved-preview list, preview ID route, or “reopen existing preview” control. After reopening the map in a fresh Chrome tab, the preview panel was empty and no persisted preview ID was visible. Because the requested guard forbids creating another preview or injecting fake state, this run could not reach the already-completed 8-diff panel.

Therefore the following are **not independently re-verified in this run**: the eight real diff rows, Chinese field labels, node titles/IDs, and concrete `from → to` values. The prior API artifact still records the real refresh preview `803a6aaefca740408d6296c23bbab8c7` with `diff_count=8`, including GAT `29000 → 29014`; the new v6 formatter remains covered by the authorized Chromium fixture suite, but this production run cannot claim that panel as visible without a supported reopen path.

### Verdict

**BLOCKED / production recheck incomplete (no new frontend defect proven).** Indexed document association/navigation, map counts, partial status, layer state, and non-mutating reopen behavior pass on `3a99d5f`. The requested real 8-diff visual check is blocked by the production UI's missing saved-preview reopen entry; no duplicate preview or external call was made. This is a product verifiability limitation, not a new backend or frontend code change in this run.

## abcad3a narrow rerun: server-persisted preview restored in a fresh Chrome session (2026-10-20)

- **Run:** `task04-browser-e2e-20261020-refresh-r3`
- **Runtime:** real Google Chrome through CUA/Playwright, `http://127.0.0.1:8000/#literature-maps-view` (ready endpoint was reported 200 by the deployment handoff).
- **Candidate:** local commit `abcad3a` (JSv7/CSSv5); no code, test, deploy, environment, provider, import, or apply changes in this run.
- **Fresh-session guard:** opened a new Chrome tab (`325738138`) and did not write, clear, or inject `sessionStorage` or any other browser state.
- **Map reused:** `0baabeae7268429c9f7e4de8098ae1d0` (`API E2E graph attention networks r2`); no second map was created.

### Verified production UI

1. Selected the map by its real `data-map-id`. The map header remained `21 个节点 · 18 条关系 · 已完成 · 阶段：apply`; the graph legend still showed solid citation arrows and dashed similarity lines. The existing provider degradation remained visibly labelled `部分完成` / `SEMANTIC_SCHOLAR_INVALID_RESPONSE`.
2. Clicked the visible `打开上次预览` entry. The UI first showed `正在读取上次预览…`, then restored the persisted `刷新预览预览` without exposing a new create/confirm action.
3. The restored panel rendered eight real diff rows with Chinese field labels, node titles/IDs, and concrete values. The first row was `论文《Graph Attention Networks》（21041260a5394f42891b020128fa60fa）：引用数：29000 → 29014`; the eighth was `Predicting multicellular function through multi-layer tissue networks ... 引用数：null → 605`. The other six rows likewise exposed actual title, node ID, field, and `from → to` values rather than `未提供`.
4. Capacity and duplicate suppression remained real: `已选择 0/20；地图容量 21/200（还可加入 179）`; existing candidates showed disabled checkboxes and `已在当前地图`.
5. Closed the read-only preview and activated the real GAT SVG node with keyboard Enter. The detail panel showed `已加入知识库 · 文档 ID：55afc3b8f01445429462fe78ed0d4c98` and the existing `在知识库中查看` button. No duplicate import/download was offered or invoked.

### Mutation and evidence boundary

- This run only selected the existing map, opened the persisted preview, closed that read-only panel, and opened an existing node detail. It did not click `刷新预览`, `继续搜索`, `确认刷新`, import/download, stop, retry, remove, or restore; therefore no new preview/provider call or apply was initiated by this browser run.
- The inline CUA action restored the server-backed record in a new tab without browser storage injection. The browser diagnostic surface exposed console logs but not HTTP-method traces; the GET-only conclusion here is limited to the read-only restore path and the absence of any mutation action, rather than an invented network-log claim.
- One key preview screenshot was captured inline by CUA after scrolling the restored panel into view. The tool returned image bytes only, so no fake filesystem screenshot path is recorded.

### Verdict

**PASS for the frontend persisted-preview reopen path.** The fresh-session UI recovered the real saved preview and displayed all eight real diffs with safe, readable values; the graph remained 21 nodes / 18 relations and the indexed document association persisted. The inherited `SEMANTIC_SCHOLAR_INVALID_RESPONSE` warning remains an explicit backend/provider degradation and is not a frontend regression in this run.

## 9be1707 real refresh apply rerun (2026-10-20)

- **Run:** `task04-browser-e2e-20261020-refresh-r4`
- **Runtime:** real Google Chrome through CUA/Playwright, `http://127.0.0.1:8000/#literature-maps-view`; the deployment handoff reported `/api/ready` HTTP 200.
- **Candidate:** local commit `9be1707`; no code, test, deploy, environment, import, download, or new-preview changes in this run.
- **Map reused:** `0baabeae7268429c9f7e4de8098ae1d0` (`API E2E graph attention networks r2`); no second map was created.
- **Preview supplied by backend tester:** `3e1c582efb704b188599e8ef805f8dda`, job `0ff677c2560e4ad5b40e4eb2371987e3`, `base_revision=8`; it was already completed before the browser run and was not recreated.

### Browser evidence

1. Selected the existing map by its real `data-map-id`; the UI showed `21 个节点 · 18 条关系 · 已完成 · 阶段：preview`, with both citation and similarity layers enabled.
2. Clicked the visible `打开上次预览` entry. The restored production panel showed `预览状态：已完成`, the preserved `SEMANTIC_SCHOLAR_INVALID_RESPONSE` warning, all eight real diffs, and `已选择 0/20；地图容量 21/200（还可加入 179）`. The visible rows included GAT `引用数：29000 → 29014`, AASIST `674 → 676`, IoT `76 → 77`, and the remaining five real node/title/ID changes, including `null → 605` for the final node. Existing candidates remained disabled as `已在当前地图`.
3. Captured one inline CUA screenshot after scrolling the real preview panel into view. The tool returned image bytes only; no filesystem screenshot path is invented.
4. With zero candidates selected, clicked `确认刷新` exactly once. No `刷新预览`, `继续搜索`, import, download, stop, retry, remove, restore, pan, zoom, or layout-save action was invoked.
5. After the apply, closed the preview and activated the real GAT SVG node with keyboard Enter. The detail panel showed citation count `29014`, `indexed`, and `已加入知识库 · 文档 ID：55afc3b8f01445429462fe78ed0d4c98`.

### Read-only server verification after the browser confirmation

The host-permission, read-only API checks confirmed the mutation result without replaying it:

- `GET /previews/3e1c582efb704b188599e8ef805f8dda` returned `status=applied`, `base_revision=8`, and the persisted eight-item diff.
- `GET /jobs/1dc9a2492fdb432491be82efefc3ce46` returned `operation=preview_apply`, `status=completed`, `cursor.preview_id=3e1c582efb704b188599e8ef805f8dda`, and counts `added_count=0`, `updated_count=8`, `relation_count=4`.
- `GET /0baabeae7268429c9f7e4de8098ae1d0` returned `revision=9` and `latest_job=1dc9a2492fdb432491be82efefc3ce46`.
- `GET /0ba.../graph` returned `revision=9`, 21 nodes, 18 edges; the persisted GAT node was `citation_count=29014`, `document_id=55afc3b8f01445429462fe78ed0d4c98`, `download_status=indexed`, and position `{x:120,y:80}`. The saved viewport remained `{x:10,y:20,scale:1.1}`.

The browser-visible status remained on the transient `已提交确认，地图正在保存新增结果` copy during the short polling window, but the subsequent real node detail GET and the server job/map GETs showed the completed apply and updated citation. The apply POST body and generated idempotency key were not exposed by CUA's diagnostic surface; this report does not invent them. The empty-selection semantics are independently evidenced by `added_count=0` and `updated_count=8` in the completed server job.

### Verdict

**PASS.** Real Chrome restored the backend-supplied preview, displayed its actual diff values, and performed one empty-selection confirmation. The server persisted revision 9 and eight metadata updates; the GAT UI/graph now reports the real citation change `29000 → 29014`, while the indexed document and saved layout remain intact. The inherited `SEMANTIC_SCHOLAR_INVALID_RESPONSE` warning remains explicit and is not misreported as full provider success.
