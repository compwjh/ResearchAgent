# Task06：真实 CLI 重建 LLM 接线修复报告

## 结果状态和摘要

**状态：PASS（局部修复，未执行真实 Qdrant/`--confirm-replace`）**

真实维护 CLI 的默认 `CandidateRebuildService` 现在注入既有
`backend.app.knowledge_base.infrastructure.chunkers.ollama_boundary_judge`。
因此 v2 provenance 构建不再因默认 `llm=None` 直接触发
`V2_RULES_ONLY_LLM_NOT_USED`；同步索引和候选重建复用同一个 LLM 边界实现。

注入 `service_factory` 的测试 seam 保持兼容：自定义工厂仍只收到原有
`metadata_path`、`papers_dir`、`runtime_root`、`index` 四个参数；未通过捕获
`TypeError` 等方式吞掉真实工厂错误。默认工厂路径由离线 Spy 测试证明收到的
对象就是 `rebuild_index.ollama_boundary_judge`。

## 改动文件

- `backend/app/knowledge_base/rebuild_index.py`
  - 导入既有 `ollama_boundary_judge`。
  - 仅在未注入 `service_factory` 时向默认服务构造传入 `llm`。
- `tests/test_kb_rebuild_cli.py`
  - 新增默认工厂 LLM 接线测试；使用 Spy，不联网、不调用真实 Ollama。

## 测试命令、退出码和结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest tests/test_kb_rebuild_cli.py -q` | 0 | `3 passed` |
| `.venv/bin/python -m pytest tests/test_kb_candidate_rebuild.py -q` | 0 | `62 passed`（5 warnings） |
| `.venv/bin/python -m py_compile backend/app/knowledge_base/rebuild_index.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |

未执行真实 Qdrant、embedding、Ollama 或 `--confirm-replace`；新增测试显式使用
dry-run 与 FakeQdrant/SpyService。

## 决策依据

`index.py::index_paper_chunker` 在 v2 未显式传入 LLM 时已经使用
`ollama_boundary_judge`。候选重建是同一正式切分语义的维护入口，故复用该函数，
不新建 HTTP 客户端或改变 v2 的 `llm_used` 硬门。dry-run 仍只执行服务的只读
preflight，不触发 LLM/embedding；只有 confirm 进入 build 时才会使用该注入。

## 风险与阻塞

- 风险：真实运行仍依赖本机 Ollama 可用、模型配置正确及 Task06 生产门禁；本修复
  未改变这些既有前置条件。
- 阻塞：无本次代码级阻塞。真实索引切换、alias、manifest finalize 和服务重启
  不在本子任务中执行。

## 主 Agent 后续动作

1. 复核本报告及两处代码/测试 diff，确认不与其他并行改动混入。
2. 在 Task06 生产门禁满足、服务停止且已获 confirm 授权后，执行 dry-run，再按
   固定命令运行真实候选重建；观察 v2 `llm_used=true`，不要放宽硬门。
3. 汇总独立 backend reviewer/tester 结果后再推进最终验收与部署流程。

## 时间与执行统计

- 开始：2026-09-10（具体开始时间未由运行器提供）
- 结束：2026-09-10（具体结束时间未由运行器提供）
- 总耗时：约 10 分钟（含上下文读取、RED/GREEN 与回归）
- 模型/token/工具统计：本子任务运行器未提供可用统计；使用文件读取、补丁编辑和本地 pytest/py_compile/diff 检查。

