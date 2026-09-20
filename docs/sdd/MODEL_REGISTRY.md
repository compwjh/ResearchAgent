# 模型库（Model Registry）

> **两个"唯一"分清楚，别混**：
> - **模型库清单（本文件）**：可选用哪些型号、各自特性与选型原则——**选型**的唯一来源。
> - **角色 agent 当前档位（`.codebuddy/agents/<role>.md` 的 `model` 字段）**：**实际分派用哪个**的唯一真源。
>   填 spec「执行配置」的模型列时**去读那个字段**，不要从本文件或任何文档里抄型号。
>
> 选型原则：**能力够用 + 价格最低**；中低复杂度角色（`backend-tester` / `frontend-tester` 等）优先用本地 Ollama 模型以省成本，强推理角色（评审、复杂实现）用更高档位。
> **本地模型名必须以 `ollama list` 实测，禁止凭空猜测**：填写 spec 执行配置或维护本文件前，先运行 `ollama list` 取本机真实已装模型；未核实的本地模型名一律无效。本机无 Ollama 时相关角色回退线上模型并备注原因。架构师角色由当前执行任务的 Agent 自身承担，"架构师"模型填该 Agent 实际使用的模型。

## 线上模型

| 模型 | 能力档位 | 上下文窗口 | 参考单价（输入/输出，每 1M tokens） | 适用角色 |
|------|----------|-----------|--------------------------------------|----------|
| Claude Opus 4.1 | 旗舰/最强推理 | 200k | 高 | 架构师、开发主管 |
| GPT-5.1 | 旗舰/强推理 | 128k | 高 | 架构师、开发主管 |
| Gemini 2.5 Pro | 旗舰/强推理 | 1M | 中高 | 架构师、开发主管 |
| Claude Sonnet 4.1 | 强代码/推理 | 200k | 中 | 开发主管、复杂实现 |
| GPT-5.1-mini | 中等代码 | 128k | 低 | 初级开发、测试 |
| Gemini 2.5 Flash | 中等代码 | 1M | 低 | 初级开发、测试 |

> 上表为示例默认值，实际请以各厂商最新公布为准，并按项目预算调整。

## 本地 Ollama 模型（零边际成本，优先用于中低复杂度角色）

> 以下为本机 `ollama list` 实测结果（2026-09-03 复核），非示例值。新增/更换模型请用 `ollama pull <模型名>`。

| 模型（ollama 名） | 能力档位 | 本地上下文 | 适用角色 |
|-------------------|----------|-----------|----------|
| **qwen3.8:27b-mlx** | 中高通用/推理（**MLX 版，27B 首选**） | 32k | 开发主管、后端开发 `backend-dev`、后端评审 `backend-reviewer`、**前端开发 `frontend-dev`、前端评审 `frontend-reviewer`**、初级开发（兼容）、复杂实现（**2026-09-03 起 27B 统一使用**；实测解码 24.3 tok/s） |
| qwen3.8:27b | 中高通用/推理（GGUF 全精度，需大显存） | 32k | ~~开发主管、复杂实现~~ **已弃用**：2026-09-03 起改用 `qwen3.8:27b-mlx`（GGUF 仅 13.8 tok/s，易致子代理超时） |
| oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU | 中高通用/推理（q4 量化，显存占用低） | 32k | ~~开发主管、初级开发~~ **已弃用**：含 `/` 的命名空间 ID 不被子代理框架识别（报 `model not found`），改用 `qwen3.8:27b-mlx` |
| deepseek-coder:33b | 中高代码（全精度，需大显存，本机可能跑不动） | 32k | 备选；若显存不足改用量化 27B |
| deepseek-coder-v2:16b | 专门代码（DeepSeek，16B，约 11GB 显存） | 32k | 初级开发（代码专精，拉取中，优于 33B 且显存友好） |
| qwen2.5-coder:14b | 专门代码（阿里，14B，约 10GB 显存） | 32k | 初级开发首选 coder（需 `ollama pull`） |
| qwen2.5-coder:7b | 专门代码（阿里，7B，约 5GB 显存） | 32k | 初级开发轻量备选（显存极紧时） |
| qwen3.5:9b | 中低通用/代码 | 32k | 产品经理、测试、**后端回归 `backend-tester`、前端回归 `frontend-tester`**、简单脚本 |

> 本地模型上下文受本机显存限制，落盘时按实际可用值填写。

## 选型速查

