# Spec 035 — 线上模型接入与模型库端侧/线上分组

## 状态

**当前状态：已完成**

> 2026-09-13 用户指示「现在开工」，spec 转 `已确认`，进入实现。
> **临时决策（本次会话有效）**：子代理模型统一改用 **`hy3`**（0.00 倍率），临时覆盖 `AGENTS.md`「角色模型分配表」的 `Deepseek-V4.1-Flash`；本 spec 执行配置表中的模型名暂不改写，实际分派以 `hy3` 为准，会话结束前恢复原值。
> **流程偏离记录**：按 `AGENTS.md` 三道门禁应「先评审后实现」，本次按用户「开工」指示先行实现，需求/技术评审并入 Task07 执行（见任务计划）。

## 一句话目标

让模型库能接入**线上模型**（如 DeepSeek）：以 `create_chat_model()` 为**唯一收口点**按模型名分发 provider，使对话、知识库问答、文章助手、技能调用等**所有模块无缝支持线上模型**；模型库界面按「端侧模型 / 线上模型」两组展示；线上模型的 Key / 地址 / 模型清单在 `.env` 静态声明；`/api/health` 的 `models` 字段**保持不变**，新增 `GET /api/models` 承载分组结构。

## 背景与现状（已核实）

| 现状 | 位置 | 影响 |
|---|---|---|
| 模型列表唯一来源是 Ollama `/api/tags`，且 `get_available_models()` **只取 `name` 丢弃全部元数据** | `backend/app/platform/ollama.py:189` | 无 size/family 可用；返回 `List[str]` |
| 模型列表对外**只有一个端点** `GET /api/health` 的 `models` 字段 | `backend/app/api/routes_system.py:25` | 被前端 3 处消费（模型库 / 对话下拉 / KB 下拉） |
| `create_chat_model()` **固定返回 `ChatOllama`** | `backend/app/platform/ollama.py:199` | 没有任何线上 provider |
| `create_chat_model()` 是**唯一收口点**，被 4 个模块调用 | `chat_runner.py`、`knowledge_base/infrastructure/retrieve.py`、`article_agent.py`、`download_paper_skill.py` | 在此分发即可让全部模块无缝支持线上模型 |
| `build_chat_graph(model)` 是**鸭子类型**，只用 `model.stream()` + `chunk.content` | `backend/app/chat/application/chat_graph.py:9` | 换任意 LangChain chat model 即可复用流式/思维链过滤/观测 |
| **6 处路由用 `model in get_available_models()` 做校验** | `routes_chat.py:63`、`routes_conversations.py:238/297`、`routes_kb.py:134/966`、`routes_article.py:56` 等 | **关键接缝**：线上模型不在 Ollama 列表内，不改则选中即被判 404/503 |
| 配置用 `python-dotenv` + `config.py` 模块常量（无 pydantic-settings） | `backend/app/platform/config.py` | 新增常量即可；非法值 warn 回退，不 fail-fast |
| **未安装** `openai` / `langchain-openai` | `requirements.txt` 无此项 | 需新增依赖 |
| 前端 `renderModelList()` 扁平循环，**无分组** | `frontend/app.js:4064` | 需改造为分组渲染 |
| 模型库**无任何自动化测试** | `tests/` 下 0 命中 | 需补契约测试 |

## 设计决策（grill 结论，已由用户裁决）

