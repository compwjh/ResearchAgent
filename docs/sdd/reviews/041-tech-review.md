# Spec041 技术评审：Langfuse 部署切换 + 埋点 input 全量

## 评审元数据

- 评审对象：`docs/sdd/specs/041-langfuse-trace-detail-and-waterfall.md`（状态：已确认）、`vendor/langfuse/worker/src/env.ts`、`backend/app/platform/observability/*.py`
- 评审角色：架构师（评审总控）
- 评审范围：dual 模式双写成本/迁移/回退（a）、spans.py input 全量对单测/存储/fail-open 的影响（b）、实施任务拆分（c）、风险登记（d）
- 源码依据：`vendor/langfuse/worker/src/env.ts:569-728`、`backend/app/platform/observability/spans.py:13-22,44-52,126-240,276`、`safe.py:13-22`、`config.py:73-78,128`、`routes_chat.py:107-110,169-200`
- 评审时间：2026-09-21（Asia/Shanghai）

## 结论

**有条件通过。**

根因定位准确、fail-open 设计（`safe_call`）与既有「禁止第二套实现」原则未被破坏，dual 配置在 `validateV4Flags` 下合法（env.ts:701-728），回退安全。但有 4 项必改（T1-T4）阻断直接通过，核心仍是：**dual 让 observations 非空 ≠ A4/A5 的 5 阶段瀑布条已实现**（见需求评审 P1-1）；修复点必须落在 `redact_prompt_messages` 函数本体以覆盖全部 5 个调用点；query_log 启用有额外 GRANT 前置。

## 技术核对矩阵

| 技术点 | 判定 | 依据 |
|---|---|---|
| dual 配置合法性 | 通过 | env.ts:569-571 枚举含 `dual`；:692-693 `v4WritesToLegacyTables` 在 `dual` 下为真；:701-728 `validateV4Flags` 的 three hard-error 分支均不命中 `dual+direct` |
| dual 双写成本 | 通过（可接受） | `dual` 同时写 events（ClickHouse）+ legacy traces/observations（Postgres）；本地单用户规模可接受，无新基础设施 |
| dual 迁移要求 | 通过（低） | spec-013:72 写明 v4 全新部署 schema 迁移启动自动应用；dual 仅改变写入目标，legacy 表本就随 schema 创建，无需重跑独立迁移 |
| dual 回退安全 | 通过 | 回退=改回 `events_only`/删变量+重启；dual 期写入的 legacy 行在 events_only 下不被读、无害，无数据损坏 |
| spans.py input 全量—修复点 | **不通过（T1）** | 修复须改 `redact_prompt_messages` 函数本体（spans.py:225-227），覆盖 5 调用点（spans.py:168、routes_article.py:133、routes_chat.py:107、routes_kb.py:1058、routes_conversations.py:933）；仅改 spans.py:168 会让 4 个 routes 仍脱敏 |
| spans.py input 全量—单测 | 通过（须新增） | 测试目录 grep `redact_prompt_messages` 无命中，无既有锁定；边界 6 要求的「content 保留原文」单测须新建 |
| spans.py input 全量—存储体积 | 通过（有界） | 输入经 `_truncate(formatted_input, max_input_chars())`（spans.py:193），上限 `OBS_MAX_INPUT_CHARS=20000`（config.py:128）；由「≈0 字符」变为「≤20k 字符/observations」，增量有界 |
| spans.py input 全量—fail-open | 通过（轻微提示） | `safe_call`（safe.py:13-22）包住 `_report`（spans.py:210/276）；格式化在 :157-209 位于 safe_call 外（既有），改全量不新增异常面；建议把 :168 格式化移入 `_report` 以严格 fail-open（非阻断） |
| metadata 一致性 | 通过 | `input_chars`（spans.py:169）与 `prompt_observation_metadata` 的 role_count/role_names/char_counts（:230-240）本就取原始 content，与「input 全量」不冲突，脱敏此前已不彻底 |
| A4/A5 原生瀑布图可达性 | **不通过（T3）** | spans.py:13-22 已废弃 phase 子 span，改 metadata+numeric score；SCORE_METRICS(:44-52) 无独立 5 阶段条；前端无 Langfuse 瀑布图渲染。dual 仅保证单条 generation 条 |

## a) dual 模式：数据双写成本、迁移与回退

