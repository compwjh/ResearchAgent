# ADR 0002：把 Langfuse 启用列为验收前置，并维持离线评测范围

- 状态：已接受（Spec-045 grill with docs 裁决，2026-11-08）
- 范围：评测与可观测性的交付边界、验收条件、在线评测的范围排除
- 关联：[spec-045](../sdd/specs/045-evaluation-observability-hardening.md) ｜ [spec-042](../sdd/specs/042-openeval-agent-evaluation.md) ｜ [spec-041](../sdd/specs/041-langfuse-trace-detail-and-waterfall.md)

> 本 ADR 满足 `domain-modeling` 技能「只在三条同时成立时创建」的条件：
> **难逆转**（验收条件决定什么算「做完」，事后改动会使既有验收结论失效）、
> **无背景会令人困惑**（spec-042 已宣告「评测闭环完成」，未来读者会问为何还要重新启用监控）、
> **真实取舍**（在「可演示的离线闭环」与「生产级在线评测」之间做了明确选择）。
> 按 Q6 裁决，本 spec **只创建这一条 ADR**。

## 背景

1. `docs/sdd/specs/042-openeval-agent-evaluation.md` 于 2026-10-23 收口为「已完成」，
   描述的是**离线评测闭环**：从 Langfuse 已有 trace 导出数据集 → 本地模型判官评分 →
   报告落盘 + score 回写。该 spec 的完成结论依赖当时 Langfuse 处于启用状态
   （`MEASUREMENT-langfuse-2026-09-22.md` 记录一轮实验产生 178 条新 trace）。
2. 但 2026-11-08 实测当前部署中 **Langfuse 已默认关闭**：
   `backend/app/platform/config.py:122` `LANGFUSE_ENABLED` 默认 `false`，
   仓库根 `.env` 未配置 `LANGFUSE_*`，运行进程环境亦无该变量。
   因此评测的 `--export` 当前取不到真实 trace，观测看板也是空的。
3. 这造成一个容易误判的局面：代码与单测（评测 85 个用例、观测约 54 个）
   **全部通过且全部为 mock**，但用户打开界面看不到任何变化。
   `docs/sdd/plans/042/task-04-offline-evaluation-delivery.md:92` 明确
   「测试只使用 mock/fake transport」，`spec-041:93` 也把 SDK 升版回归交给人肉执行。
4. 同时，`spec-042:163-165` 明确第一期**不做在线实时评测**、不追求绝对分数对齐；
   `backend/eval_042/report.py:225-233` 强制 `human_agree_rate=None`、
   `constructed_gold_only=True`，即没有人工金标集。

若不在本期把这条边界写清楚，会出现两种失败模式：
一是「代码全绿但没人真跑过」的假完成，二是有人顺手把在线评测塞进范围、
使 spec 从一次性交付变成需要持续算力与标注人力的长期项目。

## 决策

1. **把「启用 Langfuse + 造一批可复现样本 + 跑通一次真实端到端」列为验收硬前置**，
   编号 `task-02`，但注明「由验收执行者完成，不由开发任务代劳」。
   缺任一项不得判定 spec `已完成`。
2. **验收证据集固定为四类，缺一不验收**：
   ① 缺陷类先红后绿的测试记录；
   ② 一次真实 `eval_042` CLI 产出的 `report.json` + `report.md`（含数据集/模型/prompt 指纹）；
   ③ Langfuse 中可查的一条完整 trace（四段 phase span + 一次 score 回写，附 trace ID）；
   ④ 瀑布图截图。各类须写明保存路径。
3. **维持离线评测范围，明确不做在线实时评测**，也不做人工标注 gold 集、
   不做业务 `quality_score` 与 Langfuse score 的口径统一。
   这三项属于后续阶段，需持续人力标注、线上算力与架构决策，
   且在线评测依赖本期先完成 trace 统一与采样一致，顺序不能颠倒。
4. **本期只交付文档，不改业务代码、不启用 Langfuse、不跑评测**。
   启用动作发生在后续实施/验收阶段，由验收执行者在受控环境完成；
   本期文档阶段 `spec-045` 保持 `待确认`。
