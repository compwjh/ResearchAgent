# Spec 014 — 知识库本地 Rerank 重排

## 状态

**当前状态：`实施中`（2026-09-02；Task 03–07 已完成，Task 08 等待 spec-013 明确 commit）**

> 进入实施前已用当前未提交代码完成首页、健康接口与全量测试验证；不得通过回滚、stash 或清理工作树保护/修复 spec-013。
> 状态变更须同步追加 `docs/sdd/spec-status-changelog.md`。

## 一句话目标

在个人知识库的 dense + sparse + RRF 召回之后增加本地 Qwen3-Reranker 批量重排，使最终送入回答模型的片段更贴近用户问题；Reranker 关闭或异常时必须自动回退到原 RRF 顺序，知识库问答继续可用。

## 背景与实测证据

1. 当前 `backend/app/services/kb/retrieve.py` 已预留 `rerank()`，但它把每个片段逐条交给聊天模型，要求输出 0–10 整数。这不是 Qwen3-Reranker 的原生用法，且会产生 N 次串行模型调用。
2. 当前链路先把 RRF 结果截断到最终 `top_k`，再调用 rerank。重排只能改变这几条的顺序，无法从更大的候选池中找回更相关片段。
3. 本机已安装 `dengcao/Qwen3-Reranker-0.6B:Q8_0`。实测其 Ollama chat 输出、现有打分 prompt 和 logprobs 路径不能稳定得到可用的相关性分数；将其现有 GGUF 直接交给 llama.cpp rerank 路径时，明显不同文档仍得到相同分数。因此该包保留，但不作为本功能的运行时模型。
4. Qwen3-Reranker 应使用 yes/no 分类 logits 或兼容的专用 rerank 接口。本 spec 采用 llama.cpp 原生 `/v1/rerank`，目标模型为 `ggml-org/Qwen3-reranker-0.6B-Q8_0-GGUF:Q8_0`。
5. spec-013 正由另一 Agent 在独立任务中开发。本 spec 先从共同基线独立推进，待 spec-013 完成后再接入其 KB 阶段观测，避免互相覆盖未提交文件。

## 回滚点（Rollback Baseline）

| 项 | 值 |
|---|---|
| 基线 commit | `294138ce9e709d3ed4213b3f1fcb11286f05dbdc`（短 `294138c`） |
| 目标分支 | `feature/spec-014-kb-reranker` |
| 完整关闭 | `RERANKER_ENABLED=false`，不发送任何 rerank 请求 |
| 运行时降级 | Reranker 停机或失败时直接使用 RRF 结果 |
| 数据回滚 | 不改 Qdrant schema、不写回 rerank 分数，无索引迁移与数据回滚 |

> 实施时使用独立 worktree；不得清理、覆盖或提交当前 spec-013 Agent 的工作树改动。

## 数据模型与配置

### 配置项

| 配置 | 类型 | 默认值 | 约束 |
|---|---|---|---|
| `RERANKER_ENABLED` | bool | `true` | `false` 时完全跳过探针和重排请求 |
| `RERANKER_BASE_URL` | str | `http://127.0.0.1:11435` | 仅允许本机服务；末尾 `/` 需规范化 |
| `RERANKER_MODEL_PATH` | str | `<项目>/data/models/qwen3-reranker-0.6b-q8_0.gguf` | llama-server 启动使用的已校验本地 GGUF；不得传给 API model 字段 |
| `RERANKER_API_MODEL` | str | 空 | Task 02 实测请求可省略 `model`；配置非空时才发送，不得与模型来源混用 |
| `KB_RERANK_CANDIDATES` | int | `20` | 最小 1；实际不超过 RRF 返回数量 |
| `RERANKER_CONNECT_TIMEOUT_SECONDS` | float | `2` | 非正值回退默认值并告警 |
| `RERANKER_READ_TIMEOUT_SECONDS` | float | `60` | 非正值回退默认值并告警 |
| `RERANKER_SERVER_BIN` | str | 空 | 可选；未配置时依次查 PATH 与 Ollama App 内置二进制 |

### 运行时结果

`Hit` 可增加仅存在于当前请求内的可选字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `rerank_score` | float / null | 服务返回的相关性分数；未执行或降级时为空 |
| `rerank_rank` | int / null | 重排后的 1-based 名次；未执行或降级时为空 |

这些字段不得写回 Qdrant payload，不改变 point id、chunker 或论文元数据。

### 运行状态

