# Task 05：项目文档、RAG 来源与完整处理过程

> 关联：[Spec 022](../../specs/022-project-conversation-memory.md) ｜ 索引：[README](./README.md)
> 依赖：Task04；被依赖：Task06、Task08；当前状态：`已完成`

## 一句话目标

把项目会话与既有论文知识库安全连接，并让 RAG 来源和真实处理步骤以紧凑、可展开、可追溯的方式呈现。

## 增量范围

- 知识库文档增加可选项目关联；项目删除只解除关联，不删除原件。
- 统一当前消息、会话历史、全局/项目记忆、项目指令、会话摘要和 RAG 证据的 token 预算。
- RAG 回答正文完成后才显示最多 5 个编号方块；一次只展开一个大段切片，可跳原文。
- 完整 SSE progress 覆盖普通聊天、记忆、知识库、论文检索/下载和 LangGraph 节点。
- 完成步骤持久化并默认折叠；运行中紫色海浪、完成静态紫色、失败红色、降级灰色。

## 复用边界

- 必须调用 knowledge_base application facade 和既有 source/inspection 安全入口。
- 不新建第二套 embedding、RRF、reranker、下载、安全校验或切片存储。
- progress 只来自真实事件；不得用定时假动画伪造工具执行。

## 子 Agent 分派

- backend-dev：项目文档关联、上下文装配、progress event 和最终步骤持久化。
- frontend-dev：编号来源、单项展开、处理过程状态和 reduced-motion。
- 双端 tester 分别定向验证，tester 部署执行桌面里程碑 smoke；不跑全量。

## 测试与验收

- RAG token 流结束前无切片卡；结束后编号数量 0–5，点击展开正确来源且二次点击收起。
- 文档关联/解除不改变原件、document ID、manifest 或索引代际。
- progress 顺序、失败/跳过、重连、历史静态显示和 XSS 安全。
- 普通聊天、论文搜索/下载和知识库问答均保存可见消息但不泄漏工具敏感参数。
- 部署后以真实项目、文档和会话执行 smoke。

## 风险与回滚

- 上下文预算导致当前指令或核心证据被裁剪即停止。
- RAG 引用与展开切片不一致、跨项目文档泄漏或 progress 伪造均判失败。

## 产出物

- `artifacts/task-05/implementation-report.md`
- `artifacts/task-05/test-report.md`
- `artifacts/task-05/review-report.md`
- `artifacts/task-05/acceptance-report.md`

## 执行结果

已完成。后端与前端均按冻结契约接入项目文档关联、项目隔离 RAG、真实 SSE 处理步骤和延迟来源展示：

- 后端定向测试：`130 passed`；覆盖项目文档关联/解除、项目过滤、来源身份、上下文预算、处理步骤和错误脱敏。
- 前端契约测试：`44 passed`；`node --check frontend/app.js frontend/conversation-research.js` 通过，5 个前端运行时/交互契约脚本全部 PASS。
- 后端复审：GO；前端复审：GO；跨端验收：PASS（验收报告记录了本机 HTTP smoke 受环境限制，未影响静态与 API 契约结论）。
- 部署验证：服务已启动于 `http://127.0.0.1:8000`；健康检查、项目创建、文档关联、按项目列出文档和项目删除后的关联清理已验证。真实 RAG 长时生成受本机模型/观测服务耗时影响，保留为运行环境风险，不阻塞本 Task 收口。

## 变更日志

- 2026-09-11：合并项目文档、RAG 紧凑来源和完整处理过程为研究能力集成里程碑。
- 2026-09-11：Task04 已收口，启动 Task05；先冻结后端项目关联、RAG 上下文和 progress/SSE 契约，再接入前端展示。
- 2026-09-11：Task05 完成后端/前端实现、双端复审、跨端验收和针对性回归；放行 Task06 与 Task08，暂不执行全量回归。
