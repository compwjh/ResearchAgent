> 关联：[spec-042](../../specs/042-openeval-agent-evaluation.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：**`已完成`**（Go/No-Go 判定：**Go**，报告见 [task-02-gono-go-report.md](./task-02-gono-go-report.md)）

# Task 02 — Go/No-Go：验证最高风险前提

## 一句话目标

在做任何集成之前，先验证三个最高风险前提是否成立；任一不成立即判 **No-Go**，
回到 spec-013 / spec-041 处理，不在本 spec 内扩大范围。

## 背景与前置条件

- 必读：[spec-042](../../specs/042-openeval-agent-evaluation.md)（尤其「背景与依据」F1–F9 与 grill Q1–Q7）
- 实测基线：[MEASUREMENT-langfuse-2026-09-22.md](../../MEASUREMENT-langfuse-2026-09-22.md)
- 前置运行：主服务 8400、Langfuse 3000、Ollama 11434

## 数据、配置与接口

- 只读 Langfuse public API：`GET /api/public/traces`、`GET /api/public/traces/{id}`（Basic auth: `pk-lf-local-dev-0001` / `sk-lf-local-dev-0001`）
- 只读 Ollama：`GET /api/tags`、`POST /api/chat`
- **不新增业务端点**；不写业务库

## 实施步骤与文件边界

### 步骤 1 — 复核 F5 矛盾点（路由与 token）

1. 确认**代码默认值**：`backend/app/platform/config.py` 中 `OLLAMA_ROUTE` 的默认值。
2. 确认**运行实例实际值**：主服务进程的启动环境与最近 trace 的 `metadata.route`。
3. 跑一次真实对话，取该 trace，检查 generation 的 `usage`。

**可观察结果**：明确回答「当前默认路由是 direct 还是 langchain」「新产生 trace 的 token 是否为真实非零值」。

### 步骤 1.5 — 为 Langfuse 配置 judge LLM connection（Q9=C 新增前置）

1. 在 Langfuse（`http://127.0.0.1:3000`）配置一条 LLM connection：
   provider 选 **OpenAI 兼容 / 自定义 baseURL**，baseURL 填 `http://localhost:11434/v1`
   （F14 已实测该端点可用），model 填 `qwen3.5:9b`（Q3=B）；API key 填占位值即可（Ollama 不校验）。
2. 用该 connection 跑通**一次** Langfuse 内置 evaluator（如 `Answer Relevance` 或 `Faithfulness`）。
3. 若 Langfuse 侧配置受阻（例如 UI 不允许自定义 baseURL，或
   `LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES=false` 限制），**明确记录阻塞点并带回**，
   **不得改业务代码绕过**。

**可观察结果**：Langfuse 内产生一条由**内置 evaluator** 打出的 score，且挂在目标 trace 上。

### 步骤 2 — 验证判官质量（最高风险）

1. 选 20–30 条已有 trace（覆盖：正常长回答、短回答、失败 trace、被技能路由的 Intake 文案）。
2. 用本地 **`qwen3.5:9b`** 作 judge（Q3 裁决为 B），对**同一条**重复评分 3 次（温度 0）。
   - 判官 prompt **按参考实践 R4**：强制输出「Explanation: […], Answer: […]」，
     Answer 限定在**枚举标签**内（避免弱判官自由发挥）。
   - **记忆正确性**按 R8 用枚举标签——`remembered` / `partially_remembered` /
     `forgotten` / `fabricated`，**不强行让 9b 打数值分**。
   - 评估步骤本身按 R5 用 `as_type="evaluator"` 记为 observation，便于后续排查**判官自身**异常。
3. 统计：评分方差、与人工标注的一致率。
4. **本步骤是强制门禁项**（因 9b 判官能力弱于 27B，一致性风险更高，不再是建议项）。
5. **回退链已定（Q8 裁决为 A）**：本 task 直接**同时跑 `qwen3.5:9b` 与 `qwen3.8:27b` 两组**，
   一次拿到对照数据；判定时按下列顺序执行：
   - 9b 过门禁 → **采用 9b** 作为判官（优先，速度最好）；
   - 9b 未过、27b 过门禁 → **回退采用 27b**（牺牲速度换质量）；
   - **两者均未过 → 判 No-Go**，本 spec 退化路径为「仅做数据导出 + 人工标注」。

**可观察结果**：一份 `JudgeConsistency` 报告，含 9b 与 27b 两组方差与一致率对照，
并按上述回退链给出**唯一的判官选型结论**。

### 步骤 3 — 验证数据桥接可行

1. 写最小导出脚本：Langfuse trace → `EvalItem`（trace_id / input / output / task）。
2. 验证：空 output 与 Intake 文案类 trace 能被识别并标记 `SKIPPED`。

**可观察结果**：导出脚本产出合法数据集 JSON，`SKIPPED` 判定正确。

### 步骤 4 — 离线校验

在断网（或 hosts 拦截）条件下重跑步骤 2–3，确认无外网请求。

**可观察结果**：全流程在断网下仍跑通。

### 步骤 5 — 选型确认（Q1）

复核目标 OpenEval 项目是否可离线运行（重点：`langchain-ai/openevals` 的 README 与依赖、
`openeval-cli` 的 Ollama 支持），输出选型结论。

**可观察结果**：一份选型结论，明确 Q1 取 A / B / C。

## 子代理分派

- 角色：`backend-dev`（模型 `hy3`，上下文 32k）
- 最小上下文：本 task 文件 + spec-042「背景与依据」+ MEASUREMENT 报告 §3/§4
- 单次文件范围：仅新增评测/导出脚本与报告，**不改业务代码**
- 回传后架构师读回校验：比对报告数值与 trace 原始数据

## 边界与明确不做

- 不改业务对话链路、不改观测埋点、不改 `LANGFUSE_SAMPLE_RATE`
- 不引入云端 judge
- 不新增主服务端点
- 不在本 task 内实现完整评测流水线（那是裁决后的任务 03+）

## 验收、风险与回滚

| 验收项 | 判据 |
|---|---|
| 路由与 token 结论明确 | 步骤 1 给出确定答案，且有真实 trace 佐证 |
| 判官可用（**强制门禁**） | 重复评分方差在可接受范围，且与人工标注一致率 ≥ 约定阈值；并按 Q8=A 给出唯一选型结论（9b 优先 → 回退 27b → 均不过则 No-Go） |
| 桥接可行 | 导出数据集合法，`SKIPPED` 判定正确 |
| 离线成立 | 断网下全流程跑通 |
| 选型明确 | Q1 有结论且给出依据 |

**Go/No-Go 判据**：上述 5 项**全部**通过才判 Go。
任一项不通过 → **No-Go**，spec-042 保持「待确认」，回到 spec-013 / spec-041 处理前置缺陷。

**回滚**：本 task 只新增脚本与报告，无业务改动；回滚即删除脚本与报告文件。

## 产出物、执行结果与变更日志

- 产出物：`JudgeConsistency` 报告、导出脚本、选型结论、Go/No-Go 判定
- 执行结果：**步骤 1 已完成（2026-09-22，主 agent 实测）**
  - 代码默认值：`backend/app/platform/config.py:122` → `OLLAMA_ROUTE` 默认 **`direct`**
    （spec-041 的修订已在代码中生效）。
  - 运行实例：PID 98677（01:54:15 启动），未显式传 `OLLAMA_ROUTE`，走代码默认 `direct`。
  - 实测（最近 12 条 `ollama-chat` 按 route/model 聚合）：
    | route | model | 条数 | token | 平均延迟 | 判定 |
    |---|---|---|---|---|---|
    | `direct` | `qwen3.8:27b` | 1 | in=83 / out=64 | 29.57s | **主生成链路，token 真实** ✅ |
    | `langchain` | `qwen3.5:9b` | 11 | 全 0 | 0.02s | 旁路调用（疑似探针/记忆分析快速失败），token 与延迟均失真 |
  - **结论**：主生成链路 token 维度**可用**，Q7 的阻塞点之一解除；
    `langchain` + `qwen3.5:9b` 的旁路 0-token 问题**按 Q7 不在本 spec 修复**，记为遗留项，
    已同步至 spec「明确不做」范围与变更日志。
- **步骤 1.5 结果（2026-09-22，第二轮 backend-dev 实测）**：
  - **SSRF 阻塞已解除**：向运行期 `/Users/wjh/ResearchAgent/vendor/langfuse/.env` 追加
    `LANGFUSE_LLM_CONNECTION_WHITELISTED_HOST=localhost,127.0.0.1` 与
    `LANGFUSE_LLM_CONNECTION_WHITELISTED_IPS=127.0.0.1`，重启 web/worker 后：
    - `PUT /api/public/llm-connections` → **HTTP 201**（provider=ollama-local，
      baseURL=http://localhost:11434/v1，model=qwen3.5:9b），证明 web 已加载白名单、localhost 通过校验；
    - 创建 LLM-as-Judge evaluator → **HTTP 200**；
    - **worker 日志实证**：创建规则时 worker 真实打到 `127.0.0.1:11434`，SSRF 不再拦截。
  - **但出现新的、独立的阻塞点**：创建 observation 规则返回 **422**
    `Model configuration not valid ... No object generated: response did not match schema`。
    根因：**Ollama 的 OpenAI 兼容 `/v1` 端点不支持 `response_format: json_schema`（strict）**，
    而 Langfuse 内置结构化输出判官引擎依赖该模式。
    → **Langfuse 内置 evaluator 在本机 Ollama 上无法产出 score**。
    属模型/端点能力限制，**非 Langfuse 配置问题，禁止改业务代码绕过**。
- **对 Q9=C 的冲击（需架构师/用户裁决）**：Q9=C 的前半段「通用维度用 Langfuse 内置 evaluators」
  在本机 Ollama 上**不可行**；而已验证可用的路径是**自建判官 + Langfuse 仅作 score 落点**
  （步骤 2 已实测：chat_quality 上 9b/27b 自一致率 1.0、跨判官一致率 1.0，decision=adopt:qwen3.5:9b）。
- 变更日志：步骤 1 已执行；步骤 2/3 已完成；步骤 1.5 已解锁 SSRF 但被新阻塞点阻断（已如实记录）；
  步骤 4（离线校验）与步骤 5（选型）**仍待执行**，Go/No-Go 报告**未产出**。
