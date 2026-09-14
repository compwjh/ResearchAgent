# Task10 — 最终评审、回归、真实 Smoke、部署与复盘

> 关联：[Spec034](../../specs/034-conversational-deep-research-agent-runtime.md) ｜ 索引：[README](./README.md)
> 依赖：Task02–Task09；当前状态：`实施中`

## 一句话目标

以独立评审、唯一最终全量回归、真实 Ollama 浏览器流程和直接部署证明 Spec034 完整可用，并完成状态台账和复盘。

## 背景与前置条件

- 所有前置 Task 均已定向通过且交接物落盘。
- 必读 Spec034 验收方式、SDD Gate Checklist、部署 README 和受影响测试清单。

## 数据、配置与接口

- 不新增产品接口；只允许修复已确认范围内的 P0/P1 和验收缺陷。
- 若发现需新增数据模型、公开接口、用户行为或通用执行能力，停止并回到 Spec 修订确认。

## 实施步骤与文件边界

1. 后端/前端 reviewer 分端评审并批量关闭 P0/P1。
2. 后端/前端 tester 定向复核，tester 汇总跨端验收。
3. 运行一次最终候选全量回归、静态检查和冲突标记扫描。
4. 启动真实服务和 Ollama，用固定主题“软件供应链攻击”、目标“总结 2020–2024 年 USENIX Security 论文中的攻击面与防御方法”、`time_range=2020–2024`、`source=usenix`、中文输出完成完整会话式研究 Smoke，包括前端审批、真实目录 Tool、三级树刷新和报告下载。
5. 直接部署/启动服务，验证 health、实际端口和关键页面。
6. 落盘复盘、三份评审、验证证据；最后更新 Spec 和 changelog 为已完成。

## 子代理分派

- `backend-reviewer` / `frontend-reviewer` 独立评审。
- `backend-tester` / `frontend-tester` 分端验收；`tester` 汇总并签字。
- 架构师只做合并裁决、真实运行复核和部署，不伪造独立结论。

## 边界与明确不做

- Fake Runtime 不能替代真实 Smoke；环境失败必须如实记录和给出复验命令。
- 真实成功证据必须包含 `resolved_model/reasoning_effort`、实际 Tool 名、`research-event:{task}:{seq}`、三级 ProcessingStep 和 Markdown/HTML/manifest ID；Ollama/来源不可用时记录稳定错误与复验命令，不以 Fake 冒充成功。
- 不因收口顺手实现 Spec028/030 或完整安全中心。
- 不主动 push 或合并 main，除非用户再次明确授权。

## 验收、风险与回滚

- 全量回归、三道门禁、真实 Smoke、部署和引用检查全部有命令、退出码和证据。
- 最终回复必须给出可点击地址、实际端口和真实启动命令。
- 任何 P0/P1 或核心真实流程失败都不得把 Spec 标为已完成。

## 产出物、执行结果与变更日志

- 产出：需求/技术/验收评审、测试报告、Smoke 证据、部署记录和 retro。
- 执行结果：实施中（代码与自动化门禁通过，真实 Smoke 阻塞）。最终全量 pytest 通过 `1863 passed, 5 warnings, 52 subtests`；后续 Task10 定向集合 `80 passed`。服务/页面 health 与浏览器可达，Intake→Plan→Approval→Runner→三级事件流真实通过；并已修复重复只读 Tool、WorkItem 依赖命名空间、Search→Evaluator bounded 证据交接和角色 JSON 合同。2026-09-15 受控 smoke 进一步确认：真实 USENIX 目录检索可命中稳定候选，详情来源失败和最小元数据评估均以 `partial`/`UPSTREAM_WORK_ITEM_FAILED` 收口，仍未产生 `keep=true` 证据和报告 Artifact；因此不标记完成。详见 `artifacts/task-10/smoke-report.md`、`smoke-evidence-path.md` 与 `acceptance-review-final.md`。
- 变更日志：2026-09-15 启动 Task10；Task09 双端最终复审 GO，进入 Spec034 最终验收阶段。修复 reasoning capability 与 Spec027 兼容回归后全量回归归零；真实模型 Smoke 留有真实失败证据，不新增 Spec028/030 范围。