| 字段 | 类型 | 含义 |
|---|---|---|
| `enabled` | bool | 配置是否启用 |
| `available` | bool | HTTP 与排序质量探针是否通过 |
| `backend` | str | 固定为 `llama.cpp` |
| `model` | str | 当前配置的兼容模型标识 |
| `reason` | str / null | 禁用或不可用原因；可用时为空 |

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败与降级 |
|---|---|---|---|
| llama.cpp `POST /v1/rerank` | `{model, query, documents}`；一次包含全部候选 | 每项至少含原候选 `index` 与有限数值 `relevance_score` | 连接、超时、协议或分数校验失败时不重试当前问答，回退 RRF |
| `POST /api/kb/ask` | 沿用现有 `question/model/top_k/chunker` | SSE 协议、回答文本与引用格式保持兼容 | Reranker 失败不得改变 HTTP/SSE 成功语义 |
| `GET /api/kb/health` | — | 保留 `reranker: bool`，新增 `reranker_detail` | 探针失败仍返回健康响应，在 detail 中报告原因 |

### 检索顺序

1. dense 与 sparse 两路各按 `KB_CANDIDATE_POOL` 召回，默认各 30 条，并沿用相同的 paper/chunker/citation 过滤器。
2. 使用现有 RRF 融合与去重。
3. 从 RRF 排名中取最多 `KB_RERANK_CANDIDATES` 条，默认 20 条。
4. 对候选执行一次批量 `/v1/rerank`；按 `relevance_score` 降序排列，分数相同时保持 RRF 原顺序。
5. 成功时返回重排后的最终 `top_k`；失败、禁用或候选不足 2 条时返回 RRF 前 `top_k`。

## 边界（每条之后会变成一条测试）

- `RERANKER_ENABLED=false` 时不得做健康探针或重排网络请求。
- collection 不存在、问题为空或候选为空时沿用现有返回语义，不调用 Reranker。
- 候选只有 1 条时直接返回；候选少于配置上限时只发送实际条数。
- `top_k` 大于候选数时返回全部实际候选，不补空记录、不重复片段。
- HTTP 连接失败、超时、非 2xx、响应不是 JSON、缺少结果列表，全部回退 RRF。
- 返回的 `index` 必须是整数、唯一、位于候选范围内；缺失、重复或越界均视为整批无效。
- `relevance_score` 必须是有限数值；NaN、Infinity、字符串或缺失均视为整批无效。
- 质量探针使用至少 3 条相关度明显不同的文档；若分数完全相同或最相关文档未排第一，服务判为不可用。
- 正常业务文档出现同分时不判失败，按 RRF 原顺序稳定排序；“同分即失败”只用于固定质量探针。
- Reranker 失败不得中断 `/api/kb/ask` 的 SSE，不得吞掉已生成内容。
- 必须保留 spec-012 的 chunker v1/v2 隔离、citation 意图过滤、page/page_end 与引用格式。
- 日志和 spec-013 观测只记录模型名、候选数、片段标识、耗时与降级原因，不记录完整片段正文。
- llama.cpp 仅监听 `127.0.0.1`。默认端口占用时脚本选择可用端口，并把实际 URL 传给应用。

## 明确不做（划出范围，防 AI 自由发挥）

- 不使用云端 Rerank API，不增加 API Key 或计费依赖。
- 不把 Qwen3-Reranker 当普通 ChatOllama 对话模型使用。
- 不删除、改名或覆盖现有 `dengcao/Qwen3-Reranker-0.6B:Q8_0`。
- 不更换 `bge-m3`，不调整其 `num_batch=1024`，不改变 dense/BM25/RRF 算法。
- 不重建旧论文索引，不迁移 Qdrant，不拆分 collection，不把 rerank 分数持久化。
- 不改变 v1/v2 chunker、citation 规则、上传/重建/删除流程或回答模型。
- 不增加前端模型选择、候选数、阈值或权重调节面板；用户无需手动操作 rerank。
- 不提供公网或局域网 Reranker 服务，不做多用户鉴权与远程部署。
- 不因 Reranker 不可用而阻止知识库提问。
- 不提前修改或整理 spec-013 Agent 尚未完成的代码；只在专门集成任务中处理。

## 评审强制约束（实现必须遵守）

> 来源：`docs/sdd/reviews/014-requirement-review.md` 与 `docs/sdd/reviews/014-tech-review.md`。两份评审均通过（附意见），以下约束漏做即不得进入下一门禁。

