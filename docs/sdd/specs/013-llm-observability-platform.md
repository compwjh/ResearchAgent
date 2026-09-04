# Spec 013 — 本地 LLM 调用观测与性能评估平台

## 状态

**当前状态：`已完成`**

> 本 spec 涉及**重建 Python 虚拟环境**与**在本机常驻 4 个基础设施服务**，风险面显著大于常规功能开发。
> 因此 spec 中固化了「回滚点」与分阶段 Go/No-Go 关卡。
> 状态变更须同步追加 `docs/sdd/spec-status-changelog.md`。

## 一句话目标

把每次本地大模型调用都记录下来，能回看完整输入构成、输出与思考过程，并能像 Chrome 网络面板那样看到一次调用内部各阶段（排队 / 模型加载 / 预填充 / 首 token / 解码 / 网络）分别花了多少时间，从而定位「首 token 慢」到底慢在哪一环。

## 背景与要解决的问题

用户反馈：**对话模型输出速度太慢，首 token 花太多时间加载**。

现有链路 `ChatOllama`（LangChain 包装）→ LangGraph 流式输出，只能看到「总共花了多久」，无法回答：

- 首 token 之前的等待，是耗在**模型加载**（冷启动，权重读进显存）还是**输入预填充**（prefill）？
- LangChain 包装层自身引入多少额外开销？
- 知识库问答链路里，embedding / 检索 / 重排 / 生成各自占多少？

Ollama 的 `/api/chat` 原生返回 `load_duration` / `prompt_eval_duration` / `eval_duration` / `total_duration`（纳秒级），正是拆解这些问题的钥匙——但 `ChatOllama` 把字段丢弃了。**这是必须新增直连客户端的根本原因。**

## 回滚点（Rollback Baseline）

本次改动风险较高，先固化一个可完全回退的基线状态。

| 项 | 值 |
|---|---|
| 分支 | `feature/spec-011-knowledge-base-rag` |
| 基线 commit | `294138ce9e709d3ed4213b3f1fcb11286f05dbdc`（短 `294138c`） |
| 基线内容 | spec-011 知识库实现 + spec-012 切分 v2 实现 + 论文卡片布局修复 + 三份评审与两份复盘文档 |
| 基线验证 | 全量测试 `253 passed`；`/api/kb/health` 正常 |

**完整回滚命令**（丢弃本 spec 之后的全部改动，执行前确认无未提交的重要工作）：

```bash
cd /Users/wjh/ResearchAgent
git reset --hard 294138ce9e709d3ed4213b3f1fcb11286f05dbdc
```

**分阶段回退**（只回滚某一阶段时用）：

| 阶段 | 回退动作 |
|---|---|
| 仅关闭埋点 | 设 `LANGFUSE_ENABLED=false`，业务链路完全不受影响 |
| 撤销统计视图 | 删除 Langfuse 侧新增页面/路由，埋点数据不受影响 |
| 撤销 Python 升级 | `.venv-py39.bak` 重命名回 `.venv`（升级时保留的旧环境） |
| 撤销基础设施 | 执行 `deploy/langfuse/stop-infra.sh` |

> **Go/No-Go 关卡**：任务 02（非 Docker 部署）是整体可行性闸门。若 ClickHouse 官方二进制在 macOS 上无法稳定运行到 Langfuse 要求的 ≥25.12，则**立即停在本阶段**，回到需求评审重新选型，不再投入后续工作量。

## 关键调研结论（已核实的硬事实）

| 组件 | Langfuse v4 要求 | 本机现状 | 结论 |
|---|---|---|---|
| Docker | 官方仅提供 Compose | **未安装** | 不用 Docker，改命令行启动（用户拍板） |
| PostgreSQL | 15 最低，16 推荐 | brew `postgresql@17` 17.11 可装 | 满足 |
| Redis | 7.0 最低，7.2 推荐 | brew `redis` 8.10.1 可装 | 满足 |
| 对象存储 | S3 兼容 | brew `minio` 可装 | 满足 |
| ClickHouse | **25.12 最低，26.4 推荐** | brew 条目报错（`undefined method 'first' for nil`） | 只能走官方单文件二进制，**最高风险项** |
| Node | 24（`.nvmrc` 指定） | v26.7.0 | 需降到 24 |
| pnpm | 11.22.0（corepack） | 未安装 | 需装 |
| Python（SDK） | SDK ≥4.7.0 要求 **Python ≥3.10** | 项目 `.venv` = 3.9.7，pip 最高只给 3.7.0 | 必须升级项目 Python（用户拍板升 3.11） |
| 内存 / 磁盘 | 建议 4C16G | **36 GB / 385 GB 可用** | 充足 |

