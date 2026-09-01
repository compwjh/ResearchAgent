# Spec 012 验收评审 — 知识库召回质量与切分 v2

- **结论：通过**（无阻塞项；评审过程中发现并修复 2 个漏做项，见下）
- 评审者：架构师（子代理 `tester` 两次分派均中途失效，未产出，改由人工评审）
- 评审时间：2026-09-01
- 被审对象：spec `docs/sdd/specs/012-kb-recall-quality.md`（状态：已确认）

## 0. 评审方式说明（重要）

本应分派 `tester` 子代理做验收，实际**两次分派均失败**：

| 子代理 | 模型 | 结果 |
|---|---|---|
| `junior-dev`（编码） | `qwen3.8-27b-q4` | 一次 aborted、一次 idle timeout；超时后仍在后台写入并覆盖他人代码 |
| `tester`（验收） | `qwen3.5:9b` | 29 次工具调用、18 分钟，仅完成"跑全量测试"即中断，**未产出报告** |

因此本次验收**由架构师人工执行**：逐条核对 spec 验收点与评审强制约束（R1–R2、T1–T6），
并以单测与真实命令输出为依据。所有判定均可复现（命令见文末）。

## 1. 验收结论速览

| 维度 | 判定 | 说明 |
|---|---|---|
| 全量回归 | ✅ | `253 passed`（含新增 3 个测试文件） |
| 需求一：参考文献不召回但入库 | ✅ | payload 带 `is_citation`，默认过滤，问参考文献时自动放开 |
| 需求二：文本清洗 | ✅ | 断词合并 + 软换行转空格，结构行不被误伤 |
| 需求三：切分 v2 | ✅ | 硬上限、跨章节不合并、跨页合并、降级均达标 |
| 评审约束 R1–R2 / T1–T6 | ✅ | 8 条全部落实（R1 与跨页引用为评审中发现后补做） |
| 前端 | ✅ | 进度条 / 版本选择 / 重建按钮齐全，class 与 CSS 一一对应，`?v=12` |

## 2. 逐项验收

### 2.1 需求一：参考文献仍入库，但默认不参与召回

| 验收点 | 判定 | 依据 |
|---|---|---|
| payload 带 `is_citation` | ✅ | `index.upsert_chunks` 写入该字段，由 `normalize.detect_citation` 计算 |
| 默认检索排除参考文献 | ✅ | `retrieve.build_filter(include_citations=False)` 追加 `is_citation == False`；`hybrid_search` 默认按意图自动判定 |
| 问参考文献时自动放开 | ✅ | `retrieve.looks_like_citation_query`，命中则 `include_citations=True` |
| 仅自动意图识别、无手动开关 | ✅ | `KBAskRequest` 未引入任何 citation 开关字段，符合"明确不做" |
| **负例不误判** | ✅ | 单测覆盖 `reference implementation 是什么`、`这个方法的复杂度`、`实验结果怎么样` 均不触发 |
| 正例能命中 | ✅ | `这篇论文的参考文献有哪些`、`列出参考书目`、`list of references`、`bibliography`、`which papers are cited` |

### 2.2 需求二：修复召回文本的换行混乱

| 验收点 | 判定 | 依据 |
|---|---|---|
| 行末连字符断词合并 | ✅ | `proce-\ndural` → `procedural`（T5 正例） |
| 行内真连字符不误伤 | ✅ | `state-of-the-art`、`e-mail` 保持原样（T5 负例） |
| 软换行转空格 | ✅ | `skills\noperate across tasks` → 合成一行 |
| 句末换行保留 | ✅ | `This is one.\nThis is two.` 保留换行 |
| 列表/编号/全大写标题换行保留 | ✅ | `- item`、`1. Introduction`、`ABSTRACT` 前换行均保留 |
| 参考文献区只有新条目换行 | ✅ | `ref_zone=True` 下 `[1]…\ncontinued` 合并，`[1]…\n[2]…` 分开 |
| v1 与 v2 共用清洗后文本 | ✅ | 两者输入均为 `extract_pages_normalized` 的产出 |
| 已知局限已记录 | ✅ | 复合词折行（`state-\nof` → `stateof`）无法区分，已在 spec 风险区与单测注释固化 |

