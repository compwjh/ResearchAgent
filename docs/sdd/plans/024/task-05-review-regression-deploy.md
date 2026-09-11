# Task 05：评审、全量回归、部署与复盘

> 关联：[Spec 024](../../specs/024-visible-reasoning-controls.md) ｜ 索引：[README](./README.md)
> 依赖：Task03、Task04；被依赖：无；当前状态：待执行

## 一句话目标

完成双端复审、唯一一次全量回归、真实 Ollama 性能验收、部署和 Spec024 收口。

## 前置门禁

- Task03、Task04 的实现、测试和评审报告均已落盘。
- P0/P1 已清零；工作树无无关修改。
- 旧会话清理数量和保留数据证据可审计。

## 执行步骤

1. backend-reviewer 与 frontend-reviewer 分别复核最终 diff。
2. backend-tester、frontend-tester 完成单端回归；tester 汇总跨端验收。
3. 运行全量 pytest，仅此 Task 执行一次。
4. 部署服务，预热模型，以固定问题验证 xhigh、low、off。
5. 记录首反馈、首真实推理、首正文和总耗时；xhigh 预热环境首真实推理不晚于 20 秒。
6. 更新评审、Task、README、Spec、状态台账和复盘，完成本地原子提交；不主动 push 或合并 main。

## 完整分派 Prompt

~~~text
角色：tester，使用 Spec024 执行配置中的测试总控模型。
目标：基于已落盘实现/评审报告完成 Spec024 最终验收，不修改业务代码。
只需读取：
1. docs/sdd/specs/024-visible-reasoning-controls.md
2. docs/sdd/plans/024/task-05-review-regression-deploy.md
3. artifacts/task-03 与 artifacts/task-04 的固定报告
4. 实际最终 diff
允许修改：
- docs/sdd/reviews/024-acceptance-review.md
- docs/sdd/plans/024/artifacts/task-05/acceptance-report.md
禁止：
- 修改 backend/** 或 frontend/**
- 放宽测试断言掩盖失败
- 修改模型、Ollama 部署或知识库数据
- reset、stash、clean、push、合并 main
完成后的可观察状态：
- 全量回归有唯一、完整、退出码为 0 的证据
- xhigh、low、off 真实 smoke 有阶段耗时
- 数据清理保留边界被验证
- 给出 PASS 或 FAIL
必须验证：
- 全量 pytest
- node --check 与全部前端合同
- health/home smoke
- 真实浏览器交互
- 预热 Ollama 三档 smoke
- git diff --check 与全仓冲突标记检查
结果写入：
docs/sdd/plans/024/artifacts/task-05/acceptance-report.md
固定返回字段：
结果状态和摘要；改动文件；测试命令、退出码和结果；产物路径；决策依据；风险与阻塞；主 Agent 后续动作；开始、结束和总耗时；可用时记录模型、token 和工具调用统计。
若环境冷启动或 Ollama 忙，记录环境并重做一次预热样例；不得为满足 20 秒门槛修改业务语义。
~~~

## 主 Agent 必须校验

- 读回所有评审和验收报告，确认命令与实际退出码一致。
- 确认全量回归只在本 Task 运行一次且最终为通过。
- 确认服务实际启动并返回健康状态，浏览器资源为最新版本。
- 确认 Spec025 仍为占位，无 Task、无业务实现。

## 验收标准

- 五档选择、会话继承和不支持档位错误通过。
- 普通/项目会话事件顺序、刷新恢复、失败/中止终态通过。
- 推理草稿过滤、20,000 字符上限、记忆隔离通过。
- 旧会话删除且项目、长期记忆、SystemRule、知识库保留。
- 预热 xhigh 首段真实推理内容在 20 秒内；硬件异常单独记录。
- 全量回归通过，部署 smoke 通过，三份评审真实落盘。

## 风险、停止条件与回滚

- 全量回归失败、P0/P1 未清或实际部署不可用时不得标记 Spec 完成。
- 真实性能失败先区分冷启动、Ollama 忙与应用事件丢失，不为追数字无限修改。
- 回滚到 Task02 记录的 commit 和数据库备份；不得破坏其他 Spec 修改。

## 产出物

- docs/sdd/reviews/024-requirement-review.md
- docs/sdd/reviews/024-tech-review.md
- docs/sdd/reviews/024-acceptance-review.md
- docs/sdd/plans/024/artifacts/task-05/acceptance-report.md
- docs/sdd/retro/2026-09-XX-visible-reasoning-controls.md

## 执行结果

待执行后填写。

## 变更日志

- 2026-09-11：建立最终评审、全量回归、部署和复盘任务。
