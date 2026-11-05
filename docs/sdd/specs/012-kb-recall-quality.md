# Spec 012 — 知识库召回质量与切分 v2

## 状态

**当前状态：`已完成`（2026-09-01，验收通过 + 开发主管签字）**

> 说明：本 spec 的需求已通过 4 个决策点（citation 触发方式 / LLM 模型与异步进度 / 版本选择粒度 / 旧论文处理）在计划阶段与用户逐项澄清并确认，故落盘即置 `已确认`；实现完成、验收通过且开发主管签字后转 `已完成`。
> 状态变更须同步追加 `docs/sdd/spec-status-changelog.md`。

## 一句话目标

让知识库召回的片段**可读、有用、成块**：清洗 PDF 排版噪声（行末断词、段落内硬换行）；参考文献仍入库但默认不参与召回，仅在问题明显在问参考文献时自动启用；新增基于 LLM 结构分析的切分 v2（异步建索引、进度可见），上传时 v1/v2 双版本都建索引，提问时可选版本。

## 背景与实测证据（需求来源）

用户在 spec-011 交付后人工使用，反馈三个问题。经实测复核，均属实：

1. **召回的主要是 citation**：末页实测整页都是 `[48] K. Nottingham, P. Ammanabrolu, ... "Do embodied agents dream of pixelated sheep: ..." in International Conference on Machine Learning (ICML), 2023, arXiv:2301.12050.` 这类条目。BM25 极易命中作者名/年份/会议名，与正文语义无关却大量占位。
2. **召回格式换行未处理**：对 20 页论文 `page.get_text("text")` 实测——
   ```
    3| Abstract—Agentic systems increasingly rely on reusable proce-   ← 行末连字符断词
    4| dural capabilities, a.k.a., agentic skills, to execute long-horizon
    8| interfaces. Unlike one-off plans or atomic tool calls, skills    ← 句子中间硬换行
    9| operate (and often do well) across tasks.
   ```
   **不是 pymupdf 提取的问题，是 LaTeX 排版产物**（hyphenation 断词 + 段落内硬换行），解法是在解析后加一层文本规范化，而非更换提取库。
3. **切分需要结构感知**：v1 是"逐页 + 递归分隔符"切分，会把同一章节/同一表格的内容切断，且从不跨页。

## 数据模型

### Chunk（Qdrant payload 扩展，兼容 spec-011）

| 字段 | 类型 | 约束 |
|---|---|---|
| `chunker` | str | 必填，`v1` / `v2`。**新增**：用于版本隔离与检索过滤 |
| `is_citation` | bool | 必填。是否为参考文献条目 |
| `page` | int | 必填。起始页（v2 跨页合并时为起始页） |
| `page_end` | int | **新增**。结束页，单页时等于 `page` |
| `section` | str | **新增**。v2 识别出的结构标题（如 `3.2 Method`），可为空串 |
| `paper_id` / `file_name` / `chunk_index` / `text` / `uploaded_at` | — | 沿用 spec-011 |

### point_id

`uuid5(ns, f"{paper_id}:{chunker}:{chunk_index}")`
—— **必须带 chunker 维度**，否则 v1/v2 的 `chunk_index` 会撞车互相覆盖（spec-011 原为 `f"{paper_id}:{chunk_index}"`）。

### PaperRecord（新增双版本状态）

```jsonc
{
  "paper_id": "...", "file_name": "...", "page_count": 20,
  "status": "indexed",          // 兼容字段，等价于 chunkers.v1.status
  "uploaded_at": "...",
  "chunkers": {
    "v1": {"status": "indexed", "chunk_count": 125, "progress": 100, "error": null},
    "v2": {"status": "indexing", "chunk_count": 0,  "progress": 45,  "error": null}
  }
}
```

