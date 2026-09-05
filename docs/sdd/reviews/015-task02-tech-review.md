# Spec 015 Task 02 数据源子批次技术复核

- 评审者：当前协作 Agent
- 角色：独立开发主管（Tech Lead）
- 评审时间：2026-09-04 15:53:26 CST
- 评审范围：`docs/sdd/specs/015-security-paper-discovery.md`、`docs/sdd/plans/015/task-02-validate-baseline-and-sources.md`、`docs/sdd/plans/015/task-03-conference-registry-and-retrieval.md`、`docs/sdd/reviews/015-task02-baseline-review.md`、`backend/app/services/article_search.py`
- 约束：只读复核；不修改业务代码、Spec015 用户已有修改；不执行 `reset`、`clean`、`stash`、`push`

## 结论：条件放行

本次复核结论为：**条件放行（仅放行 Task03 中“不依赖 live DBLP Venue Search”的子范围）**。

- `DBLP publication search`：**可带约束放行**。`429/500/503/timeout` 与 `conf/uss` 混入 `SOUPS` 说明当前 live 数据源**不适合按“stream 命中即可信”直接编码**，但这更像“必须固化降级与过滤契约”的门禁，而不是把整个 Task03 一刀切打成不可继续。只要内置会议使用冻结的 `stream + venue_aliases + 类型过滤 + warning code` 契约，会议召回本身可以继续。
- `DBLP Venue Search`：**当前仍是 No-Go**。Task 02 计划把 `venue/api` 正向验证列为显式步骤，tester 也未拿到任何成功样本；因此“自定义会议搜索/新增”这条链路不能宣称已放行。
- `OpenAlex`：**可放行**。可以作为 DBLP 召回后的 DOI 优先补全层，标题仅能做 DBLP 候选兜底补全，不能替代会议/年份约束，更不能单独承担排序或主召回。

因此，**Task02 整体不能宣称 Full Go**；但 **Task03 可以在收紧范围后继续**：先做四个内置会议种子、DBLP 论文召回、主会过滤、去重、OpenAlex 补全与搜索会话持久化，把依赖 live Venue Search 的“会议搜索/新增”明确保留为阻塞项。

## 关键依据

1. spec 已明确 DBLP 会议流会混入 Workshop/Poster/Demo，不能只判断 `stream id`，并要求 `venue_aliases` 白名单过滤；这与 tester 实测 `conf/uss` 混入 `SOUPS @ USENIX Security Symposium` 相互印证。见 `docs/sdd/specs/015-security-paper-discovery.md:19-21`、`docs/sdd/reviews/015-task02-baseline-review.md:35-36`、`docs/sdd/reviews/015-task02-baseline-review.md:91-93`。
2. Task 02 当前把 `DBLP Venue Search` 成功验证写成显式步骤，而 tester 本轮只拿到 `429/503`，没有成功样本，所以这部分必须维持阻塞。见 `docs/sdd/plans/015/task-02-validate-baseline-and-sources.md:21-23`、`docs/sdd/plans/015/task-02-validate-baseline-and-sources.md:45-48`、`docs/sdd/reviews/015-task02-baseline-review.md:49-56`。
3. Task 03 当前同时包含“内置会议召回”和“用户会议必须来自 Venue Search 结果”两类工作，因此**不能按原文整包放行**；需要把依赖 Venue Search 的子范围单独挂起。见 `docs/sdd/plans/015/task-03-conference-registry-and-retrieval.md:18-20`、`docs/sdd/plans/015/task-03-conference-registry-and-retrieval.md:32-37`、`docs/sdd/plans/015/task-03-conference-registry-and-retrieval.md:60-63`。
4. 当前代码里的 OpenAlex 仅支持宽召回 `search=`，且 `_request_json()` 只有通用重试/超时，没有显式 `User-Agent` 或 DBLP 专用契约，所以 OpenAlex 只能做补全，DBLP 客户端也必须在 Task03 内单独落地。见 `backend/app/services/article_search.py:44-55`、`backend/app/services/article_search.py:79-98`。

## 判定细化

### 1. DBLP 的 429/500/503/timeout 与 stream 混流是否构成当前 No-Go

结论：**对“Task02 整体 Full Go”是 No-Go；对“Task03 的内置会议召回子范围”不是绝对 No-Go。**

- 构成 No-Go 的部分：
  - `venue/api` 没有成功样本，不能证明“用户搜索并新增非内置会议”可稳定工作。
  - `conf/uss` 已证明会混流；如果设计仍允许“只认 stream”，那就是明确的 No-Go。