### 2.3 需求三：切分 v2

| 验收点 | 判定 | 依据 |
|---|---|---|
| 硬上限不突破 | ✅ | 单测断言所有 chunk `len(text) <= max_chars`（含无句子边界的 5000 字符长块） |
| 跨章节不合并 | ✅ | `TABLE 1` 与 `3.2 Method` 正文分属不同 chunk |
| 允许跨页合并并记录页码范围 | ✅ | 组内 `page` 取首块、`page_end` 取末块 |
| `section` 写入 payload | ✅ | 识别出的 `3.2 Method`、`TABLE 1` 进入 payload 与 `Hit` |
| 规则预筛减少 LLM 调用 | ✅ | 编号小节、章节名、表格/图题、参考文献条目直接判边界 |
| LLM 失败降级且不阻塞上传 | ✅ | 抛异常 / 空回复 / 不可解析三种情形均产出 v2 且不抛错 |
| `think: false` 保留 | ✅ | `ollama_boundary_judge` 显式携带，并有单测守着 |
| LLM 编号口径正确 | ✅ | 单测验证**每批编号都从 1 开始**（曾因用全局编号导致第 2 批起判定全部错位） |
| 不产出重复 chunk | ✅ | 单测断言 chunk 文本无重复（曾因分组循环未推进 `start` 而大量重叠） |

### 2.4 评审强制约束

| 约束 | 判定 | 依据 |
|---|---|---|
| **R1** 并发/显存策略 | ✅（评审中发现后补做） | 见 §3.1 |
| **R2** 意图白名单可测且含负例 | ✅ | 单测含 5 个正例 + 4 个负例 |
| **T1** 版本隔离三件套 | ✅ | ① payload 带 `chunker` ② `rrf_fuse` key 改为 `(paper_id, chunker, chunk_index)` ③ dense/sparse 两路均传同一 `query_filter`，有单测守着 |
| **T2** 显存竞争 | ✅ | 同 R1 |
| **T3** 先删后写 | ✅ | `index_paper_chunker` 在 upsert 前调 `delete_paper_chunker(paper_id, chunker)`，单测断言两路 filter 含 `paper_id` + `chunker` |
| **T4** 锁范围与顺序 | ✅ | LLM 结构分析在 `index._write_lock` **外**执行，仅 `upsert_chunks` / `delete_paper_chunker` 内部持锁；无反向嵌套 |
| **T5** 清洗测试三件套 | ✅ | 正例 / 负例 / 边界齐备，已知局限已写明 |
| **T6** 前端 class ⇄ CSS 一致、`?v` 升级 | ✅ | 新增 7 个 class 均在 CSS 有定义；js/css 每次改动同步升版，当前 `?v=12` |

### 2.5 异步索引与进度

| 验收点 | 判定 | 依据 |
|---|---|---|
| 单线程池 `max_workers=1` | ✅ | `tasks.get_executor`，docstring 说明原因（显存 + Qdrant 写锁） |
| 任务去重 | ✅ | 单测：重复提交第二次返回 `False`，`running_count` 为 1 |
| 分阶段百分比进度 | ✅ | 解析清洗 0→10、LLM 10→70、入库 70→100；单测断言单调且终值 100 |
| 进度回调异常不影响主流程 | ✅ | 单测注入抛异常的回调，切分仍完成 |
| 重启残留标记失败 | ✅ | `mark_interrupted_tasks`；启动时经 `lifespan` 调用 |
| 线程带异常退出不留 `indexing` | ✅ | `_guarded_run` 兜底，单测验证会标记 `failed` |
| 前端仅在有任务时轮询 | ✅ | `renderKbPapers` 返回是否仍有 `indexing`，无则 `stopKbPoll` |

### 2.6 前端