状态取值沿用 spec-011：`indexing` / `indexed` / `indexed_partial` / `failed`。

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败 |
|---|---|---|---|
| POST `/api/kb/upload` | multipart PDF | v1 同步索引完成后立即返回，含 `chunkers`（v2 为 `indexing`/progress 0） | 400 非 PDF / 超限 / 空文件；v1 失败则整体 `failed` |
| GET `/api/kb/papers` | — | `papers` 每项含 `chunkers` 双版本状态与 `progress` | 200 空列表 |
| POST `/api/kb/papers/{id}/reindex` | `{chunker?: "v1"\|"v2"\|"all"}`（默认 all） | 提交异步任务，返回各版本状态 | 404 论文不存在 |
| POST `/api/kb/ask` | `{question, model?, top_k?, chunker?: "v1"\|"v2"}` | SSE 流式，事件同 spec-011；`chunker` 默认 `v1` | 400 空问题 / 非法 chunker / 模型不存在 |
| GET `/api/kb/health` | — | 同 spec-011，另含 `v2_llm`（结构分析模型是否可用） | — |

**进度可见性**：前端仅在存在 `indexing` 任务时按 2.5s 轮询 `GET /api/kb/papers`，全部完成后停止轮询。

## 边界（每条之后会变成一条测试）

- **清洗不误伤**：`e-mail`、`state-of-the-art`、`fine-tuning` 等真连字符**中间无换行**，不得被合并；`proce-\ndural` 必须合并为 `procedural`。
- **结构行保护**：以 `[数字]`、`•`、`-`、`*`、`数字.` 开头的行，以及全大写短标题行，其换行**必须保留**（否则列表与参考文献条目会粘成一段）。
- **软换行处理**：上一行不以句末标点（`. ! ? : ;`）结尾且下一行非结构行时，单个 `\n` 转空格；段间空行保留为 `\n\n`。
- **citation 判定**：位于参考文献起始页之后 + （`^\[\d+\]` 条目 ≥2 或 特征词密度超阈值）→ `is_citation=true`；正文里出现单个 "reference" 一词**不得**判为 citation。
- **意图防误判**：仅当问题命中「问来源/问清单」的短语正则才纳入 citation（如 `参考(文献\|书目)`、`引用了(哪些\|什么)`、`reference (list\|section\|entry)`、`bibliography`、`cited by`）；正文问题含单词 "reference" 不触发。
- **v2 LLM 降级**：LLM 不可用 / 超时 / 返回不可解析 → 仅用规则边界生成 v2，标记 `llm_used=false`，**上传不失败**。
- **v2 未完成时提问 v2**：只召回已入库部分；若 v2 无任何片段，返回"该切分版本尚未就绪"提示，不报错、不回退到 v1。
- **服务重启残留**：启动时把仍为 `indexing` 的 chunker 置为 `failed`（error="服务重启导致中断"），可点「重建索引」重跑。
- **任务去重**：同一 `paper_id + chunker` 已有进行中任务时，重复提交返回已存在状态，不重复跑。
- **并发安全**：异步索引仍走 `index._write_lock`；线程池 `max_workers=1`（Ollama 9b 与 bge-m3 并存会抢显存）。
- **删除**：按 `paper_id` 删除，两个版本一次清空，逻辑不变。
- **跨页引用**：v2 跨页合并片段的引用显示为 `p.3-4`，单页仍为 `p.3`。

## 明确不做（划出范围）

- 不做 OCR（扫描件仍按 spec-011 标记 `indexed_partial`，不索引）。
- 不改 `bge-m3` 的 `num_batch=1024`（过小静默截断、过大 OOM，已修复过一次，不得回退）。
- **不做「包含参考文献」手动开关**（用户明确选择仅自动意图识别）。
- 不做全局切分版本切换（用户明确选择每次提问时选）。
- 不做自动为旧论文补建 v2（用户明确选择提供「重建索引」按钮，按需触发）。
- 不做语法高亮、不做向量库迁移工具、不做多 collection 拆分（双版本共存于同一 collection，靠 payload 过滤）。

## 评审强制约束（tech-lead 评审沉淀，实现必须遵守）

> 来源：`docs/sdd/reviews/012-requirement-review.md`（R1–R2）、`docs/sdd/reviews/012-tech-review.md`（T1–T6）。
> 以下 8 条是实现期的验收硬条件，漏做会造成**静默数据污染**（检索错但不报错）。