| # | 决策 | 结论 |
|---|---|---|
| Q1 | 线上模型能否实际调用 | **能**（本期即打通调用，非仅展示） |
| Q2 | spec 编号 | **035**（034 空缺，按用户指定） |
| Q3 | 线上清单来源 | **`.env` 静态声明**（不调厂商 `/models` 动态发现） |
| Q4 | 接口契约 | **新增 `GET /api/models`**，`/api/health` 一字不动（零回归） |
| Q5 | 当前模型语义 | **全局唯一** `activeModel`，端侧/线上可互相切换 |
| Q6 | 实现形态 | **引入 `langchain-openai` 的 `ChatOpenAI`**（OpenAI 兼容协议，覆盖 DeepSeek 等） |
| Q7 | 分组形态 | **同页两个分组标题 + 各自列表**（不加 tab） |
| Q8 | 测试策略 | **开发/验收仅测连通性、极低消耗**（`max_tokens=1`）；产品运行时默认不探测，仅在**打开页面/模型库时轻量探测一次**（结果缓存） |
| Q9 | 异常状态展示 | **未配 Key → 不展示**；**已配但连通失败 → 展示并标记** |
| Q10 | 适用范围 | **不限制单模块**：改动落在模型层，所有模块自动适配 |

## 数据模型

### 1. `.env` 配置（静态声明，唯一的线上模型来源）

```bash
# 线上模型清单：逗号分隔的 provider:model。缺 Key 或地址非法者不会被注册。
ONLINE_MODELS=deepseek:deepseek-chat,deepseek:deepseek-reasoner

# 每个 provider 一组配置（provider 名转大写 + 下划线）
DEEPSEEK_API_KEY=sk-xxxxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

**解析规则**（`backend/app/platform/model_catalog.py`）：

| 规则 | 行为 |
|---|---|
| 去空白、忽略空项 | 静默跳过 |
| 项内无 `:` 或含多个 `:` | 跳过该项 + `logger.warning`，**不 fail-fast** |
| provider 统一小写 | env 查 `<PROVIDER_UPPER>_API_KEY` / `<PROVIDER_UPPER>_BASE_URL` |
| **缺 `API_KEY`** | 该项**不注册**（对应 Q9：不展示） |
| 缺 `BASE_URL` | 用内置默认表（`deepseek`→`https://api.deepseek.com`，`openai`→`https://api.openai.com/v1`）；未知 provider 且无地址 → 跳过 + warning |
| `BASE_URL` 协议 | **仅允许 `https://` 或 loopback `http://`**（SSRF 防护）；其余拒绝 + warning |
| 重复 `provider:model` | 保留首个，后续跳过 + warning |
| 与本地模型同名 | 线上 id 天然带 `provider:` 前缀，**不冲突**；同名时本地优先 |

### 2. 线上模型注册表项（后端内部）

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | str | `provider:model`，全局唯一，即前端 `value` 与请求体模型名 |
| `provider` | str | 小写，如 `deepseek` |
| `model` | str | 厂商侧真实模型名，如 `deepseek-chat` |
| `display_name` | str | 展示名，默认等于 `id` |
| `base_url` | str | 必填（默认映射或 env 覆盖） |
| `api_key` | str | 必填，**绝不出现在任何 HTTP 响应中**，日志全掩码 |
| `source` | str | 固定 `"online"` |

### 3. 模型项（API 返回体）

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | str | 端侧为 Ollama 名；线上为 `provider:model` |
| `name` | str | 真实模型名 |
| `source` | str | `"local"` \| `"online"` |
| `provider` | str \| null | 仅线上有值 |
| `display_name` | str | 展示名 |
| `current` | bool | 是否为全局当前模型 |
| `status` | str | 线上：`"ready"` / `"unreachable"` / `"unknown"`；端侧恒 `"ready"` |
| `capabilities` | object | `{ reasoning_efforts: [...] | null }`，**线上恒 `null`** |

## 端点 / 接口

| 动作 | 输入 | 成功返回 | 失败情况 |
|---|---|---|---|
| `GET /api/models` | 无 | 分组结构（不做探测，`status` 为 `unknown`） | 200（Ollama 不可达时 `local` 组为空，不报错） |
| `GET /api/models?probe=1` | 无 | 同上，但对**已配置**线上模型做轻量探测并填充 `status` | 200；单个模型探测失败只降级该项 `status`，不影响整体 |
| `GET /api/health` | 无 | **结构不变**（`models` 仍为 `List[str]`） | 不变 |

`GET /api/models` 成功返回示例：

