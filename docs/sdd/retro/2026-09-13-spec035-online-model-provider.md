# 复盘：Spec 035 线上模型接入与模型库端侧/线上分组

- 日期：2026-09-13
- 角色：架构师（自身）
- 分支：`feature/spec-035-online-model-provider`
- 结果：全量回归 1702 passed / 2 failed（均为基线存量），需求/技术评审通过，服务已部署并通过运行时 smoke

## 一、做对了什么

### 1. 找「唯一收口点」而不是逐模块改造

需求最初被理解为「打通对话链路」。质询中用户指出：这是模型层改动，应当**无缝适应所有模块**。

核实后发现 `create_chat_model()` 是唯一收口点，被 `chat_runner`、`retrieve.py`（知识库）、`article_agent`、`download_paper_skill` 共同调用；且 `build_chat_graph(model)` 是**鸭子类型**（只用 `model.stream()` + `chunk.content`）。于是在 `create_chat_model` 内部按模型名分发 provider，**四个模块零改造即全部支持线上模型**。

> 沉淀：面对「让所有模块支持 X」类需求，先找收口点，而不是枚举调用方。

### 2. 提前识别隐藏接缝

在写 spec 阶段就发现：6 处路由用 `model in get_available_models()` 做校验，线上模型不在 Ollama 列表内，**不改则选中即 404/503**——「无缝」会变成空话。这条被单独拆成 Task05，成为本 spec 最关键的一环。

### 3. 零回归的接口策略

坚持新增 `GET /api/models`，`/api/health` 的 `models` 字段与 `get_available_models()` **一字未动**。技术评审独立核验 `git diff 79cfa21 -- routes_system.py` 输出为空——63+ 处 mock 全程未受影响。

## 二、最大的坑：替换校验函数会击穿 44 处 patch 目标

Task05 把 membership 校验换成 `is_model_available(model)`。逻辑正确，但**全量回归炸了 3 个用例**：

```
FAILED tests/test_api_routes_coverage.py::RunAgentBranchTests::test_run_chat_branch_reports_exception
FAILED tests/test_api_routes_coverage.py::RunAgentBranchTests::test_run_chat_branch_streams_answer
FAILED tests/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_...
```

根因：**44 处测试 patch 的目标是各路由的模块级符号** `backend.app.api.<module>.get_available_models`：

| patch 目标 | 处数 |
|---|---|
| `routes_conversations.get_available_models` | 14 |
| `routes_kb.get_available_models` | 12 |
| `routes_chat.get_available_models` | 11 |
| `routes_article.get_available_models` | 7 |

`is_model_available()` 内部走的是 `ollama.get_available_models`，**不是被 patch 的那个符号** → patch 全部静默失效。

**修法**：新增**纯函数** `is_online_model(name)`（只查线上注册表，不调 Ollama、不发网络请求），路由改回保留模块级 patch 目标的写法：

```python
if m not in get_available_models() and not is_online_model(m):
    ...原有错误分支...
```

> **沉淀为长期规则**：在已被大量测试 patch 的位置替换函数时，必须保住原 patch 目标。
> 正确姿势 = **保留原调用 + 新增一个「纯函数」做并集短路**，而不是把原调用整体换掉。
> 「纯函数」是关键——它不引入新的外部依赖，因此不会成为新的 patch 失效点。

### 教训：定向测试没覆盖到真正的风险面

Task05 的验收命令跑了 `test_conversations_api`、`test_reasoning_options_endpoint` 等，**唯独漏了 `test_api_routes_coverage.py`**——而失败恰好就在那里。
> 沉淀：改公共校验逻辑时，验收清单必须包含**所有 patch 了该符号的测试文件**，而不是凭直觉挑几个。

## 三、方法论：用 git worktree 建干净基线做归因

回归出现 5 个失败时，没有急着修，而是先用干净基线隔离：

```bash
git worktree add /tmp/s035-base 79cfa21
cd /tmp/s035-base
env -u PYTHONPATH <主项目>/.venv/bin/python -m pytest tests/test_chat_route.py \
    tests/test_api_routes_coverage.py tests/test_kb_upload_closure_matrix.py -q --basetemp=/tmp/xxx
```

结论：`test_chat_route` 的 2 个失败**基线即存在**（存量），另外 3 个才是本次引入。

> **沉淀**：面对「这是不是我弄坏的」，`git worktree` 建干净基线比 `git stash` 安全得多——它**完全不动当前工作树**，在多人/多 agent 并行改同一棵树时尤其重要。用完 `git worktree remove --force` + `git worktree prune` 清理。

## 四、容易漏掉的连带：spec-018 冻结清单

改了 `backend/app/api/routes_kb.py`，结果 `test_kb_upload_closure_matrix.py` 报 sha256 不匹配——它在 spec-018 的**冻结清单**里。

按 spec-020 BUG-08 既有惯例刷新（改 `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` 的该项 sha256 与 `inventory_digest`），diff 仅 2 行。

> 沉淀：任何被冻结清单覆盖的文件发生**授权改动**后，必须同步刷新 hash；但刷新前要确认改动确实经本 spec 授权，不能无脑刷新掩盖未授权改动。

## 五、多 agent 共享工作树的并发风险

本工作树同时有 **spec-034（工具源码查看器）** 的在途改动：`routes_tools.py`(+40)、`tool_service.py`(+96)、`test_tool_registry.py`(+292)、`test_frontend_skill_tool_contract.py`(+113)，以及 `plans/034/`、`specs/034-*`。

带来两个实际影响：
1. **提交范围必须严格限定**——不能 `git add -A`，否则把 034 的代码卷进 035 的 commit。
2. **静态资源版本号被并发 bump**：Task06 设的 `?v=44` 被 034 推到 `?v=45`；我们同步的 3 个契约测试也随之变成 45。版本号必须与 `index.html` 实际值一致，不能照抄任务书里的数字（已在 task-06 文档中改为「以 index.html 实际值为准」）。

> 沉淀：多 agent 并行时，**提交前必须逐文件确认归属**；版本号这类共享资源以**实际文件值**为准，不信任文档里的历史数字。

## 六、遗留与建议

| 项 | 说明 |
|---|---|
| 端到端未验证 | 本机 Ollama（局域网 `192.168.31.180:11434`）不可达 + 未配线上 Key → 端侧真实渲染、`status=ready/unreachable` 真实探测、ChatOpenAI 真实流式均**未端到端验证**，需在可用环境补验 |
| 存量失败 2 个 | `test_chat_route.py::test_prompt_never_contains_secrets`、`::test_record_generation_called_once_with_route` 基线即失败，建议另立修复项 |
| 历史 lint | `routes_conversations.py` 6 个、`ollama_direct.py` 等 22 个既有 ruff 错误，非本次引入，未扩大范围修 |
| 低危建议 | 技术评审 L3：developer 模式异常回显理论上可能带出 Key，建议经 `_redact_sensitive` 脱敏；L4：loopback 校验放行 `0.0.0.0` 略宽 |