### 需求侧

- **R1（并发策略声明）**：必须明确 v1 同步索引与 v2 异步任务的资源竞争策略。当前仅 `max_workers=1` 串行 v2 任务，**不保护 v1 同步与 v2 异步之间的 bge-m3/LLM 显存竞争**。
  → 落地：**v1 同步索引也纳入同一单线程池排队**（推荐），或在文档显式承认「v1 上传期间 v2 可能降速/OOM」为已知风险。禁止默认无视。
- **R2（意图白名单可测）**：citation 意图正则必须落为可测试白名单，测试须含**负例**（正文里含单词 `reference` 但不问来源时不触发）。

### 技术侧

- **T1（版本隔离三件套，缺一即混召回）**：
  1. `upsert_chunks` 的 payload **必须**带 `chunker` 字段；
  2. `rrf_fuse` 归并 key 由 `(paper_id, chunk_index)` 改为 **`(paper_id, chunker, chunk_index)`**（当前 retrieve.py:54 缺 chunker）；
  3. `hybrid_search` 的 dense 与 sparse **两路都必须**传 `query_filter`（当前两路均无 filter，`build_filter` 是未调用的预留）。
- **T2**：见 R1 的显存竞争策略。
- **T3（reindex 先删后写）**：重建索引前**必须先按 `paper_id + chunker` 删除该版本旧点**再 upsert。确定性 point_id 无法自动清理多出的旧点，残留会永久污染检索。
- **T4（锁范围与顺序）**：LLM 结构分析必须在 `index._write_lock` **外**执行，仅 `upsert_chunks` 入库时持锁；保持「先 `index._write_lock` 后 `store._lock`」的固定获取顺序，禁止反向嵌套（防 ABBA 死锁）。
- **T5（清洗测试三件套 + 已知局限）**：测试须含正例（`proce-\ndural` → `procedural`）、负例（`e-mail` / `state-of-the-art` 行内连字符不合并）、边界（`[48]` 参考文献行、`-` 列表项换行保留）。
  **已知局限（不追求消除，须写入风险区）**：LaTeX 把复合词折行（如 `state-\nof`）会被合并成 `stateof`，无法与真断词区分。
- **T6（前端高频回归点）**：进度条 / chunker 下拉 / 「重建索引」按钮实现时，须核对 JS 渲染的 class 名 ⇄ CSS 选择器一致，且 `frontend/index.html` 静态资源 `?v=N` 随 js/css 改动升级。

## 产品使用步骤

> 初稿由架构师编写，待 `Task(pm)` 补充用户旅程与验收场景。

1. 用户在知识库视图上传 PDF：列表立刻出现该论文，v1 状态为「已索引」，v2 显示「索引中 0%」并有一条进度条。
2. 用户刷新或停留页面：v2 进度以百分比递增（解析清洗 → LLM 结构分析 → 切分 → 向量化），完成后变为「已索引」并显示片段数。
3. 用户在问答区提问：切分版本下拉默认「v1（按页递归）」，可切换为「v2（结构感知）」；发送后按所选版本召回。
4. 用户问「这篇论文引用了哪些参考文献？」：系统自动纳入参考文献条目召回，其他问题仍默认过滤。
5. 用户点论文条目上的「重建索引」：重新构建该论文的两个版本索引，进度同样可见。
6. 验收场景：上传 → v1 立即可用 / v2 进度到 100% → 同一问题分别用 v1、v2 提问对比 → 问参考文献能召回条目 → 重建索引可用。

## 执行配置（由架构师填写，落盘可查）

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、技术决策、落地校验 |
| 产品经理 | `qwen3.5:9b`（本地 Ollama） | 32k | `Task(pm)` | 补「产品使用步骤 / 用户旅程 / 验收场景」 |
| 开发主管 | `qwen3.8:27b`（本地 Ollama） | 32k | `Task(tech-lead)` | 需求/技术评审、任务拆分、合并裁决 |
| 初级开发 | `qwen3.8:27b`（本地 Ollama） | 32k | `Task(junior-dev)` | 已确认范围内的编码实现 |
| 测试 | `qwen3.5:9b`（本地 Ollama） | 32k | `Task(tester)` | 验收评审、Bug 复现 |

