# BLOCKED — Task04 real API E2E

## API E2E artifact

- Spec: `043-literature-map-topic-exploration`
- Task: `task-04-expansion-recovery`
- Run ID: `task04-api-e2e-20261019T184828Z-r1`
- Runtime: `http://127.0.0.1:8000`, revision `a54c119`; `/api/ready` returned HTTP 200.
- Evidence JSON: [api-evidence.json](./api-evidence.json)
- No code, deployment, PDF download, direct provider URL, or KB import was performed by this run.
- Existing map reused: `0baabeae7268429c9f7e4de8098ae1d0`; no second map was created.

The baseline map GET and graph GET both returned HTTP 200. Before this run the map was `partial`, revision 2, with 20 nodes and 17 edges (12 citation, 5 similarity); the source node was GAT `21041260a5394f42891b020128fa60fa` with arXiv `1710.10903`, DOI `10.17863/cam.48429`, and Semantic Scholar ID `33998aff64ce51df8dee45989cdca4b6b1329ec4`.

### References preview → candidate confirmation

One real request created a references preview for the existing GAT node:

```http
POST /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/previews
Content-Type: application/json
```

```json
{"kind":"references","node_id":"21041260a5394f42891b020128fa60fa","idempotency_key":"task04-api-e2e-20261020-gat-references-r1"}
```

It returned HTTP 202 with preview `7fda3c448a7a4274be866ade62c39b19` and job `debcc085663044c9be0755da2ab0a0da`. A subsequent GET returned HTTP 200 with `status=completed`, 45 real candidates, no warnings, and `provider_request_count=0`; this was a cache-hit path. Candidate `candidate-812a45f9239f2632d20662a0` was a new paper with DOI `10.1093/bioinformatics/btx252`, arXiv `1707.04638`, and Semantic Scholar ID `b7c4570d7d97f327e7f82fe28100172ec5e94cac`.

The one-candidate apply used the preview snapshot and `expected_revision=2`. It returned HTTP 202, revision 3, completed apply job `19cff1e0178c4910990ef249eb22fe56`, and one added node `24e44e61d9d44d1b85918fa8f7362ff0`. Replaying the exact same idempotency key returned HTTP 202 with the same job and node handle; it did not add a second node.

The real node GET returned HTTP 200. The new node retained the server snapshot identity and had no document ID, as expected; it was not imported.

### Refresh preview and read-only guarantee

A single real refresh preview was created with key `task04-api-e2e-20261020-refresh-r1`. It returned HTTP 202 with preview `803a6aaefca740408d6296c23bbab8c7` and job `e6a3cf56ea484f94a348d172c6d83fd4`. After a bounded wait, the preview GET returned HTTP 200 with:

- `status=completed`, 21 candidates, 8 metadata diffs;
- `provider_request_count=8` persisted in the preview job;
- real citation-count diffs including GAT `29000 → 29014`, AASIST `674 → 676`, and the IoT paper `76 → 77`;
- warnings `SEMANTIC_SCHOLAR_INVALID_RESPONSE` and `SEMANTIC_SCHOLAR_RATE_LIMITED`.

The subsequent graph GET remained revision 3 with 21 nodes, 18 edges, viewport `(10,20,1.1)`, and the original GAT position `(120,80)`. Refresh preview did not modify the map. A no-difference refresh case was not separately exercised; the real non-empty diff and the provider warnings are preserved rather than treated as a clean no-op.

### CAS, tombstone, and reopen checks

Applying the refresh snapshot with stale `expected_revision=2` returned the fixed HTTP 409 body:

```json
{"detail":{"code":"MAP_CONFLICT","message":"地图版本或作业状态已变化，请重新读取后重试","retryable":false}}
```

A following graph GET remained revision 3 with 21 nodes and 18 edges, confirming the stale request did not write.

The newly added node was then removed once with revision 3, returning HTTP 200 and revision 4. It was restored once with revision 4, returning HTTP 202, revision 5 in the response, `restored_node_id=24e44e61d9d44d1b85918fa8f7362ff0`, and completed restore job `3a887b86d37a4642b383b7e8ae106bf2`. The final read observed revision 6, 21 nodes, 18 edges, `removed=false` for the restored node, and the latest job `restore/completed`; the intervening revision is recorded without attributing it to a specific actor. The original GAT node still returned document `55afc3b8f01445429462fe78ed0d4c98`, `download_status=indexed`, and position `(120,80)`. No KB document was deleted or created.

## Manual acceptance case (API-backed handoff)

This backend run does not claim production browser labels or processing copy. The frontend reviewer should reuse the recorded map and preview IDs instead of creating another provider job.