- **双写成本**：`dual` 使 worker 在写入 ClickHouse events 表的同时写入 Postgres legacy `traces`/`observations` 表（env.ts:692-693）。写入量约翻倍，但本机单用户场景可接受；无需新增组件。
- **迁移要求**：spec-013:72 明确「v4 全新部署无需三步迁移，schema 迁移启动自动应用」。legacy 表属于 v4 schema 一部分，启动即建；`dual` 只是改变写入目标，**不需要重跑独立迁移**，仅改 `.env` + 重启。注意：spec 第 52 行「重启后需重跑/确认迁移」表述略夸张，应改为「重启后确认 worker 健康、legacy 表开始写入」即可。
- **历史数据不回填**：`LANGFUSE_BACKGROUND_MIGRATION_V4_ENABLE_HISTORIC_BACKFILL` 默认 true（env.ts:601-603），但注释 597-600 说明「对 net-new 部署（无 legacy 数据）是 no-op」。已存在的 ~1769 事件行**不会**回填 legacy 表 → 切换 dual 后**历史 trace 仍无详情/瀑布图**，仅新 trace 受益。须写入实施文档（对应需求评审 P2-5）。
- **回退**：将 `LANGFUSE_MIGRATION_V4_WRITE_MODE` 改回 `events_only`（或删除该行）并重启即可。`dual` 期写入的 legacy 行在 events_only 下不被读取、无外键/级联风险（`v4WritesToLegacyTables=false` 仅停止新写），无数据损坏。**回退安全**。

## b) spans.py input 全量：单测 / 存储 / fail-open 影响

- **修复点（T1，阻断）**：`redact_prompt_messages`（spans.py:225-227）是**唯一**脱敏 seam，被 5 处调用（见矩阵）。改为保留 `content` 原文即可一次性覆盖全部入口，符合「禁止第二套实现」（regression-guard #9）。**禁止只改 spans.py:168**，否则 routes_article/chat/kb/conversations 仍先脱敏再传给 `record_ollama_generation(prompt_messages=observation_messages)`（如 routes_chat.py:171/197），造成「改了等于没改」。
- **单测（边界 6）**：测试目录当前无 `redact_prompt_messages` 相关用例（grep 无命中）。须在 `tests/` 新增：传入含 `content` 的消息列表，断言返回项 `content` 等于原文、`role` 保留。这是边界 6 的验收载体。
- **存储体积**：`formatted_input` 经 `_truncate(..., max_input_chars())`（spans.py:193），上限 20000 字符（config.py:128）。由「content 清零」变为「原文≤20k」，单 observation 体积有界增长，无失控风险。
- **fail-open（T 轻微）**：`safe_call`（safe.py:13-22）是 fail-open 唯一 seam；`:210`/:276 把 `_report` 包入。但 `derive_metrics`/`get_client`/`:168` 的 `redact+format+truncate`/`:170` `_build_metadata` 均在 safe_call **外**（:157-209）。改全量文本不实质扩大异常面（纯字符串操作），但为严格满足边界 7「观测层异常不得影响业务」，建议把 `:168` 的输入格式化移入 `_report` 内部，使异常同样被吞掉。属非阻断优化。
- **metadata 一致性**：`input_chars`（:169）与 `prompt_observation_metadata`（:230-240）本就取原始 content 计算，与 input 全量不冲突；恰恰说明此前脱敏不彻底（仅 `input` 文本清零，metadata 早已暴露真实 char_counts/role）。用户裁决「不需要隐私设计」与之自洽。

## c) 实施任务拆分建议（4 个子任务）

| 子任务 | 涉及文件 | 验收方式 |
|---|---|---|
| **T-A Langfuse 部署切换为 dual** | `vendor/langfuse/.env`（新增 `LANGFUSE_MIGRATION_V4_WRITE_MODE=dual`；确认不在 events_only）、重启 Langfuse | 边界 1（worker 不抛 V4 校验错）、边界 2（新调用后 `observations`/`analytics_observations` 非空）、边界 3（详情页可打开）；边界 8（复测 query_log 报错） |
| **T-B 埋点 input 全量** | `backend/app/platform/observability/spans.py:225-227`（改 `redact_prompt_messages` 保留 content；同步清理 :166-168 隐私注释）；不动其余 4 个 routes 调用点（由函数本体统一生效） | 边界 6（新增单测断言 content=原文、role 保留）；`source .venv/bin/activate && cd backend && python -m pytest -q` 全量通过；`ruff check .` 通过 |
| **T-C 瀑布图/A4/A5 实证与缺口处置** | 实测 dual 后原生 Langfuse 详情页瀑布图形态；若为单条 generation 条而非 5 阶段条，则决策：(i) 在 spans.py 内补 `phase:*` 子 observation（受 SDK `start_time` 限制，spans.py:13-18 已论证脆弱）或 (ii) 落实 Task07 自研视图并修订 spec-013「不自研甘特图」约束 | 边界 4、边界 5；若确认原生单条条已满足用户「必须看到瀑布图」裁决，则书面锁定该验收形态并关闭 A4/A5 的 5 阶段强约束 |
| **T-D query_log 处置与收尾** | 复测 `V4LegacyApiUsageJob` 报错；若仍报，评估启用 ClickHouse `system.query_log`（需先补 GRANT：spec-013:74 列 `system.query_log*` SELECT 等）或记为遗留运维项；同步修订 spec-013 相关表述 | 边界 8；如启用 query_log，验证 worker 不再每分钟报错 |

