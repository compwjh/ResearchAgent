# Spec 035 实施计划索引

> 关联 spec：[035 线上模型接入与模型库端侧/线上分组](../../specs/035-online-model-provider.md)

## 目标

让模型库接入线上模型（如 DeepSeek），并把模型库拆成「端侧模型 / 线上模型」两组展示。

三条断链：

- **断链一（无 provider）**：`create_chat_model()` 写死返回 `ChatOllama`，线上模型无处落地。
- **断链二（校验被拒）**：6 处路由用 `model in get_available_models()` 校验，线上模型不在 Ollama 列表内，**选中即 404/503**。
- **断链三（无分组）**：前端 `renderModelList()` 扁平循环，无法区分端侧与线上。

## 核心设计（务必先读）

- **唯一收口点**：`create_chat_model()`（`backend/app/platform/ollama.py:199`）被 `chat_runner` / `retrieve.py` / `article_agent.py` / `download_paper_skill.py` 调用。在它内部按模型名分发 provider，**所有模块自动无缝支持线上模型**，不需要逐个模块改造。
- **签名不可变**：`create_chat_model` 的名字与参数必须保持原样（63+ 处测试 patch 目标是 `backend.app.platform.ollama.create_chat_model`）。
- **零回归接口**：新增 `GET /api/models` 承载分组结构，`/api/health` 的 `models` 字段**一字不动**，`get_available_models()` 返回值不变。
- **配置来源**：只在 `.env` 静态声明（`ONLINE_MODELS` + `<PROVIDER>_API_KEY` / `<PROVIDER>_BASE_URL`），重启生效，UI 不填 Key。

## 任务顺序

| 编号 | 任务 | 角色 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-035 | 架构师(自身) | — | 完成 |
| 02 | [`.env` 配置解析与线上模型注册表](./task-02-online-model-config-registry.md) | `backend-dev` | 01 | 待执行 |
| 03 | [provider 分发与并集校验](./task-03-provider-dispatch-and-validation.md) | `backend-dev` | 02 | 待执行 |
| 04 | [`GET /api/models` 与轻量探测](./task-04-models-endpoint-and-probe.md) | `backend-dev` | 03 | 待执行 |
| 05 | [各模块无缝适配](./task-05-module-seamless-adaptation.md) | `backend-dev` | 04 | 待执行 |
| 06 | [前端模型库分组展示](./task-06-frontend-model-library-grouping.md) | `frontend-dev` | 04 | 待执行 |
| 07 | [测试、评审、回归、部署与复盘](./task-07-review-regression-deploy.md) | `backend-tester` / `frontend-tester` / `tester` / `architect` | 05, 06 | 待执行 |

## 运行测试的前置约定

- 一律 `env -u PYTHONPATH .venv/bin/python -m pytest`（`PYTHONPATH` 会注入沙箱 shim）。
- 每次必须给**全新的** `--basetemp=/tmp/xxx`，复用旧目录会因 `mkdir` 变 `PermissionError` 而假红。
- 多文件一起跑容易超过前台时限被 SIGTERM（退出码 137），按文件分批跑。

## 低消耗硬约束（用户明确要求）

- 开发/验收阶段**只测连通性**，禁止编写会真实消耗大量 token 的用例。
- 唯一允许的真实请求：`max_tokens=1` 的最小 chat completion。
- 无 Key 的 CI/本地环境必须 `skip`，**不得因为缺 Key 而 fail**。

## 风险

| 风险 | 缓解 |
|---|---|
| 新增 `langchain-openai` 依赖可能与现有 `langchain-core 1.6.2` 冲突 | Task02 先做依赖可行性验证（PoC），不通过则回退 httpx 自研方案并回 spec |
| 6 处模型校验改造面广 | 统一收敛到 `is_model_available()`，逐处替换并保留原测试 |
| 前端静态资源版本号未升导致页面不更新 | `index.html` 的 `?v=43` 必须同步递增，并同步硬编码版本号的旧契约测试 |
