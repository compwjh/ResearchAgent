> 关联：[spec-035](../../specs/035-online-model-provider.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02；当前状态：`待执行`

## 1. 状态与一句话目标

`待执行`。在 `create_chat_model()` 内部按模型名分发 provider（线上→`ChatOpenAI`，否则→`ChatOllama`），并提供 `is_model_available()` 并集校验，为「所有模块无缝支持线上模型」打好地基。

## 2. 背景与前置条件

- `backend/app/platform/ollama.py:199` `create_chat_model(model_name, *, reasoning=None)` 当前**固定返回 `ChatOllama`**。
- 它是**唯一收口点**：`chat_runner.py`、`knowledge_base/infrastructure/retrieve.py`、`article_agent.py`、`download_paper_skill.py` 均通过它取模型。
- `build_chat_graph(model)`（`chat/application/chat_graph.py:9`）是**鸭子类型**，只用 `model.stream()` + `chunk.content`，换 `ChatOpenAI` 可直接复用流式与思维链过滤。
- 依赖任务 02（注册表已可用）。

## 3. 数据、配置与接口

| 函数 | 位置 | 契约 |
|---|---|---|
| `create_chat_model(name, *, reasoning=None)` | `ollama.py`（**名字与签名一字不改**） | 命中线上注册表 → `ChatOpenAI(model=entry.model, api_key=..., base_url=..., timeout=..., max_retries=...)；否则 → 现状 `ChatOllama`（行为零变化） |
| `is_model_available(name) -> bool` | `model_catalog.py`（新建） | **本地 ∪ 线上** 并集；内部复用 `get_available_models()` 与 `get_online_models()`，单侧失败互不影响 |

线上分支对 `reasoning` 参数：**忽略**并 `logger.debug("线上模型不支持 think 参数，已忽略：%s", name)`（Ollama 的 `think` 是本地专有）。

## 4. 实施步骤与文件边界

| 顺序 | 文件 | 改动 |
|---|---|---|
| 1 | `backend/app/platform/model_catalog.py` | 新增 `is_model_available()` |
| 2 | `backend/app/platform/ollama.py` | `create_chat_model` 内部加分发分支（**不动函数签名与调用点**） |
| 3 | `tests/test_online_model_dispatch.py`（**新建**） | 覆盖分发与并集校验 |

**硬约束（违反即打回）**：

- `create_chat_model` 的函数名、参数名、参数顺序、返回值语义**保持原样**——现有 63+ 处测试 patch 的目标是 `backend.app.platform.ollama.create_chat_model`，调用点按模块属性解析。
- `ChatOllama` 分支的行为必须**逐字节不变**（含 `trust_env=False` 三处 client_kwargs 与 `reasoning` 透传）。
- `api_key` **不得**出现在任何日志、异常信息或返回值中。

完成后的可观察结果：传入线上 id 得到 `ChatOpenAI` 实例；传入本地名得到与改动前完全一致的 `ChatOllama`；`is_model_available()` 对两类 id 均返回 `True`。

## 5. 子代理分派

| 项 | 内容 |
|---|---|
| 角色 | `backend-dev`（`Deepseek-V4.1-Flash`） |
| 最小上下文 | 本 task 文件 + `ollama.py:189-219` 原文 + `chat_graph.py` 全文（证明鸭子类型）+ 任务 02 产出的 `model_catalog.py` |
| 单次文件范围 | 只改上表 3 项 |
| 回传后读回校验 | 架构师 diff `ollama.py` 确认 `ChatOllama` 分支未变，并跑既有 `tests/test_ollama_service.py` |

## 6. 边界与明确不做

- 边界：线上 id / 本地名 / 不存在的名 / 注册表为空 / `reasoning` 为 True/False/None/字符串 / 线上模型被删除。
- 明确不做：**不在本任务替换 6 处路由校验**（那是任务 05）；不改 `chat_runner` 的路由选择逻辑（任务 05）；不做探测（任务 04）；不改前端。

## 7. 验收、风险与回滚

验收：

```bash
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_online_model_dispatch.py tests/test_ollama_service.py tests/test_ollama_direct.py --basetemp=/tmp/s035t03 -q
.venv/bin/ruff check backend
```

- 新测试全绿，**且 `test_ollama_service.py` / `test_ollama_direct.py` 无回归**。
- 风险：若 `ChatOpenAI` 与 `chat_graph` 的 `stream()` 行为不兼容，会在任务 05 端到端暴露；本任务只需保证实例可构造。
- 回滚：`git checkout backend/app/platform/ollama.py` 即可（调用点未动）。

## 8. 产出物、执行结果与变更日志

待执行后填写。
