# Spec028 Task02 durable runtime gate

## 状态

**GO（核心合同通过；公平调度运行时探针因当前环境缺少可选依赖而跳过）**

## 范围与变更

- `backend/app/research/infrastructure/research_store.py`
  - ResearchStore 连接统一启用 SQLite WAL。
  - 设置 30 秒 `busy_timeout`，保留既有 `BEGIN IMMEDIATE` 写事务和状态机；没有新增第二套任务状态机或生产调度器。
- `tests/test_spec028_runtime_contract.py`
  - 临时 SQLite 固定样本验证跨进程唯一租约领取、过期接管、旧 token 心跳拒绝。
  - 验证 checkpoint 先持久化、输入摘要校验、旧计划版本不能推进节点。
  - 复用既有 `_GlobalWorkerScheduler` 验证双任务均分及资源不超卖（依赖可用时执行）。
  - 复用既有 `ResearchStore`/`state_machine` 验证 WorkItem 与 Task 终态不可重新进入 running。

## 验证

命令：

```text
python -m pytest --noconftest -q tests/test_spec028_runtime_contract.py
```

结果：退出码 `0`，`5 passed, 1 skipped`。跳过项为 `test_global_worker_scheduler_is_fair_and_never_oversells_capacity`；当前执行环境缺少 `langchain_ollama`，无法导入既有 Ollama 调度模块。该测试未用替代实现伪造通过；在完整开发依赖环境中应执行既有 `_GlobalWorkerScheduler` 探针。

附加检查：

```text
python -m py_compile backend/app/research/infrastructure/research_store.py tests/test_spec028_runtime_contract.py
```

结果：退出码 `0`。

## 证据摘要

- ResearchStore 临时库 `PRAGMA journal_mode` 为 `wal`，外键仍为开启状态。
- 两个独立 `spawn` 进程并发执行单条条件 `UPDATE`，结果严格为一个成功、一个失败。
- 已过期租约可被新 token 接管；旧 token 的条件心跳更新行数为零。
- checkpoint 的规范化 JSON SHA-256 摘要可在新连接中复验；计划版本不匹配时节点 CAS 行数为零；篡改内容无法通过摘要比较。
- 已完成 WorkItem/Task 均由既有状态机拒绝回到 `running`。

## 风险与后续

- 本 Task 只冻结数据库/CAS/公平调度合同；SchedulerLease、SchedulerCheckpoint、ResourceReservation 的生产表和调度服务留给 Task03，不在本 Task 提前实现。
- 完整依赖环境应重新运行同一命令，确认公平调度项为通过而非跳过。
- 未运行全量回归、未提交或推送。

时间：2026-09-16（Asia/Shanghai）
