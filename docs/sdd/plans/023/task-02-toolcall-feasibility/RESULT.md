# spec-023 Task02 — 本地 27B 能力可行性验证（Go/No-Go）

> 关联 spec：[023-skill-tool-management.md](../../../specs/023-skill-tool-management.md)（决策 Q4 / Q9）
> 关联计划：[023/README.md](../README.md)
> 执行角色：backend-dev ｜ 执行时间：2026-09-11 19:33–20:20 (+0800)
> 探测环境：`qwen3.8:27b-mlx` @ `http://192.168.31.180:11434`（`OLLAMA_BASE_URL`）

---

## 一、结论

| # | 验证项 | 结论 | 依据摘要 |
|---|---|---|---|
| 1 | 原生 function calling（`/api/chat` + `tools` → `tool_calls`） | ✅ **GO** | 6 用例中 5 次稳定返回结构化 `tool_calls`，参数名/类型正确，耗时 1.7–11.7s |
| 2 | thinking 模型在 `think:false` 下输出稳定性 | ✅ **GO，但必须显式 `think:false`** | `think:false` 输出稳定（5/5 一致）；`think:true` 时 `content` **为空**，内容落 `thinking` 字段（已复现） |
| 3 | 意图识别（判断用哪个 / 不用 Skill） | ✅ **GO** | `B-llm-t3` 单次 3 选 1：**误判率 5%（1/20）**，修正 ground truth 后 **0%（20/20）**；**假阳性 0** |

**总判定：GO。** spec Q9 按原设计「C 混合」实现（原生 function calling 优先），**无需**把降级路径"计划 JSON"作为默认；Q4 的「规则匹配 + LLM 意图识别」双触发**建议都保留**，但**规则必须收紧**（见风险 R2）。

---

## 二、探测方法

| 脚本 | 用例数 | 说明 |
|---|---|---|
| `probe_toolcall.py` | 6 | 直连 `/api/chat`，覆盖 无 system / 有 system / `think:true` 对照 / 无需工具 / 显式点名 Skill / 下载意图 |
| `probe_intent.py` | 20 × 3 策略 | P01–P10（期望命中某 Skill）+ N01–N10（期望 `none`），策略 `B-rule`（纯规则）/ `B-llm-t2`（两段式）/ `B-llm-t3`（单次 3 选 1 受控 JSON，`temperature=0`） |
| `result_retry.json`（`/tmp/probe_retry.py`） | 15 | 超时复现性（P07×5）、争议样本复现（P08×5）、`temperature=0` 稳定性（×5） |
| 边界探测（`/tmp/probe_edge.py`） | 3 | `/api/show`、模型不存在、非法 `tools` schema |

所有 HTTP 调用统一 `httpx.Client(trust_env=False)`（macOS 系统代理会劫持内网请求）；所有 LLM 调用统一 `think=false`。原始请求/响应逐条留档于 `raw/`。

---

## 三、验证项 1：原生 function calling —— GO

### 3.1 服务端声明
`POST /api/show` 返回：
```json
{"capabilities": ["completion", "vision", "tools", "thinking"],
 "details": {"family": "qwen3_5", "parameter_size": "27.8B", "quantization_level": "nvfp4"}}
```

### 3.2 真实响应片段（`result_toolcall.json` / `raw/A*.json`）

| 用例 | think | 耗时 | 判定 | 真实 `tool_calls` |
|---|---|---|---|---|
| A1 无 system | false | 11.66s | `TOOL_CALL_OK` | `search_paper_catalog{query:"fuzzing", year:2024}` |
| A2 带 system | false | 5.19s | `TOOL_CALL_OK` | `search_paper_catalog{query:"fuzzing", year:2024, page_size:10}` |
| A3 对照 | **true** | 2.80s | `TOOL_CALL_OK`（但 `content` 空） | `search_paper_catalog{query:"fuzzing", year:2024, page_size:10}` |
| A4 无需工具 | false | 5.94s | `TEXT_ONLY`（`tool_calls:[]`） | — |
| A5 显式点名 | false | 1.84s | `TOOL_CALL_OK` | `search_paper_catalog{query:"隐私", year:2023}` |
| A6 下载意图 | false | 1.72s | `TOOL_CALL_OK` | `download_and_import_paper{search_id:"search-abc", catalog_paper_id:"42"}` |