> v2 结构分析模型（非角色）：**`qwen3.8-27b-q4`**（本地 Ollama 量化 27B），调用须关思考（`think: false`）。
>
> **变更（2026-09-01 用户拍板）**：原定 `qwen3.5:9b`（≤10B）改为 `qwen3.8-27b-q4`，以换取更准的结构边界判定。随之而来的代价需要在实现中兜住：
>
> - **耗时显著上升**：27B 单次响应约 30–40s（实测探针 38.73s），按每篇 5~6 批调用估算，v2 单篇 LLM 阶段约 3–5 分钟。这正是 v2 必须**异步 + 百分比进度**的原因，进度反馈不可省略。
> - **显存竞争**：量化 27B 约 17GB，与 bge-m3 向量化同时在跑时可能抢显存 → 沿用评审约束 R1 的策略：v2 任务走单线程池串行，避免与 v1 同步索引并发。
> - **降级更重要**：27B 超时概率高于 9b，LLM 失败/超时必须降级为纯规则切分且**不阻塞上传**（边界章节已有此约束，此处重申为强制项）。
> - 该模型名须先在用户级 `~/.codebuddy/models.json` 注册才可用（已完成，blob `9c67ea656a96`，即 `q4_K_M` 量化档）。

## 评审记录

- 需求评审：`docs/sdd/reviews/012-requirement-review.md`（结论：**通过（附意见）**；评审者 tech-lead 子代理；风险定级低）
- 技术评审：`docs/sdd/reviews/012-tech-review.md`（结论：**通过（附意见）**；评审者 tech-lead 子代理；风险定级中；沉淀强制约束 T1–T6）
- 验收评审：`docs/sdd/reviews/012-acceptance-review.md`（结论：**通过**，无阻塞项；评审者架构师人工评审——`tester` 子代理两次分派均中途失效未产出报告）
  - 评审中发现并修复 3 项：①R1 未落实（v1 同步与 v2 异步抢显存，已改为共用单线程队列）②跨页引用未显示 `p.3-4` ③旧记录状态被误标为 failed
  - 另补做 spec 未提及但必需的旧索引点迁移：缺失 `chunker` 字段会被过滤条件排除，导致旧论文检索不到
