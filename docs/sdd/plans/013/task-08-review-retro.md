# 任务 08 — 评审、验收、部署、提交与复盘

> 关联：[spec-013](../../specs/013-llm-observability-platform.md) ｜ 索引：[README](./README.md)
> 依赖：任务 06、07 ｜ 当前状态：`待执行`

## 一句话目标

补齐 SDD 全部门禁，用真实运行证据验收聊天、KB、统计和降级能力，形成 spec-013 稳定本地 commit，供后续 spec-014 安全集成。

## 当前证据（2026-09-03）

- spec-013 总状态仍为 `待确认`。
- 产品使用步骤仍是占位文字。
- `docs/sdd/reviews/013-requirement-review.md`、`013-tech-review.md`、`013-acceptance-review.md` 均不存在。
- Task 05–07 尚未完成；当前工作树中的 spec-013 改动没有 commit。
- 因此本任务尚未开始，也不能进入验收签字或把 spec 标记为完成。

## Gate 1–2：需求、产品与技术确认

1. `pm` 基于 spec 补齐产品使用步骤，每一步映射 A1–A10。
2. `tech-lead` 独立生成需求评审和技术评审，结论只能为“通过”或“打回”。
3. 若评审指出“完整 prompt 本地留存”与隐私/截断边界冲突，先修订 spec，不在实现中私自改变。
4. 两项评审通过后等待用户明确确认；确认后依次记录 `已确认`、`实施中` 到 `spec-status-changelog.md`。
5. 未确认前不得继续 Task 05–07 的业务代码实现。

## Gate 3–4：测试与验收

6. 汇总任务 02–07 的执行结果、测试命令、版本、端口和实际产物。
7. `tester` 按 A1–A10 执行独立验收并生成 `docs/sdd/reviews/013-acceptance-review.md`。
8. 至少覆盖：
   - Langfuse Web/worker 和四个基础设施健康
   - chat 的 langchain/direct 两条链路
   - prompt、thinking、content 分离展示
   - TTFT/load/prefill/eval/overhead 指标正确
   - KB embedding/retrieval/rerank/generation 链路
   - 原生 Dashboard 六项统计
   - 自研页面及路径 A/B 对比
   - Langfuse 关闭、停机、采样未命中三种降级
9. 全量测试数量不得少于当前基线；若已集成 spec-014，则采用整合后的最新通过数量并记录 commit。
10. `tech-lead` 阅读真实代码、测试和验收报告后签字；验收未签字不得转完成。

## Gate 5：部署与运行时验证

11. 依次启动基础设施、Langfuse web/worker 和项目服务，记录实际端口。
12. 浏览器打开 Langfuse，发起一次聊天和一次 KB 问答，确认数据实时到达。
13. 停止 Langfuse 后重复请求，确认业务仍可用；随后恢复并复测。
14. 若默认端口占用，使用明确可用端口并同步脚本/文档；不得声称未启动的服务已部署。

## 跨 spec 收口与提交顺序

15. 先把 spec-013 自身代码、测试、评审和复盘整理为稳定 commit；提交前逐项审核文件范围，不整体提交工作树中的 spec-014 文档或其他无关文件。
16. 在 spec-013 commit 形成前，spec-014 不得复制当前脏工作树快照。
17. spec-013 commit 形成后，由 spec-014 的 Task 08 以明确 commit 做语义集成，重点检查 `config.py`、routes、KB retrieve、requirements 和 deploy 脚本。
18. 全仓扫描 `<<<<<<<`、`=======`、`>>>>>>>`，范围包含 `.gitignore`；读回所有冲突文件。

## 文档收口

19. 生成 `docs/sdd/retro/2026-09-xx-spec-013-observability-retro.md`，至少记录：
   - 非 Docker 部署与 ClickHouse 权限坑
   - Python 3.11 升级影响
   - SDK v4 不支持虚拟 start_time 后的设计调整
   - 本地子代理 GGUF/MLX 性能差异
   - 路径 A/B 的维护成本和用户最终选择
20. 更新 spec 的任务状态、评审记录、实际改动、验证结果和变更日志。
21. 更新计划索引和 `spec-status-changelog.md`；全部 DoD 满足后才把 spec 标记为 `已完成`。
22. 在 feature 分支做关联 spec-013 的本地原子 commit；不主动 push、不合并 main。

## 子代理分派

- 产品步骤：`pm`。
- 需求/技术评审和最终验收签字：`tech-lead`。
- 测试与验收报告：`tester`。
- 验收发现代码缺陷时，退回 `junior-dev` 窄任务修复，不能由主会话绕过代码分派。
- 所有角色输出必须落盘；模型与上下文以执行时 `MODEL_REGISTRY.md`、角色 agent 配置和实际注册结果为准。

## 完成清单

- [ ] 产品使用步骤已填写并映射 A1–A10
- [ ] 需求评审通过
- [ ] 技术评审通过
- [ ] 用户明确确认 spec
- [ ] Task 05–07 完成并有真实执行结果
- [ ] 验收报告通过
- [ ] 开发主管签字完成
- [ ] 全量测试与运行时验收通过
- [ ] 服务实际启动且访问地址、端口、命令已记录
- [ ] spec/changelog/任务索引状态一致
- [ ] 复盘已落盘
- [ ] 冲突标记 0 命中
- [ ] spec-013 稳定本地 commit 已形成

## 风险与回滚

- 任一门禁失败：保持真实状态并退回对应任务，不强行收口。
- 路径 A/B 尚未由用户择优：两者都保留并记录成本，不擅自删除。
- 部署失败：写明具体组件、日志和恢复命令，不报告“已完成”。
- Git 回滚只针对明确的 spec-013 commit；禁止对含有他人未提交改动的工作树执行 `reset --hard`、`clean` 或整体覆盖。

## 产出物

- 三份 013 评审文档与开发主管签字。
- 全量测试、运行时验收和部署记录。
- spec-013 复盘文档。
- 状态一致的 spec、计划索引和 changelog。
- 可供 spec-014 集成的明确本地 commit。

## 执行结果

> 待前置任务和门禁完成后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师（自身） | 对照当前工作树和 SDD 门禁补齐收口任务，状态保持待执行 |
