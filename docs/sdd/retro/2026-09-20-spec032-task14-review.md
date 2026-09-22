# Spec032 Task14 评审复盘

## 发现

本轮相关测试全绿（751 passed），但静态路径审计仍发现 Planner 接受七来源而 `CatalogSourceFactory` 仅支持 USENIX/DBLP 的集成断层。说明合同级测试、来源 Adapter 测试和 Tool 注册测试不能替代 Planner→AgentRuntime→实际 Tool 的端到端 source-selection 测试。

## 可复用经验

- 新增来源时必须同时核对四处：Planner 输入校验、Research search adapter 装配、注册 Tool schema/能力快照、真实 Worker dispatch；任何一处仍是旧枚举都应判 P1。
- “统一 Tool 已注册”不等于“Research 计划已使用统一 Tool”；必须在真实计划执行中观察 `source_id`、`worker-tool-v1` 和 server-owned handle。
- 离线 fake adapter、SQLite 重启测试和前端契约通过，只能标记静态/定向 PASS；服务未启动时真实 smoke 必须明确 BLOCKED。
- 复用审计应同时检查下载、安全、导入、批任务、身份校验、embedding/RRF；本轮未发现第二套实现，但新来源接线缺失仍足以阻塞收口。

## 后续门禁

先退回开发 Task 修复多来源 source selection，再由独立 reviewer/tester 复评；服务启动后补真实 smoke、部署和签字。Spec032 在这些动作完成前保持 `实施中`。