原始响应（A6 节选）：
```json
{"message":{"role":"assistant","content":"","tool_calls":[
  {"id":"call_r5az9mbg","function":{"index":0,"name":"download_and_import_paper",
   "arguments":{"catalog_paper_id":"42","search_id":"search-abc"}}}]},
 "done":true,"done_reason":"stop","eval_count":45}
```

**要点**：
1. `tool_calls` 是 Ollama 的**结构化对象**，`function.arguments` 已是 **dict（非 JSON 字符串）**，无需二次 `json.loads`。
2. 参数抽取正确且类型合理：`year` 为 int、`query` 为中文原样保留、A6 从自然语言里准确抽出 `search_id` / `catalog_paper_id`。
3. A2 中 tool description 写的「固定 10」被模型遵守（自动补 `page_size:10`）→ **工具描述是有效的参数引导手段**。
4. A1 未给 `page_size`（未在 description 强约束时），说明**必填字段必须写进 `required`**，不能靠描述暗示。
5. A4 证明**不相关提问不会乱调工具**。

### 3.3 thinking 陷阱（已实证）
- `think:false` → `content` 有值，`thinking` 空。
- `think:true` → **`content` 为空字符串**，全部文本落在 `thinking` 字段。若链路只读 `content`，表现为「模型无响应」。

> **硬结论**：聊天链路必须显式传 `"think": false`，并且**后端仍应兜底**：`content` 空但 `thinking` 非空时，判定为「think 未生效」而非「模型无输出」。

---

## 四、验证项 2：意图识别 —— GO

### 4.1 误判率（20 条 ground truth）

| 策略 | 正确 | **误判率** | 均耗时 | 假阳性 | 备注 |
|---|---|---|---|---|---|
| `B-rule` 纯规则 | 18/20 | **10.0%** | ~0s | **2** | 零成本但两个误判都是「不该调用却调用」 |
| `B-llm-t2` 两段式 | 18/20 | **10.0%** | 2.79s | 0 | 1 次 `ReadTimeout`（不可复现） |
| `B-llm-t3` 单次 3 选 1 | 19/20 | **5.0%** | 1.92s | 0 | 唯一「误判」经复核为 ground truth 争议 |

**修正后（P08 归为 `none`）**：`B-rule` 90%、`B-llm-t2` 95%、**`B-llm-t3` 100%**。

### 4.2 逐条误判明细（全部 4 条）

| 用例 | 消息 | 期望 | 实际 | 性质 |
|---|---|---|---|---|
| N07 | "帮我用 usenix-**papper**-catalog-search 搜论文。" | `none` | `B-rule`→catalog；两种 LLM→`none` ✅ | **规则假阳性**（正则命中 `usenix` 子串） |
| N10 | "我**听说过** usenix-paper-catalog-search 这个东西。" | `none` | `B-rule`→catalog；两种 LLM→`none` ✅ | **规则假阳性**（弱提及被当成指令） |
| P07 | "这篇 USENIX 的 prepublication PDF 能帮我验证并导入吗？" | download | `B-llm-t2` → `ERROR:ReadTimeout` | 传输抖动，**重跑 5/5 正确（1.44–1.90s）**，不可复现 |
| P08 | "帮我从 DBLP 补齐 2021 年 USENIX Security 论文的 DOI 信息。" | （标注）catalog | 两种 LLM 均 `none`（5/5 稳定） | **ground truth 争议**：DBLP 补字段是 catalog Skill 的内部子步骤，非用户独立意图，判 `none` 亦合理 |

### 4.3 稳定性
- `temperature=0` 下同一请求重复 5 次：**5/5 完全一致**（`usenix-paper-catalog-search`），无漂移。
- 争议样本 P08 重复 5 次：**5/5 一致**判 `none` → 是**稳定的模型判断**，非随机噪声。
- 重复调用耗时：t3 稳定 1.2–1.9s，波动可接受。

---

## 五、失败形态与边界（供 Q9 降级判据参考）

