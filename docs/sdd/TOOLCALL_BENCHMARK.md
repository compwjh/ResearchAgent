# 本地模型 Function Call 能力实测报告

- 实测时间：2026-08-28
- 实测人：架构师（Hy4）
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

## 补充：代码产出能力对比（2026-08-28，同一编码任务）

任务：实现 `mask_model_name(name, max_len=24)`，含 5 条约束（长度截断、含 `/` 取末段**且取冒号前**、空串处理、返回串总长等于 max_len、不抛异常）。

| 模型 | 冒号前处理 | 返回长度正确 | 整体质量 | 耗时 | 支持 tools | 结论 |
|---|---|---|---|---|---|---|
| `qwen3.5:9b` | ✅ 正确处理 | ✅ | 最佳（唯一完整理解需求） | 18.7s（含思考） | ✅ | ✅ **推荐给编码类角色** |
| `deepseek-coder-v2:16b` | ❌ 未处理 | ✅（截断段正确） | 一般（短名分支返回原值，与"取末段"矛盾） | — | ❌ | ⚠️ 仅纯文本场景 |
| `deepseek-coder:33b` | ❌ 未处理 | ❌（拼回前缀导致超长） | 较差（啰嗦、逻辑绕） | 24.1s | ❌ | ⚠️ 不推荐 |

### 第一轮结论（指令风格）与其偏差

两个 deepseek-coder 模型表现明显偏差：漏"冒号前"约束、33b 返回超长串。

**但这次测试方法有偏差，已复测修正（见下）**。

### 第二轮复测：修正用法后（2026-08-28）

发现三个用法问题，修正后结论有变化：

1. **base 模型 vs instruct 模型用错了场景**
   `ollama show` 显示本机两个 deepseek-coder 的 Capabilities 只有 `completion`/`insert`，**无 chat** → 它们是 **base 模型**，擅长**代码补全（续写）**，不擅长"按指令实现函数"。DeepSeek 官方文档亦指出 instruct 版才针对指令遵循训练。
   → 改用**补全风格** prompt（给出函数签名 + docstring 让模型续写实现）后，v2:16b 输出明显改善（还自动生成测试用例，仅 3.6s）。
2. **量化差异未控制**：`deepseek-coder:33b` 是 **Q4_0**（最粗糙的 4bit 量化），qwen 系列是 **Q4_K_M**（分组量化，质量更好）。同参数量下 Q4_0 质量明显打折。
3. **thinking 模型会耗尽 token 预算**：`qwen3.8:27b`、量化 27B、`qwen3.5:9b` 均为 thinking 模型，默认开启思考时会把 `num_predict` 预算耗在推理上，**导致最终代码输出为空**（实测 27b 首轮输出空白，45.9s）。
   → 必须传 `"think": false`（或 `ollama run --hidethinking`）后再测。

### 复测结果（补全风格 + temperature=0.2 + think=false）

| 模型 | 冒号 tag 处理 | 完整性 | 耗时 | 支持 tools | 结论 |
|---|---|---|---|---|---|
| `qwen3.8:27b` | ✅ | ✅ **全部 5 条满足**（含类型检查、try 包裹、注释清晰） | 29.2s | ✅ | ✅ 编码质量最佳 |
| `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU` | ✅ | ✅ 全部满足（逐条注释对应规则） | 45.4s | ✅（官方声明 tools+thinking） | ✅ 质量优，agent 最稳 |
| `deepseek-coder-v2:16b` | ❌ 仍漏 | 部分（结构对、自带测试用例） | **3.6s**（最快） | ❌ | ⚠️ 快但能力上限有限 |
| `qwen3.5:9b` | ✅ | 较好 | ~19s | ✅ | 速度优先场景可用 |

**修正后的结论**：
1. 用法修正后 coder 模型**确有改善**（补全风格下 v2:16b 仅 3.6s 且结构正确），但仍**漏掉关键约束**，且**始终不支持 function call** → **无法驱动编码 Agent**（编码需要读写文件、跑测试，必须有 tools）。
2. **编码质量排序**：27B 级（qwen3.8:27b / 量化 27B）> `qwen3.5:9b` > deepseek-coder 系列。

→ **编码类角色（junior-dev）升级为 `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU`**：官方声明 tools + thinking（agent 最稳），编码质量经复测满足全部约束。

### 第三轮：同条件对比「9b vs 27B」（2026-08-28，回答"9b 够不够"）