- **交付后缺陷修复（2026-09-02，同功能范围，不新建编号）**：用户反馈「论文卡片内容展示不完全，索引重建和删除看不到，标题也展示不完全」。根因两条，均为纯前端布局问题，不涉及后端接口与数据：
  1. `.kb-item-name` 为 `white-space: nowrap` + `text-overflow: ellipsis`，且与页数 meta 并排争抢 320px 侧栏宽度 → 长标题被截断为「…」。改为标题独占一行、允许完整换行（`word-break: break-word; overflow-wrap: anywhere`），meta 独立成行；侧栏宽度 320px → 360px。
  2. `actions`（重建索引 / 删除）是卡片的第 3 个 grid 行，加上双版本徽章行与进度条后单卡高度约 110px，而 `.kb-side` 高度固定、`.kb-list` 只有约 300px 可视区 → 按钮被滚动区裁切。改为把 `actions` 移入版本徽章行并右对齐（`margin-left: auto`），进度条改为独占一行、去掉 `flex: 1 1 90px` 的挤占，单卡高度降到约 80px；按钮补 `border` 与 `nowrap` 提升可辨识度。
  - 验证：`node --check` 通过；静态资源升 `?v=13`；服务冒烟（端口 8014）`/` 返回 200、新 CSS/JS 已发布；全量回归 `253 passed`。
  - 复盘：`docs/sdd/retro/2026-09-02-kb-card-layout-retro.md`。

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-08-31 | 用户 | 反馈三个问题：召回多为 citation、换行未处理、需切分 v2（LLM 结构分析 + 固定上限） |
| 2026-08-31 | 架构师(自身) | 实测诊断：确认换行问题是 LaTeX 排版断词与硬换行（非提取库问题）；确认末页整页为参考文献条目 |
| 2026-08-31 | 用户 | 拍板 4 个决策点：①citation 仅自动意图识别 ②v2 用 ≤10B 模型 + 异步 + 百分比进度 ③版本每次提问时选 ④旧论文给重建按钮 |
| 2026-08-31 | 架构师(自身) | 编写 spec-012，状态置 `已确认`（需求已逐项澄清） |
| 2026-08-31 | 开发主管(tech-lead 子代理) | 需求评审通过（附 R1/R2）、技术评审通过（附 T1–T6），0 阻塞项；**抓出 spec 遗漏**：`rrf_fuse` 归并 key 缺 chunker、`hybrid_search` 两路无 filter → 漏做会 v1/v2 静默混召回 |
| 2026-08-31 | 架构师(自身) | 将 R1–R2 / T1–T6 固化为 spec「评审强制约束」章节；更新评审记录结论 |
| 2026-09-01 | 架构师(自身) | 完成前两项实施：新增 `normalize.py`（文本清洗 + 参考文献识别）并接入 `parse.py`；子代理模型命名问题排查归档至 `docs/sdd/retro/2026-09-01-subagent-model-naming.md` |
| 2026-09-01 | 用户 | **变更决策点②**：v2 结构分析模型由 `qwen3.5:9b`（≤10B）改为 **`qwen3.8-27b-q4`**（量化 27B），换取更准的结构边界；接受耗时与显存代价 |
| 2026-09-01 | 架构师(自身) | 完成第三项实施（切分 v2 + 双版本索引 + 异步进度 + 重建按钮 + 前端版本选择，前端 `?v=12`）；全量回归 253 passed |
| 2026-09-01 | 开发主管(tech-lead 子代理) | 验收签字：同意验收，阻塞项 0；spec-012 转 `已完成` |
| 2026-09-02 | 用户 | **缺陷反馈**：论文卡片内容展示不完全，「重建索引 / 删除」按钮看不到、标题展示不完全 |
| 2026-09-02 | 架构师(自身) | 定位为前端布局缺陷（标题 `nowrap` 截断 + 卡片过高导致按钮被滚动区裁切），修复并升 `?v=13`；全量回归 253 passed；复盘落盘 `docs/sdd/retro/2026-09-02-kb-card-layout-retro.md` |

---
**五条自检**：①每条边界都能写成测试 ②2 分钟内可审完 ③范围已划死（不做 OCR / 不改 num_batch / 不做手动开关与全局切换）④执行配置五行齐全 ⑤产品步骤可映射到验收点。

## 2026-11-06 索引任务重启后永久卡「索引中 0%」缺陷（待确认）

**状态：已完成（2026-11-06 验收通过、部署验证通过、架构师签字同意收口）。** 本段为 Spec012 收口后用户反馈的缺陷修订，按 Bug 处理规则不新建编号；主实现状态仍为「已完成」。用户明确「这个确认做」，并对文末三点**全部确认默认是**：① 一次性批量恢复全部 13 个卡住版本（不只截图这一篇）；② 启动收敛后允许自动重排一次；③ 只做最小修复（启动收敛接线 + 提交竞态 + `auto_requeued` 标记语义），**不做持久化队列**。冻结范围见文末「用户确认与冻结范围」。确认前未修改业务代码、未执行写操作、未重启服务、未批量重排索引。

### 复现证据（2026-11-06，当前部署版本，全部只读）

