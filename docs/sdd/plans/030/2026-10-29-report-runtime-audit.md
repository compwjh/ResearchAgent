# Spec 030 runtime report audit

**Captured:** 2026-10-29 03:12 UTC  
**Runtime:** `http://127.0.0.1:8000`  
**Evidence:** [sanitized GET summary](artifacts/20261029-runtime-audit/summary.json)

## Scope and method

I read the public route declarations and used GET requests to list session/task summaries, read two completed sessions, download their existing Markdown and citation-manifest artifacts in memory for structure counts, read the corresponding canonical-report URLs, and list knowledge-base document metadata. No POST or model call was made, and no paper source/PDF was fetched. The report text itself was not saved; the companion JSON contains only identifiers, statuses, hashes, sizes, and derived counts. Two GET paths do have implementation-level side effects: session detail can reconcile session/plan projections, and the task event stream drains projection retries.

The sample is intentionally small: one known historical session (`a93fc08be4394a73a85b9710edaf1af1`) and one completed task visible on the first 100-item task-list page (`fc83662fd8f15748b57ed7f49ad32445`, created 2026-10-08). The list response had a next cursor, so this is not an exhaustive census and does not establish the distribution of all generated reports.

## Current GET routes

The route module exposes session list/detail and immutable artifact list/download under `/api/research-sessions`, task list/detail under `/api/research-tasks`, and canonical versioned reports at `/api/research-tasks/{task_id}/reports/{version}`. Artifact metadata includes artifact ID, task ID, report version, type, content hash, run ID, timestamp, and a download path; it intentionally omits the storage path and body. The canonical report route accepts `json`, `markdown`, or `html` formats. Source: [routes_research.py](../../../../backend/app/api/routes_research.py:71).

## Sampled outputs

| Task / session | Runtime state | Existing artifacts | Markdown body | Canonical report GET |
|---|---|---|---|---|
| `83592e7cd6b85e2ca9462d1bc62078c6` / `a93fc08be4394a73a85b9710edaf1af1` | Task `completed`; session-detail GET returned `completed` (may reconcile), version 1; 2026-09-16 | Markdown, HTML, citation manifest; 5 manifest entries | 1,435 Unicode chars / 2,105 UTF-8 bytes; heading levels H1/H2/H3/H4 = 1/2/5/5; five paper-entry headings and five citation-reference lines | `GET .../reports/1` → **404** |
| `fc83662fd8f15748b57ed7f49ad32445` / `da70204dd1eb46f7a48652dd2a1118b1` | Task `completed`; session-detail GET returned `completed` (may reconcile), version 1; 2026-10-08 | Markdown, HTML, citation manifest; 5 manifest entries | 7,649 Unicode chars / 8,197 UTF-8 bytes; H1/H2/H3/H4 = 1/2/1/5; five paper-entry headings and five citation-reference lines | `GET .../reports/1` → **404** |

The longer artifact is still a five-paper catalog-card report: it has five abstract rows (four nonempty), five keyword rows (none nonempty), five method rows (none nonempty), and only two nonempty values each for source, year, and official URL. Across both samples, the heading structure exposes “research results” and citation-list sections, but no explicit cross-paper comparison, claims, limitations, or recommendations section. The 1,435-character sample has no more detailed body fields identifiable by the newer template’s literal labels. These are two samples, not evidence that all reports are this short or that every report follows the same template.

The finding that is directly supported is that both sampled tasks are marked `completed` and have delivered three immutable artifacts, while the canonical evidence-report GET returns 404 for version 1. Thus the completed artifact delivery path is present, but a canonical matrix-backed report is not readable for either sample.

## Runtime path evidence and limit

Both samples’ `generated_by_agent_run_id` values use actual-run-shaped IDs (`...:syn:run-1` and `...:syn:run-1:attempt-4`). The historical task’s event stream also contains a completed `synthesizer` worker, and both task summaries report provider `ollama`. The source says real AgentRunner paths pass their actual Run ID; the synthetic deterministic-only run uses `<work_item_id>:report-run-v<version>` with provider `internal` and resolved model `deterministic` ([orchestrator.py](../../../../backend/app/research/application/orchestrator.py:3395)). This supports classifying the sampled runs as AgentRunner-backed.

Artifact metadata does **not** distinguish whether the model-owned synthesis envelope passed validation or the deterministic candidate fallback rendered the report after a synthesis error. Both routes deliver through the same artifact service with the synthesis run ID. The exposed response did not record that branch decision. The text renderer itself is a fixed, sanitized template; its being deterministic does not prove the fallback branch ran. The source contains a separate canonical matrix/report generation path and explicitly documents candidate artifacts as a fallback when canonical output is unavailable ([orchestrator.py](../../../../backend/app/research/application/orchestrator.py:2325)).

## Knowledge-base evidence check

`GET /api/kb/documents?limit=100` returned 53 document records: 52 PDFs, 51 indexed documents with chunks, two still indexing, and 53 immutable sources. The two sampled reports each cite five unique candidate IDs; none of those ten IDs directly matched a KB `document_id`. The list route exposes document IDs and indexing metadata but does not provide a catalog-paper-to-document crosswalk. So the runtime has indexed KB material in sufficient quantity, but this read-only check cannot establish that the exact five cited papers in either sample have matching full-text documents. It does not yet prove that a reproducible five-paper full-text report can be built from those specific candidates. No source PDF or document content was read. Source: [routes_kb.py](../../../../backend/app/api/routes_kb.py:420).

## Read-path side effects

The session-detail GET handler calls `reconcile_session_projection` for linked tasks ([routes_research.py](../../../../backend/app/api/routes_research.py:1210)). That service can persist terminal session status and complete a proposed/active plan ([research_service.py](../../../../backend/app/research/application/research_service.py:224)). I used this GET for both samples before noticing the write-capable reconciliation path. I had no pre-read projection snapshot, so I cannot confirm whether either call actually changed a stored session or plan value.

The task event stream is also an HTTP GET, but its handler calls `drain_processing_projection_retries` before streaming ([routes_research.py](../../../../backend/app/api/routes_research.py:1761)). I invoked it once; the response included a completed synthesizer worker and `TRACE_PROJECTION_FAILED` trace-sync frames. I had no pre-read retry-state snapshot, so I cannot confirm whether the drain changed persisted retry state. The worker-completed event is not evidence that model output passed synthesis validation or that a retry succeeded. No POST, report-generation request, model call, acquisition, or source-document request was made.

## Audit conclusion

The runtime has completed, AgentRunner-backed sample tasks and versioned Markdown/HTML/citation artifacts, but both sampled canonical report endpoints return 404. The longer body is substantially more complete as catalog metadata than the older sample, yet neither sampled heading structure shows cross-paper analysis. The KB contains indexed/chunked documents, but the available metadata does not tie them to the sampled five-paper candidate sets. A controlled reproducibility check will need an explicit candidate-to-document mapping and a report path whose canonical version is readable; this audit did not start that pipeline.
