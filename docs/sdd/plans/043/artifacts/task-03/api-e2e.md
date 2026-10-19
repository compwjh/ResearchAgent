# BLOCKED — Task03 real API E2E

## API E2E artifact

- Spec: `043-literature-map-topic-exploration`
- Run ID: `task03-api-e2e-20261019T133632Z`
- Runtime: `http://127.0.0.1:8000`, service commit `4cb57358a50c34f487fc6bcc73d75fc01a8b009c`, `RERANKER_ENABLED=false`.
- Evidence JSON: [api-evidence.json](./api-evidence.json)
- No code, configuration, deployment, or user-data deletion was performed by this run; the one permitted import API call naturally persisted the node's failed download status.

The readiness endpoint returned HTTP 200. The real create request was:

```http
POST /api/literature-maps
Content-Type: application/json
```

```json
{"topic":"graph attention networks","name":"API E2E graph attention networks","limit":20,"idempotency_key":"e2e-gan-20261019-backend"}
```

It returned HTTP 202 with `map_id=9b1e4739443e40c98400cfb69aec1e45` and `job_id=b4ccc1dfe6814c36a42a1f67e7681f52`. The unscoped Semantic Scholar discovery returned `provider_count=1000`, `accepted_count=20`, `provider_truncated=1`, and retained 20 nodes. This is evidence that the application accepted and bounded the provider result rather than claiming the provider honored `limit=20`.

The job progressed from `queued/discover` to `running/references`, then `running/similarity`, and ended at event 7 as `partial/finished`. Final job counts were:

```text
provider_count=1000
accepted_count=20
node_count=20
provider_request_count=21 (budget 60)
citation_edge_count=0
similarity_edge_count=0
```

The citation layer was `partial` with fixed error `SEMANTIC_SCHOLAR_INVALID_RESPONSE`; the failed-unit list also contained two retryable `SEMANTIC_SCHOLAR_RATE_LIMITED` units. The similarity layer was `completed`, but it returned no edge, score, model, or content hash. No threshold was lowered and no synthetic edge was added. Therefore this run does not claim citation direction or cosine evidence.

The graph endpoint returned 20 real nodes with independent external identities. For example, node `2e35b888d3cb414090e2d8e55e5bae1a` retained arXiv `1809.07041`, DOI `10.1007/978-3-030-01264-9_42`, and Semantic Scholar ID `0000fcfd467a19cf0e59169c2f07d730a0f3a8b9`; its `catalog_paper_id` remained null because the request did not select a catalog source. No extra citation neighbor nodes were inserted.

## Saved-layout and reopen evidence

`PATCH /api/literature-maps/9b1e4739443e40c98400cfb69aec1e45/view` with `expected_revision=1` saved one real node position `(120,80)`, viewport `(10,20,1.1)`, and returned HTTP 200 with revision 2. A fresh map GET and graph GET returned HTTP 200, revision 2, the same viewport, and the same node position. The map remained explicitly `partial` after reopening.

## One permitted import-bridge check

One explicit import action was made for the node carrying arXiv `1809.07041`; no second import attempt was made. The endpoint returned HTTP 202 with business result `status=failed`, `download_status=failed`, and `error_code=PDF_NOT_FOUND`, with `paper_id=null`, `document_id=null`, and `catalog_paper_id=null`. A subsequent node read confirmed `document_id=null` and `download_status=failed`; no document was fabricated or attached.

## Manual acceptance case (API-backed handoff)

This backend run does not claim unverified browser labels. The browser reviewer should reuse the map ID above rather than creating a second provider job.

1. **Open the map entry**
   - 点击/输入: open the deployed application at `http://127.0.0.1:8000` and choose the real `文献地图` entry; exact browser label is not verified in this backend run.
   - 点击后提示: the existing map named `API E2E graph attention networks` should be listed with status `partial`.
   - 等待: wait for the map list request to return HTTP 200 and include the recorded map ID.
   - 等待中显示: a loading/list state is acceptable; do not start another map.
   - 下一步: open the recorded map ID and inspect the graph and status banner.
   - 失败恢复: refresh once; if the map is absent, use the API artifact and report `MAP_NOT_REDISCOVERABLE` rather than creating a duplicate.
