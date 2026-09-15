> 关联：[spec-035](../../specs/035-online-model-provider.md) ｜ 索引：[README](./README.md)
> 依赖：任务 04；当前状态：`待执行`

## 1. 状态与一句话目标

`待执行`。把 6 处「`model in get_available_models()`」校验改为 `is_model_available()` 并集校验，并处理线上模型的 `think` 降级与 `direct` 路由回退，使**对话、知识库问答、文章助手、技能调用全部无缝支持线上模型**。

## 2. 背景与前置条件

**这是本 spec 的关键接缝**：线上模型不在 Ollama 列表内，不改校验则选中线上模型即被判 404/503。已知校验点：

| 位置 | 现状 |
|---|---|
| `backend/app/api/routes_chat.py:63-67` | `POST /api/chat` 校验，502 不可达 / 400 模型不存在 |
| `backend/app/api/routes_conversations.py:238-242` | `_validate_model()`，503 `MODEL_UNAVAILABLE` |
| `backend/app/api/routes_conversations.py:297-311` | `/api/chat/reasoning-options`，404 `MODEL_NOT_FOUND` |
| `backend/app/api/routes_kb.py:134`、`966-970` | KB 校验 + 状态探测 |
| `backend/app/api/routes_article.py:56,117,235,322` | skill 状态探测 |

依赖任务 04（`is_model_available` 已就绪）。

## 3. 数据、配置与接口

| 改动点 | 目标行为 |
|---|---|
| 6 处模型校验 | `is_model_available(model)`（本地 ∪ 线上），错误码与文案**保持不变** |
| `/api/chat/reasoning-options`（线上模型） | 返回 **200 + `{supported:false, efforts:[]}`**，**不得 404**（避免前端报错） |
| `OLLAMA_ROUTE=direct` + 线上模型 | **强制回退 langchain 路由**（direct 是 Ollama 专有直连链路）；记 debug 日志 |
| KB / 文章助手 / 技能调用 | 不做额外改动——它们已走 `create_chat_model()`，任务 03 的分发使它们自动支持线上模型 |

## 4. 实施步骤与文件边界

| 顺序 | 文件 | 改动 |
|---|---|---|
| 1 | `routes_chat.py` / `routes_conversations.py` / `routes_kb.py` / `routes_article.py` | 6 处校验替换为 `is_model_available()` |
| 2 | `routes_conversations.py` | reasoning-options 对线上模型返回不支持（200） |
| 3 | `backend/app/chat/application/chat_runner.py` | 线上模型强制 langchain 路由 |
| 4 | `tests/test_online_model_validation.py`（**新建**） | 校验并集 + reasoning 降级 + 路由回退 |

**硬约束**：现有错误码（`MODEL_NOT_FOUND` / `MODEL_UNAVAILABLE` / 502 / 503）与响应结构**不得改变**，否则前端既有处理会失效。

完成后的可观察结果：`POST /api/chat` 传入线上 id 不再被 400 拒绝；`reasoning-options` 对线上模型返回 200 且 `supported=false`。

## 5. 子代理分派

| 项 | 内容 |
|---|---|
| 角色 | `backend-dev`（`Deepseek-V4.1-Flash`） |
| 最小上下文 | 本 task 文件 + 上表 6 处校验点的**具体行号原文**（由架构师提供，不给整个文件） |
| 单次文件范围 | 只改上表 4 项；**不得**顺手重构无关逻辑 |
| 回传后读回校验 | 架构师 `grep -n "get_available_models" backend/app/api/*.py` 确认只剩预期调用，并跑既有对话/KB 测试 |

## 6. 边界与明确不做

- 边界：线上 id / 本地名 / 不存在名 / 注册表被清空 / Ollama 不可达但线上可用 / 线上可用但 Ollama 不可达 / 当前模型为线上模型。
- 明确不做：不改错误码语义；不给线上模型新增思考档位；不解析 `reasoning_content`；不改前端；不做 direct 路由对线上的适配（直接回退 langchain）。

## 7. 验收、风险与回滚

验收：

```bash
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_online_model_validation.py tests/test_conversations_api.py tests/test_reasoning_options_endpoint.py --basetemp=/tmp/s035t05 -q
.venv/bin/ruff check backend
```

- 新测试全绿，**`test_reasoning_options_endpoint.py` 与 `test_conversations_api.py` 无回归**（这两个文件对校验路径覆盖最密）。
- 风险：校验放宽后，若某处依赖「模型必须本地」的隐含假设（如 Ollama 专有的 `think` 参数）会暴露——`chat_runner` 已对线上忽略该参数。
- 回滚：逐文件回退 6 处校验替换即可，注册表与端点不受影响。

## 8. 产出物、执行结果与变更日志

待执行后填写。
