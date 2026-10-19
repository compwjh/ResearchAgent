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
