# 交接：Agent 研究流水线 P0 返工（spec029 / 030 / 031）

> 交接时间：2026-09-19
> 交接原因：主会话不再继续执行，转由其他 agent 接手。
> 本文件是**唯一权威的当前状态快照**，请先读完本文再动手。

---

## 0. 一句话概括

研究任务能跑完，但 **synthesizer 被跳过（`NO_VALIDATED_EVIDENCE`）**、且 **`research_paper_selections` 落库 0 条**。
根因是 **召回白名单（recall_allowlist）取不到值**，导致 `_validated_evaluator_candidates` 丢弃了 evaluator 的聚合产出。
修复方向已用**真实数据验证成立**，但 **2 个测试用例仍红**，需要定位并收口。

---

## 1. 精确的仓库状态

- 仓库根：`/Users/wjh/work/ResearchAgent-2/ResearchAgent`
- 分支：`fix/spec029-030-031-pipeline`
- HEAD：`1186caf fix(sse): 研究 intake 流补发终止帧，失败流改用带序号的 EventSequencer`
- venv：`.venv/bin/python`（python3.11）
- 前端为原生 JS/CSS/HTML，无构建步骤；当前资源版本 `frontend/index.html` 为 **`?v=55`**（app.js 与 styles.css 均是）

### 1.1 工作区（**全部未提交**）

```
 M backend/app/research/application/orchestrator.py      (+156 / -43)
 M tests/test_agent_selection_persistence.py             (+114)
 M tests/test_validated_evaluator_candidates_metadata_backfill.py  (+102)
?? memory.sqlite3      ← 垃圾文件，需删除
?? research.sqlite3    ← 垃圾文件，需删除
```

**除上述 3 个文件外，其余此前的工作都已提交**，不要重复做：

- `beba8b9 perf(startup): 首屏数据就绪——启动预热 + 模型列表缓存 + 就地加载态`
  （含 `backend/app/platform/warmup.py`、`GET /api/ready`、`get_available_models` 30s TTL 缓存、前端 `withAsyncSlot` 就地加载态、`?v=55`）
- `73daed0 feat(research): 研究 intake 参数表单化 + 取消入口（前端）`

---

## 2. 已完成的改动（未提交，需要你接手验收）

### 2.1 `backend/app/research/application/orchestrator.py`

| 位置 | 内容 |
|---|---|
| 第 87-115 行 | **新增模块级函数 `_recall_allowlist_from_search_outputs(search_outputs)`**：从 search-worker 输出中提取 `candidates` / `evidence_refs`（`catalog:` 前缀）/ `citation_allowlist`，汇总为召回白名单 |
| `_fail_work_item` 之前 | **新增方法 `_catalog_metadata_resolver()`**：返回本地目录元数据回填闭包，复用 `PaperDiscoveryStore.get_catalog_paper`（唯一的本地目录出口，禁止第二套实现） |
| ~第 1060-1104 行（合成器路径） | 计算 `recall_allowlist` 并传入 `_validated_evaluator_candidates(...)`；`metadata_resolver` 改为调用 `self._catalog_metadata_resolver()` |
| ~第 1256-1275 行（选集 / artifact 路径） | **本次新增**：补上 `recall_allowlist` 与 `metadata_resolver`。此前该路径只传 `catalog_metadata`，注释却写着"与上面合成器路径保持一致"——实际不一致，**这正是"选集 0 条"的第二处原因** |

`_work_item_output(value)`（第 74-84 行）会把持久化的 AgentRun 包装剥到内层 `output_json`，所以 `completed_outputs` 中存的是**带 `candidates` 的内层 dict**。

### 2.2 测试

- `tests/test_agent_selection_persistence.py`：新增 `test_persist_agent_selections_keeps_batch_aggregate_keep_false`、`test_batch_aggregate_evaluator_runs_synthesizer`，以及 fixture `_runner_for_batch_aggregate()` / `_planner_with_search_evaluator_synth()`
- `tests/test_validated_evaluator_candidates_metadata_backfill.py`：新增 102 行覆盖

---

## 3. 已验证成立的部分（真实数据，可信）

任务 `81241f3f01885e2c8f0490123f2215f3`（库：`data/research/research.sqlite3`，表 `research_work_items`）。