- **当前现场保护**：实施前运行门禁实测首页、`/api/health`、`/api/kb/health` 均为 200，Langfuse v4 健康，全量测试 `253 passed`。当前工作树禁止 `git reset --hard`、`git clean`、`git stash`、覆盖式 checkout 或批量复制。
- **工作树隔离**：spec-014 worktree 从明确 commit 创建，只搬运列明的 014 spec、plan、review 与状态记录；spec-013 代码只通过其最终明确 commit 集成。
- **Go/No-Go**：Task 02 必须使用最终二进制和目标 Q8_0 模型完成中英文探针、20 候选热请求、有限分数与稳定排序验证。HTTP 200 不代表通过；失败必须停止 Task 03–09，禁止退回聊天 prompt 打分。
- **模型契约**：模型启动来源与 API model 标识分开配置；Task 02 用实际启动参数与 `/v1/rerank` 响应回填合法值，不允许一个变量承担两个含义。
- **批量与映射**：一次问答最多一次 rerank 请求；index 必须是非 bool 整数且唯一/不越界，score 必须是非 bool 有限数值；同分保持 RRF 顺序，整批异常回退原对象顺序。
- **Fail-open 与熔断**：当前问答不重试；连接/读取超时上限 2 秒/60 秒。不可达或质量探针失败后至少缓存负状态 30 秒，避免每个问答重复等待。禁用及 0/1 候选零网络请求。
- **URL 与隐私**：base URL 只接受 HTTP loopback；日志、reason、span 不得包含 query、完整文档、异常堆栈、环境变量或敏感命令行。
- **生命周期所有权**：动态端口必须通过明确状态文件或 stdout 协议传给 FastAPI，禁止依赖子脚本 `export`；只终止 PID 与启动标识均匹配的本项目进程，覆盖前台 Ctrl+C、后台 stop、探针失败和陈旧 PID。
- **health 并发缓存**：使用单调时钟和并发保护；30 秒内并发请求只触发一次探针，disabled 不探针，`reranker == enabled && available`。
- **冻结质量集**：不少于 10 个问题及目标片段必须在首次查看 rerank 排名前落盘，禁止事后删题或改标签。
- **动态回归基线**：最终测试数不得低于 `max(253, spec-013 最终验收通过数)`，覆盖率不得低于 80%，不得跳过 spec-011/012/013 用例。
- **模型登记与集成**：编码分派前把已实测存在的 `qwen3.8:27b-mlx` 补入 `MODEL_REGISTRY.md`；Task 08 只集成 spec-013 明确 commit，并验证 Langfuse/Reranker 四种启停组合及全仓冲突标记 0 命中。

## 验收方式

| 验收点 | 验证方法 |
|---|---|
| A1 运行时可用 | llama.cpp `/v1/rerank` 在本机启动，固定三文档探针通过 |
| A2 批量重排 | 一次请求发送全部候选，明显相关片段排在无关片段前 |
| A3 候选池生效 | RRF 最多 20 条进入重排，最终才截取 `top_k` |
| A4 稳定映射 | 服务返回乱序 index、合法同分时，结果映射和稳定排序正确 |
| A5 异常降级 | 停服、超时、非法 JSON、重复/越界 index、非法分数均回退 RRF |
| A6 API 兼容 | 现有 `/api/kb/ask` 请求、SSE 和引用显示不变 |
| A7 健康可解释 | health 能区分禁用、不可达、质量探针失败和可用 |
| A8 召回质量 | 不少于 10 个标注问题上，MRR@5 不低于 RRF，且至少 1 个问题的目标片段排名提升 |
| A9 性能资源 | 记录冷启动、20 条热请求延迟与内存峰值；热请求不触发 60 秒超时且本机无 OOM |
| A10 观测集成 | spec-013 完成后，KB trace 含 rerank 候选数、输出数、耗时、降级状态与原因 |
| A11 回归 | 全量测试不少于 `max(253, spec-013 最终验收通过数)`，项目覆盖率不低于 80% |
| A12 运行时交付 | 实际启动 Reranker 与 FastAPI，首页/health/真实 KB 问答均验证成功 |

## 产品使用步骤（PM 补充）

### 正常用户旅程

1. 用户按项目原有方式启动本地服务，看到应用首页可以打开，知识库健康状态显示 Reranker 已启用且可用；这表示问答服务与本地重排能力均已准备完成。（映射 A1、A7、A12）
2. 用户继续使用已有知识库，或按原流程上传论文，无需重新建立历史索引，也无需选择 Rerank 模型或调整额外参数；原有论文列表、分块版本和上传操作保持不变。（映射 A6、A11）
3. 用户在知识库页面按原方式输入问题并提交，看到回答仍以原有流式形式逐步显示，引用样式和跳转方式保持不变。（映射 A6、A12）
4. 用户无需额外操作即可获得经过自动重排的检索结果；对明确相关的问题，答案引用应优先来自更相关的片段，且不能出现重复、错位或无效引用。（映射 A2、A3、A4、A8）
5. 用户连续提出正常问题，看到回答在可接受时间内开始并完成；本机不应因重排出现长时间无响应、内存耗尽或应用退出。（映射 A9、A11）
6. 用户在观测页面查看本次知识库问答，能够确认是否执行了 Rerank，并看到候选数量、输出数量、耗时、降级状态和原因；页面不得暴露完整问题或文档正文。（映射 A10）

