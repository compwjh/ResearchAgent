# 实施计划索引：spec-042 OpenEval 接入

> 关联：[spec-042 OpenEval 接入：本地离线 Agent 评测闭环](../../specs/042-openeval-agent-evaluation.md)
> Spec 当前状态：**待确认**（Q1–Q7 未裁决，spec 转「已确认」前所有任务保持 `待执行`）

## 目标（一句话）

在本机离线约束下建立「Langfuse trace → 本地模型判官评分 → 结果可回看」的最小评测闭环。

## 任务索引

| 编号 | 任务 | 任务文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-042（含 grill with docs 分析） | [spec-042 本体](../../specs/042-openeval-agent-evaluation.md) | — | 完成（待确认） |
| 02 | Go/No-Go：验证最高风险前提 | [task-02-validate-feasibility.md](./task-02-validate-feasibility.md) | 01 | 待执行 |

> 任务 03 起待 Q1–Q7 裁决后再增补。裁决前不创建占位文件，避免 spec 中出现无法跳转的链接。

## 关键前置事实（取自 spec-042「背景与依据」）

- F2：观测数据已充足（一轮实验即 178 条 trace）
- F3：token 用量只在 **direct 路由**下为真实值
- F5：**矛盾点**——实测仍见 `route=langchain` 且 usage 为 0，Task 02 必须复核
- F6：硬约束——数据不出本机、零外网依赖
- F8：OpenEval 名字冲突（三个候选项目），接入前须复核目标项目是否可离线运行

## 门禁

- 需求评审 → 技术评审 → 用户确认 → 执行 → 验收（详见 `docs/sdd/SDD-GATE-CHECKLIST.md`）
- Task 02 判定为 **No-Go** 时，回到 spec-013 / spec-041 处理路由与埋点缺陷，本 spec 保持「待确认」。
