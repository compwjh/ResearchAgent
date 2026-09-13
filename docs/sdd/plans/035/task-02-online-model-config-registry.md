> 关联：[spec-035](../../specs/035-online-model-provider.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`待执行`

## 1. 状态与一句话目标

`待执行`。建立线上模型的**配置解析与注册表**，并验证 `langchain-openai` 依赖可行性；交付一个可独立验收的「`.env` → 注册表」能力。

## 2. 背景与前置条件

- 现状：项目没有任何线上 provider；配置集中在 `backend/app/platform/config.py`（`python-dotenv` + 模块常量，无 pydantic-settings），`.env.example` 只有 Ollama 相关 5 项。
- 依赖任务 01（spec 已落盘，**尚未经用户确认**）。
- 必读（最小上下文）：`backend/app/platform/config.py`（全文 140 行，重点看 `_env_bool` / `_env_positive_number` 的「warn 后回退、不 fail-fast」风格）、`.env.example`。
- 硬约束：本任务**不触碰**任何业务路由与前端。

## 3. 数据、配置与接口

`.env` 新增（同步写入 `.env.example`，**值留空**）：

```bash
# 线上模型清单：逗号分隔的 provider:model
ONLINE_MODELS=
# 每个 provider 一组（provider 名转大写 + 下划线）
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

注册表项字段（见 spec 035「数据模型 §2」）：`id` / `provider` / `model` / `display_name` / `base_url` / `api_key` / `source`。

解析规则严格按 spec「解析规则」表实现（去空白、非法跳过+warning、provider 小写、缺 Key 不注册、缺地址用内置默认表、协议仅 https 或 loopback http、重复保留首个、与本地同名本地优先）。

内置默认地址表：`deepseek` → `https://api.deepseek.com`，`openai` → `https://api.openai.com/v1`。

## 4. 实施步骤与文件边界

| 顺序 | 文件 | 改动 |
|---|---|---|
| 1 | `backend/app/platform/config.py` | 新增 `ONLINE_MODELS` 常量读取（沿用 `os.getenv` 风格） |
| 2 | `backend/app/platform/model_catalog.py`（**新建**） | `OnlineModelEntry` dataclass + `get_online_models()` 解析 + `get_online_model(id)` 查询 |
| 3 | `.env.example` | 追加上面 3 行（带中文注释说明） |
| 4 | `requirements.txt` / `requirements.lock.txt` | 新增 `langchain-openai` 及锁定版本 |

**依赖可行性 PoC（第一步，不通过即停）**：

```bash
.venv/bin/pip install langchain-openai
.venv/bin/python -c "from langchain_openai import ChatOpenAI; m=ChatOpenAI(model='x', api_key='k', base_url='https://api.deepseek.com'); print(type(m))"
```

若与现有 `langchain-core 1.6.2` 冲突或 import 失败，**立即停止并报告**，由架构师决定是否回退 httpx 自研方案（回退需先修订 spec，不得自行决定）。

完成后的可观察结果：`get_online_models()` 能从 `.env` 解析出条目；缺 Key 的条目不出现；非法条目被跳过且只 warning。

## 5. 子代理分派

| 项 | 内容 |
|---|---|
| 角色 | `backend-dev`（`Deepseek-V4.1-Flash`） |
| 最小上下文 | 本 task 文件 + `config.py` 的 `_env_bool`/`_env_positive_number` 段落 + spec 035「数据模型」 |
| 单次文件范围 | 只改上表 4 项；**不改** `ollama.py`、任何路由、任何前端文件 |
| 回传后读回校验 | 架构师 `read_file` 确认新增代码与 `.env.example` 实际写入，并跑一次 ruff |

## 6. 边界与明确不做

- 边界：空值、无冒号、多冒号、空项、重复项、大小写不一致、缺 Key、未知 provider 且无地址、非 https 且非 loopback、前后空格。
- 明确不做：不发任何网络请求（探测在任务 04）；不改 `get_available_models()`；不动 `/api/health`；不在 UI 暴露 Key；不写 Key 到日志。

## 7. 验收、风险与回滚

验收：

```bash
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_online_model_registry.py --basetemp=/tmp/s035t02 -q
.venv/bin/ruff check backend
```

- 新增测试 `tests/test_online_model_registry.py`（**按功能命名，不带 spec 编号**）覆盖上述全部边界，全绿。
- 不得出现真实 Key；测试用 mock/monkeypatch 注入 env，不依赖真实网络。
- 风险：依赖冲突（见 §4 PoC）；回滚：卸载 `langchain-openai` 并回退 `requirements.txt`，注册表解析代码可保留（不含网络调用）。

## 8. 产出物、执行结果与变更日志

待执行后填写（真实命令、退出码、通过数量、新增文件清单）。