| 验收点 | 判定 | 依据 |
|---|---|---|
| 双版本状态标签 | ✅ | `kb-chunker-badge` 按状态着色，显示 `v1 已索引 · 125 片段` / `v2 索引中 45%` |
| 百分比进度条 | ✅ | `kb-progress` / `kb-progress-fill`，带 `role=progressbar` 与 aria 值 |
| 重建索引按钮 | ✅ | 调 `POST /api/kb/papers/{id}/reindex`，`chunker=all` |
| 切分版本下拉（默认 v1） | ✅ | `kb-chunker-select`，`KBAskRequest.chunker` 默认 `v1` |
| XSS | ✅ | 新代码全部 `textContent`，未新增任何 `innerHTML` 拼接 |
| 静态资源版本 | ✅ | `?v=12` |
| JS 语法 | ✅ | `node --check frontend/app.js` 通过 |

## 3. 评审中发现并已修复的问题

### 3.1 R1 未落实：v1 同步索引与 v2 异步任务会抢显存（已修复）

- **问题**：初版实现里 v1 上传直接同步建索引，v2 走线程池，两者可同时跑，
  bge-m3 与 27B 结构分析并存会抢显存。R1 明确"禁止默认无视"。
- **约束冲突**：R1 推荐"v1 也纳入单线程池排队"，但产品要求"上传返回时 v1 已索引"。
- **解法**：新增 `tasks.run_index_task_sync`——提交到**同一个**单线程池并同步等待结果。
  既保持 v1 的同步返回语义，又让 v1/v2 共用一条串行队列。
- **代价（已知）**：若后台有 v2 任务在跑（27B 约 3–5 分钟/篇），新上传会排队等待。
  权衡为"等待"优于"OOM"。
- **验证**：`tests/test_kb_routes.py::UploadTests` 断言 v1 走 `run_index_task_sync`、v2 走 `submit_index_task`。

### 3.2 跨页引用未显示为 `p.3-4`（已修复）

- **问题**：spec 边界章节要求"v2 跨页合并片段的引用显示为 `p.3-4`，单页仍为 `p.3`"，
  但 `prompts.citation_payloads` 未输出 `page_end`，`build_context` 也只有单页。
- **修复**：`citation_payloads` 增加 `page_end`（缺省回落到 `page`）；
  `build_context` 用 `_page_label` 输出 `第 3-4 页`；前端 `renderKbCitations` 相应显示 `p.3-4`。
- **验证**：`tests/test_kb_services.py::CitationPageRangeTests`（4 条）。

## 4. 评审过程中发现并已修复的数据问题（非代码缺陷）

首次冒烟启动时，3 篇已有论文的 `status` 被从 `indexed` 误改成 `failed`。

- **根因**：`store.ensure_chunkers` 对 spec-011 遗留记录（无 `chunkers` 字段）
  一律按 v1=`indexing` 补齐，导致启动扫描把它们当成"中断任务"标记失败。
- **修复**：`ensure_chunkers` 改为**沿用顶层 `status` 与 `chunk_count`**，
  v2 一律 `pending`；并已把 3 篇恢复为 `indexed`（备份见 `data/kb/papers.json.bak.*`）。
- **防回归**：`tests/test_kb_tasks.py` 中两条用例——旧记录不被误伤（`marked == 0`）、
  真正的 `indexing` 仍会被标记（`marked == 2`）。

## 5. 旧数据迁移（spec 未提及，但必需）

spec 的检索会按 `chunker` 等值过滤，而 Qdrant 对**缺失该字段的点不匹配**，
若不迁移，旧论文在点「重建索引」之前会完全检索不到。

- 实现：`index.backfill_chunker_defaults`，启动时经 `lifespan` 调用，
  为缺失字段的点补 `chunker=v1` / `is_citation=False` / `section=""` / `page_end=page`。
- **实测**：本机 345 个点全部补齐，`by chunker: {'v1': 345}`，`missing = 0`。

## 6. 遗留风险与建议（不阻塞）

1. **v2 单篇耗时约 3–5 分钟**（27B，5~6 批调用）。已用异步 + 百分比进度兜底；
   若嫌慢，改配置项 `CHUNK_V2_LLM_MODEL` 即可换回 `qwen3.5:9b`，无需改代码。
2. **R1 的排队代价**：上传可能等待后台 v2 任务（见 §3.1）。
3. **v2 质量未经真实论文验证**：现有验证均为构造文本 + mock LLM。
   建议对 3 篇已有论文各点一次「重建索引」，人工比对 v1/v2 的召回差异。
