> 关联：[spec-035](../../specs/035-online-model-provider.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03；当前状态：`待执行`

## 1. 状态与一句话目标

`待执行`。新增 `GET /api/models` 端点返回「端侧 / 线上」分组结构，并实现**极低消耗**的轻量连通性探测（`max_tokens=1`），供前端打开页面时调用一次。

## 2. 背景与前置条件

- 现有模型列表唯一端点是 `GET /api/health` 的 `models` 字段（`List[str]`），被前端 3 处消费；**本任务不得改动它**。
- 路由聚合在 `backend/app/api/routes.py`（prefix `/api`）。
- 依赖任务 03（`is_model_available` / 注册表可用）。

## 3. 数据、配置与接口

`GET /api/models`（`?probe=1` 时触发探测），返回结构见 spec 035「端点 / 接口」：

```json
{"current": "...", "groups": [{"source":"local","label":"端侧模型","models":[...]}, {"source":"online","label":"线上模型","models":[...]}]}
```

模型项字段：`id` / `name` / `source` / `provider` / `display_name` / `current` / `status` / `capabilities`。
线上模型 `capabilities.reasoning_efforts` **恒 `null`**；端侧恒 `"ready"`。

`probe_online_model(entry, *, timeout=8.0)`：

| 项 | 取值 |
|---|---|
| 请求 | `POST {base_url}/chat/completions`，body `{model, messages:[{role:"user",content:"ping"}], max_tokens:1, stream:false}` |
| 单次超时 | 8s；总耗时上限 15s |
| 缓存 | 内存 60s（同 id 不重复消耗） |
| 失败 | 超时 / 非 2xx / 异常 → `unreachable`；**绝不影响 `/api/models` 返回 200** |
| 日志 | 只记 provider + 状态码，**不记 Key、不记响应体** |

## 4. 实施步骤与文件边界

| 顺序 | 文件 | 改动 |
|---|---|---|
| 1 | `backend/app/platform/model_catalog.py` | 新增 `probe_online_model()` + 60s 缓存 |
| 2 | `backend/app/api/routes_models.py`（**新建**） | `GET /api/models`，含 `?probe=1` |
| 3 | `backend/app/api/routes.py` | `include_router` 注册 |
| 4 | `tests/test_online_models_api.py`（**新建**） | 端点结构 + 探测降级 + 缓存 |
| 5 | `tests/test_online_model_probe.py`（**新建**） | 探测的超时/失败/缓存，**全部 mock，不发真实请求** |

完成后的可观察结果：`curl -s localhost:8000/api/models` 返回两组结构；`?probe=1` 时线上项带真实 `status`；Ollama 不可达时 `local` 组为空但仍 200。

## 5. 子代理分派

| 项 | 内容 |
|---|---|
| 角色 | `backend-dev`（`Deepseek-V4.1-Flash`） |
| 最小上下文 | 本 task 文件 + `routes_system.py` 的 `/api/health` 实现（仿其降级风格）+ `routes.py` 注册写法 |
| 单次文件范围 | 只改上表 5 项 |
| 回传后读回校验 | 架构师实际启动服务 `curl` 验证返回结构，并确认响应体**不含任何 Key** |

## 6. 边界与明确不做

- 边界：无任何线上配置（online 组空数组）、Ollama 不可达（local 组空，仍 200）、探测超时、探测非 2xx、60s 内重复请求命中缓存、`ONLINE_MODELS` 非法项、当前模型是线上模型、当前模型已被删除（回退第一个可用）。
- 明确不做：不改 `/api/health`；不做写入类端点；不做逐模型并发探测（串行即可）；**探测不得成为页面加载的阻塞项**。

## 7. 验收、风险与回滚

验收：

```bash
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_online_models_api.py tests/test_online_model_probe.py --basetemp=/tmp/s035t04 -q
curl -s "http://127.0.0.1:8000/api/models" | python3 -m json.tool
```

- 新测试全绿；响应体中 grep 不到任何 Key 片段。
- 风险：真实探测依赖外网与有效 Key——**测试一律 mock**，真实连通性只在任务 07 由人工用真实 Key 点一次。
- 回滚：移除 `routes.py` 的 include 与 `routes_models.py` 即可，其余模块不受影响。

## 8. 产出物、执行结果与变更日志

待执行后填写。