```json
{
  "current": "qwen3.8:27b-mlx",
  "groups": [
    {
      "source": "local",
      "label": "端侧模型",
      "models": [
        {"id":"qwen3.8:27b-mlx","name":"qwen3.8:27b-mlx","source":"local",
         "provider":null,"display_name":"qwen3.8:27b-mlx","current":true,
         "status":"ready","capabilities":{"reasoning_efforts":["off","low","medium","high","xhigh"]}}
      ]
    },
    {
      "source": "online",
      "label": "线上模型",
      "models": [
        {"id":"deepseek:deepseek-chat","name":"deepseek-chat","source":"online",
         "provider":"deepseek","display_name":"deepseek:deepseek-chat","current":false,
         "status":"ready","capabilities":{"reasoning_efforts":null}}
      ]
    }
  ]
}
```

### 后端核心函数（platform 层）

| 函数 | 位置 | 契约 |
|---|---|---|
| `get_online_models()` | `platform/model_catalog.py` | 解析 `.env` → 已注册线上模型列表 |
| `is_model_available(name)` | `platform/model_catalog.py` | **本地 ∪ 线上** 并集判断；替换现有 6 处 `model in get_available_models()` |
| `create_chat_model(name, *, reasoning=None)` | `platform/ollama.py`（**签名与名字不变**） | 线上 → `ChatOpenAI`；否则 → `ChatOllama`（现状不变）。线上忽略 `reasoning` 并 debug 日志 |
| `probe_online_model(entry, *, timeout)` | `platform/model_catalog.py` | `max_tokens=1` 最小 chat 请求，返回 `ready` / `unreachable` |

> `create_chat_model` 保持名字与签名不变是硬约束：现有 63+ 处测试 patch 的目标是 `backend.app.platform.ollama.create_chat_model`，调用点（`chat_runner` 等）按模块属性解析，均不受内部实现变更影响。

### 轻量探测（低消耗、低风险）

| 项 | 取值 |
|---|---|
| 请求 | `POST {base_url}/chat/completions`，body `{model, messages:[{role:"user",content:"ping"}], max_tokens:1, stream:false}` |
| 单次超时 | 8s |
| 结果缓存 | 内存，60s（同 id 不重复消耗） |
| 总耗时上限 | 15s（超出直接置 `unknown`，不阻塞页面） |
| 失败处理 | 超时 / 非 2xx / 异常 → `unreachable`，**绝不影响 `/api/models` 返回 200** |
| 日志 | 只记 provider + 状态码，**不记 Key、不记响应体** |

## 边界（每条之后会变成一条测试）

1. 未配置 `ONLINE_MODELS` → 线上组为空数组，页面只显示端侧，**不报错**。
2. 配了 `ONLINE_MODELS` 但缺 `API_KEY` → 该模型**不注册、不展示**。
3. `API_KEY` 有但 `base_url` 不可达 → **展示**，`status=unreachable`，可选中；实际调用失败时返回明确错误。
4. `ONLINE_MODELS` 格式非法（缺 `:` / 空项 / 重复） → 跳过非法项 + warning，**服务正常启动**。
5. provider 名大小写不一致（`DeepSeek` vs `deepseek`） → 统一小写匹配 env。
6. 线上模型 id 与本地模型名冲突 → `provider:` 前缀天然隔离，同名时本地优先。
7. 模型库全空（Ollama 不可达且无线上模型） → 显示空态「暂无可用模型」。
8. `/api/chat/reasoning-options?model=deepseek:deepseek-chat` → 返回 `200` + `{supported:false, efforts:[]}`，**不报 404**（避免前端报错）。
9. 探测超时 / 网络异常 → `status=unreachable`，`/api/models` 仍 200。
10. 60s 内重复打开模型库 → 命中缓存，**不重复发请求**。
11. 别名（spec-008 `localStorage`）对线上模型同样生效；`value` 仍为真实 id。
12. **XSS**：所有展示名走 `textContent`，禁止 `innerHTML`。
13. 当前模型是线上模型 → 刷新页面后仍正确恢复（`activeModel` 语义不变）。
14. `.env` 中删除了当前所用的线上模型 → 回退到第一个可用模型，不崩溃。
15. `OLLAMA_ROUTE=direct` 时选中线上模型 → **强制回退 langchain 路由**（direct 是 Ollama 专有链路）。