**简单任务**（`mask_model_name`，单函数 5 条约束），统一补全风格 + temp=0.2 + think=false：

| 模型 | 完整性 | 耗时 |
|---|---|---|
| `qwen3.5:9b` | ✅ 全部满足（注释详尽） | **14.6s** |
| 量化 27B | ✅ 全部满足 | 45.4s |
| `qwen3.8:27b` | ✅ 全部满足 | 29.2s |
| `deepseek-coder-v2:16b` | ❌ 漏冒号约束 | 3.6s |

→ 简单任务上 **9b 与 27B 质量相当，9b 快约 3 倍**。

**复杂任务**（带 TTL 的线程安全 LRU 缓存装饰器，7 条要求含并发/边界）：

| 维度 | `qwen3.5:9b`（35.3s） | 量化 27B（76.0s） |
|---|---|---|
| 可哈希判断 | ❌ `try` 位置错误（元组拼接不抛 TypeError，只有 dict 查找才抛） | ✅ 主动 `hash(key)` 测试，捕获 TypeError/AttributeError |
| **并发处理** | ❌ **在 `with lock` 内调用用户函数**（阻塞其他线程、可能死锁） | ✅ **锁外计算**，并注释 "avoid holding lock during computation" |
| 双重检查 | ❌ 无 | ✅ 重新加锁后检查其他线程是否已写入 |
| LRU 淘汰 | 基本实现 | ✅ `while len(cache) > maxsize: popitem(last=False)` |
| TTL 过期 | 基本实现 | ✅ 过期删除 + `move_to_end` |
| 接口挂载 | — | ✅ `wrapper.cache_clear` / `cache_info` |

→ **复杂任务上 27B 有实质质量优势**（尤其并发正确性，9b 存在持锁调用的真实缺陷）。

**最终结论**：
- **简单/独立小函数**：`qwen3.5:9b` 足够且快 3 倍 → 性价比较高。
- **复杂/并发/边界要求高的编码**：**必须用 27B 级**（9b 会产生持锁调用这类真实缺陷）。
- 因此 `junior-dev` 保持 `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU` 是正确的（编码质量优先）。
- `deepseek-coder-v2:16b`（3.6s 最快）作为**快速草稿**角色 `code-drafter`：仅用于独立小片段初稿，产出需复核，且因其不支持 tools 而不能操作文件。

## 对角色 Agent 选型的指导

- **需要 function call 的 Agent（如验收测试 agent）**：首选 `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU`（官方声明 tools + thinking，最稳）；若追求速度可选 `qwen3.5:9b`。
- **不需要 tool call 的纯文本产出（如评审文档写作）**：任意可用本地模型均可。
- **禁止**用 deepseek-coder 系列驱动任何 Agent（会直接 400 失败）。
- 此结论用于填写 `.codebuddy/models.json` 的 `supportsToolCall` 与 `.codebuddy/agents/*.md` 的 `model` 字段；后续新增模型须**重新实测**再入库。
## 当前角色模型分配（2026-08-28 定稿）

| 角色 agent | 模型 | 选择理由 |
|---|---|---|
| `pm` | `qwen3.5:9b` | 文案类任务，最快（tool call 1.7–7.4s） |
| `junior-dev` | `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU` | **用户要求编码质量优先**，升级到 27B 级：复测满足全部约束、官方声明 tools（编码 agent 需读写文件与跑测试） |
| `tester` | `qwen3.5:9b` | 判定类任务，快；实测单次任务 90s |
| `tech-lead` | `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU` | 评审需更强推理，用量化 27B（官方声明 tools+thinking，最稳）；代价是慢（单次 3–8 分钟） |

> **决策记录（2026-08-28，用户拍板）**：`tech-lead` 的工作（需求/技术评审、PR 裁决）**比较重要，质量优先于速度**，因此**保持量化 27B，不降级到 9b**。其余角色（pm/junior-dev/tester）用 `qwen3.5:9b` 以提速。后续不要为了提速擅自调整 tech-lead 的模型。
| `sdd-orchestrator` | `inherit`（主会话模型） | 编排走主模型，避免本地慢模型拖慢整体流程 |

> 用户级 `~/.codebuddy/models.json` 已注册上表所需模型（原 `qwen3.8:27b` 保留，新增 `qwen3.5:9b` 与量化 27B），改动前已备份为 `models.json.bak.<时间戳>`。