1. **Open the existing map**
   - 点击/输入: open `http://127.0.0.1:8000/#literature-maps-view` and select the existing `文献地图` entry for map `0baabeae7268429c9f7e4de8098ae1d0`.
   - 点击后提示: exact Task04 browser label is not verified in this backend run; the API-backed map name is `API E2E graph attention networks r2` and status is `partial`.
   - 等待: wait for the map and graph GETs to return HTTP 200.
   - 等待中显示: preserve the current loading/progress state; do not create a second map or preview.
   - 下一步: open the map and compare the graph with this run’s final counts (21 nodes, 18 edges).
   - 失败恢复: refresh once; if the map or IDs are absent, stop with `MAP_NOT_REDISCOVERABLE` and use this artifact for diagnosis.
2. **Review the saved references preview**
   - 点击/输入: open preview `7fda3c448a7a4274be866ade62c39b19` if the UI exposes the preview panel.
   - 点击后提示: 45 candidates should be available, with the selected one identifiable by candidate ID `candidate-812a45f9239f2632d20662a0`.
   - 等待: wait for preview GET status `completed`; do not submit a second preview.
   - 等待中显示: loading or queued state is acceptable until the persisted preview is returned.
   - 下一步: verify the one added node is present and the graph revision is at least 3.
   - 失败恢复: if the panel reports a stale revision, reread the map and do not replay with a new idempotency key.
3. **Review refresh differences without applying them**
   - 点击/输入: open refresh preview `803a6aaefca740408d6296c23bbab8c7`.
   - 点击后提示: 8 real metadata diffs and the two provider warnings must remain visible; warnings must not be rendered as an empty successful refresh.
   - 等待: wait for persisted preview `completed` and job `completed`.
   - 等待中显示: a bounded processing state is acceptable; no second refresh request should be sent.
   - 下一步: compare the visible diff with the three recorded citation-count changes and leave it unapplied.
   - 失败恢复: on `SEMANTIC_SCHOLAR_RATE_LIMITED` or invalid-response display, preserve the partial warning and use a bounded retry only after the provider condition is resolved.
4. **Verify remove/restore and KB preservation**
   - 点击/输入: inspect added node `24e44e61d9d44d1b85918fa8f7362ff0` and the original GAT node.
   - 点击后提示: added node is active after restore; GAT retains `document_id=55afc3b8f01445429462fe78ed0d4c98` and `indexed` status.
   - 等待: wait for the restore job to show `completed`, then reopen the graph.
   - 等待中显示: the map remains `partial`; no import or PDF action is part of this case.
   - 下一步: verify the original viewport and GAT position remain `(10,20,1.1)` and `(120,80)`.
   - 失败恢复: if the document ID disappears or a removed node is shown as active before restore, stop with `KB_HANDLE_MUTATED` or `TOMBSTONE_STATE_MISMATCH`.

## Readiness matrix

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Service started and reachable | PASS | `/api/ready` HTTP 200, warmup statuses ready |
| 2 | Real API preview/apply entry | PASS | preview 202→200, apply 202, real IDs persisted |
| 3 | Parameters and server identity parsed | PASS | references node identity and preview candidate IDs persisted |
| 4 | Entity state progressed | PASS | queued/running→completed preview; apply, refresh, remove, restore jobs persisted |
| 5 | Frontend processing display | FAIL | production browser labels were not exercised by this backend run |
| 6 | User wait/click condition | FAIL | browser waiting copy was not independently verified |
| 7 | Core Task04 artifacts generated | PASS_WITH_LIMITATIONS | 45-candidate preview, one added node, 8 refresh diffs, CAS 409, tombstone restore; inherited map remains partial |
| 8 | Failure has actionable recovery | PASS | stale CAS fixed 409; provider warnings and bounded retry boundary are explicit |
| 9 | Page/API state consistency | FAIL | no production browser run in this backend evidence |
| 10 | Steps reproducible without chat context | PASS | this report and JSON contain URLs, IDs, requests, waits, responses, and recovery limits |

## Final decision

**BLOCKED.** The deployed API successfully exercised the Task04 backend expansion/recovery path through real HTTP: references preview, persisted candidate GET, one-candidate apply, idempotent replay, refresh diff, stale CAS rejection, remove/restore, and reopen. It is not `READY_FOR_USER` because the reused map remains explicitly `partial`, refresh completed with real provider warnings, and the production browser processing/labels were not exercised by this backend run. No additional retry, PDF download, import, or deployment was performed. The frontend reviewer may reuse map `0baabeae7268429c9f7e4de8098ae1d0`, preview `7fda3c448a7a4274be866ade62c39b19`, and refresh preview `803a6aaefca740408d6296c23bbab8c7` for the browser handoff.
