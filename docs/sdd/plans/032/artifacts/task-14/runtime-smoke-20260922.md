# Task14 运行时 smoke 证据（2026-09-22）

本记录只保存受控小范围运行证据；不代表四会议逐年覆盖已完成。

## 环境

- 启动命令：`PORT=18080 RERANKER_ENABLED=false ./deploy/start.sh`
- 地址：`http://127.0.0.1:18080`
- `GET /api/health`：HTTP 200，`paper_discovery_enabled=true`。

## 来源同步

| 来源/范围 | sync id | 终态 | 证据 |
|---|---|---|---|
| USENIX Security 2024 | `sync-usenix-2f71bd0968624480` | `completed`, `degraded=false` | summer/fall 两个页面单元，227 篇 |
| NDSS 2024 | `sync-ndss-6a4e6e04bb1641b5` | `completed`, `degraded=false` | official 单元，142 篇 |
| DBLP 2024 | `sync-dblp-9df36fe7786646f2` | `failed`, `degraded=true` | 稳定错误码 `DBLP_INVALID_RESPONSE`，未写入假数据 |

## 缓存检索

- `POST /api/papers/searches`：`query=security`、`conference_ids=["usenix-security"]`、`years=[2024]`。
- search id：`8b2944b58b994a00bdc02011a5e7ff48`。
- 终态：HTTP 200，`partial`，`total_results=227`；USENIX 使用已完成缓存，DBLP 显示 `SOURCE_SKIPPED`。
- `GET /api/papers/searches/{id}/results?page=1`：HTTP 200，第一页 10 篇、总页数 23；目录阶段未触发 PDF 请求。
- `degraded=true` 仅表示当前索引/RAG 运行环境降级，不影响目录候选冻结和分页读取。

## 重启与 Semantic Scholar

- 服务重启后再次访问 `/api/health`：HTTP 200，已完成的来源状态可从 SQLite 读取。
- `GET /api/papers/semantic-scholar/autocomplete?query=privacy&limit=1`：HTTP 200，返回一条候选。
- 429 测试和 SQLite 重启持久化测试均通过；真实 API 仍受供应商速率限制，调用必须使用共享 1 RPS 限流器。

## 导入批次恢复读取

- 重启后读取既有批次 `83846ea1-0178-421a-bc8b-2ea5d8b7a0de`：HTTP 200，状态 `partial_success`，6 项中 3 项 `completed`、3 项 `failed`。
- 失败项保留稳定错误码 `KB_IMPORT_FAILED`、`cleanup_pending` 和 `attempt_count=1`；成功项保留文档名与 `paper_id`。
- 该证据证明批次快照和失败状态可恢复读取；尚未将失败项强行重试或伪造为成功。

## 尚未满足的 Task14 门禁

- IEEE S&P、CCS 及未验证年度的官方覆盖仍需按 NO-GO/复验路径记录。
- 候选评估→批准计划→实际导入/失败队列人工修复的业务批次尚未完成真实闭环。
- 独立 tech-lead/tester 签字、唯一全量回归和 Spec032 最终状态更新仍未完成。