用手写的核对脚本（**不是单测**）直接调用新代码：

```
search 输出数: 2 | evaluator 输出数: 1
recall_allowlist 大小: 12          ← 修复前是空集
validated（仅白名单、零元数据）= 12   ← 修复前是 0 → NO_VALIDATED_EVIDENCE
```

**结论：白名单提取逻辑正确，12 条候选全部通过，连元数据都不需要。** 这是本次修复的核心证据。

补充事实（真实数据形状）：

- search-worker 的持久化 `output_json` 是 **AgentRun 包装**，keys 为
  `agent_run_id, approval_signal, checkpoint_hash, checkpoint_ref, error_code, model_metadata, output_hash, output_json, schema_version, status, tool_results, usage`
- `candidates` 在**内层** `output_json.output_json`（第一个 worker 有 6 个 ID）
- evaluator 输出顶层 keys：`candidate_id, evidence_refs, keep, output_hash, reason, relevance_score, safe_summary, schema_version, source_refs`
  —— 注意**没有 `kept` 字段**（此前一度按 `kept` 求证是错的），真实批量聚合形态是 `candidate_id=None` + `keep=False`

---

## 4. 未解决的问题：2 个失败用例（**互相矛盾，需你裁决**）

复跑命令：

```bash
cd /Users/wjh/work/ResearchAgent-2/ResearchAgent && \
.venv/bin/python -m pytest \
  tests/test_agent_selection_persistence.py \
  tests/test_agent_work_item_failure_visibility.py \
  tests/test_validated_evaluator_candidates_metadata_backfill.py -q
```

结果：**2 failed, 16 passed**（最后单独复跑两文件为 2 failed, 8 passed）。

### 4.1 `test_agent_selection_persistence.py::test_batch_aggregate_evaluator_runs_synthesizer`

- **性质**：本次**新增**的目标用例，意图就是复现真实任务
- **断言**：`syn_items[0].status == "completed"`；**实际 `"failed"`**
- **fixture 事实**：
  - search worker 产出 `candidates: ["paper-1", "paper-2", "paper-3"]`
  - planner 用 `role: "search-worker"`（连字符），runner 判 `run_input.role == "search_worker"`（下划线）
  - **这个判据是对的**：`orchestrator.py` 第 911 行有映射 `{"search-worker": "search_worker", "paper-evaluator": "paper_evaluator"}`，`run_input.role` 是规范化后的下划线形式
- **未定位**：该场景下 allowlist 仍为空 / `validated` 仍为 0 的原因
- **建议排查顺序**（按嫌疑度）：
  1. 在用例内临时打印 `recall_allowlist` 与 `validated` 的长度，先确认到底是"白名单空"还是"白名单非空但候选仍被丢"
  2. `_canonicalize_search_worker_binding()`（第 455 行）是否改写了 search 输出的 `candidates`（合成器路径在 `completed_outputs` 里读的是**规范化后**的 dict，见第 1193 行）
  3. 合成器路径第 1064 行的祖先 role 判定 `item_by_id[ancestor_id].role == "search-worker"` 是否命中
  4. `_validated_evaluator_candidates` 第 286 行的准入条件
     `if ref_id in effective_metadata or (recall_allowlist is not None and ref_id in recall_allowlist)`
  5. **注意矛盾点**：该用例没有提供任何本地 catalog 元数据，而 `catalog_metadata` 为空——确认"仅凭白名单即可展开为候选"这条设计是否真的生效

### 4.2 `test_agent_work_item_failure_visibility.py::test_skipped_synthesizer_is_marked_failed_not_queued`

- **性质**：**既有用例**（来自提交 `c721dc9`，本次未改动）
- **断言**：`synth.status == "failed"` + `error_code == "NO_VALIDATED_EVIDENCE"` + `result.status == "partial"`
- **实际**：`"completed"`（即 synthesizer 现在**不会**被跳过）
- **它的构造**：evaluator 聚合产出 `candidate_id: None`、`evidence_refs: ["catalog:paper-1"]`；用例意图是"指向没有元数据来源的 ID → 无有效候选 → 跳过 synthesizer"
- **与 4.1 意图相反**：4.1 要求"有白名单就必须跑"，4.2 要求"无元数据就必须跳过"
- **需要裁决**：
  - 若该用例的 search 输出**确实**含 `paper-1`，则按新设计"白名单内 ID 可展开为候选"成立 → **该用例的断言已过时，应随设计更新**
  - 若 search 输出**不含** `paper-1`，则说明有路径在**从本地目录扩大候选集**（违反核心约束）→ 那是**真 bug，必须修**
  - 先确认这一点，再决定改代码还是改用例