- 用户截图 `Screenshot 2026-11-06 at 02.41.52.png`：文档 `2021-Conference-End-to-End-Spectro-Temporal-…pdf` 显示「已索引 · 0 页」、`v1 已索引 · 55 片段`（绿）、`v2 索引中 0%`（紫），「重建索引 / 删除」按钮可见。
- `GET /api/kb/papers`：`document_id=1b967ed8638e46569d36e3f6565c51eb`、`status=indexed`、`page_count=0`、`chunk_count=55`；`chunkers.v1={status:indexed, chunk_count:55, progress:100, error:null}`；`chunkers.v2={status:indexing, chunk_count:0, progress:0, error:null}`；`auto_requeued_chunkers.v2="2026-11-05T15:47:39+00:00"`；顶层 **`error=null`**。
- `GET /api/kb/health`：`qdrant=true`、`embedding=true`、`v2_llm.available=true`（qwen3.8-27b-q4）、`generation.ready=true` → 依赖与索引代次门当前均可用，**不是模型/Qdrant 故障**。
- `deploy/run.log:1491450`：导入时 `论文导入失败：索引成功但收尾失败（代次漂移/元数据写回） … 索引返回=v1=indexed; v2=pending 异常=ManifestStoreError: INDEX_FINALIZE_REQUIRED` → v1 成功、v2 未启动，`page_count` 未写回（历史代次门未 finalize 故障期）。
- `deploy/run.log:1506559`：用户点「重建索引」后 `POST /api/kb/documents/1b967ed…/reindex 202 Accepted`；此后日志**只有前端轮询 GET**，无任何索引任务执行/完成/失败记录，随后出现 FastAPI 启动 warning（服务重启）。
- 全库扫描：共 **13 个切分版本卡在 `indexing 0%`**（12 篇文档，其中 `1a3c542b…`、`8cd741ab…` 两篇 v1+v2 双卡）。**非单篇问题。**

### 根因链条

1. **任务不持久化**：`backend/app/knowledge_base/infrastructure/tasks.py` 用模块级 `ThreadPoolExecutor(max_workers=1)` + 内存字典 `_running` 承载全部索引任务；`submit_document_reindex()`（`application.py:846-857`）**先把状态写成 `indexing`**，再提交到该线程池。
2. **重启丢任务**：服务重启（`launchctl kickstart -k` / 部署）杀掉线程，`_running` 与队列消失，但 `papers.json` 里已落盘的 `indexing 0%` 不会回滚 → 进度条永久卡住。
3. **启动收敛函数从未接线**：`store.mark_interrupted_tasks()`（`store.py:785-810`）与 `tasks.mark_interrupted_on_startup()`（`tasks.py:148-154`）都已实现，docstring 明写「启动时调用：把残留的 indexing 标记失败」，但**全仓无任何调用点**；`main.py` lifespan（:29-86）只调了 `recover_paper_catalog_searches` / `recover_research_tasks` / `require_generation` / `recover_failed_reindexes` / `recover_literature_map_jobs` / `start_warmup` / `start_capability_scheduler`，**漏掉了它**。
4. **自愈只看 failed**：`recover_failed_reindexes()`（`application.py:861-907`）只遍历 `iter_failed_chunkers()`（`status=failed`），对 `indexing` 不处理；即便收敛成 `failed`，`is_chunker_auto_requeued()` 也会因本文已写过 `auto_requeued_chunkers.v2` 而跳过 —— 防重启风暴的幂等标记把「被中断的重排」误判成「已给过机会」。
5. **前端持续误报**：`chunkers.v2.status=indexing` 使卡片一直显示「索引中 0%」；`isFailed=false` 时按钮文案为「重建索引」而非「重试」（`frontend/app.js:6476-6479`），用户重试后又可能被下一次重启打断。
6. **v1 可用、v2 不可用**：顶层 `status` 由 v1 推导（`store.py:806-807`），所以文档看似「已索引」，实际 v2 检索无片段。

### 目标

① 让该文档与另外 12 个卡住版本恢复为可用索引；② 服务重启后不再出现永久 `indexing 0%`；③ 失败态对用户可见、可自助重试。

### 数据模型与接口（拟）

