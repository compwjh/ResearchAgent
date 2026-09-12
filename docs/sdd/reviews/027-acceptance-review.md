# Spec027 最终验收评审（Task06）

## 结论

**通过，允许 Spec027 标记为已完成（附环境延期风险）。** Task02–05 交接物齐全，复用审计通过；最终全量回归 1700 passed、1 skipped、退出码 0；固定样本通过；FastAPI 已在 `127.0.0.1:18081` 启动并通过 health、首页和 Research Task 入口 smoke。未发现 P0/P1。真实 USENIX/DBLP 及 Ollama chat 的阻断已如实记录，不把环境失败计作成功。

## 复用与范围门禁

- `search_catalog` 通过 `CatalogSearchAdapter` 惰性调用 Spec015 `CatalogSearchGraph` / `CatalogRagAdapter`，未在 `backend/app/research/**` 复制目录、RAG、下载或导入。
- 模型清单/资源探针回到 `backend/app/platform/ollama.py`，未新增模型客户端。
- 研究表与前端报告只保留 `catalog_paper_id` 等安全投影；未展示完整 Prompt、隐藏思维链或原始论文元数据。
- 研究端点和前端无 pause/resume；移动端合同保持只取消，符合 Spec028 分界。
- 全量回归暴露的 `backend/app/main.py` 冻结 SHA 漂移已按既有 Spec018 清单惯例同步 hash/digest，未改动 Spec015/022 业务逻辑。

详细依据见 [`docs/sdd/plans/027/artifacts/task-06/reuse-audit.md`](../plans/027/artifacts/task-06/reuse-audit.md)。

## 评审复用

- 技术/需求维度复审：`docs/sdd/reviews/027-tech-review.md`，P0-1/P0-2 与 P1×8 已关闭，结论通过。
- 前端复审：`docs/sdd/reviews/027-frontend-review.md`，P0/P1 为 0，结论 GO；Task06 补齐真实服务入口 smoke。
- Task03 后端复审、Task04 前端验收、Task05 双端交接均已复用并核对当前代码与报告，不重复改写历史评审。

## 验证记录

### 全量与固定样本

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q`（最终） | 0 | **1700 passed、1 skipped、5 warnings、52 subtests** |
| `PYTHONPATH=. .venv/bin/python docs/sdd/plans/027/artifacts/task-05/task05-close-probe.py` | 0 | 固定 ModelRouter 升级、Adapter 降级与 fixed source 均通过 |
| `node --check frontend/research-tasks.js` + `node --check frontend/app.js` | 0 | 通过 |
| `for f in tests/test_frontend_*.js; do node "$f"; done` | 0 | 5/5 通过 |
| `.venv/bin/python -m pytest tests/test_frontend_*.py -q` | 0 | 173 passed |
| `.venv/bin/ruff check backend/app/research backend/app/api/routes_research.py backend/app/platform/ollama.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

全量首轮为 1699 passed、1 skipped、1 failed；唯一失败是冻结清单 SHA。更新清单后，`tests/test_kb_upload_closure_matrix.py` 定向复验 2 passed，最终全量通过。

### 服务与 API

启动命令：`PORT=18081 RERANKER_ENABLED=false ./deploy/start.sh`。

| 请求 | 结果 |
|---|---|
| `GET /api/health` | 200，`status=ok`，11 个模型 |
| `GET /` | 200，首页加载成功；含 research 导航/模式/脚本 |
| `GET /api/research-tasks` | 200，空列表稳定返回 |
| `POST /api/research-tasks` `{}` | 400，`PLAN_VALIDATION_FAILED` 稳定错误体 |

服务验证后以 Ctrl-C 正常停止，不能把临时服务当作持续后台部署；用户如需复验可运行同一命令并打开 [http://127.0.0.1:18081](http://127.0.0.1:18081)。

## 环境阻断与风险

1. 真实 Ollama `/api/tags` 在 `127.0.0.1:11434` 成功，最小 `qwen3.5:9b` chat 在 3 秒超时；固定路由仅证明 `fast→fast retry→strong` 算法，不证明真实推理质量/延迟。
2. USENIX 最小调用返回 `USENIX_UNAVAILABLE`；DBLP 返回 `DBLP_NETWORK_ERROR`/`DBLP_UNAVAILABLE`。固定 Adapter 与诚实降级路径已通过。
3. 首次默认 8000 启动在沙箱中无法绑定；18080 已被 PID 61835 占用，故使用脚本支持的 18081 并实际验证成功。

上述均为环境风险，不是 Spec027 代码 P0/P1；后续在网络和 Ollama chat 可用时，重跑既有 Task05 探针及 USENIX/DBLP source smoke 即可。

## 签字

- 开发主管/架构师（当前执行任务 Agent）：**通过**
- 后端评审结论：复用 Task03/Task05 报告，**无新增 P0/P1**
- 前端评审结论：复用 `027-frontend-review.md` GO，Task06 静态检查与服务入口 **通过**

日期：2026-09-13（Asia/Shanghai）