## 明确不做（划出范围，防 AI 自由发挥）

1. **不在 UI 填写/修改 Key**：只能在 `.env` 配置并重启生效（避免 Key 落浏览器、避免引入加密存储）。
2. **embedding / rerank 不接线上**：继续用本地 `bge-m3` 与本地 reranker。
3. **不支持线上模型的思考档位**：Ollama 的 `think` 参数对线上模型忽略；`reasoning-options` 对线上返回不支持；**不解析/展示 `reasoning_content` 流式思考内容**。
4. **不改动 `/api/health` 的 `models` 字段**（新结构只走 `/api/models`）。
5. **不做**：多 Key 负载均衡、用量/计费统计、配额限流、模型自动下载。
6. **不补端侧模型的 size / 参数量元数据**（`/api/tags` 有但现被丢弃；结构预留字段，本期不展示）。
7. **不做**模型库的搜索 / 排序 / 筛选。
8. **不自动探测未声明的线上模型**（只认 `.env` 声明的清单）。
9. **不改动 `docs/sdd/MODEL_REGISTRY.md`**：它服务于 **agent 分派**选型，与运行时模型库是两回事。
10. **不改 `get_available_models()` 的 `List[str]` 返回值**（63+ 处 mock 依赖）。

## 产品使用步骤（草案，待产品经理确认后定稿）

1. 用户在项目根目录 `.env` 中填写 `ONLINE_MODELS=deepseek:deepseek-chat` 与 `DEEPSEEK_API_KEY=sk-...`，重启服务。
2. 打开页面，左侧「模型库」角标显示模型总数；进入模型库，看到**「端侧模型」**与**「线上模型」**两个分组。
3. 线上分组中 `deepseek:deepseek-chat` 卡片显示状态徽标（已连通 / 连接失败 / 未探测）。
4. 点击任一线上模型卡片 → 它成为全局当前模型，顶部模型标签与对话下拉同步更新。
5. 在对话中提问 → 请求经线上 API 返回，流式输出与本地模型体验一致。
6. 切换到知识库，模型下拉中同样能看到并按 `optgroup` 分组的线上模型，选中后 KB 问答走线上模型。
7. Key 填错或网络不通时：卡片显示「连接失败」但仍可见可排查；发起对话时返回明确错误信息，不静默空转。

- 验收场景 A：配置正确 → 模型库分两组、线上卡片状态「已连通」、选中后对话真实返回。
- 验收场景 B：`API_KEY` 置空 → 该线上模型**不出现**在列表，端侧模型不受影响。
- 验收场景 C：Key 错误 → 卡片显示「连接失败」，对话返回明确错误，服务不崩溃。
- 验收场景 D：`ONLINE_MODELS` 填非法值 → 服务正常启动，非法项被跳过并记日志。
- 验收场景 E：无任何线上配置 → 模型库退化为改动前形态（仅端侧），无回归。

## 执行配置（由架构师填写，落盘可查）

> 依据 `AGENTS.md`「角色模型分配表」（2026-09-10 用户指定）与 `.codebuddy/agents/*.md` 的 `model:` 字段保持一致。
> 架构师行填「自身」，不写死模型代号。

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | **自身**（当前执行任务的 Agent，不写死模型代号） | 200k | 主会话 | 编写/修订本 spec、技术决策、落地校验 |
| 产品经理 | `Deepseek-V4.1-Flash` | 128k | `Task(doc-updater)` | 定稿产品使用步骤与验收场景 |
| 开发主管 | `Deepseek-V4.1-Flash` | 128k | `Task(architect)` | 需求/技术评审、任务拆分、合并裁决 |
| 初级开发 | `Deepseek-V4.1-Flash` | 128k | `Task(backend-dev)` / `Task(frontend-dev)` | 后端 provider 分发与前端分组实现 |
| 测试 | `Deepseek-V4.1-Flash` | 128k | `Task(backend-tester)` / `Task(frontend-tester)` / `Task(tester)` | 单端回归与跨端验收 |