- 不新增表/字段/迁移；不改 `papers.json` schema；不改 `GET /api/kb/papers`、`GET /api/kb/health`、`POST /api/kb/documents/{id}/reindex` 的响应契约。
- 在 `main.py` lifespan 中，于 `recover_failed_reindexes()` **之前**调用 `tasks.mark_interrupted_on_startup()`，把残留 `indexing` 收敛为 `failed`（带「服务重启导致中断」原因）。
- 收敛时清除该 `(document, chunker)` 的 `auto_requeued_chunkers` 标记（或等价机制），使 spec-036 Task06 的一次性机会重排能用于「被重启打断的任务」；同时保留「真正跑失败过」不无限重试的语义。**必须区分两类 failed**。
- `submit_document_reindex()` 消除「先写 `indexing` 再提交」竞态：`submit_index_task()` 返回 False 时不得把状态改成 `indexing`，返回明确 `INDEX_ALREADY_RUNNING`；提交异常时回滚为 `failed` 并记录原因。
- 前端：卡片对「上次因服务重启中断」的 failed 显示可操作提示与「重试」按钮；启动收敛后不再残留「索引中 0%」。

### 边界与明确不做

- 不改切分算法（v1/v2 chunker）、不改 embedding / LLM 模型、不改 Qdrant collection 拓扑与代次门（`FinalizeBundleStore` / `require_generation`）逻辑。
- 不把任务队列改为持久化队列（Celery / DB outbox 等），不做分布式调度。
- 不自动无限重试；仍坚持「每 (document, chunker) 一次机会」，只补「被中断重排」的判定。
- 不改知识库检索、引用、生成链路，不改文献地图 Task11 逻辑。
- **确认前不批量重排 13 个任务、不修改 `papers.json`、不重启服务。**

### 验证方式（确认后执行）

1. **一次性运维恢复**（写操作，仅确认后）：收敛残留 `indexing` → 重排 13 个版本（或先修启动恢复再重启由自愈接管），逐个 `GET /api/kb/papers` 核对 `chunkers.*.status=indexed` 且 `chunk_count>0`，落盘请求、响应、实体 ID、最终状态与产物路径。
2. 后端定向：启动收敛接线、`auto_requeued` 清除语义、`submit_document_reindex` 竞态、重启模拟（先写 `indexing` 再启动 → 收敛且重排）、真失败不无限重试。
3. 前端定向：失败态文案 /「重试」按钮、无残留「索引中 0%」。
4. 真实服务 E2E：重启服务 → `/api/kb/health 200` → 目标文档 `chunkers.v2` 由 `indexing 0%` 变为 `indexed` 且有片段 → 浏览器硬刷新核对卡片。
5. 人工验收：逐步点击「重试」、点击后提示、等待条件、完成态判据、失败恢复与产物查看路径。

### 用户确认与冻结范围（2026-11-06）

用户批复「这个确认做」，三点**全部按默认是**：

1. **批量恢复**：确认后一次性恢复全部 13 个卡住版本，不只截图这一篇。
2. **自动重排一次**：启动收敛成 `failed` 后允许走既有 `recover_failed_reindexes()` 的一次性机会重排；不无限重试。
3. **最小修复**：仅 ① `main.py` lifespan 接线 `tasks.mark_interrupted_on_startup()`；② 消除 `submit_document_reindex()` 的「先写 `indexing` 再提交」竞态；③ 收敛时区分「被重启打断」与「真失败」的 `auto_requeued_chunkers` 标记语义；④ 前端失败态可操作提示与「重试」。**不做持久化队列 / Celery / DB outbox / 分布式调度**。

**冻结的实现边界**（只读核实，绝对路径 + 行号）：

| # | 文件 | 改动点 |
|---|---|---|
| B1 | `backend/app/main.py` | `:15-18` 增加 `tasks` 导入；`:59` `recover_failed_reindexes()` **之前**插入 `tasks.mark_interrupted_on_startup()`（沿用每段 try/except 只记日志、不阻塞启动） |
| B2 | `backend/app/knowledge_base/application.py` | `:845-857` 把 `update_chunker_state(status=indexing)` 移到 `submit_index_task()` 返回 True 之后；返回 False / 提交抛异常时不写 `indexing`，回滚 `failed` 并给明确原因（可复用 `:1224-1236` 既有回滚范式） |
| B3 | `backend/app/knowledge_base/infrastructure/store.py` | `:785-810` `mark_interrupted_tasks()` 收敛 `indexing → failed` 时，仅对本次因「服务重启导致中断」的版本清除 `auto_requeued_chunkers[chunker]`，让 B1 之后的自愈重排能生效；**真失败不动标记**，保留防重启风暴 |
| F1 | `frontend/app.js` | `:6417-6425` / `:6473-6479` / `:6513-6519`：被重启打断的 failed 显示可读提示 +「重试」；收敛后不再残留「索引中 0%」。不改 `POST /reindex` 契约、不改轮询间隔 |
| F2 | `frontend/styles.css` | `#kb-view` 作用域新增 `.kb-item-error-restart` / `.kb-item-hint` 两条失败态与兜底提示样式（评审 A-9 已补反向 DOM 断言） |
| V1 | `frontend/index.html` | `app.js?v=70→71`、`styles.css?v=68→69`，同步全部版本断言 |