| 场景 | 真实形态 | 处理建议 |
|---|---|---|
| 模型不存在 | HTTP **404** + `{"error":"model 'not-exist-model' not found"}` | 可解析，直接映射为可读错误 |
| `tools` schema 非法 | HTTP **200**，**工具被静默忽略**，模型改当普通对话回答（`"Hi there! How can I help you today?"`） | ⚠️ **不能依赖 Ollama 校验**；后端必须先自校验 tools schema |
| `think:true`（未按约定传 false） | `content == ""`，内容在 `thinking` | 后端兜底检测并告警 |
| 首轮冷启动 | 单次 `ReadTimeout`（A1 11.66s vs 稳态 1.5s）；重跑正常 | 客户端超时 ≥60s + 一次重试 |

---

## 六、风险与对后续 Task 的约束

| # | 风险 | 影响 | 建议动作（归属 Task） |
|---|---|---|---|
| **R1** | Ollama **静默忽略非法 tools**，不报错 | 拼错工具名会一路透传到执行层 | Task07 必须**独立校验** `tool_calls[].function.name` ∈ 注册表且 enabled，且 `arguments` 过参数白名单；**不得**依赖模型端校验 |
| **R2** | 纯规则匹配有 **2 处假阳性**（拼写错误 N07、弱提及 N10） | 「不该调用却调用」，会误触发 Skill | Task06 规则**收紧**：① 匹配 Skill 名用**词边界**而非子串；② 增加**指令性动词**约束（"使用/帮我用/请用 + 技能名"），单纯的"听说过/关于"不触发；**LLM 作为第二跳兜底** |
| **R3** | 27B 首轮冷启动可达 11.7s | 首条消息体感卡顿 | Task06/07 设超时 ≥60s；首轮预热（可选） |
| **R4** | 单次 `ReadTimeout` 曾发生 | 偶发失败 | 调用需带 1 次重试；失败时降级到规则匹配而非直接报错 |
| **R5** | 3 选 1 提示词若改动可能影响准确率 | 回归风险 | Task06 的 prompt 视为**受控资产**，改动需重跑本探测脚本回归 |
| **R6** | 样本量小（20 条） | 误判率置信区间宽 | 结论按「无假阳性 + 稳定性 5/5」采信；Task09 验收时用真实用户话术补充样本 |

### 对 Q9 的明确建议
- **原生 function calling 可用 → 走 A 路径为默认**，降级 B（计划 JSON）仅作为**异常兜底**（404 模型缺失 / 连接失败 / `tool_calls` 解析失败），不必默认启用。

### 对 Q4 的明确建议
- **双触发都保留**：规则负责**零延迟、确定性命中显式点名**（P01/P10 这类），LLM 负责**边界与泛化**（N07/N10 这类假阳性纠正、P05 这类未直接点名的意图）。
- 规则命中时**直接执行不再问 LLM**（省一次推理）；规则未命中时才调 LLM（t3 单次 3 选 1，均 1.92s）。

---

## 七、复现方式

```bash
cd /Users/wjh/work/ResearchAgent-2/ResearchAgent
.venv/bin/python docs/sdd/plans/023/task-02-toolcall-feasibility/probe_toolcall.py   # 探测项 1
.venv/bin/python docs/sdd/plans/023/task-02-toolcall-feasibility/probe_intent.py     # 探测项 2（约 2-4 分钟）
```

> 两脚本均只读探测，不修改 `backend/**` 业务代码、不修改 `.agents/skills/*`。

## 八、产物清单

| 文件 | 内容 |
|---|---|
| `probe_toolcall.py` | function calling 探测脚本（可复现） |
| `probe_intent.py` | 意图识别探测脚本（可复现） |
| `result_toolcall.json` | 6 用例判定汇总 |
| `result_intent.json` | 20×3 策略汇总 + 逐条明细 |
| `result_retry.json` | 超时复现性 / 争议样本 / 稳定性补充数据 |
| `raw/A*.json` | function calling 原始请求与响应 |
| `raw/intent/*.json` | 意图识别逐条原始响应 |
| `.intent.log` | 意图探测运行日志 |
