# Spec 032.1 任务索引 — USENIX Skill 解耦与详情页摘要补齐

> 关联：[spec-032.1](../../specs/032.1-usenix-skill-decoupling.md) ｜ 上级：[spec-032](../../specs/032-research-source-expansion.md)

## 目标与范围

确立并落地 **Skill（编排层）/ Tool（执行层）** 分层，补齐 USENIX presentation 详情页摘要抓取。
三条互不耦合的改动线：修复抓取缺陷、新增编排 Skill、迁移非领域规则。

> 2026-09-20 对账：本计划是 [Spec032](../../specs/032-research-source-expansion.md) 的 USENIX 子规格。Task02–06 已有实现；Task07 本规格评审仍需真实收口；Task08/10 待办移交 [Spec032 Task13](../032/task-13-spec0321-carryover.md)。原 Task09 文档缺失，不编造结果。旧索引“全部待执行”已过时。

## 任务列表

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-032.1 | [spec](../../specs/032.1-usenix-skill-decoupling.md) | — | 完成 |
| 02 | `parse_usenix_detail` 补齐 abstract 解析 | [task-02](./task-02-detail-abstract-parser.md) | 01 | 已完成（待本规格收口复核） |
| 03 | 详情页抓取单元接入目录同步 | [task-03](./task-03-detail-fetch-unit.md) | 02 | 已完成（待本规格收口复核） |
| 04 | 注册 `fetch_paper_detail` | [task-04](./task-04-register-detail-tool.md) | 03 | 已完成（待本规格收口复核） |
| 05 | 新增两个编排 Skill，旧的加遗留标记 | [task-05](./task-05-orchestration-skills.md) | 01 | 已完成（待本规格收口复核） |
| 06 | 非领域规则归位 | [task-06](./task-06-migrate-non-domain-rules.md) | 05 | 已完成（待本规格收口复核） |
| 07 | 本规格评审、定向回归与状态收口 | [Spec 评审记录](../../specs/032.1-usenix-skill-decoupling.md#评审记录) | 04、06 | 进行中，未完成 |
| 08 | IDE 本地会话 USENIX 助手 | [task-08](./task-08-local-session-usenix-skill.md) | 04 | 待执行，转 Spec032 Task13 |
| 10 | 会话 Skill 粘性（无原 Task09 文档） | [task-10](./task-10-session-skill-stickiness.md) | 会话 Skill | 待执行，转 Spec032 Task13 |

## 共用约束

- **URL 安全**：详情页必须过 `_safe_url(..., presentation=True)`，禁止任意 URL 入参与第二套下载器。
- **LLM 不碰 HTML**：抓取/解析/缓存/provenance 全部为确定性代码。
- **fill-if-missing**：详情页摘要仅填补缺失，不覆盖列表页已有摘要。
- **最小增量**：Task 阶段定向验证；本规格收口按 AGENTS.md 运行所需回归，不以旧 Prompt 的禁止全量回归语句代替最终门禁。
- **角色名真实**：只引用 `.codebuddy/agents/` 中实际存在的角色，**不存在 `junior-dev`**。

## 变更日志

- 2026-09-20：校正旧索引状态与失效的“待创建”链接，记录 032.1→032 任务移交；不将 Task07 或本规格虚标完成。