**明确不做**（沿用上节「边界与明确不做」）：不改切分算法/embedding/LLM/Qdrant 代次门、不新增表字段迁移、不改 `papers.json` schema、不改 `GET /api/kb/papers` / `GET /api/kb/health` / `POST /reindex` 响应契约、不改知识库检索与文献地图逻辑、不自动无限重试。

### 风险区（2026-11-06，架构评审 A-1 / A-8 强制约束）

1. **不做持久化队列是用户裁决**：用户 2026-11-06 明确「只做最小修复，不做持久化队列」。因此索引任务仍由 `tasks.py` 的模块级单线程池 + 内存 `_running` 承载，**服务重启仍会丢失正在运行的线程任务**；代价由「启动收敛 `mark_interrupted_on_startup()` + 一次性自愈重排 `recover_failed_reindexes()`」兜住，不再出现永久 `indexing 0%`，但需要一次重启触发。
2. **防重启风暴上界**：每次启动、每个 `(document, chunker)` 最多获得 **1 次**自动重排机会，由顶层 `auto_requeued_chunkers` 幂等标记保证；收敛时仅清除「被本次重启打断」版本的标记，真 `failed` 记录的标记一律保留。
3. **残余窗口（有界，不是缺陷）**：`submit_document_reindex()` 返回到 `mark_chunker_auto_requeued()` 落盘之间不是原子的；若进程恰在该毫秒级窗口被杀，下次启动会先收敛再重排一次，即**重复重排一次**。后果有界：终态仍收敛到 `indexed` 或 `failed`，不会永久卡 `indexing 0%`。彻底闭合需持久化队列或「标记与状态同一次原子落盘」，均已排除在本次范围外。
4. **提交与状态写入的窄窗口**：`submit_index_task()` 返回 True 与写 `indexing` 之间，若 runner 瞬间跑完并落盘终态，提交方不得覆盖；实现用「提交前采样 `before_status`、提交后比对 `current_status`，仅当两者相同才写 `indexing`」。若 runner 在采样窗口内写回与 `before_status` 同名的状态（要求纳秒级跑完整轮索引，单线程池 + LLM 实际不可达），仍会由启动收敛兜底。
5. **代次门瞬时竞态（运维观测）**：2026-11-06 批量恢复时，首个任务写 manifest 期间 `_live_manifests_digest()` 短暂失配，导致同一批其余 11 个 `POST /reindex` 返回 503 `INDEX_FINALIZE_REQUIRED`；串行重试后全部 202 并完成。属既有代次门 fail-closed 设计，未改其逻辑（明确不做），批量运维需串行提交。证据见 `docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery*.json`。
6. **已知前端性能基线**：`tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions` 在本机稳定超阈（`maxGestureWallMs` 1.4–1.9s vs 1s），干净 HEAD 同样失败、fixture 自包含不加载本批次资源，与本批次无因果，单独立项跟踪，不放宽阈值掩盖。

**分端执行**：后端 `backend-dev`（B1–B3 + 后端定向测试）；前端 `frontend-dev`（F1 + V1 + 前端定向测试），**跨端拆两次分派**；随后 `backend-reviewer` / `frontend-reviewer`、`backend-tester` / `frontend-tester` 分端评审回归；最后由主会话执行一次性运维恢复 13 个版本、重启服务与真实 E2E，`tester` 汇总验收、架构师签字后收口。