其他已核实要点：

- **v4 为全新部署无需三步迁移**：无历史数据，默认 `events_only` 写模式，schema 迁移启动自动应用。
- **SDK 版本决定实时性**：Python SDK <4.7.0 的数据走 dual-write 管道，**约 15 分钟延迟**；≥4.7.0 直写新表实时可见。故必须装 ≥4.7.0（当前最新 4.15.1）。
- **v4 的 ClickHouse 用户需要比 v3 更多 GRANT**（`DROP VIEW`、`ALTER ADD/MODIFY COLUMN`、`ALTER VIEW MODIFY QUERY`、`ALTER ADD/DROP/MATERIALIZE INDEX`，以及 `system.parts` / `system.mutations` / `system.tables` / `system.processes` / `system.query_log*` 的 SELECT），否则迁移报 `Not enough privileges`。
- **v4 UI 主视图改为 Observations**：trace 以 root observation 表示（表格默认过滤 `Is Root Observation = true`，即一行一个 trace），**span 瀑布图仍然存在**——即用户要的「甘特图」替代物，无需自研组件。
- **macOS 代理坑**：所有指向 `localhost:11434` 的 httpx 请求必须 `trust_env=False`，否则被系统代理截走返回 503（项目 `ollama.py` 已记录此坑，直连客户端必须继承）。

## 数据模型

### 一次调用的 span 结构（对话链路）

```
trace (root observation)
└── span  "chat_request"                 # 请求接入，tags: route / model / session
    └── generation "ollama_chat"          # input=完整 prompt 组成, output=正式输出
        ├── span "phase:load"             # 模型加载（服务端 load_duration）
        ├── span "phase:prefill"          # 输入预填充（服务端 prompt_eval_duration）
        ├── span "phase:first_token"      # 首 token（客户端实测）
        ├── span "phase:decode"           # 逐段解码（服务端 eval_duration）
        └── span "phase:overhead"         # 网络+框架开销 = client_wall_ms - server_total_ms
```

> **服务端 timings 与客户端墙钟是两个时间轴，必须分开呈现**：Ollama 返回的是服务端耗时，不含排队/网络/框架开销。做法是以 generation 起点为基准按 `load → prefill → decode` 顺序累加映射为**虚拟子 span**，另记 `client_wall_ms - server_total_ms` 为独立「网络+框架开销」段，两者都在瀑布图上可见。

### 上报字段

| 字段 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `prompt_messages` | list | 必填 | prompt 完整组成，逐条上报（system / history / user / 检索片段） |
| `content` | str | 必填 | 正式输出，超长按 `MAX_OUTPUT_CHARS` 截断（默认 20000） |
| `thinking` | str | 可为空 | 思考过程（qwen3 `message.thinking`），与 content 分开累积 |
| `load_ms` | float | ≥0 | 模型加载耗时 |
| `prompt_eval_ms` | float | ≥0 | 预填充耗时 |
| `eval_ms` | float | ≥0 | 解码耗时 |
| `total_ms` | float | ≥0 | 服务端总耗时 |
| `ttft_ms` | float | ≥0 | 首 token 延迟（客户端视角） |
| `client_wall_ms` | float | ≥0 | 客户端墙钟总耗时 |
| `prompt_tokens` / `completion_tokens` | int | ≥0 | 缺失时为 0，不阻塞上报 |
| `tokens_per_sec` | float | ≥0 | 吞吐 = completion_tokens / (eval_ms/1000) |
| `is_cold_start` | bool | 默认 false | `load_ms > COLD_START_THRESHOLD_MS`（默认 200） |
| `route` | str | `langchain` / `direct` | 链路标识，用于 A/B 对比分组 |
| `model` | str | 必填 | 模型名 |

> 数值型指标**同时**作为 numeric score 上报（`ttft_ms` / `load_ms` / `prefill_ms` / `eval_ms` / `tokens_per_sec` / `is_cold_start`），供原生 Dashboard 做分位与聚合。

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况 |
|---|---|---|---|
| 直连对话（内部） | messages, model, stream | `OllamaChatResult`（content / thinking / timings / first_token_ms / client_wall_ms） | 连接失败 → 抛异常由上层处理；timings 缺失 → 字段置 0 且 `timings_available=false`，不阻塞 |
| 埋点上报（内部） | span 结构与字段 | 静默成功 | SDK 未配置/异常 → no-op 降级，**不冒泡到业务** |
| 基准对比（内部端点） | question, model | 两条链路各自耗时 | 任一条失败 → 返回该条 error，另一条结果仍返回 |
| Langfuse Web UI | — | `http://127.0.0.1:3000` | 依赖基础设施就绪 |

