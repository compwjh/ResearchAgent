# Spec031 验收评审：动态模型路由与资源调度优化

## 评审结论

**GO（单 Ollama 实例范围）**。Task02–06 已完成；多实例因缺少第二实例与独立资源证据保持 NO-GO，未被伪装成已实现能力。

## 证据

- Task02 benchmark 已补齐固定 JSON 响应质量校验、ResourceProbe、可用内存、监听端口和运行环境 provenance；单实例 cap=1 约束仍生效。
- Task03 的值级脱敏、owner 隔离、shadow replay 与观测降级通过。
- Task04 的额度并发、过期回收、grant 隔离、服务端 evidence gate 与策略回滚通过。
- Task05 的路由解释、Worker/降级、warm/cold 基准只读 UI 通过；前端使用 `textContent`，不展示 Prompt、回答、思维链或主机秘密。
- evaluator 完成事件新增安全的 `selected_paper_ids` 投影，论文选集在报告生成前可见；没有把标题、摘要、Prompt 或思维链写入事件。
- 最终全量回归：`.venv/bin/python -m pytest -q`，退出码 0，`2539 passed, 5 warnings, 67 subtests passed`。
- 前端语法与合同：`node --check frontend/research-tasks.js` 通过，Spec029/030/031 合同通过。
- 部署 smoke：`http://127.0.0.1:8500` 的 `/api/health` 与首页均 HTTP 200，资源版本为 `research-tasks.js?v=10`。

## 未纳入本次 GO 的边界

- 不启动第二个 Ollama 实例，不做跨机器集群调度。
- 不自动下载/卸载模型，不因 Langfuse 不可用阻塞业务。

## 复核时间

2026-09-17（Asia/Shanghai）。