> ⚠️ **红线**：**不要**为了让测试变绿，去放宽 `_validated_evaluator_candidates` 让它从本地目录扩大候选集。

---

## 5. 硬约束（违反会导致其它测试变红或设计走偏）

1. **白名单只来自 search worker 输出**（`candidates` / `evidence_refs` / `citation_allowlist`），**绝不从本地目录扩大候选集**。
2. **本地 catalog 只允许"为白名单内 ID 回填元数据"**（`get_catalog_paper`），它是唯一的本地目录出口，禁止第二套检索实现。
3. **不要改 `GET /api/conversations/{id}/context-usage` 的返回结构**：有测试断言其键集合恰为
   `{used_tokens, budget_tokens, ratio, segment_count, compaction_status, breakdown}`，`breakdown` 每项恰为 `{kind, label, tokens, bytes}`。
4. 本任务**不涉及前端**，不要改 `frontend/**`。

---

## 6. 环境与命令

```bash
# 复跑本任务相关测试
cd /Users/wjh/work/ResearchAgent-2/ResearchAgent
.venv/bin/python -m pytest \
  tests/test_agent_selection_persistence.py \
  tests/test_agent_work_item_failure_visibility.py \
  tests/test_validated_evaluator_candidates_metadata_backfill.py -q

# lint（注意：orchestrator.py 在 ~2346 行有 2 个**既有历史**错误
#       "Remove assignment to unused variable `exc`"，与本任务无关，不要顺手改）
.venv/bin/python -m ruff check backend/app/research/application/orchestrator.py
```

真实数据核对（可直接复用）：

```python
import sqlite3, json
from backend.app.research.application.orchestrator import (
    _work_item_output, _recall_allowlist_from_search_outputs, _validated_evaluator_candidates)

tid = '81241f3f01885e2c8f0490123f2215f3'
c = sqlite3.connect('data/research/research.sqlite3'); c.row_factory = sqlite3.Row
rows = c.execute('SELECT work_item_id,role,status,output_json FROM research_work_items WHERE research_task_id=?', (tid,)).fetchall()
roles = {r['work_item_id']: r['role'] for r in rows}
completed = {r['work_item_id']: _work_item_output(json.loads(r['output_json'] or '{}'))
             for r in rows if r['status'] == 'completed'}
search = [o for w, o in completed.items() if roles.get(w) == 'search-worker']
evals  = [o for w, o in completed.items() if roles.get(w) == 'paper-evaluator']
allow = _recall_allowlist_from_search_outputs(search)
print('allowlist:', len(allow))
print('validated:', len(_validated_evaluator_candidates(evals, {}, recall_allowlist=allow, metadata_resolver=None)))
```

---

## 7. 收尾事项（请一并处理）

1. **删除仓库根的两个垃圾 DB 文件**（未跟踪，是测试/脚本在 cwd 生成的）：
   - `memory.sqlite3`（258 KB）
   - `research.sqlite3`（540 KB）
   - 注意：真正使用的库在 `data/memory/`、`data/research/` 下，**不要误删那些**。
2. **子 agent 的模型当前被临时改为 `hy3`**（用户当时的"临时决策"，为走 0.00 倍率）。我**故意保持原样未还原**，以便后续分派的子 agent 继续走低成本模型：
   - `.codebuddy/agents/backend-dev.md` 第 6 行：`model: hy3`
   - `.codebuddy/agents/frontend-dev.md` 第 6 行：`model: hy3`
   - 若不再需要，还原为 `model: Deepseek-V4.1-Flash` 即可。

---

## 8. 建议的下一步

1. 先跑第 4 节的两条用例，确认失败可复现。
2. 用第 4.1 节的排查顺序定位 `test_batch_aggregate_evaluator_runs_synthesizer` 失败原因（**优先确认 `_canonicalize_search_worker_binding` 是否吞掉了 `candidates`**——这是目前嫌疑最大的点）。
3. 裁定 4.2 用例的语义归属（改代码 vs 改用例），依据是"该 search 输出是否真的含 `paper-1`"。
4. 两个用例都绿后，跑一次更大范围的回归（`tests/` 下与 research/orchestrator 相关的文件），确认没有连带破坏。
5. 完成第 7 节收尾，再决定是否提交。