5. **术语不并入根 `CONTEXT.md`**：该文件是 Spec018 专属 glossary，
   `docs/sdd/context/CONTEXT.md` 是论文检索专属，全仓无 `CONTEXT-MAP.md`。
   本期在 `spec-045` 内设「术语」小节，不新建多语境结构。

## 备选方案与取舍

| 方案 | 为什么不选 |
|---|---|
| 把启用 Langfuse 当作普通实施任务，由开发 task 顺带完成 | 会与「本期只交付文档」冲突，且开发自证自验，无法作为独立验收门槛 |
| 用现有 mock 测试 + 报告文件即判定完成 | 正是当前「代码全绿但界面没变化」的成因；四类证据集里的真实 trace 与 CLI 产物可堵住这个缺口 |
| 本期一并做在线实时评测 | 违反 `spec-042` 第一期边界；需要额外判官算力、线上延迟预算与熔断设计，且缺人工金标时结论不可信 |
| 直接把评测/观测术语写进根 `CONTEXT.md` | 污染 Spec018 专属 glossary，且 skill 要求 CONTEXT.md 只做术语表、不承载实现决策 |

## 后果

**正面**

- 「能演示、能验收」成为可检查的条件，而不是一堆只有单测能证明的改动。
- 未来读者能解释：为什么 spec-042 已「完成」，spec-045 仍要求重新启用监控。
- 在线评测与人工标注被明确推迟，避免范围蔓延成长期运营项目。

**代价与已知边界**

- 验收依赖外部运行时（自托管 Langfuse 栈 + 真实 Ollama），
  `deploy/langfuse/start-langfuse.sh` 依赖 ClickHouse / PostgreSQL / Redis / MinIO，
  环境未就绪时 spec 不能收口。
- 评测结论仍是**相对回归基线**：没有人工金标集，`human_agree_rate` 保持 `null`，
  不能对外宣称绝对准确率。
- 两套质量分数口径（业务 `quality_score` 与 Langfuse score）仍互不相认，
  可能在看板上给出不一致的「质量」结论；统一工作留待后续架构决策。
- 私有 SDK 符号封装（Q7 并入 P1）**不保证瀑布图永不退化**：
  私有符号消失后精确时间轴仍会退化，封装只保证「退化可发现（显式降级 + 告警）」
  与「修复点唯一」。真正根治需上游 SDK 公开支持设置 `start_time`，或放弃精确瀑布图。

## 复核记录（grilling + domain-modeling，2026-11-08）

- `grilling` 共 3 轮访谈、Q1–Q12 全部裁决完毕，**设计树前沿为空**，用户确认共识。
  其中 Q11 由用户推翻推荐（原推荐不创建 plans 文件，用户要求本期创建）。
- `domain-modeling` 完成：
  ① 挑战术语冲突 —— 「测评」在代码中对应 `eval_042`（离线评测）、
     `bench_ollama_routes.py`（性能基准）、`quality_score`（业务分）、
     Langfuse `score`（评测分）四个对象，已在 spec-045「术语」小节拆分并给出 Avoid 列表；
  ② 锐化模糊语言 —— 「修复」改为「加固与闭环」，11 项按
     `缺陷修复 / 能力补齐 / 规格落地` 分类，因 F3/F7/F17 属「从未实现/从未跑通/规格未落地」，
     无回归可修、写不出红测；
  ③ 具体场景压力测试 —— 采样率 0.1 下同一 trace 各阶段独立随机导致瀑布图缺段、
     多进程共用 `--output-dir` 覆盖报告、升版后私有符号缺失静默退化；
  ④ 代码交叉核对 —— 对 spec 与两份 notes 的 125 个路径引用做存在性与行号校验，
     122 个存在、无行号越界；其余为 `.json` 被正则截断的误报与本轮待创建的
     `plans/045/`、`adr/0002` 文件（创建后链接即全通）；
  ⑤ 术语表结构冲突已记录于 F18，按 Q4 采用轻量方案，不修改根 `CONTEXT.md`。
