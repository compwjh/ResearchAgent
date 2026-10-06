# Langfuse 观测测量报告（2026-09-22）

> 目标：跑若干「多记忆、多输入多输出」任务，核对 Langfuse 是否收到对应数据，
> 评估可产出哪些测量指标，并分析 OpenEval 用于本 agent 的可行性。
> 关联：`docs/sdd/specs/041-langfuse-trace-detail-and-waterfall.md`、`deploy/langfuse/README.md`

---

## 1. 结论摘要

| 问题 | 结论 |
|---|---|
| Langfuse 部署了吗？ | ✅ 已部署并在运行。web :3000、worker :3030、ClickHouse/PostgreSQL/Redis/MinIO 全在监听 |
| 后端追踪开启了吗？ | ✅ 已开启（`backend/.env`：`LANGFUSE_ENABLED=true` + 项目 pk/sk） |
| 能收到任务数据吗？ | ✅ 能。本轮实验产生 **178 条新 trace**，其中 `ollama-chat` **56 条** |
| 能拿到 token 用量吗？ | ⚠️ **取决于路由**：`direct` 路由有真实 token；`langchain` 路由恒为 0 |
| 能产出测量报告吗？ | ✅ 能，但需先切到 `direct` 路由，否则 token 维度全是 0（见第 4 节） |
| 目标 1k 输入 / 300 输出达成吗？ | ✅ 超额：实测 2214 输入 / 937 输出、2878 输入 / 1137 输出 |

**最重要的发现**：默认 `langchain` 路由下，Langfuse 里所有 generation 的 `usage` 恒为
`{"input":0,"output":0,"total":0}`——**token 维度此前完全无法测量**；
同时该路由还会让 Ollama 返回 HTTP 500，导致对话直接失败。

---

## 2. 环境与前提

- 主服务：`http://127.0.0.1:8400`（FastAPI + 本地 Ollama）
- 模型：`qwen3.8:27b`（Q4_K_M，36GB 统一内存 M3 Max）
- Langfuse：v4.27.0，非 Docker 脚本部署，`http://127.0.0.1:3000`
- 观测埋点：`backend/app/platform/observability/`，trace 名 `ollama-chat`，
  附 `phase: load/prefill/decode/overhead` 四个子 span

### 本次为完成测量所做的运行期变更（需你确认是否保留）

为绕过第 3 节的阻塞，我把主服务重启为 **`OLLAMA_ROUTE=direct`**：

```bash
lsof -nP -iTCP:8400 -sTCP:LISTEN -t | xargs kill -TERM
OLLAMA_ROUTE=direct PORT=8400 bash deploy/start.sh -d
```

> 默认值为 `langchain`。当前服务运行在 `direct`。若你不认可，可用默认参数重启恢复
> （但会同时回到「对话 500 + token 恒为 0」的状态，见第 3 节）。

---

## 3. 阻塞与排查（三个真实缺陷）

### 缺陷 1：默认 langchain 路由下 Ollama 返回 HTTP 500

现象：`POST /api/conversations/messages` 返回 `CHAT_FAILED`，
`Ollama /api/chat 失败（HTTP 500）`。Ollama 服务端日志给出两种原因：

```
① Jinja Exception: Unexpected reasoning effort high.
   Supported types are xhigh (default), medium, and low.
② Jinja Exception: System message must be at the beginning.
```

- 原因 ①：后端把 `reasoning_effort=xhigh` 映射成布尔 `think=true`，Ollama 解析为 `high`，
  而 qwen3.8 模板不接受 `high`。实测 `think` 取值：`low/false/true → 200`，`high → 500`。
- 原因 ②：langchain 分支直接把原始 messages 发给 Ollama，多个 system 消息顺序不保证，
  触发模板校验。`direct` 分支有 `normalize_ollama_messages()` 做 system 合并归一，可规避。

### 缺陷 2：langchain 路由下 token 用量恒为 0（测量盲区）

