# Task07 — processing_steps 三级树与实时投影

> 关联：[Spec034](../../specs/034-conversational-deep-research-agent-runtime.md) ｜ 索引：[README](./README.md)
> 依赖：Task02、Task05；当前状态：`已完成`

## 一句话目标

把现有会话处理步骤升级为兼容一至三级的通用树，并将 ResearchEvent 幂等投影成可恢复、可展开且不抢滚动位置的实时研究轨迹。

## 背景与前置条件

- 必读 Spec034 的 ProcessingStep v2、投影关系和显示规则。
- 保留现有 `processing_steps`、`/messages/{id}/processing-steps` 和 progress SSE 的旧客户端兼容。

## 数据、配置与接口

- v2 字段：parent_step_id、node_type、node_key、display_order、detail_json、source_event_id、research_session_id、schema_version。
- 迁移只增列/索引，不重写旧行；旧行按 `schema_version=1` 根节点读取。新增唯一索引 `(message_id,node_key)`，非空 `source_event_id` 全局唯一，事件 ID 规范为 `research-event:{task}:{seq}`。
- REST 返回扁平邻接表，SSE 增量 upsert；前端按 parent_step_id 建树。
- 层级固定 Phase → Agent/WorkItem → Skill或Tool，最多三级。

## 实施步骤与文件边界

1. 后端先实现迁移、树校验、node_key/source_event 幂等和 projector retry。
2. 前端抽取同一处理树组件，兼容旧扁平和普通二级步骤。
3. 实现运行展开、完成折叠到二级、失败强展、localStorage 和滚动保护。
4. 补 reduced motion、ARIA、乱序缓存、XSS 和局部 DOM 更新测试。

## 子代理分派

- `backend-dev`、`frontend-dev` 分端并行，后端合同冻结后前端开始。
- `backend-reviewer` 检查树完整性、投影幂等和跨库失败。
- `frontend-reviewer` 检查 DOM、状态、XSS、ARIA、CSS 作用域和 `?v=N`。

## 边界与明确不做

- 不展示完整 Prompt、凭据或隐藏思维链。
- 不增加第四级；Tool 以标签关联指导 Skill。
- 不做跨设备展开同步，不重写旧 processing step 数据。

## 验收、风险与回滚

- v1 扁平、v2 二级/三级同时可渲染；非法父链被后端拒绝。
- SSE 断线、乱序、重复、投影失败和刷新均无重复/丢失。
- Projector 按事件序重放；失败写待重放标记并返回 `TRACE_PROJECTION_FAILED`，重试成功后清除；迟到结果不能覆盖终态。
- 用户阅读旧节点时不自动跳走；失败节点可见且强展开。

## 产出物、执行结果与变更日志

- 产出：ProcessingStep v2、Projector、共享前端树组件、双端测试与评审报告。
- 执行结果：双端实现、复审与独立验收均 GO；真实浏览器 smoke 留 Task10。
- 变更日志：2026-09-13 启动后端迁移、树校验、Projector 幂等与重试实现；复用 Task02 canonical event/replay 接缝，不重写旧 processing step 数据。后端定向 227 passed、5 subtests，前端定向 193 passed，双端 reviewer/tester 均 GO；真实浏览器 smoke 留 Task10。