- 不构成绝对 No-Go 的部分：
  - 对四个内置会议，spec 已经给出更强的约束：`stream + venue_aliases + 类型过滤 + 单源 warning 降级`。这套契约足以支撑先做论文召回与补全。
  - `429/500/503/timeout` 说明必须有显式 `User-Agent`、有限重试、退避、warning code 和“全部源都失败才整体失败”的降级，不等于内置会议召回完全不能实现。

### 2. OpenAlex 补全契约是否可放行

结论：**可放行，但只能按补全层契约使用。**

- 放行条件已基本齐备：
  - spec 已写明“DBLP 主召回，OpenAlex 补摘要/OA/PDF”，且“单源失败尽量返回可用结果”。见 `docs/sdd/specs/015-security-paper-discovery.md:151-156`、`docs/sdd/specs/015-security-paper-discovery.md:174-175`、`docs/sdd/specs/015-security-paper-discovery.md:210-213`。
  - tester 证据表明 DOI 精确命中稳定、伪 DOI 返回 `0` 可作为 warning 降级；标题搜索宽召回但相关性不足。见 `docs/sdd/reviews/015-task02-baseline-review.md:58-66`。
- 不允许的误用：
  - 不能让 OpenAlex 代替 DBLP 的会议/年份约束。
  - 不能把 OpenAlex `search=` 的返回直接拿来排序上屏。
  - 不能因为 OpenAlex 超时/0 hit 就让整次搜索失败，只能降级为 DBLP-only。

### 3. Task03 是否可在不依赖 live Venue Search 的情况下继续

结论：**可以，但必须按“限缩范围”继续；按当前 Task03 原文则不能完整继续。**

可继续的部分：

- 四个内置会议种子与持久化存储
- DBLP publication search 客户端
- 主会过滤、去重、搜索会话、候选 ID
- OpenAlex 补全与 warning 降级
- `/api/papers/search`
- `/api/papers/conferences` 中不依赖 live venue 的只读/内置启停能力

暂不放行的部分：

- `/api/papers/conferences/search`
- 基于 live DBLP Venue Search 的用户会议搜索、新增、保存受控 `dblp_stream`
- 任何把“当前 live venue 成功”当成既成事实的验收项

也就是说，**Task03 可以先实现“内置会议召回闭环”，但不能在当前证据下宣称“自定义会议闭环”也能一起完成。**

## 需要的最小门禁修订

以下修订是我认为能把当前结论落到单一真相里的**最小集合**：

1. 在 Task 02 结论里明确拆分两个门禁：
   - `DBLP publication search + OpenAlex enrichment = Conditional Go`
   - `DBLP Venue Search for custom conferences = No-Go / blocked`

2. 在 Task 03 文档中把范围拆开写清楚：
   - 先放行“内置会议 registry + `/api/papers/search`”。
   - 把“会议搜索/新增”显式标成依赖 `venue/api` 正向样本解锁；未解锁前不得验收“用户会议可搜索、新增、删除”。

3. 冻结 DBLP 过滤与降级契约：
   - `conf/uss` 不得仅凭 stream 放行，必须绑定 `venue_aliases` 白名单。
   - 未知类型默认拒绝或标记 warning，不直接放行。
   - `429/500/503/timeout` 必须映射为稳定 warning/error code；只有全部召回源失败时整次搜索才失败。
   - Task03 新客户端必须带显式 `User-Agent`，不能继续沿用当前通用实现。

4. 冻结 OpenAlex 使用边界：
   - DOI 优先、标题兜底。
   - 标题兜底仅作用于 DBLP 已召回候选。
   - `0 hit`、超时、5xx 一律作为 warning 降级，不阻断 DBLP 结果返回。

## 风险与后续动作

- 当前最大风险不是 OpenAlex，而是**把 Venue Search 未验证和 USENIX 混流问题一起带入 Task03 原始范围**，这样实现者会误以为“自定义会议链路也已可开工”。
- 如果架构师接受上面的最小修订，我建议：
  - 先继续 Task03 的内置会议召回子任务；
  - 把 live Venue Search 留在 Task02 持续验证，或单独拆成一个明确阻塞子项；
  - 在拿到至少 1 个成功 `venue/api` 样本前，不要让 `junior-dev` 接“自定义会议新增”那部分代码。

## 最终裁定

**条件放行。**

- 放行：OpenAlex 补全、内置会议 registry、DBLP publication search、主会过滤、去重、搜索会话。
- 不放行：live DBLP Venue Search、自定义会议搜索/新增闭环。
- 当前 Task03 若不改范围说明，仍会误导实现，不能按“整任务无条件 Go”执行。
