# 技术评审：spec-012 知识库召回质量与切分 v2

- 评审角色：开发主管（tech-lead）
- 评审对象：`docs/sdd/specs/012-kb-recall-quality.md`（实现前可行性评审）
- 评审时间：2026-08-31
- 评审方式：基于代码事实（只读 `parse.py`/`index.py`/`store.py`/`retrieve.py` 指定位置）
- 评审范围：仅技术侧 3 点（双版本共存 / 异步并发 / 清洗误伤）

## 结论：通过（附意见）

代码现状核对：
- `point_id()` 现为 `uuid5(ns, f"{paper_id}:{chunk_index}")`（index.py:66-68），**无 chunker 维度**。
- `hybrid_search()` dense+sparse 两路**均无 filter**（retrieve.py:70-99）；`build_filter()` 是未被调用的预留（:130）。
- `rrf_fuse()` 归并 key 为 `(paper_id, chunk_index)`（retrieve.py:54），**不含 chunker**。
- `index.py` 用 `threading.Lock`（write）、`store.py` 用 `threading.RLock`（papers.json）；删除按 `paper_id`（index.py:108-120）；`upsert_chunks` 在 write lock 内做 `embed_texts`。
- `build_chunks()` 逐页切片、`chunk_index` 逐页从 0 递增（parse.py:104-112）→ v1/v2 各自编号会重叠，**这是必须加 chunker 维度的依据（spec 判断正确）**。

## 三风险点逐条判定

| # | 维度 | 判定 | 一句话依据 |
|---|---|---|---|
| 1 | point_id 加 chunker 防撞车 | ✅ 方向正确 / ⚠️ 有配套缺口 | chunker 进 `uuid5` 输入串→点 id 不同，v1/v2 不互相覆盖，删除按 `paper_id` 安全；**但** RRF key 缺 chunker、`hybrid_search` 两路均无 filter，不补齐会 v1/v2 混召回或误归并。 |
| 2 | 线程池 + 双锁并发安全 | ⚠️ 风险（非阻塞） | 单进程下 `threading.Lock` 跨线程有效、方案成立；**但** ①`max_workers=1` 只串行 v2 间，不保护 v1 同步与 v2 异步的显存竞争 ②reindex 若上次残留 chunk 30-50、本次仅 30 个，残留点**不会被删** ③LLM 分析若在 lock 内会阻塞 v1/删除。 |
| 3 | 清洗规则误伤 | ✅ 基本可控 / ⚠️ 固有局限 | `e-mail`/`state-of-the-art` 行内无换行→规则A 不匹配不误伤；参考文献/列表靠结构行保护（`^\[\d+\]`/`-`/`数字.`）不粘；**局限**：LaTeX 把复合词折行（如 `state-\nof`）会被合并成 `stateof`，属无法区分的固有缺陷，须测试覆盖并文档承认。 |

## 强制约束（技术侧，实现必须遵守）

- **T1（风险1）**：`upsert_chunks` payload **必须新增 `chunker` 字段**；`rrf_fuse` 归并 key 由 `(paper_id, chunk_index)` 改为 `(paper_id, chunker, chunk_index)`；`hybrid_search` 的 dense 与 sparse **两路都必须**传 `query_filter=chunker`。三者缺一即会 v1/v2 混召回或误归并。
- **T2（风险2.①）**：明确 v1 同步与 v2 异步的 bge-m3/LLM 显存竞争策略——要么给 embed 层加进程级互斥，要么在 spec 文档承认「v1 上传期间 v2 可能降速/OOM」为已知风险，禁止默认无视。
- **T3（风险2.②）**：`reindex` 前**必须先按 `paper_id+chunker` 删除该版本旧点**再 `upsert`，否则失败残留点会永久污染检索（确定性 point_id 无法自动清掉多出的 index）。
- **T4（风险2.③）**：LLM 结构分析必须在 `_write_lock` **外**执行，仅 `upsert_chunks` 入库持锁；并保持「先 `index._write_lock` 后 `store._lock`」固定获取顺序，禁止反向嵌套（否则 ABBA 死锁）。
- **T5（风险3）**：测试集须含正例（`proce-\ndural`→`procedural`）+ 负例（`e-mail`/`state-of-the-art` 行内不合并）+ 边界（`[48]` 参考文献、`-` 列表项换行保留）；跨行复合词误合并列为**已知局限**写入 spec 风险区，不追求消除。
- **T6（高频回归点·前端）**：进度条/chunker 下拉/「重建索引」按钮实现时，须核对 JS 渲染 class 名 ⇄ CSS 选择器一致，且 `frontend/index.html` 静态资源 `?v=N` 随 js/css 改动升级（历史事故点，spec 未涉及前端细节，实现前须确认）。

## 判定统计

- 三风险点：方向正确 2（风险1、风险3）/ 风险 1（风险2，3 个可缓解子项）→ **0 硬阻塞**。
- 强制约束条数：**6**（T1–T6）。
- 阻塞项：**0**；方案方向（point_id 改法、锁模型、清洗规则）正确，隐患均可在实现时满足，已沉淀为强制约束。

## 风险定级：中

理由：涉及并发显存竞争、reindex 残留点、RRF 归并 key 三处，若实现漏做会造成**静默数据污染**（检索错但无报错），故定「中」；全部可由 T1–T4 闭环，无需打回。