2. **Inspect real nodes and layer status**
   - 点击/输入: select a returned node, including the arXiv/DOI node recorded above.
   - 点击后提示: node metadata and its external IDs are shown; citation layer should visibly indicate partial/error, not success.
   - 等待: wait for the graph GET to finish and compare node count 20 and edge count 0.
   - 等待中显示: the UI should retain the partial/progress indicator while reading the graph.
   - 下一步: leave the citation/similarity layer state unchanged and continue to layout verification.
   - 失败恢复: if the UI displays partial as success or invents an edge, stop with `PARTIAL_MISREPRESENTED`.
3. **Verify saved layout after reopen**
   - 点击/输入: reopen the same map and inspect the recorded sample node position and viewport.
   - 点击后提示: revision 2 and position `(120,80)` should be restored without a new provider request.
   - 等待: wait for map and graph GETs to complete.
   - 等待中显示: no provider discovery should start during a read-only reopen.
   - 下一步: compare the visible state with the API evidence JSON and close the case.
   - 失败恢复: refresh once; if revision/position differs, report `VIEW_PERSISTENCE_MISMATCH`.
4. **Import failure recovery boundary**
   - 点击/输入: do not repeat the import action; the one permitted import attempt already returned `PDF_NOT_FOUND`.
   - 点击后提示: the node should show failed download/no document, not a successful KB import.
   - 等待: none beyond the node GET.
   - 等待中显示: the failure code and retryability should remain explicit.
   - 下一步: stop the acceptance case and hand the PDF resolution issue to the import owner.
   - 失败恢复: do not retry in this run; provide a direct public PDF candidate or approved import-bridge fix before another bounded attempt.

## Readiness matrix

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Service started and reachable | PASS | `/api/ready` HTTP 200 |
| 2 | Real API create entry | PASS | POST returned HTTP 202 and stable IDs |
| 3 | Main-path parameter parsing | PASS | topic and limit 20 persisted; provider returned 1000 and app accepted 20 |
| 4 | Job/entity state progressed | PASS | queued → running/references → running/similarity → partial/finished |
| 5 | Frontend processing display | FAIL | Browser evidence is not present in this backend run; delegated browser verification remains pending |
| 6 | User knows wait/click condition | FAIL | Browser copy and wait affordance are not verified by this backend run |
| 7 | Core graph artifact generated | FAIL | 20 nodes exist, but final map is partial with zero citation/similarity edges |
| 8 | Failure has actionable recovery | PASS | fixed error codes and retryable flags are returned; no unbounded retry was run |
| 9 | Page/API state consistency | FAIL | Browser page was not exercised in this backend run |
| 10 | Reproducible steps | PASS | this report and `api-evidence.json` contain IDs, requests, waits, responses, and recovery boundaries |

## Final decision

**BLOCKED.** The deployed API create/read/layout/reopen paths are real and reproducible, but the required graph relationship artifact did not complete: the citation layer ended with `SEMANTIC_SCHOLAR_INVALID_RESPONSE`, the similarity layer had no threshold-verifiable edge, and the only permitted import check returned `PDF_NOT_FOUND`. `partial` is intentionally not reported as success. A controlled retry may be considered for the retryable rate-limit units after the provider response-shape and PDF-source gaps are resolved; this run made no additional retry and did not alter user data.

## Follow-up diagnosis: `SEMANTIC_SCHOLAR_INVALID_RESPONSE`

One additional real provider request was made, and only one: the already recorded failed Semantic Scholar ID `0012eafe0b3c79c42e00dd11fbc9bd4bea75c6eb`, relation `references`, offset `0`, limit `100`, and the same `SEMANTIC_SCHOLAR_METADATA_FIELDS`. The existing `SemanticScholarGraphClient` was reused with `retries=0`; no key or raw payload values were emitted.

The safe observed result was:

