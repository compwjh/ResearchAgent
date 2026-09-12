# Task06 — 论文目录、评估、Critic 与覆盖补偿

> 关联：[Spec034](../../specs/034-conversational-deep-research-agent-runtime.md) ｜ 索引：[README](./README.md)
> 依赖：Task05；当前状态：`待执行`

## 一句话目标

用真实 Search Worker、Evaluator 和 Critic 接通现有论文目录，让默认路径能找到论文、解释筛选和在证据不足时有界补搜。

## 背景与前置条件

- 必读 Spec034 的检索/阈值策略、角色 Skill 和零结果边界。
- 复用 Spec015 `CatalogSearchGraph`/`CatalogRagAdapter`、Spec032.1 来源 Skill 和 Spec033 解析结果；禁止研究命名空间内复制采集、目录或 RAG。

## 数据、配置与接口

- 新增 `research-paper-evaluation`、`research-coverage-review` Skill 与对应结构化 Schema。
- Search Worker 输出查询、来源、命中、刷新、候选和诊断；Evaluator 输出相关度、保留/淘汰及理由；Critic 输出 CoverageGap 与补搜建议。
- “总体综述”不得作为自动 facet；相关度阈值是可解释软门槛，用户硬范围不可突破。

## 实施步骤与文件边界

1. 冻结现有目录 Tool 接口和真实缓存路径，先复现空目录/高阈值问题。
2. 实现本地优先、覆盖不足远程增量刷新和查询变体。
3. 批量评价候选并保存淘汰统计；零结果执行来源/目录/阈值诊断。
4. 最多两轮同范围 Re-plan，范围扩大转审批；证据不足生成 partial 或明确 failed。

## 子代理分派

- `backend-dev`：分 Search、Evaluate、Critic 小批实现，不跨文件大改。
- `backend-reviewer`：审查目录复用、论文提示注入、阈值和无结果真实性。
- `backend-tester`：固定样本、单源/双源失败、真实目录 smoke。

## 边界与明确不做

- 不下载 PDF、不复制目录、不实现完整 Claim/Evidence 矩阵。
- 不能因低于单一阈值把全部候选静默丢弃。
- 不用固定假文章让真实运行显示成功。

## 验收、风险与回滚

- 本地有相关论文时必须产生候选；本地不足时能证明调用远程目录刷新。
- 每个被淘汰批次有原因统计；阈值软化有边界和记录。
- 恶意论文文本不能改变 Skill、Tool、预算或计划。

## 产出物、执行结果与变更日志

- 产出：两个 Skill、三类角色执行接线、诊断数据、后端测试与评审报告。
- 执行结果：待执行后填写。
- 变更日志：待执行后填写。
