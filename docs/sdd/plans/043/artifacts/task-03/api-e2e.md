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