```text
client code: SEMANTIC_SCHOLAR_INVALID_RESPONSE
retryable: false
graph_page: false
payload type: dict
top-level keys: citingPaperInfo, data
data type: NoneType
data count: not applicable
total/offset/next: all absent
```

The existing client therefore did receive a JSON payload; its result type does not expose the HTTP status, so the exact numeric status cannot be recovered without issuing a second request. This was not classified as transport unavailable, auth failed, not found, or rate limited. The endpoint/field selection also matches the production path in `service.py`: `/paper/{paper_id}/references`, `limit=100`, `offset=0`, and the shared metadata field list.

The precise failure is the provider envelope shape: `data=null` with no explicit `total=0` or pagination fields. `_parse_graph_page` intentionally rejects this shape, while accepting a list page or an explicitly empty page. The same shape is already captured as an invalid—not zero-reference—case in the Task02 feasibility evidence. The safe conclusion is therefore “provider returned an ambiguous success envelope,” not “this paper has no references.”

### Minimal fix/test recommendation

- No safe production parser change is justified from this single envelope. Accepting it as an empty page would erase the distinction required by the contract and could hide a provider schema or transient failure.
- If Semantic Scholar documents this envelope as a valid empty page, the smallest implementation change is confined to `backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py`, with a fixture-level parser test in `tests/paper_discovery/test_semantic_scholar_graph_api.py` (and a map-layer regression in `tests/literature_maps/test_map_feasibility.py`) proving the exact rule. Until that provider contract is confirmed, keep `SEMANTIC_SCHOLAR_INVALID_RESPONSE` partial.
- If the goal is better diagnosis rather than reinterpretation, expose a redacted provider HTTP status/envelope-shape diagnostic in the existing GraphClient result; this is a separate narrow change and was not made here.

### Can the current job retry be reused?

Technically yes: the stored job is `partial`, the store retry path requeues the same job without resetting checkpoints, and the cumulative budget remains 21/60. Semantically it is not a fix for this incident: the current service collects all failed reference units, including `retryable=false` invalid envelopes, so a retry would re-call those units and likely reproduce the same shape; only the two rate-limited units are explicitly retryable. Do not invoke the current job retry until the provider shape is clarified or the retry selection is narrowed to retryable units. No retry was issued in this diagnosis.

## Follow-up diagnosis: bulk selection and topic relevance

The persisted graph provides direct evidence that the 20 selected Semantic Scholar IDs are in ascending `paperId` order (`ids_sorted_ascending=true`), from `0000f44e...` through `004e4e6b...`, with 20 unique IDs. Recomputing the service's actual `_select_rows` lexical rule over the stored title/abstract metadata gives score `3` for every selected node: each contains all three query tokens (`graph`, `attention`, `networks`) as substrings somewhere in title or abstract. With equal scores, the service tie-breaker is `paper_id`, so this run's selection is effectively ID order rather than a relevance-ranked topic selection.

The relevant production path is `LiteratureMapService._select_rows`: it counts token-substring hits, sorts by `(-score, paper_id)`, and truncates to 20. The unscoped discovery path calls `SemanticScholarGraphClient.search_bulk`, whose implementation sends `GET /paper/search/bulk` with `limit=20` and then parses the returned rows. The real response contained 1,000 rows, so `provider_count=1000` is consistent with the bulk endpoint's documented batch behavior; the application did truncate after receiving the provider result, but it did not receive or preserve a relevance score. The current bulk client has no `sort` or continuation-token parameter and no relevance-search method.

The existing `CatalogSearchGraph` is not a drop-in fix for this unscoped path: it ranks indexed `CatalogPaper` records through local dense/sparse/RRF/rerank machinery and returns catalog IDs. Reusing it here without an attested catalog scope would mix identities and violate the map's separate S2 identity contract. It can be reused only for explicitly scoped catalog maps after the catalog adapter has established identity.

