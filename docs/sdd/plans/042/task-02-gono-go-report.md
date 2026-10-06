> 关联：[spec-042](../../specs/042-openeval-agent-evaluation.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01（spec 已确认）；当前状态：**已产出**

# Task 02 — Go/No-Go 判定报告

## 总体判定：**Go**（首期 `chat_quality` 评测闭环可落地）

> 判定时间：2026-09-23 ｜ 判定人：架构师（主 agent）
> 附 2 条遗留项，均不阻断首期落地。

## 五条验收项逐条结论

### ① 路由与 token —— ✅ Go

- `backend/app/platform/config.py:122`：`OLLAMA_ROUTE` 默认已是 **`direct`**（spec-041 修订已生效）。
- 运行实例未显式传该变量，走代码默认 `direct`。
- 实测（最近 12 条 `ollama-chat` 按 route/model 聚合）：

| route | model | 条数 | token | 平均延迟 | 判定 |
|---|---|---|---|---|---|
| `direct` | `qwen3.8:27b` | 1 | in=83 / out=64 | 29.57s | 主生成链路，token 真实 ✅ |
| `langchain` | `qwen3.5:9b` | 11 | 全 0 | 0.02s | 旁路（探针/记忆分析），token 与延迟失真 |

- **遗留 L1**：旁路 `langchain` + `qwen3.5:9b` 仍 0-token。按 Q7 属 spec-013/041 范围，
  **不在本 spec 修复**，不阻断首期（首期评测对象是主生成链路）。

### ② 判官可用 —— ✅ Go（`chat_quality`）／ ⚠️ Deferred（`memory_correctness`）

依据 `task-02-judge-consistency-chat_quality.json` 与 `task-02-judge-consistency-memory.json`
（判官 primary `qwen3.5:9b`、fallback `qwen3.8:27b`、温度 0、每条重复 3 次）：

| 维度 | n | 9b 自一致 | 27b 自一致 | 跨判官一致 | 结论 |
|---|---|---|---|---|---|
| `chat_quality` | 20 | **1.0** | **1.0** | **1.0** | ✅ `adopt: qwen3.5:9b` |
| `memory_correctness` | 6 | 1.0 | 1.0 | **0.5** | ⚠️ Deferred |

- **遗留 L2**：`memory_correctness` 跨判官一致率仅 0.5（n=6），根因是**本数据集缺少专门的记忆探针
  trace**，该维度在当前数据上不适定。**留待 task 03 用专门记忆探针重测**，不伪造结论、不强凑数据。
- 按 Q8=A 回退链：9b 自一致达标 → 采用 9b；若后续 9b 不达标则回退 27b。本次 9b 达标，无需回退。

### ③ 数据桥接可行 —— ✅ Go

- 数据集：`task-02-eval-dataset.json`（24 条：20 scored / 2 empty / 2 intake）。
- `SKIPPED` 判定正确：空 output 与被技能路由劫持的「研究 Intake 已保存…」类条目均被跳过，**未记 0 分**。
- 回写闭环实测（第三轮）：判官 3/3 命中 → 读 Langfuse **727 条** → **写回 score 成功**（id `8f24dd05`）
  → 删除校验 **202**。产物：`task-02-run-eval.py`、`task-02-eval-run-summary.json`。

### ④ 离线成立 —— ✅ Go

- **结构性保证**：`task-02-run-eval.py` 内置 `offline_guard`，任何非 loopback 主机在 HTTP 调用前即被拒绝。
- **实证**：完整闭环（判官 → Langfuse 读/写/删）全部成功，而 Langfuse(3000) 与 Ollama(11434)
  均在 `127.0.0.1`；若存在外网依赖该闭环无法成立。
- 备注：`--dry-run` 模式不触发判官调用（仅分类统计），故不适合作为采样对象；
  离线结论以**结构性守卫 + 闭环实证**为准。

### ⑤ 选型明确 —— ✅ Go（结论已定，并已修订 Q9）

- **F16**：SSRF 白名单（`LANGFUSE_LLM_CONNECTION_WHITELISTED_HOST` / `_IPS`）放行后，
  Langfuse 已能连本机 Ollama（`llm-connections` 201、创建 evaluator 200、worker 日志实证连到 127.0.0.1:11434）。
- **F17（决定性）**：创建规则仍返回 422 `No object generated: response did not match schema` ——
  **Ollama 的 OpenAI 兼容 `/v1` 不支持 `response_format: json_schema`（strict）**，
  而 Langfuse 内置结构化输出判官引擎依赖该模式 → **内置 evaluator 在本机产不出 score**。
- **结论**：Q9=C 前半段证伪，修订为**全部维度走自建判官、Langfuse 仅作 score 落点**（Q4 不变）。
  在 `chat_quality` 上，**openeval-cli 不再必要**——「自定义 prompt 判官 + `create_score` 写回」已满足需求。
  记忆正确性维度待 task 03 专用探针后再定是否需要外部评测库。

## 遗留项

| 编号 | 内容 | 归属 | 是否阻断 |
|---|---|---|---|
| L1 | 旁路 `langchain` + `qwen3.5:9b` 调用 token 恒为 0、延迟失真 | spec-013 / spec-041 | 否 |
| L2 | `memory_correctness` 跨判官一致率 0.5，数据集缺记忆探针 | task 03（专用探针重测） | 否 |

## 下一步

- Task 03：用**专门记忆探针 trace** 重测 `memory_correctness`，补齐 Q5-B 维度。
- 期间可先用 `task-02-run-eval.py` 对 `chat_quality` 做常态化评测与回归基线。
