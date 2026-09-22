# Spec041 需求评审：Langfuse trace 详情可见、瀑布图可用、input/output 全量

## 评审元数据

- 评审对象：`docs/sdd/specs/041-langfuse-trace-detail-and-waterfall.md`（状态：已确认）
- 关联：`docs/sdd/specs/013-llm-observability-platform.md`（A2/A3/A4/A5、第 143 行「不自研甘特图」约束）
- 评审角色：架构师（评审总控）
- 评审范围：目标清晰度、8 条边界可验证性、与 spec-013 A3/A4/A5 对齐、范围自洽（input 全量 vs spec-013 表述冲突的消解）、明确不做与兜底 v3 路径前置条件
- 评审时间：2026-09-21（Asia/Shanghai）

## 结论

**有条件通过。**

Spec041 的目标（「必须看到瀑布图，无论用什么方式」+ input 全量、不保留隐私脱敏）由用户 grill 裁决明确，方向正确，根因定位（events_only 写模式 + redact 清零）在源码层面属实。但有三处 P1 必改项阻断「直接通过」：

1. **边界 4 / 边界 5 对 spec-013 A4 / A5 过度承诺**：dual 模式只让 `observations` 表非空，使原生 Langfuse 详情页与「单条 generation 瀑布条」出现；但 A4 要求的 `load / prefill / first_token / decode / overhead` **五阶段独立时间条**、A5 要求的「冷调用 load 段明显更长」目前后端**并未以子 span 实现**（spans.py:13-22 已明确废弃 phase 子 span 方案，改为 metadata + numeric score；SCORE_METRICS 仅有 `load_ms / prompt_eval_ms / eval_ms / overhead_ms / ttft_ms`，无独立 5 阶段条）。前端也无任何 Langfuse 瀑布图/phase 条渲染。故 dual 修复「必要但不充分」于 A4/A5。
2. **「input 全量 vs A3 冲突」归因错位**：真正承诺完整 prompt 的是 spec-013 **A2（第 155 行：「展开可见完整 prompt 组成（system / 历史 / 用户问题）」）**，A3（第 156 行）只承诺 output。冲突实际是「实现 redact 违反了 A2」，而非 spec 与 A3 歧义；spec-041 第 36、66 行把修订锚点只放在 A3 是错位的。
3. **备选方案 premise 错误**：`LANGFUSE_MIGRATION_V4_ALLOW_PREVIEW_OPT_IN` 在 env.ts:590-592 **默认已是 `"true"`**，故「保持 events_only 并显式置 true」近乎无操作；且实测 `/api/public/traces` 在 events_only 下被硬阻断（与 opt-in 无关），env.ts:720-727 注释说明 opt-in 仅 gating **web 读取路径**（events vs legacy 表），不解除 public REST API 阻断。

P2 项（不阻断通过，但实施前须书面澄清）：兜底 v3 路径的 SDK 改写成本、历史 trace 不回填声明。

## 评审范围与边界逐条核对

| 边界 | 判定 | 依据与说明 |
|---|---|---|
| B1 `dual` 后 Langfuse 正常启动、worker 不因 V4 配置校验抛错 | 通过 | env.ts:701-728 `validateV4Flags`：`dual` + 默认 `NATIVE_OTEL_BEHAVIOUR=direct` 不触发任一 hard-error 分支（仅 `legacy+direct`、`events_only+dual_write`、`events_only+!optin` 抛错）。 |
| B2 新产生调用后 `observations`/`analytics_observations` 非空 | 通过（范围明确） | `v4WritesToLegacyTables` 在 `dual` 下为真（env.ts:692-693），写 legacy 表。仅影响**新**写入，与边界措辞一致。 |
| B3 详情页可打开且 input/output 全量（input 不再是 0 字符） | 通过（input 部分依赖修复） | output 沿用现状（A3 已满足）；input 依赖根因 2 修复（见技术评审）。output 全量无需改动。 |
| B4 详情页瀑布图可见，并按 A4 呈现 5 阶段时间条 | **不通过（P1）** | 见结论 1：5 阶段条后端未实现为子 span，前端无渲染；dual 仅保证单条 generation 条。须重定义验收形态。 |
| B5 冷/热调用在瀑布图可区分（A5） | **不通过（P1）** | 同结论 1：原生瀑布图不含独立 load 段条，无法呈现「冷调用 load 段明显更长」。依赖 A4 处置结果。 |
| B6 input 全量后 `redact_prompt_messages` 旧行为不再生效（单测锁定 content 保留原文） | 通过（须修函数本体） | 须作用于函数本体以覆盖 5 个调用点（技术评审必改项）。现有测试无相关锁定（grep 测试目录无命中），需新增。 |
| B7 观测层异常不影响业务（fail-open 不变） | 通过 | `safe_call`（safe.py:13-22）为唯一 fail-open seam；`record_ollama_generation`/`record_event` 的 `_report` 均包于 `safe_call`（spans.py:210/276）。 |
| B8 `system.query_log` 缺失报错切换后复测；仍报错则评估启用 query_log（不阻断主链路时记遗留） | 通过 | 边界措辞自洽，属记录+复测，非阻断。技术评审 R2 补充 GRANT 前置。 |

## 与 spec-013 A3/A4/A5 对齐核对

