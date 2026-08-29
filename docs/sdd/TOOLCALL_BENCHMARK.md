# 本地模型 Function Call 能力实测报告

- 实测时间：2026-08-28
- 实测人：架构师（Hy3）
- 目的：验证本地 Ollama 模型能否稳定产出 OpenAI 风格 `tool_calls`，以决定角色 Agent 能否用本地模型驱动
- 探测方式：对 `http://localhost:11434/v1/chat/completions` 发**带 `tools` 定义**的请求（定义 `read_file`、`list_models` 两个工具），每个模型跑 3 个语义明确的 prompt，判定是否返回 `tool_calls`、参数 JSON 是否合法、工具选择是否正确
- 探测脚本：`/tmp/ollama_toolcall_probe.py`（一次性，不入库）

## 结论总览

| 模型 | `ollama show` Capabilities | 上下文 | 实测 tool_calls | 单次耗时 | 判定 |
|---|---|---|---|---|---|
| `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU` | **tools**, thinking | 262144 | **3/3** | 3.7–19.2s | ✅ **推荐**（官方声明 + 实测双通过） |
| `qwen3.8:27b` | completion, vision | 262144 | **3/3** | 6.0–16.6s | ✅ 可用（未声明但实测通过） |
| `qwen3.5:9b` | completion, vision | 262144 | **3/3** | 1.7–7.4s | ✅ 可用（最快，未声明但实测通过） |
| `deepseek-coder-v2:16b` | completion, insert | 163840 | 0/3 | — | ❌ 不支持（Ollama 返回 `does not support tools`） |
| `deepseek-coder:33b` | completion | 16384 | 0/3 | — | ❌ 不支持（同上） |

## 关键发现

1. **Capabilities 声明与实际能力不一致**：只有量化版 `qwen3.8-27b:q4-km-32gbGPU` 在 `ollama show` 中声明了 `tools`；但 `qwen3.5:9b`、`qwen3.8:27b` 虽**未声明**，实测却**稳定 3/3 产出 tool_calls**，且工具选择与参数均正确。
   → 不能只看 Capabilities 下结论，**必须实测**。
2. **工具选择准确**：三个可用模型都能把"读文件"映射到 `read_file`（path 填对、可选参数 `lines` 也正确补上）、把"列模型"映射到 `list_models`。
3. **参数合法性**：全部 `tool_calls` 的 `arguments` 都是**合法 JSON**（`args_valid_json: true`）。
4. **deepseek 系列全线不支持**：两个 deepseek-coder 模型均被 Ollama 明确拒绝（`does not support tools`），**不可用于 agent 模式**。
5. **速度与上下文**：`qwen3.5:9b` 最快（1.7–7.4s）；qwen3.8 系列上下文达 262144，足以支撑多轮工具调用。

## 对角色 Agent 选型的指导

- **需要 function call 的 Agent（如验收测试 agent）**：首选 `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU`（官方声明 tools + thinking，最稳）；若追求速度可选 `qwen3.5:9b`。
- **不需要 tool call 的纯文本产出（如评审文档写作）**：任意可用本地模型均可。
- **禁止**用 deepseek-coder 系列驱动任何 Agent（会直接 400 失败）。
- 此结论用于填写 `.codebuddy/models.json` 的 `supportsToolCall` 与 `.codebuddy/agents/*.md` 的 `model` 字段；后续新增模型须**重新实测**再入库。