4. **`section` 可能偏长**：参考文献条目整行会作为 `section`（长度上限 80 字符内），
   前端若展示需考虑截断。
5. **子代理可用性**：本次两个子代理（`junior-dev` 27B、`tester` 9b）均无法完成长流程任务，
   且 27B 在超时后仍会在后台写文件覆盖他人代码。后续长任务建议由主会话直接承担，
   或对子代理产出做强制回归验证（详见 `docs/sdd/retro/2026-09-01-subagent-model-naming.md`）。

## 7. 复现命令与真实输出

```bash
# 全量回归
.venv/bin/python -m pytest tests/ -q
# 253 passed, 6 warnings in 51.24s

# 前端语法
node --check frontend/app.js   # 通过

# 服务冒烟（端口 8013）
nohup .venv/bin/python -m uvicorn backend.app.main:app --port 8013 --host 127.0.0.1 &
curl -s http://127.0.0.1:8013/api/kb/health
# {"qdrant":true,"embedding":true,"reranker":false,"papers":3,"chunks":345,
#  "v2_llm":{"model":"qwen3.8-27b-q4","available":true}}

curl -s http://127.0.0.1:8013/api/kb/papers
# 3 篇均为 top=indexed，v1=indexed(125/88/132)，v2=pending

curl -s http://127.0.0.1:8013/ | grep -o "app.js?v=[0-9]*"   # app.js?v=12

# 旧点迁移核验（需先停服务，Qdrant 本地模式禁止多进程）
# total points: 345 / by chunker: {'v1': 345} / missing chunker field: 0
```

## 8. 签字

**验收结论：通过**（无阻塞项）——判定依据见上文逐项验收与复现命令。

> **开发主管签字**：同意验收结论（通过），无阻塞项（阻塞项 0）。
>
> - **签字人**：tech-lead 子代理（`qwen3.8:27b`），2026-09-01
> - **抽查情况**（对照实现逐一核实报告关键判定，非全项目扫描）：
>   1. `retrieve.py`：`build_filter` 支持 `chunker` 等值过滤与 `is_citation==False`；
>      `rrf_fuse` 归并 key 为 `(paper_id, chunker, chunk_index)`（T1.2 属实）；
>      `hybrid_search` 的 dense/sparse 两路均携带同一个 `query_filter`（T1.3 属实），
>      `include_citations=None` 时按 `looks_like_citation_query` 短语白名单自动判定，
>      手工复核 `reference implementation 是什么` / `这个方法的复杂度` / `实验结果怎么样`
>      均不命中任何模式（R2 负例判定成立）；
>   2. `tasks.py`：`run_index_task_sync` 提交到同一 `max_workers=1` 单线程池并同步等待，
>      v1 上传与 v2 异步任务共用一条串行队列，R1 落地方式与报告 §3.1 描述完全一致；
>   3. `index.py`：`point_id` 含 `chunker` 维度；`index_paper_chunker` 先
>      `delete_paper_chunker(paper_id, chunker)` 再 `upsert_chunks`（T3 先删后写属实）；
>      LLM 结构分析 `build_chunks_v2` 在 `_write_lock` 外执行、仅入库/删除内部持锁（T4 属实）；
>      `backfill_chunker_defaults` 按报告 §5 为缺失字段点补
>      `chunker=v1 / is_citation=False / section="" / page_end=page`；
>   4. `routes.py` 上传路径：v1 走 `run_index_task_sync`、v2 走 `submit_index_task`（§3.1 接线属实）。
> - **附加意见**：无阻塞项；报告 §6 遗留风险（真实论文 v2 召回人工比对、v1 上传可能排队等待
>   后台 v2 任务）维持"非阻塞"定级。签字后 spec-012 状态可转 `已完成`（满足 AGENTS.md 硬规则第 8 条）。

- 结论：**通过**，无阻塞项。
- 已修复：R1 显存竞争（§3.1）、跨页引用 `p.3-4`（§3.2）、旧记录状态误标（§4）。
- 待办（非阻塞）：对 3 篇真实论文各点一次「重建索引」，人工比对 v1/v2 召回差异（§6.3）。