## 边界（每条之后会变成一条测试）

- Ollama 未启动 / 连接被拒：直连客户端抛明确异常，埋点记录失败状态，业务返回错误提示
- 流式响应中途断开：已收到的部分内容仍上报，timings 标记为不完整
- 响应**缺失 timings 字段**：所有耗时字段置 0 并置 `timings_available=false`，不得抛异常
- `thinking` 为空（非思考模型）：上报空串，不写占位符
- `client_wall_ms < server_total_ms`（时钟误差）：overhead 段取 0，不出现负数时间条
- 超长输入 / 超长思考过程：按阈值截断并追加标记，不撑爆单事件大小限制
- Langfuse 服务不可达：埋点静默失败并记一次警告日志，对话功能完全不受影响
- `LANGFUSE_ENABLED=false` 或采样未命中：全程零开销，不发起任何网络调用
- 采样率边界：`0` 全不上报、`1` 全上报，越界值回退到默认并告警

## 明确不做（划出范围，防 AI 自由发挥）

- **不做 Docker 部署**（用户明确要求命令行启动）
- **不覆盖文章检索下载链路**（本次只做对话 + 知识库 RAG）
- **不改动现有 LangGraph 流程与 KB 业务逻辑**，埋点以包裹方式外挂
- **不替换 `ChatOllama` 为默认链路**：`OLLAMA_ROUTE` 默认 `langchain`，保持现有行为不变
- **不自研甘特图组件**（复用 Langfuse 瀑布图）
- **不做用户体系 / 权限**（本地单人使用）
- **不做自动告警与阈值通知**（v4 的 Monitors 功能本次不启用）
- **不做自动告警与阈值通知**（v4 的 Monitors 功能本次不启用）
- **不迁移任何历史数据**（全新部署）
- **不直接修改项目外的 Langfuse 源码目录**；二次开发必须先导入项目内可追踪的 vendor 工作树并固定版本/基线。

## 验收方式

| 验收点 | 验证方法 |
|---|---|
| A1 平台可访问 | Langfuse Web 在 `http://127.0.0.1:3000` 打开，能创建项目并拿到 API Key |
| A2 请求详情 | 发起一次对话，在 Langfuse 中能看到该次调用，展开可见完整 prompt 组成（system / 历史 / 用户问题） |
| A3 返回详情 | 可见完整输出内容；使用思考模型时，思考过程与正式输出**分别可见** |
| A4 阶段耗时 | trace 详情页瀑布图呈现 `load / prefill / first_token / decode / overhead` 各阶段时间条，长度与实测耗时一致 |
| A5 首 token 归因 | 对同一模型做冷调用（模型已卸载）与热调用（刚调过），瀑布图能明显区分：冷调用 load 段很长，热调用 load 段接近 0 |
| A6 双链路对比 | 基准对比能给出 `langchain` 与 `direct` 两条链路各自的耗时与差值 |
| A7 KB 链路 | 知识库提问的 trace 中能看到 embedding / 检索 / 重排 / 生成各阶段 |
| A8 统计六项 | 首 token 分解与冷/热对比、分位与 Top N、吞吐、输入规模相关性、耗时构成占比、思考过程占比与趋势，六项均可查看 |
| A9 埋点零侵入 | `LANGFUSE_ENABLED=false` 或 Langfuse 停机时，对话与知识库功能完全正常，无异常抛出 |
| A10 回归 | Python 3.11 后全量测试通过，数量不少于升级前的 `253` |

## 产品使用步骤（由产品经理在 spec 确认后填写）

> 待 PM 补充：基于上面的数据模型/接口，写出真实用户视角的操作步骤与验收场景，每条映射到一个验收点。

## 执行配置（由架构师填写，落盘可查）

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、技术决策、落地校验 |
| 产品经理 | `qwen3.5:9b`（本地 Ollama） | 32k | `Task(pm)` | 梳理产品使用步骤、用户旅程、验收场景 |
| 开发主管 | `qwen3.8:27b-mlx`（本地 Ollama） | 32k | `Task(tech-lead)` | 需求/技术/验收评审、任务拆分、代码审查、合并裁决 |
| 初级开发 | `qwen3.8:27b-mlx`（本地 Ollama） | 32k | `Task(junior-dev)` | 已确认范围内的窄任务编码（单文件粒度、限时分派） |
| 测试 | 不适用（近期 `tester` 子代理两次分派均中途失效，验收由主会话承担；原因见 `docs/sdd/retro/2026-09-01-subagent-model-naming.md`） | — | — | 主体回归测试由主会话执行 |