> 说明：T-A 与 T-B 可并行（互不影响）；T-C 依赖 T-A 的 observations 非空结果；T-D 可与 T-A 同期复测。

## d) 风险登记

| 风险 | 等级 | 描述与处置 |
|---|---|---|
| R1 dual 不可用降级路径 | 高 | 若 dual 实测仍拿不到瀑布图：备选 `events_only+optin` 实质是当前默认状态（env.ts:590-592 optin 默认 true）且 `/api/public/traces` 在 events_only 下硬阻断（实测），**无法作为有效备选**；故实际只剩 v3 兜底。v3 需改写 SDK 接入（spec-013:73 要求 v4 SDK≥4.7.0 实时，v3 不同），成本最高。处置：把 dual 明确为唯一现实首选，v3 兜底前置「修订 spec-013 + 重写 SDK 接入」评审。 |
| R2 query_log 缺失 | 中 | `V4LegacyApiUsageJob` 每分钟报错（根因 3）。启用 `system.query_log` 需 ClickHouse 额外 GRANT（spec-013:74：`system.query_log*` SELECT、`DROP VIEW` 等），若 GRANT 不足启用本身会失败。处置：先确认 GRANT，再决定是否启用；否则记为遗留运维项（不阻断主链路）。 |
| R3 A4/A5 原生瀑布图缺口 | 高 | dual 仅使 observations 非空，后端未以子 span 实现 5 阶段条（spans.py:13-22），前端无渲染。即使 dual 成功，原生瀑布图大概率只显示单条 generation 条，A4 的 5 阶段条、A5 的冷/热 load 段区分**无法呈现**。处置：T-C 实证后决策补 phase 子 span 或 Task07 自研视图（与 spec-013:143「不自研甘特图」冲突，须同步修订）。 |
| R4 历史 trace 不回填 | 低 | dual 仅影响新写入，已产生事件不回填 legacy 表 → 历史 trace 切换后仍无详情/瀑布图。处置：实施文档书面声明，避免误判。 |
| R5 全量 prompt 存储/PII | 低 | 完整 prompt（≤20k/observations）入库；本地单人使用（spec-013:144「不做用户体系/权限」），且用户已裁决放弃隐私设计，可接受。处置：维持 `max_input_chars` 上限，不在本 spec 放宽。 |

## 必改项清单

| 编号 | 级别 | 必改内容 | 位置 |
|---|---|---|---|
| T1 | 阻断 | 修复作用于 `redact_prompt_messages` 函数本体（spans.py:225-227），覆盖全部 5 调用点，而非仅 spans.py:168 | 技术评审 b) |
| T2 | 阻断 | 实施文档补「dual 回退步骤」与「历史 trace 不回填」声明 | 技术评审 a) |
| T3 | 阻断 | T-C 必须实证 dual 后原生瀑布图形态并处置 A4/A5 缺口，否则边界 4/5 不可验收 | 技术评审 c)/d) R3 |
| T4 | 阻断 | query_log 处置须先确认 ClickHouse GRANT（spec-013:74），否则启用会失败 | 技术评审 d) R2 |
| T5 | 非阻断 | 把 spans.py:168 输入格式化移入 `_report`（safe_call 内）以严格 fail-open | 技术评审 b) |
| T6 | 非阻断 | 修正 spec 第 52 行「重跑迁移」为「重启后确认 worker 健康与 legacy 写入」 | spec-041:52 |

## 评审边界

本技术评审只修改本评审文档；未修改 `backend/**`、`vendor/langfuse/.env`、spec 正文或测试；未执行部署、未运行全量 pytest、未 push/merge。fail-open、双写、回退结论均基于已读源码行号，落地以 T-A~T-D 实施任务为准。

## 签字

- 评审人：架构师（评审总控）
- 日期：2026-09-21
- 结论：有条件通过（T1 / T2 / T3 / T4 关闭后可转「通过」）