- `spans.py:303` 写入 `usage_details={"input": result.timings.prompt_tokens, ...}`
- 真实值只在 `ollama_direct.py` 从 Ollama 的 `prompt_eval_count/eval_count` 解析得到
- `chat_runner.py:111` 的 langchain 分支用的是 `OllamaTimings()`（全 0 默认）

结果：langchain 路由的 trace 里 `usage` 全是 0，**无法统计 token、成本、吞吐**。

### 缺陷 3：模型能力探测失败会直接拒答

7/9 轮次报 `当前模型不支持该推理档位`
（`routes_conversations.py:583`，`REASONING_EFFORT_UNSUPPORTED`，HTTP 409）。
在长生成把 Ollama 占满后，能力探测失败即整轮拒绝，**且 `retryable=False`**。
即使请求的是 `reasoning_effort=off`（本不需要探测）也一样被拒。

---

## 4. 实测数据

### 4.1 成功轮次（direct 路由，token 为真实值）

| 轮次 | 时间 | route | 输入 token | 输出 token | 总 token | 延迟(s) | 输出速率(tok/s) | 输入字符 | 输出字符 |
|---|---|---|---|---|---|---|---|---|---|
| A-材料分析 T1 | 01:57:56 | direct | 2214 | 937 | 3151 | 130.6 | 7.17 | 3526 | 1639 |
| A-材料分析 T2 | 02:01:21 | direct | 2878 | 1137 | 4015 | 204.4 | 5.56 | 4776 | 2020 |

对照目标「约 1000 输入 / 300 输出 token」：输入达成并超出 2~3 倍；输出超出 3 倍以上
（提示词要求「不少于 600 字」，模型实际给了 1639~2020 字符）。

短轮次样本（同模型、小输入）：输入 83 / 输出 48~67 token，延迟 8.5~31.6s。

### 4.2 Langfuse 侧收到的 trace（本轮窗口内共 178 条）

| trace 名 | 条数 | 平均延迟 | 说明 |
|---|---|---|---|
| `ollama-chat` | 56 | 18.41s | 主对话生成，其中 **15 条 usage 非 0**（即 direct 路由产生） |
| `kb.embedding` | 41 | ~0 | 知识库向量化 |
| `kb.retrieval` | 35 | ~0 | 向量检索 |
| `kb.rerank` | 32 | ~0 | 重排（当前 Reranker 降级，模型文件缺失） |
| `kb.generation` | 7 | 1.17s | KB 问答生成 |
| `compaction_summary_degraded` | 4 | ~0 | 上下文压缩摘要（降级路径） |
| `flush_memories_skipped` | 2 | ~0 | 记忆落库（跳过） |
| `backdate-probe` | 1 | 7.0s | 探测任务 |

> 说明：Langfuse 里能看到 input/output 文本、`latency`、metadata（`model`/`route`/`input_chars`/
> `reasoning_present`）、4 个阶段子 span 与若干 score；**只有 direct 路由的 generation 带 token**。

### 4.3 可产出的测量维度

已具备：调用量、按 trace 类型的分布、端到端延迟、输出 token 吞吐、输入/输出文本规模、
阶段耗时（load/prefill/decode/overhead 瀑布）、记忆与压缩事件、检索链路各段。

暂不具备（待修复缺陷 2 后才能全域可用）：全域 token 用量、成本、按 token 的 P50/P95、
真实的上下文占用。

---

## 5. OpenEval 用于本 agent 的可行性分析

### 5.1 先澄清：名字冲突，至少三个不同项目

| 项目 | 定位 | 与本项目相关性 |
|---|---|---|
| `langchain-ai/openevals`（MIT，Python+JS，1.2k stars） | 「Readymade evaluators for your LLM apps」，含 **agent 全轨迹（trajectory）评估器** | 功能最对口（要评的就是 agent 轨迹），生态成熟 |
| `open-evals.com` | 自带 metrics 与合成数据生成的评测框架 | 定位偏通用 LLM 应用 |
| `openeval-cli`（PyPI）/ `edmontecristo/openeval` | 「CLI-first，like Pytest for AI agents」，7 个内置 scorer，**CI/CD 原生，明确支持 Ollama** | 与「离线 + 本地 Ollama」约束最贴合 |

