# Spec 032.1 任务索引 — USENIX Skill 解耦与详情页摘要补齐

> 关联：[spec-032.1](../../specs/032.1-usenix-skill-decoupling.md) ｜ 上级：[spec-032](../../specs/032-research-source-expansion.md)

## 目标与范围

确立并落地 **Skill（编排层）/ Tool（执行层）** 分层，补齐 USENIX presentation 详情页摘要抓取。
三条互不耦合的改动线：修复抓取缺陷、新增编排 Skill、迁移非领域规则。

## 任务列表

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-032.1 | [spec](../../specs/032.1-usenix-skill-decoupling.md) | — | 完成 |
| 02 | `parse_usenix_detail` 补齐 abstract 解析 | [task-02](./task-02-detail-abstract-parser.md) | 01 | 待执行 |
| 03 | 详情页抓取单元接入目录同步 | 待创建 | 02 | 待执行 |
| 04 | 注册 `fetch_paper_detail` | 待创建 | 03 | 待执行 |
| 05 | 新增两个编排 Skill，旧的加遗留标记 | 待创建 | 01 | 待执行 |
| 06 | 非领域规则迁移到 AGENTS.md 与 Agent 定义 | 待创建 | 05 | 待执行 |
| 07 | 评审、定向回归、分支提交 | 待创建 | 04,06 | 待执行 |

## 共用约束

- **URL 安全**：详情页必须过 `_safe_url(..., presentation=True)`，禁止任意 URL 入参与第二套下载器。
- **LLM 不碰 HTML**：抓取/解析/缓存/provenance 全部为确定性代码。
- **fill-if-missing**：详情页摘要仅填补缺失，不覆盖列表页已有摘要。
- **最小增量**：禁止重写大文件；`ruff` 须干净；只跑定向 pytest，不跑全量回归。
- **角色名真实**：只引用 `.codebuddy/agents/` 中实际存在的角色，**不存在 `junior-dev`**。