The official [Semantic Scholar Academic Graph API documentation](https://api.semanticscholar.org/api-docs/) distinguishes the endpoints: `/paper/search` is the relevance-ranked search and supports `limit<=100`, while `/paper/search/bulk` is for bulk matching, can return up to 1,000 records, has continuation tokens, and documents `sort` only by `paperId`, `publicationDate`, or `citationCount`; it explicitly does not provide search relevance. The current call's `limit` argument is therefore not a reliable way to bound the bulk response.

One bounded comparison request used the official documentation's known core paper ID `649def34f8be52c8b66281af98ae884c09aef38b`, relation `references`, and `limit=5`, through the same GraphClient with no retry. The provider returned `SEMANTIC_SCHOLAR_RATE_LIMITED` with no payload, so it supplied no second envelope shape; this does not alter the earlier conclusion about the `data=null` response. The numeric HTTP status is not exposed by the existing result type.

### Implementable minimal recommendation

1. Add a narrow `search_relevance` method to `backend/app/paper_discovery/infrastructure/semantic_scholar_metadata.py` targeting `/paper/search`, reusing the existing rate limiter, fields, error mapping, and parser; keep the request capped at the map limit (maximum 100).
2. Use that method only in the unscoped map discovery branch of `backend/app/literature_maps/application/service.py`, with a distinct request-cache operation key. Keep `_select_rows` for year/dedup/scope gates, but do not claim provider relevance from bulk rows. If the relevance endpoint fails, preserve the current explicit partial/error behavior.
3. Add a client contract test in `tests/paper_discovery/test_semantic_scholar_graph_api.py` for endpoint/limit/fields and a map discovery regression in `tests/literature_maps/test_map_discovery.py` using a redacted 1,000-row fixture where a high-relevance candidate is not among the first paper IDs; assert the candidate is selected and no unrelated row is padded. No test should fabricate citation or similarity edges.

Passing `sort=citationCount:desc` to bulk is a bounded fallback only if the product explicitly chooses citation prominence; it is not a substitute for topic relevance and should not be presented as one. No code change or retry was made during this diagnosis.

## Follow-up real API run (2026-10-19, r2)

本节追加一次新的真实产品 API E2E，保留上方旧 run 的失败事实与实体，不覆盖或复用旧幂等 key。证据已追加到同一份 [api-evidence.json](./api-evidence.json) 的 `follow_up_runs`，run ID 为 `task03-api-e2e-20261019T140606Z-r2`。

### Runtime and create

- Runtime: `http://127.0.0.1:8000`, service commit `8c79860377512f02ac53429795a664ae65e79969`, `RERANKER_ENABLED=false`; `/api/ready` returned HTTP 200 with embedding/qdrant ready. Credentials, cookies and authorization headers were not recorded.
- Fresh request: `POST /api/literature-maps`, topic `graph attention networks`, `limit=20`, fresh idempotency key `e2e-gan-20261019-r2-edcddee3590b4505a331979baf3f6bf1`; HTTP 202.
- New entities: `map_id=0baabeae7268429c9f7e4de8098ae1d0`, `job_id=ba6bb4f9471b43afb8b1063cdc3a883d`. The map ID was immediately returned to the parent handoff for `map_frontend_review` reuse; no second map was created.

### State and provider evidence

The bounded 20-second poll observed `queued/discover`, then `running/references`, and finally the first `partial/finished` state at event 7. Before the later bounded retry, the job counts were:

```text
provider_count=20
accepted_count=20
node_count=20
provider_request_count=21 (budget 60)
citation_edge_count=11
similarity_edge_count=5
```

This run used the unscoped relevance search path; the provider returned exactly 20 rows, and every selected node retained a separate Semantic Scholar identity plus DOI and/or arXiv identity where available. A representative node is `21041260a5394f42891b020128fa60fa` with arXiv `1710.10903`, DOI `10.17863/cam.48429`, and Semantic Scholar ID `33998aff64ce51df8dee45989cdca4b6b1329ec4`. `catalog_paper_id` remained null, as expected for an unscoped search.

The first citation pass produced real edges but remained partial: 3 units were `SEMANTIC_SCHOLAR_RATE_LIMITED` and 6 were `SEMANTIC_SCHOLAR_INVALID_RESPONSE`. The invalid/ambiguous provider envelopes were retained as failures and were not interpreted as zero references. Direction evidence is present in the graph: node `28d6f9065abd47f9975875ef88634afa` (Semantic Scholar `ab30672c8c5e4787f6a5985f26a8f281f0db2fb8`) references node `21041260a5394f42891b020128fa60fa` (Semantic Scholar `33998aff64ce51df8dee45989cdca4b6b1329ec4`), matching the frozen citing→cited contract.

The similarity layer completed with five real edges. Scores were `0.79353524`, `0.83133635`, `0.79003627`, `0.811645`, and `0.76271117`, all at or above the frozen `0.75` threshold. Each edge reports basis `title_abstract`, model `bge-m3`, algorithm `dense_cosine`, and a redacted content hash. No threshold lowering or synthetic pair was used.

### One permitted import check

One explicit import action was made for the real arXiv-backed GAT node `21041260a5394f42891b020128fa60fa` (`arxiv=1710.10903`). The POST command did not emit a response body/status in the shell capture; no second import was issued. A subsequent node GET returned HTTP 200 and established the business outcome: `status=failed`, `download_status=failed`, fixed `error_code=PDF_NOT_FOUND`, `retryable=false`, `paper_id=null`, `document_id=null`, and no catalog association. The graph/node provenance now carries the same `PDF_NOT_FOUND` diagnostic. No document or index entry was fabricated.

### Layout save and reopen

`PATCH /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/view` with `expected_revision=0` saved node `21041260a5394f42891b020128fa60fa` at `(120,80)` and viewport `(10,20,1.1)`, returning HTTP 200 and revision 1. The first fresh map and graph GETs both returned HTTP 200; revision 1, the same viewport, node position, 11 citation edges, and 5 similarity edges were preserved. The map remained explicitly `partial` after reopening.

### Manual acceptance handoff for the new map

This backend run does not claim browser labels or processing copy. The frontend reviewer should reuse the already-created map rather than creating another provider job:

1. Open `http://127.0.0.1:8000`, enter the real `文献地图` view, and open map `0baabeae7268429c9f7e4de8098ae1d0` named `API E2E graph attention networks r2`. Wait for the map list and graph GETs to return; the map must show `partial`, not success.
2. Inspect the graph. Expected API-backed result after the bounded retry is 20 nodes, 12 citation edges, 5 similarity edges, citation layer partial with the fixed provider error, and similarity layer completed. Citation arrow direction must be citing→cited; the representative GATv2→GAT edge above is the cross-check.
3. Reopen the same map without creating a new one. Confirm revision 1, viewport `(10,20,1.1)`, and the sample node position `(120,80)` remain visible. A refresh is the only bounded recovery; do not trigger another provider job.
4. Inspect the sample arXiv node's explicit import status. It must remain failed with `PDF_NOT_FOUND` and no document ID. Do not retry this run; the public PDF resolution/import bridge needs a separate approved fix.

If the UI shows `partial` as success, hides the citation error, invents an edge, or loses the saved layout, stop with `PARTIAL_MISREPRESENTED`, `RELATIONSHIP_MISMATCH`, or `VIEW_PERSISTENCE_MISMATCH` respectively and attach the run ID above.

### Readiness matrix for r2

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Service started and reachable | PASS | `/api/ready` HTTP 200; commit `8c79860…` |
| 2 | Real API create entry | PASS | Fresh POST returned HTTP 202 and new map/job IDs |
| 3 | Main-path parameter parsing | PASS | Topic and limit 20 persisted; relevance search selected 20 real nodes |
| 4 | Job/entity state progressed | PASS | `queued/discover → running/references → running/similarity → partial/finished` |
| 5 | Frontend processing display | FAIL | Browser was not exercised by this backend run |
| 6 | User knows wait/click condition | FAIL | UI copy not verified here; frontend reviewer must reuse this map |
| 7 | Core graph artifact generated | FAIL | Nodes, 12 citations and 5 similarities exist after one retry, but job/layer is partial |
| 8 | Failure has actionable recovery | PASS | Fixed rate-limit/invalid/PDF error codes and bounded recovery are observable |
| 9 | Page/API state consistency | FAIL | Production browser state was not exercised in this run |
| 10 | Steps reproducible without chat context | PASS | This section and `api-evidence.json` contain IDs, requests, waits, results, and recovery limits |

### Same-job bounded retry

After a shared cooldown, one retry was issued against the same `map_id/job_id` via `POST /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/jobs/ba6bb4f9471b43afb8b1063cdc3a883d/retry`; it returned HTTP 200 with `queued/references`. The persisted counter stayed at 21/60 when queued, and successful nodes/edges were not re-created. No new map or idempotency key was used.

Two bounded 20-second polls later, the same job returned `partial/finished` at event 14. The final counts are `provider_count=20`, `accepted_count=20`, `node_count=20`, `provider_request_count=30/60`, `citation_edge_count=12`, and `similarity_edge_count=5`. The retry added one real citation edge and consumed 9 logical provider requests. Remaining failures are 2 retryable `SEMANTIC_SCHOLAR_RATE_LIMITED` units and 4 non-retryable `SEMANTIC_SCHOLAR_INVALID_RESPONSE` units. No further retry was issued.

A final read-only graph summary returned HTTP 200 with 20 nodes and 17 edges (12 citation, 5 similarity); the representative citing→cited edge and all five cosine scores remained present. The final map GET returned HTTP 200 with `revision=2`, `status=partial`, and viewport `(10,20,1.1)`, so the saved layout remained visible after the retry.

### Final decision for r2

**BLOCKED.** This rerun materially improved the real evidence: relevance selection, 12 direction-verifiable citation edges, 5 threshold-verifiable cosine edges, and layout persistence all work on the deployed candidate. It is still not `READY_FOR_USER`: the citation layer/job remains explicitly partial after the one allowed retry, with 2 rate-limited and 4 invalid-response units; the one permitted arXiv import has `PDF_NOT_FOUND` with no document; and frontend processing/labels remain delegated to the browser reviewer. The old failed run remains unchanged above, and no duplicate map or second retry was created.

## Read-only arXiv dependency diagnosis (2026-10-19)

This section diagnoses the observed `ARXIV_UNAVAILABLE` metadata probe only. No code, configuration, provider key, PDF, import, or graph was changed or requested.

### Adapter contract and fixed error mapping

The existing `ArxivFallbackAdapter` uses the public metadata endpoint `https://export.arxiv.org/api/query` with a title query, `start=0`, and `max_results=20`. Its owned HTTP client uses a 20-second timeout and `trust_env=False`; requests are separated by a three-second slot, with two retries by default and bounded exponential backoff. It does not download PDFs. Parsed entries must pass the existing year/title/author identity thresholds and must expose safe `https://arxiv.org/abs/...` and `https://arxiv.org/pdf/...` URLs on the allowlisted arXiv hosts.

The adapter maps 429 to `ARXIV_RATE_LIMITED`, other HTTP failures to `ARXIV_HTTP_ERROR`, XML/response-shape failures to `ARXIV_INVALID_RESPONSE`, and timeout/`httpx`/OS transport failures (after the bounded attempts) to `ARXIV_UNAVAILABLE`. A valid response with no identity-safe match is `ARXIV_MATCH_UNCERTAIN`; it is not interpreted as “no OA”.

The earlier controlled probe recorded in `import-api-fixes.md` used this existing adapter for the same real node with retries disabled for the probe and returned `ARXIV_UNAVAILABLE`, with no match, no identity/year match, and no PDF. That fact does not establish that arXiv lacks an OA record.

### One public endpoint connectivity check

To separate restricted execution from provider health, one metadata-only GET was made against the same `export.arxiv.org` endpoint using a known arXiv ID query and `max_results=1`. No response body was retained and no PDF URL was requested. The escalated check completed TLS/HTTPS negotiation and returned:

- HTTP/2 `200`
- `content-type: application/atom+xml; charset=utf-8`
- `content-length: 2927`
- no 4xx/5xx/429 response

The normal sandbox could not resolve `export.arxiv.org` (`socket.gaierror` / curl error 6). A separate escalated DNS check resolved it to `199.232.163.42`. Therefore the sandbox failure is an execution-network restriction, not evidence of provider downtime. The externally permitted endpoint check was reachable and healthy at the time of this diagnosis. No additional adapter/provider request was made after that check.

The local product process was reachable independently: `GET http://127.0.0.1:8000/api/ready` returned HTTP 200 with `ready=true` and embedding/qdrant warmup statuses ready.

### Classification and bounded next step

The current evidence classifies the earlier `ARXIV_UNAVAILABLE` as an environment/transport-path failure at probe time (the restricted sandbox cannot resolve the host), not server rejection and not proof of missing OA metadata. Because the adapter's owned client intentionally sets `trust_env=False`, an approved deployment that requires an HTTP proxy would need a separate, narrowly scoped client/configuration change; no such change is made here. The escalated direct endpoint check succeeded, so the present evidence does not justify calling arXiv unavailable globally or changing the resolver's fixed mappings.

For user assistance, run the metadata worker in an environment with DNS/TLS egress to `export.arxiv.org` (or an approved proxy path compatible with the existing client policy), then retry only the existing bounded resolver unit. Keep the existing `PDF_NOT_FOUND` result from the permitted import check unchanged: this connectivity diagnosis neither proves an OA PDF exists for that node nor authorizes a download/import retry. The graph remains the previously recorded `partial` result.

## Follow-up real API import retry (2026-10-19, r3)

本节追加一次对既有部署、既有图和既有节点的单次主动导入复核，保留 r1/r2 证据，不创建新图、不重复 POST。证据已追加到同一份 [api-evidence.json](./api-evidence.json)，run ID 为 `task03-api-e2e-20261019T142453Z-r3`。

### Request and business response

- `/api/ready` returned HTTP 200 with `ready=true` and embedding/qdrant ready.
- Exactly one request was sent: `POST /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/nodes/21041260a5394f42891b020128fa60fa/imports` with `{}`. It returned HTTP 202.
- The business response was terminal immediately: `status=failed`, `download_status=failed`, `error_code=SEMANTIC_SCHOLAR_RATE_LIMITED`, `retryable=true`, `paper_id=null`, `document_id=null`, and `catalog_paper_id=null`.
- The controlled resolver diagnostics were visible as `resolver_code=SEMANTIC_SCHOLAR_RATE_LIMITED` and `resolver_codes=[ARXIV_MATCH_UNCERTAIN, SEMANTIC_SCHOLAR_RATE_LIMITED]`. No raw provider exception, URL, credential, cookie, or authorization header was recorded.

### Persistence and knowledge-base readback

- `GET /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/nodes/21041260a5394f42891b020128fa60fa` returned HTTP 200 and persisted the same failed state, primary error, resolver-code list, and `retryable=true` under `provenance.import_diagnostics`.
- The node retained arXiv `1710.10903`, DOI `10.17863/cam.48429`, and Semantic Scholar ID `33998aff64ce51df8dee45989cdca4b6b1329ec4`; no S2 ID was used as a catalog ID.
- `GET /api/kb/documents?limit=1` returned HTTP 200 (`total=50`). The target node had no `document_id`, so no KB document or indexable entry was attributed to it. No direct PDF request was made.
- The POST was terminal; no bounded wait or second import request was needed or issued.

### Result

**BLOCKED.** This is a stable, retryable provider failure with diagnostics correctly exposed and persisted across HTTP readback. It is not evidence that the arXiv/OA record is absent; no blind code change or additional import retry was made. The node remains eligible for a later bounded retry after the provider rate limit clears.

## Follow-up real API import retry (2026-10-19, r4)

本节追加 identity-first 修复重启后的单次真实导入复核，复用既有图/节点，保留 r1/r2/r3 事实，不创建新图、不重复 POST。证据已追加到同一份 [api-evidence.json](./api-evidence.json)，run ID 为 `task03-api-e2e-20261019T143501Z-r4`。

### Request and business response

- `/api/ready` returned HTTP 200 with `ready=true` and embedding/qdrant ready；部署提交标识为 `1e1fddb`。
- Exactly one request was sent: `POST /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/nodes/21041260a5394f42891b020128fa60fa/imports` with `{}`. It returned HTTP 202.
- The terminal business response was `status=failed`, `download_status=failed`, `error_code=PDF_NOT_FOUND`, `retryable=false`, `paper_id=null`, `document_id=null`, and `catalog_paper_id=null`.
- Resolver diagnostics were visible as `resolver_code=SEMANTIC_SCHOLAR_NO_OPEN_PDF` and `resolver_codes=[ARXIV_MATCH_UNCERTAIN, SEMANTIC_SCHOLAR_NO_OPEN_PDF]`. No raw provider exception, credential, cookie, authorization header, or direct PDF response was recorded.

### Persistence and knowledge-base readback

- `GET /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/nodes/21041260a5394f42891b020128fa60fa` returned HTTP 200 and persisted the same failed state, primary error, resolver-code list, and `retryable=false` under `provenance.import_diagnostics`.
- The node retained arXiv `1710.10903`, DOI `10.17863/cam.48429`, and Semantic Scholar ID `33998aff64ce51df8dee45989cdca4b6b1329ec4`; `catalog_paper_id` and `document_id` remained null.
- `GET /api/kb/documents?limit=1` returned HTTP 200 (`total=50`). Because this node has no `document_id`, no KB document or indexable entry was attributed to it. No direct PDF request was made.
- The POST was terminal immediately; no bounded wait and no second import request were issued.

### Result

**BLOCKED.** The identity-first deployment now reaches a stable no-safe-PDF outcome instead of the prior Semantic Scholar rate-limit failure. The result is actionable and persisted (`ARXIV_MATCH_UNCERTAIN` plus `SEMANTIC_SCHOLAR_NO_OPEN_PDF`), but it does not prove the arXiv record is absent; no blind code change, additional retry, or direct PDF request was made.

## Follow-up real API import retry (2026-10-19, r5)

本节追加最新 identity-conflict 修复重启后的单次真实导入验证，复用既有图/节点，保留 r1–r4 事实，不创建新图、不重复 POST。证据已追加到同一份 [api-evidence.json](./api-evidence.json)，run ID 为 `task03-api-e2e-20261019T144733Z-r5`。

### Request and business response

- `/api/ready` returned HTTP 200 with `ready=true` and embedding/qdrant ready；部署提交标识为 `20ea760`。
- Exactly one request was sent: `POST /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/nodes/21041260a5394f42891b020128fa60fa/imports` with `{}`. It returned HTTP 202.
- The terminal business response was `status=failed`, `download_status=failed`, `error_code=IMPORT_IDENTITY_CONFLICT`, `retryable=false`, `paper_id=null`, `document_id=null`, and `catalog_paper_id=null`. No resolver code was exposed in this response.

### Persistence and knowledge-base readback

- `GET /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/nodes/21041260a5394f42891b020128fa60fa` returned HTTP 200 and persisted `provenance.import_diagnostics.error_code=IMPORT_IDENTITY_CONFLICT`; `document_id`, `catalog_paper_id`, and download handle remained null/failed.
- `GET /api/kb/documents?limit=1` returned HTTP 200 (`total=50`). The target node has no `document_id`, so no KB document or indexable entry was attributed to it. No direct PDF request was made.
- The POST was terminal immediately; no bounded wait and no second import request were issued.

### Result

**BLOCKED.** The deployed API now reports and persists a fixed, non-retryable `IMPORT_IDENTITY_CONFLICT`, rather than masking the identity failure as `PDF_NOT_FOUND`; no document was created. This is the actual production-chain result for r5, not a provider guess. No blind retry, code change, or direct PDF request was made.