### 降级与恢复旅程

7. 用户停止 Reranker 后再次查看健康状态，看到知识库服务仍在线，同时 Reranker 显示不可用及可理解的原因；健康检查本身不能导致整个应用显示故障。（映射 A5、A7）
8. 用户在 Reranker 不可用时按原方式提问，仍能收到完整流式回答和引用；系统自动使用原有 RRF 顺序，不要求用户重试、切换模型或修改设置。（映射 A5、A6、A12）
9. 用户恢复 Reranker 服务并再次查看健康状态，看到状态从不可用恢复为可用；之后的新问题自动恢复重排，之前的论文和问答数据不受影响。（映射 A1、A7、A12）

### 边界与验收场景

10. 边界：用户关闭 Reranker 功能后查看健康状态，应看到“未启用”而不是“服务故障”；继续提问仍能得到原 RRF 回答，且不会出现额外等待。（映射 A5、A7）
11. 边界：知识库尚无可检索内容、问题为空或检索结果为空时，用户看到的提示与现有知识库行为一致，不出现 Reranker 错误或虚构引用。（映射 A5、A6、A11）
12. 边界：本次检索只有一个候选或候选少于请求数量时，用户仍只看到真实存在的结果，不出现重复片段或空白引用。（映射 A3、A4、A6）
13. 边界：Reranker 响应超时、格式异常或返回无效排序时，用户仍获得按原顺序生成的回答；健康状态和观测信息可说明发生了降级，但不暴露敏感内容或内部异常堆栈。（映射 A4、A5、A7、A10）
14. 验收人员使用首次排序前冻结的不少于 10 个标注问题进行对比，看到 Rerank 的 MRR@5 不低于 RRF 基线，并且至少一个问题的目标片段排名提升；不得通过事后删题或改标签制造通过结果。（映射 A8）
15. 验收人员完成冷启动、20 条候选热请求、内存峰值和全量回归检查，看到热请求未触发读取超时、本机无 OOM，且测试数量不低于动态基线、覆盖率不低于 80%。（映射 A9、A11）

## 执行配置（由架构师填写，落盘可查）

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订 spec、运行时选型、编排与落地校验 |
| 产品经理 | `qwen3.5:9b`（本地 Ollama） | 32k | `Task(pm)` | 补产品使用步骤与验收场景 |
| 开发主管 | `qwen3.8:27b`（本地 Ollama） | 32k | `Task(tech-lead)` | 需求/技术/验收评审、任务拆分与合并裁决 |
| 初级开发 | `gpt-5.6-luna` | 32k | `Task(junior-dev, reasoning=high)` | 剩余任务编码；每次最多 2 文件、150 行 |
| 测试 | `gpt-5.6-luna` | 32k | `Task(tester, reasoning=high)` | 剩余任务测试、基准、验收与 Bug 复现 |

> 业务 Reranker（非角色模型）：`ggml-org/Qwen3-reranker-0.6B-Q8_0-GGUF:Q8_0`，由 llama.cpp 专用 `/v1/rerank` 服务承载。

## 任务计划

> 任务 01 = 本 spec 的编写，不单独建任务文件。任务 02 起一任务一文件；详细步骤只写在任务文件中。索引见 [`plans/014/README.md`](../plans/014/README.md)。

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-014 | 本文件 | — | 完成 |
| 02 | 验证 Reranker 运行时（Go/No-Go） | [`task-02-validate-reranker-runtime.md`](../plans/014/task-02-validate-reranker-runtime.md) | 01 | 完成（Go） |
| 03 | 管理 Reranker 服务生命周期 | [`task-03-reranker-service-lifecycle.md`](../plans/014/task-03-reranker-service-lifecycle.md) | 02 | 完成 |
| 04 | 实现 Reranker 客户端 | [`task-04-reranker-client.md`](../plans/014/task-04-reranker-client.md) | 02 | 完成 |
| 05 | 接入知识库检索链路 | [`task-05-integrate-retrieval-pipeline.md`](../plans/014/task-05-integrate-retrieval-pipeline.md) | 04 | 完成 |
| 06 | 接入健康状态与前端展示 | [`task-06-reranker-health-status.md`](../plans/014/task-06-reranker-health-status.md) | 03, 04 | 完成 |
| 07 | 执行测试与质量基准 | [`task-07-reranker-tests-benchmark.md`](../plans/014/task-07-reranker-tests-benchmark.md) | 05, 06 | 完成 |
| 08 | 集成 spec-013 观测能力 | [`task-08-integrate-spec013-observability.md`](../plans/014/task-08-integrate-spec013-observability.md) | 05，且 spec-013 完成 | 待执行 |
| 09 | 评审、部署与复盘 | [`task-09-review-deploy-retro.md`](../plans/014/task-09-review-deploy-retro.md) | 07, 08 | 待执行 |