## 任务计划

> 本章是任务索引，详细步骤见 `docs/sdd/plans/035/` 下各 task 文件。
> 任务 01 为本 spec 的编写，以 spec 本身作为文档。

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-035 | 本文件 | — | 完成 |
| 02 | `.env` 配置解析与线上模型注册表 | [`task-02-online-model-config-registry.md`](../plans/035/task-02-online-model-config-registry.md) | 01 | 待执行 |
| 03 | platform 层 provider 分发与并集校验（`create_chat_model` / `is_model_available`） | [`task-03-provider-dispatch-and-validation.md`](../plans/035/task-03-provider-dispatch-and-validation.md) | 02 | 待执行 |
| 04 | `GET /api/models` 端点与轻量连通性探测 | [`task-04-models-endpoint-and-probe.md`](../plans/035/task-04-models-endpoint-and-probe.md) | 03 | 待执行 |
| 05 | 各模块无缝适配（校验改并集、think 降级、direct 路由回退） | [`task-05-module-seamless-adaptation.md`](../plans/035/task-05-module-seamless-adaptation.md) | 04 | 待执行 |
| 06 | 前端模型库分组展示与下拉分组 | [`task-06-frontend-model-library-grouping.md`](../plans/035/task-06-frontend-model-library-grouping.md) | 04 | 待执行 |
| 07 | 测试（仅连通性、低消耗）、评审、回归、部署与复盘 | [`task-07-review-regression-deploy.md`](../plans/035/task-07-review-regression-deploy.md) | 05, 06 | 待执行 |

## 评审记录

> 初始一律写「待评审（未执行）」。评审执行后再将状态替换为真实结论。

- 需求评审：[`docs/sdd/reviews/035-requirement-review.md`](../reviews/035-requirement-review.md)（**通过**，由 `architect` 执行）
- 技术评审：[`docs/sdd/reviews/035-tech-review.md`](../reviews/035-tech-review.md)（**通过**，0 CRITICAL / 0 HIGH；1 MEDIUM 为分支混入 spec-034 在途改动，已按提交范围隔离处置；4 LOW + 1 INFO 已记录）
- 后端回归：[`docs/sdd/reviews/035-backend-regression.md`](../reviews/035-backend-regression.md)（全量 **1702 passed / 2 failed / 1 skipped**；2 个失败经 `git worktree` 干净基线 `79cfa21` 验证为**存量失败**，非本次引入）
- 前端回归：[`docs/sdd/reviews/035-frontend-regression.md`](../reviews/035-frontend-regression.md)（**184 passed**，DOM 契约 / 版本号 / XSS / 降级 / `option.value` 五项核对全 PASS）
- 验收评审：[`docs/sdd/reviews/035-acceptance-review.md`](../reviews/035-acceptance-review.md)（**通过**，跨端集成验收 7/7；开发主管已签字）

## 变更日志（Changelog）

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-13 | 架构师（自身） | 经「grill with docs」两轮质询（共 10 个决策点）与用户裁决后编写本 spec |

---

**六条自检**：
① 每条规则能否写成测试？→「边界」15 条均可直接映射为用例。
② spec 是否只描述需求、task 承载实施细节？→ 是，实现步骤全在 `plans/035/`。
③ 所有 task 链接是否真实存在且依赖无环？→ 02→03→04→{05,06}→07，无环。
④ 范围划死了吗？→「明确不做」10 条。
⑤ 执行配置五行齐全？→ 是（含"自身"）。
⑥ 产品使用步骤可映射到验收点？→ 场景 A–E 与边界 1/2/3/4 对应。