## 任务计划

> 任务 01 = 本 spec 的编写（由架构师在主会话完成，不单独建思维链文档）。
> 从任务 02 起，每个任务先生成思维链文档，本 spec 以链接关联。索引见 `docs/sdd/plans/013/README.md`。

| 编号 | 任务 | 思维链文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-013（含回滚点） | 本文件 | — | 完成 |
| 02 | 非 Docker 部署基础设施与 Langfuse v4（Go/No-Go） | [`task-02-deploy-langfuse.md`](../plans/013/task-02-deploy-langfuse.md) | 01 | 完成（Go） |
| 03 | 升级项目 Python 到 3.11 并重装依赖 | [`task-03-upgrade-python.md`](../plans/013/task-03-upgrade-python.md) | 01 | 完成 |
| 04 | 实现直连 Ollama 采集器与埋点封装层 | [`task-04-ollama-direct.md`](../plans/013/task-04-ollama-direct.md) | 03 | 完成（events_only 上报已验证） |
| 05 | 接入聊天与知识库 RAG 链路埋点 | [`task-05-instrument-chat-kb.md`](../plans/013/task-05-instrument-chat-kb.md) | 04, 02 | 完成 |
| 06 | 统计路径 A：原生 Dashboard + numeric score | [`task-06-stats-native.md`](../plans/013/task-06-stats-native.md) | 05 | 完成 |
| 07 | 导入 Langfuse 源码并实现 Ollama 专用视图 | [`task-07-stats-custom-view.md`](../plans/013/task-07-stats-custom-view.md) | 05 | 实施中（查询层、页面、分布、阶段、散点与默认折叠详情完成；待前端构建与验收） |
| 08 | 评审验收与复盘 | [`task-08-review-retro.md`](../plans/013/task-08-review-retro.md) | 06, 07 | 待执行 |

## 评审记录

> 初始一律写「待评审（未执行）」。结论只能是通过/打回，禁止留「/」。

- 需求评审：`docs/sdd/reviews/013-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/013-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/013-acceptance-review.md`（测试报告 + 开发主管签字；待评审（未执行））

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-02 | 用户 | 提出需求：模型输出慢、首 token 加载耗时，需搭建评估平台；给出两个参考源（langfuse-ollama 项目、Langfuse Ollama 集成文档） |
| 2026-09-02 | 用户 | 拍板四项：基于 Langfuse 自定义开发且不用 Docker 命令行启动、双链路并存对比、覆盖聊天+KB RAG、统计六项全选 |
| 2026-09-02 | 用户 | 拍板两项：升级项目 Python 到 3.11 用 Langfuse v4；统计路径 A 与 B 都做，事后择优保留一项 |
| 2026-09-02 | 用户 | 要求建立 plan 文件夹为任务编号并与 spec 链接关联；要求先提交 spec-012 改动作为回滚点并写入 spec |
| 2026-09-02 | 架构师(自身) | 提交 spec-011/012 实现与文档，建立基线 `294138c`；完成技术与环境调研（Docker 缺失、ClickHouse 需官方二进制、SDK 需 Python≥3.10） |
| 2026-09-02 | 架构师(自身) | 编写本 spec，状态置 `待确认` |
| 2026-09-03 | 架构师(自身) | 对照附加 plan、当前代码与测试核对真实进度；补齐 Task 05–08 文件，Task 02/03 标记完成，Task 04 标记部分完成；spec 总状态仍为待确认 |
| 2026-09-03 | 用户 | 明确要求修复 Spec 013 阻塞并继续后续开发，确认按本 spec 执行 |
| 2026-09-03 | 架构师（自身） | 修复并验证 MinIO 凭据/运行状态；v4 events_only 口径以 events_full/events_core 为准，Task 04 真实上报通过；spec 转为已确认 |
| 2026-09-03 | 用户 | 要求补齐 Task 06 固定样本与 Dashboard 配置，并将 Langfuse v4.27 源码导入项目内进行可追踪二次开发 |
| 2026-09-03 | 架构师（自身） | 将 Task 07 改为项目内 vendor 导入 + 固定版本基线 + Ollama Insights，禁止直接修改项目外源码目录 |

---
**五条自检**：①每条规则能不能写成测试？不能就是没说清。②人能在 2 分钟内审完吗？③范围划死了吗？④执行配置里每个角色都有模型与上下文吗？⑤产品使用步骤是否可映射到验收点？
**收口自检**：见 `docs/sdd/SDD-GATE-CHECKLIST.md` §3 收口清单（状态已转、changelog 已记、三份评审结论为真实结论、引用路径真实存在、复盘已落盘）。