## 评审记录

> 初始不引用尚未生成的评审文件，下游只认真实落盘文档。

- 需求评审：[`docs/sdd/reviews/014-requirement-review.md`](../reviews/014-requirement-review.md)（结论：**通过（附意见）**；风险中；无硬阻塞）
- 技术评审：[`docs/sdd/reviews/014-tech-review.md`](../reviews/014-tech-review.md)（结论：**通过（附意见）**；风险高；Task 02 为硬 Go/No-Go）
- 验收评审：待评审（未执行）

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-02 | 用户 | 提出为个人知识库增加 Rerank；指定本机已有 `dengcao/Qwen3-Reranker-0.6B:Q8_0`，说明此前接入失败 |
| 2026-09-02 | 架构师(自身) | 检查现有逐条 ChatOllama 打分实现，并实测现有模型无法产生有效专用 rerank 分数 |
| 2026-09-02 | 用户 | 选择 llama.cpp 兼容运行时，并要求与正在开发的 spec-013 独立并行 |
| 2026-09-02 | 用户 | 要求仿照 spec-013 建立任务索引，task 详细内容独立落盘，spec 的任务计划章只保留标题与跳转链接 |
| 2026-09-02 | 架构师(自身) | 创建本 spec 与 `docs/sdd/plans/014/` 全部任务文件，状态置 `待确认` |
| 2026-09-02 | 用户 | 条件确认：先验证 spec-013 未提交代码能运行；若可运行则进行 spec-014；强调禁止回滚导致工作丢失 |
| 2026-09-02 | 架构师(自身) | 建立 `/tmp/pycharmmisc-spec013-wip-20260902-1912.tar.gz` 安全快照；当前代码实测首页、health、KB health 与 Langfuse 均正常，全量回归 `253 passed`，未执行 reset/clean/stash |
| 2026-09-02 | 开发主管(独立协作 Agent) | 需求与技术评审均通过（附意见），无当前硬阻塞；将 R1–R6/T1–T12 固化为本 spec 强制约束 |
| 2026-09-02 | 架构师(自身) | 条件已满足，按用户授权将 spec 从 `待确认` 转为 `已确认` |
| 2026-09-02 | 产品经理（当前协作 Agent） | 基于 A1–A12 补充正常启动、自动重排、停服降级、恢复及空候选等边界的产品使用步骤与可观察验收结果 |
| 2026-09-02 | 架构师(自身) | 创建隔离 worktree `/private/tmp/PyCharmMiscProject-spec014`，仅搬运 014 文档与评审；spec 转为 `实施中`，启动 Task 02 |
| 2026-09-02 | 架构师(自身) | Task 02 Go：官方兼容 GGUF 哈希验证通过；中英文与 20 候选探针通过，三次热排序稳定；临时服务已停止且 11435 端口释放 |
| 2026-09-02 | 架构师(自身) | 将运行契约固化为本地 `RERANKER_MODEL_PATH` 与可选 `RERANKER_API_MODEL`，启动 Task 03 生命周期实现 |
| 2026-09-02 | 架构师(自身) | Task 03 完成：真实模型通过质量探针、动态端口、幂等启停、禁用模式和 FastAPI 联合启停验证 |
| 2026-09-02 | 架构师(自身) | Task 04 完成：批量客户端及 25 个 mock HTTP 子场景通过，启动 Task 05 检索集成 |
| 2026-09-02 | 用户 | 指定剩余任务使用 Luna 模型、高推理强度 |

---
**六条自检**：①边界均可转为测试；②spec 说明需求、task 承载实施细节；③task 链接真实且依赖无环；④明确不做已划死范围；⑤执行配置五行齐全；⑥产品步骤可映射 A1–A12。
**收口自检**：见 `docs/sdd/SDD-GATE-CHECKLIST.md` §3；三份评审、验收签字、changelog、复盘、运行时部署全部完成后才能转 `已完成`。
