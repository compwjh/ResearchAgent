# Spec043 Task11 第三阶段 B 后端独立测试

日期：2026-10-28  
角色：Backend Tester  
范围：`expand_batch` metadata worker、显式 metadata retry、analysis finish batch 投影和恢复对齐。测试由 `tmp_path` 隔离 SQLite，metadata client 与 model runner 使用测试替身；未访问真实来源、模型或生产数据库。

## 验收结果

- 定向后端测试：PASS — 74/74 passed，0 failed，0 skipped。
- 全量 pytest/collection、编译、lint、安全扫描、真实来源或模型、生产数据库、部署：本次未运行；不作为本报告通过项。
- 阻塞项：无。

## 执行记录

命令：

```text
PYTHONDONTWRITEBYTECODE=1 /Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/literature_maps/test_map_expansion_batch.py tests/literature_maps/test_map_auxiliary_jobs.py tests/literature_maps/test_map_analysis_queue.py tests/literature_maps/test_map_api_errors.py -q --basetemp=/private/tmp/spec043-worker-backend-tester-20261028
```

退出码：0；结果：74 passed in 3.27s；失败 0；跳过 0。

覆盖包括：metadata worker 的缺失摘要白名单写回及来源证明、精确身份匹配、缓存分区与持久化、显式无摘要重试的一次性 cache bypass、429 持久失败及通过现有 retry route 恢复、移除节点和迟到 token 防复活/拒写、暂停中完成与恢复对齐、`finish_analysis` 更新 batch 投影、重启状态校正不重复来源/模型工作，以及保留旧 analysis queue item 和既有错误 envelope。

未运行全量 pytest 或全量 collection；没有运行前端测试、真实 API E2E、外网/模型或部署。报告范围不含后续 UI/Spec 收口验收。

进展日志：[backend-tester 日志](../../../.codebuddy/agent-logs/spec-043/task-11/backend-tester/20261028-012019.md)。
