# Spec034 Task10 reasoning off 工厂修复

日期：2026-09-15（Asia/Shanghai）
范围：`ResearchAgentRunner` 的 Ollama 模型工厂；未 commit、未 push，未运行全量回归。

## 根因

`_ollama_model_factory` 对所有 reasoning effort 都先调用严格的
`resolve_reasoning_effort`。该 resolver 会探测 Ollama 的全部五档能力；真实
Smoke 使用 `reasoning_effort='off'` 时，探测耗时且在本地 Ollama 能力未知时会
抛出解析错误，Runner 随后把它归类为 `MODEL_UNAVAILABLE`。关闭推理并不需要
能力探测，因为 Ollama 的 transport 值已经确定为 `False`。

## 最小修复

- `backend/app/research/application/agent_runtime.py`：将规范化后的 `off` 直接
  映射到 `create_chat_model(model_name, reasoning=False)`，并包装为现有
  `_OllamaRunnerAdapter`。
- `low` / `medium` / `high` / `xhigh` 仍通过原有
  `resolve_reasoning_effort`，保留严格支持集校验与失败语义。
- `tests/test_spec034_task10_backend.py`：用 mock 断言 `off` 不调用 resolver，
  且返回现有 Adapter、模型名和 reasoning metadata 正确。

## 定向验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/test_spec034_task10_backend.py -k 'ollama_model_factory_off_skips_capability_probe'` | 0 | 1 passed，7 deselected |
| `.venv/bin/python -m pytest -q tests/test_spec034_task10_backend.py` | 0 | 8 passed |
| `.venv/bin/python -m py_compile backend/app/research/application/agent_runtime.py` | 0 | 编译通过 |
| `git diff --check -- backend/app/research/application/agent_runtime.py tests/test_spec034_task10_backend.py` | 0 | 空白检查通过 |

未运行全量 pytest，未改变聊天主链路。