> 注：`openevals` 的 README 正文未能抓取渲染，以上关于其评估器清单与模型后端支持
> 来自仓库元信息与检索摘要，**接入前需再核对 README/源码**。

### 5.2 可行性判断：可行，但有三个硬约束要先解

**✅ 有利条件**
- 后端是 Python，与 openevals / openeval-cli 同语言，可直接在 `backend/` 内集成或旁路调用。
- 已有 Langfuse 落了完整 trace（含 input/output、阶段 span、记忆事件），
  这就是 OpenEval 需要的「轨迹 + 输入输出」原始素材。
- 若要 CI 化回归评测，`openeval-cli` 的 CLI/Pytest 形态最省事，且声明支持 Ollama。

**⚠️ 必须先解决的三个约束**

1. **离线判官质量**：LLM-as-judge 需要 judge 模型。本机只有 `qwen3.8:27b` / `qwen3.5:9b`，
   用 27B 量化模型做判官，评分稳定性与一致性明显弱于云端强模型，
   必须做「判官自身一致性」校验（同一条多次评分的方差、与人工标注的一致率）。
2. **数据格式桥接缺口**：Langfuse 的 trace 结构与 OpenEval 期望的
   `inputs / outputs / reference_outputs / trajectory` 不通用，
   需要写一个导出器（Langfuse public API → OpenEval 数据集）。本次已验证
   `/api/public/traces` + `/api/public/traces/{id}` 可用（Basic auth: pk/sk）。
3. **轨迹完整性取决于缺陷 2/3**：若路由仍是 langchain，`usage` 为 0 且对话直接 500，
   采集到的轨迹既不完整也无 token 维度，评测无从谈起。**先修路由/埋点，再上 OpenEval。**

### 5.3 建议路径

1. 先把 `direct` 路由与 token 埋点固化（或修好 langchain 分支的 system 归一与 usage 回填），
   保证每次对话都有完整 trace + 真实 token。
2. 写一个最小导出器：从 Langfuse 拉 trace → 转成 OpenEval 数据集，先用本次 2 条成功样本试通。
3. 判官用本地 `qwen3.8:27b`，先做 20~30 条样本的「判官一致性」基线，再谈评测结论。
4. 优先选 `openeval-cli`（CLI + Ollama + CI 原生）做回归门禁；
   若需要 trajectory 级细粒度评估，再评估 `langchain-ai/openevals`。
5. 现阶段**不建议**引入任何需要外网/云 judge 的方案，与「数据不出本机」硬约束冲突。

---

## 6. 复现命令

```bash
# 1) 以 direct 路由启动（token 可见且对话可用）
lsof -nP -iTCP:8400 -sTCP:LISTEN -t | xargs kill -TERM
OLLAMA_ROUTE=direct PORT=8400 bash deploy/start.sh -d

# 2) 发一轮多轮对话（reasoning_effort 用 off/medium/low，不要用 high）
curl -s -N -X POST http://127.0.0.1:8400/api/conversations/messages \
  -H 'Content-Type: application/json' \
  -d '{"content":"<你的问题>","model":"qwen3.8:27b","reasoning_effort":"off"}'

# 3) 从 Langfuse 取 trace（Basic auth 用 pk/sk）
curl -s -u "pk-lf-local-dev-0001:sk-lf-local-dev-0001" \
  "http://127.0.0.1:3000/api/public/traces?limit=50&orderBy=timestamp.desc"
curl -s -u "pk-lf-local-dev-0001:sk-lf-local-dev-0001" \
  "http://127.0.0.1:3000/api/public/traces/<traceId>"
```

> 提示：提问语气若带「帮我研究/调研」会被 `deep-research-orchestration` 技能接管，
> 转入研究 Intake 流程（不调用模型生成，无 token）。
> 做观测测量时用「给定材料让模型分析」的对话形态，可稳定触发生成。