- 架构师 / 开发主管 → 线上旗舰（Opus / GPT-5.1 / Gemini 2.5 Pro）；本机有 Ollama 时开发主管用本地 **`qwen3.8:27b-mlx`**（27B 首选，**不是** `qwen3.8:27b`）。
- 初级开发 / 测试 → **需要 27B 时统一用 `qwen3.8:27b-mlx`**；简单任务可用专门的 coder 模型 `qwen2.5-coder:14b`（约 10GB）或 `deepseek-coder-v2:16b`（约 11GB）；显存极紧时退回 `qwen3.5:9b`；本机无 Ollama 时回退线上 `*-mini` / `*-flash`。
- 产品经理 → 本地 `qwen3.5:9b` 即可胜任产品使用步骤写作。
- **后端开发 / 后端评审（`backend-dev` / `backend-reviewer`）→ `qwen3.8:27b-mlx`**：后端含并发、事务、边界要求，必须 27B 级（9b 会产生真实并发缺陷）。
- **前端开发 / 前端评审（`frontend-dev` / `frontend-reviewer`）→ `qwen3.8:27b-mlx`**：2026-09-05 用户指定升配，质量优先（前端仍需可靠遵守 DOM 契约与 `?v=N` 约束）。
- **单端回归（`backend-tester` / `frontend-tester`）→ `qwen3.5:9b`**：跑测试与静态核对为主，9b 足够且快。

> ⚠️ **27B 一律选 MLX 版 `qwen3.8:27b-mlx`（注意是「冒号」），不要用 GGUF 版**：mlx 解码 24.3 tok/s、预填充 0.30s，GGUF 仅 13.8 tok/s、预填充 1.15s，mlx 解码快 76%、预填充快近 4 倍；GGUF 吞吐过低是子代理超时的主因。详见 `docs/sdd/retro/2026-09-02-subagent-timeout-mlx.md`。
> ⚠️ 子代理 `model` 字段**不能用含 `/` 的命名空间 ID**（如 `oamazonasgabriel/...`），会被判为 `model not found`；改用不含 `/` 的 `qwen3.8:27b-mlx`。
> ⚠️ 已弃用的 `qwen3.8-27b-q4` / `qwen3.8:27b`（GGUF）不再作为分派选项，仅保留记录以便回溯。

## 角色 agent 当前档位（唯一真源）

`.codebuddy/agents/<role>.md` 的 `model` 字段才是档位的唯一真源；**`AGENTS.md` 不复述型号**。
此处仅作快照记录，改动档位时以 agent 文件为准并同步本节。

| 角色 agent | 当前 `model` | 说明 |
|---|---|---|
| `architect` / `planner` / `doc-updater` | `Deepseek-V4.1-Flash` | 用户 2026-09-10 指定 |
| `backend-dev` / `frontend-dev` | `Deepseek-V4.1-Flash` | 同上 |
| `backend-reviewer` / `frontend-reviewer` | `Deepseek-V4.1-Flash` | 同上 |
| `backend-tester` / `frontend-tester` / `tester` | `Deepseek-V4.1-Flash` | 同上 |

> ⚠️ **`Deepseek-V4.1-Flash` 不在上方模型清单内**（上方为示例默认值，实际应按厂商公布为准）。该档位由用户指定，
> 属线上平台档位。若分派报 `Subagent model config is invalid` / `model not found`，说明当前环境未注册该档位，
> 按「选型速查」回退并在本次执行配置备注回退原因。

### 事故记录：临时档位不得固化为规范（2026-09-12 → 2026-09-20 还原）

- 2026-09-12 Spec027 Task03 期间，默认档撞账号级频率限制（429），临时改用更轻档位 `hy3`，16 次分派成功。
- 该临时值随后被写入 `AGENTS.md` 的「角色模型分配」表，并被标注为「实测修订：全部角色统一 `hy3`」，
  还附带「必须与 `.codebuddy/agents/*.md` 逐字一致」的同步要求 —— **把限流应急手段固化成了正式规范**。
- 用户明确表示 `hy3` 是**临时决策**，项目记忆 `.workbuddy-ai/memory/2026-09-12.md` 亦记有「临时操作，不用改 md」。
- 2026-09-20 已还原为 `Deepseek-V4.1-Flash`，并撤除 `AGENTS.md` 中复述型号的表格与「两处逐字一致」要求。

**教训**：429 临时改档只改 `.codebuddy/agents/<role>.md` 的 `model` 字段，任务结束后还原；
**不得**把临时档位写进流程纪律文档。详见 `SUBAGENT-ORCHESTRATION.md`「实测约束」。