- **A3（output 全量）**：未受影响，现状已满足，无需改动。对齐：**通过**。
- **A4（5 阶段瀑布条）**：见结论 1。当前实现把阶段耗时放入 `metadata` + `numeric score`（spans.py:44-52、103-123、203-208），并未生成 `phase:load/prefill/first_token/decode/overhead` 子 observation。Langfuse 原生瀑布图按 observation 的起止时间渲染，**单条 generation 不会拆出 5 段**。对齐：**未达成，须处置**。
- **A5（冷/热 load 段区分）**：同上，原生瀑布图无独立 load 段条，`is_cold_start` 仅作为 score（spans.py:99）而非可见时间条。对齐：**未达成，须处置**。
- 另：spec-013 第 143 行「不自研甘特图」与 spans.py:13-22「精确甘特图由任务 07 的自研视图从 metadata 渲染」**内部矛盾**，且前端无该自研视图。spec-041 的「同步修订 spec-013」必须一并消除该矛盾，否则 A4/A5 验收无着落。

## 范围自洽：input 全量 vs spec-013 表述冲突的消解

- **现状**：实现层 `redact_prompt_messages`（spans.py:225-227）把 `content` 清零，违反 spec-013 **A2（第 155 行已承诺完整 prompt 组成）**。用户裁决「不需要隐私设计」即恢复 A2 意图。
- **spec-041 错位的表述**：第 36 行称「A3 只承诺可见完整输出内容，对 prompt 原文无承诺」，第 66 行计划「消除与 A3 的表述歧义」。实际上 (a) A2 已承诺 prompt 原文；(b) A3 是 output，与 input 无关。冲突面是「实现 vs A2」，不是「A3 歧义」。
- **必改（P1-2）**：spec-041 与随之修订的 spec-013 应把 input 全量锚定到 **A2**，明确保留 A3 的 output 表述，并删除/澄清 redaction 时代的隐私注释（spans.py:166-168），而非仅动 A3。

## 「明确不做」与兜底 v3 路径前置条件

- 5 条「明确不做」（不自研甘特图[除非 A/B/兜底全失败且修订 spec-013]、不改采样率、不改 OTel/SDK、不动业务+fail-open、不修 V4LegacyApiUsageJob）边界清晰，与「禁止第二套实现」「fail-open」原则一致：**通过**。
- **备选/兜底链路逻辑缺陷（P1-3）**：spec 的「A=dual（首选）；B=events_only+optin（备选）；兜底=v3」。但 B 实质是当前默认状态（optin 默认 true），且 `/api/public/traces` 在 events_only 下硬阻断已实测 —— 即 B 在当前配置下**本就失败**，无法作为「A 失败后的备选」。故若 A(dual) 失败，实际上直接落入 v3 兜底，而非 B。spec 须重写该降级链：明确 B 不解除 public API 阻断、仅影响 web 读取路径、且瀑布图支持未证实；dual 才是唯一现实首选。
- **兜底 v3 成本（P2-4）**：v3 与 v4 SDK 不同（spec-013:73 要求 SDK≥4.7.0 实时直写；v3 为另一接入方式），换 v3 需改写 SDK 接入，spec 须显式列出该成本，不能仅写「相应调整 SDK 接入」。
- **历史 trace 不回填（P2-5）**：dual 仅影响新写入；`LANGFUSE_BACKGROUND_MIGRATION_V4_ENABLE_HISTORIC_BACKFILL` 默认 true 但对 net-new 部署是 no-op（env.ts:597-603），已产生的 ~1769 事件行不会回填 legacy 表。须书面声明：切换 dual 后**历史 trace 仍无详情/瀑布图**，仅新 trace 受益。

## 必改项清单

| 编号 | 级别 | 必改内容 | 当前位置 |
|---|---|---|---|
| P1-1 | 阻断 | 重定义边界 4 / 边界 5 与 A4/A5 的验收形态：明确「瀑布图可见」是指原生单条 generation 条，还是 5 阶段条；若要求后者，须决策补 phase 子 span 或启用 Task07 自研视图，并据此修订 spec-013 的「不自研甘特图」约束 | spec-041 边界 4/5、A4/A5 |
| P1-2 | 阻断 | 修正「input 全量 vs A3 冲突」归因：锚定 spec-013 A2（完整 prompt 已承诺），保留 A3（output），删除 redaction 时代隐私注释；spec-013 修订以此为准 | spec-041 第 36/66 行、spans.py:166-168 |
| P1-3 | 阻断 | 重写降级链：澄清 `ALLOW_PREVIEW_OPT_IN` 默认已为 true、B 不解除 public API 阻断、dual 为唯一现实首选；若 dual 失败直接评估 v3 兜底 | spec-041 第 54-60 行 |
| P2-4 | 非阻断 | 兜底 v3 路径显式列出 SDK 接入改写成本 | spec-041 第 60 行 |
| P2-5 | 非阻断 | 书面声明 dual 仅影响新 trace，历史 trace 不回填 | spec-041 第 52 行 / 边界 2 |

## 评审边界

本需求评审只核对 spec-041 与 spec-013 的文档层面与源码引用一致性；未修改 spec 正文、未修改业务代码、未执行部署或 push/merge。修复落地以技术评审结论与实施任务拆分为准。

## 签字

- 评审人：架构师（评审总控）
- 日期：2026-09-21
- 结论：有条件通过（P1-1 / P1-2 / P1-3 关闭后可转「通过」）
