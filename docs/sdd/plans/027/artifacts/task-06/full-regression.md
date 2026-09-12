# Spec027 Task06 全量回归证据

## 最终结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q`（首轮） | 1 | 1699 passed、1 skipped、1 failed、52 subtests；失败为 Spec018 冻结清单 SHA 漂移，已定向修复清单 |
| `.venv/bin/python -m pytest -q tests/test_kb_upload_closure_matrix.py`（定向修复复验） | 0 | 2 passed |
| `.venv/bin/python -m pytest -q`（最终全量） | 0 | **1700 passed、1 skipped、5 warnings、52 subtests**，96.32s |

最终全量回归在修正冻结清单后通过；DeprecationWarning 来自第三方 PDF/底层类型，不影响退出码。

## 前端与静态检查

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/research-tasks.js` | 0 | 通过 |
| `node --check frontend/app.js` | 0 | 通过 |
| `for f in tests/test_frontend_*.js; do node "$f"; done` | 0 | 5/5 Node 合同通过 |
| `.venv/bin/python -m pytest tests/test_frontend_*.py -q` | 0 | 173 passed |
| `.venv/bin/ruff check backend/app/research backend/app/api/routes_research.py backend/app/platform/ollama.py` | 0 | All checks passed |
| `git diff --check` | 0 | 无空白错误 |

## 固定样本

`PYTHONPATH=. .venv/bin/python docs/sdd/plans/027/artifacts/task-05/task05-close-probe.py` 退出码 0。固定路由调用序列为 `qwen3.5:9b → qwen3.5:9b → qwen3.8:27b-mlx`，最终 strong，并产生安全 `MODEL_ESCALATED`；固定 Adapter 无 source 为 `SOURCE_DEGRADED`，fixed source 返回 `fixed-catalog-1`。