---

## 9. 接手收口记录（2026-09-19）

### 9.1 第 4.1 节根因：不是 `_canonicalize_search_worker_binding`

打桩 `_validated_evaluator_candidates` 后实测，synthesizer 路径收到的 evaluator 输出是
`{"schema_version": "synthesis-v1", "work_item_id": "<id>-e1", "report": "ok"}`
——e1 掉进了 runner 的 `else` 分支。真因是新夹具 `_runner_for_batch_aggregate()` 里写成
`run_input.role == "paper-evaluator"`（连字符），而 `orchestrator.py:910-913` 的 `role_map`
已把角色规范化为下划线 `paper_evaluator`。白名单本身正确（`{paper-1,paper-2,paper-3}`）。
已改夹具（并在行上加注释说明规范化链路）。

### 9.2 第 4.2 节裁定：用例构造过时

该用例的 search worker 确实召回 `paper-1`，新设计下白名单内 ID 缺元数据也要展开为候选，
故"跳过"不再发生（实测 completed）。按本文判据 → **改用例**：`evidence_refs` 改为
`catalog:paper-not-recalled`（从未召回的 ID），三个断言一字未改，保留"被跳过的 item
必须落 failed 而非 queued"的原始意图。

### 9.3 验证（按用户要求未跑全量）

- 三个相关文件：**18 passed**（修复前 2 failed / 16 passed）
- 受影响领域：`-k "research|orchestrator|evidence|acquisition|selection|dispatch|skill|catalog|synthes"`
  → **460 passed / 2132 deselected / 11 subtests**
- `ruff check orchestrator.py`：仅 2 个既有历史错误（E731 @316、F841 @2347），无新增
- 评审：**GO**，见 `docs/sdd/reviews/029-031-p0-recall-allowlist-backend-review.md`（附 2 条 LOW）
- 提交：`e4ab0b6`（分支 `fix/spec029-030-031-pipeline`，**未 push**）

### 9.4 真实端到端复验（新 query，证明不复发）

- query：`模糊测试 fuzzing 内存安全漏洞挖掘`（USENIX Security 2022–2025）
- 任务 `d21317d817b051768919dfd95b177522`：search×2 / paper-evaluator / research-critic /
  **synthesizer 全部 completed，0 个 failed**，syn 产出 2864B 真实 output
- `research_paper_selections` 落库 **9 条**（evidence_level=catalog），任务终态 `partial`
  （catalog-only 报告，符合 api-sample 预期）
- **结论 GO**：修复前的症状是「synthesizer 被 NO_VALIDATED_EVIDENCE 跳过 + 选集 0 条」，
  本次在全新 query 上完全相反，证明 `e4ab0b6` 在真实数据上成立

### 9.5 P2（kb/health）处理结论：真缺陷，已修

- 判定：**不是设计如此**，是「引导-最终化未完成」——别名 `papers` 从未创建，
  `retrieve.py:139` 的 `hybrid_search` 硬编码按 `KB_COLLECTION` 检索 → **RAG 实际返回空**
- 处置：复用既有 `bind_candidate` → `create_alias("papers" → "papers_rebuild_empty_bootstrap")`
  + `refresh_live_digests()`；备份在 `/tmp/kb-finalize-backup-20260919-021036/`
- 结果：`/api/kb/health` → `qdrant: true`、`chunks: 4527`、`generation.ready: true`、`papers: 14`；
  `hybrid_search` 由空变为 **5 条命中**。未改任何 `backend/**` 代码，未重建索引

### 9.6 遗留（未处理）

- **P1 存疑**：9.4 的真实任务里选集 `relevance` 全为 `0.0`，与 P1「中文 query 命中英文目录
  排序退化」的描述一致。P1 虽已由 `3d0ce52` 标为修复，但在真实中文 query 上**未见改善，需复验**。
- 未 push；`spec-status-changelog.md` 未追加（本次为已有 spec 的缺陷修复，未发生 spec 状态变更）。
