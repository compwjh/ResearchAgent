# Spec 035 技术评审

- **评审角色**：架构师（architect）
- **评审类型**：技术评审（SDD 三道门禁 · 第二道）
- **评审日期**：2026-09-13
- **关联 spec**：`docs/sdd/specs/035-online-model-provider.md`
- **关联计划**：`docs/sdd/plans/035/README.md` + task-02..06
- **评审结论**：通过

> 核验方法：除阅读 spec/task/代码外，对关键高风险点使用 `git diff 79cfa21`（merge-base）做基线对照、用 grep 做密钥/重复实现扫描、逐行读源码确认。（分支 `feature/spec-035-online-model-provider`，基线 commit `79cfa21`。）

---

## 一、高风险点逐条核验（用户指定）

### 风险点 1：`create_chat_model` 函数名/参数/返回值语义一字未改，且 ChatOllama 分支逐字节不变
- **核验**：`git diff 79cfa21 -- backend/app/platform/ollama.py`
- 基线（79cfa21）原函数签名即为 `def create_chat_model(model_name: str, *, reasoning: Optional[bool | str] = None) -> ChatOllama:`（`ollama.py:202`）。**本次未重命名参数**（"model_name" 自基线起就是原名），函数名、参数名、参数顺序、返回值语义**逐字未改**。
- `ChatOllama(...)` 分支（`ollama.py:243-250`）在 diff 中仅因前置插入 `if entry is not None:` 分发块而整体下移，其文本**逐字节不变**：`client_kwargs={"trust_env": False}`、`async_client_kwargs={"trust_env": False}`、`sync_client_kwargs={"trust_env": False}` 三处与 `reasoning=reasoning` 透传全部保留，与 task-03 硬约束一致。
- 线上分支 `ChatOpenAI(model=entry.model, api_key=entry.api_key, base_url=entry.base_url, timeout=60.0, max_retries=2)`（`:235-241`），仅在本分支构造、不污染 ChatOllama 分支。
- **结论**：满足「63+ 处测试 patch 目标 `backend.app.platform.ollama.create_chat_model` 不受影响」的硬约束。✅

### 风险点 2：`/api/health` 的 `models` 字段与 `get_available_models()` 完全没被改动
- **核验**：`git diff 79cfa21 -- backend/app/api/routes_system.py` —— **输出为空**（零改动）。
- `routes_system.py:25-36` 的 `health()` 仍调用 `get_available_models()`（L28）并以 `models` 字段原样返回 `List[str]`（L34）。`get_available_models()` 本体（`ollama.py:192-199`）未被本 spec 改动。
- **结论**：零回归核心承诺成立。✅

### 风险点 3：6 处模型 membership 校验替换语义正确；routes_kb.py:134 与 routes_article.py 的 skill_status 判断为「不替换」是否成立
- 替换点（均已加 `is_model_available` 并集守卫，且**既有错误码/文案未变**，diff 对照确认）：
  - `routes_chat.py:63-71`：Ollama 不可达时仅当非线上非本地才 502；否则 400 文案不变。
  - `routes_conversations.py:239-248`：`_validate_model` 同构改造，503/404 文案不变。
  - `routes_conversations.py:301-319`：`reasoning-options` 对线上模型 `get_online_model(selected) is not None` 时直接 `return {"supported":False,"efforts":[]}`（L309-310），**不报 404**（边界 8）。
  - `routes_kb.py:966-974`：同 chat 改造，502/400 文案不变。
  - `routes_article.py:115-118`：`run_agent` 将 `request.model not in available_models` 改为 `not is_model_available(request.model)`，文案不变。
- **「不替换」判断复核（成立）**：
  - `routes_kb.py:134` 处的 `installed = get_available_models()` + `CHUNK_V2_LLM_MODEL in installed` 是**固定本地结构分析模型**（`CHUNK_V2_LLM_MODEL`，非用户可选模型）的可用性探测，与「用户选中模型的 membership 校验」无关，替换为 `is_model_available` 反而语义错误 → **不替换正确**。
  - `routes_article.py:54-62 / 225-244 / 315-326` 的 `skill_status(get_available_models())` 基于 `download_paper_skill.py:14` `WORKER_MODEL = "deepseek-coder:33b"`（**固定本地 worker 模型**），且 `build_download_plan` 硬编码调用 `create_chat_model(worker_model)`（:94）。该技能只在本地 worker 模型上跑，与用户选中模型无关；线上模型 id 恒带 `provider:` 前缀，永远不会等于 `deepseek-coder:33b` → **不替换正确**。
- **结论**：6 处接缝语义正确，两处「不替换」判断经源码复核成立。✅

### 风险点 4：`api_key` 是否可能出现在任何 HTTP 响应体、日志、异常信息中
- **响应体**：`routes_models.py:69-79` 的模型项仅含 `id/name/source/provider/display_name/current/status/capabilities`，**不含 `api_key`，也不含 `base_url`**；探测只回写 `status` 字符串。✅
- **日志**：`model_catalog.py` 中 `api_key` 仅两处使用——`ChatOpenAI(api_key=...)`（经 `create_chat_model`）与探测头 `Authorization: Bearer {entry.api_key}`（:199）。日志仅 `:207-215` 记 `provider + http_status`，`get_online_models` 的 warning 只记 `provider:model/provider_upper/base_url`，**无任何位置记 `entry` dataclass 整体或 `api_key`**。✅
- **异常信息**：`routes_conversations.py:346-352` 的 `_redact_sensitive` 是既有主动脱敏 helper（含 `api_key/token/secret/bearer` 正则），印证工程有密钥脱敏习惯。代码层无 `str(entry)`/`repr(entry)` 写日志或响应。
  - **残留理论风险（LOW，见清单 L3）**：developer 模式下 `routes_chat.py:189` 等以 `str(error)` 回显异常原文；若 `ChatOpenAI` 构造因 Key 非法抛错且其异常消息回显 Key，则 developer 模式响应可能泄漏。langchain-openai 一般不回显 Key，但建议确认/在 developer 回显前对线上模型错误做脱敏。
- **结论**：响应体/日志无泄漏；异常路径在 developer 模式存在理论边界风险（非阻塞）。✅（细节见 L3）

### 风险点 5：前端 `<optgroup>` 的 `option.value` 仍是真实 id；无 `innerHTML` 拼接模型名；`?v=44` 是否与实际资源一致
- **option.value = 真实 id**：`refreshModelOptions`（`app.js:4043` `opt.value = m.id`）、`refreshKbModelOptions`（`app.js:4428` `opt.value = m.id`）均用真实 id；`renderModelListItem`（`app.js:4177` `li.dataset.model = id`）同样用真实 id。✅
- **无 innerHTML 拼接模型名**：模型库渲染全走 `document.createElement` + `textContent`——`renderModelText`（`app.js:4083/4086`）、徽标 `badge.textContent`（`app.js:4209`）、分组标题 `titleEl.textContent`（`app.js:4273`）。全文 `innerHTML` 出现处（:11/:267/:460/:1230/:2397/:2402/:4386）均为发送按钮标签恢复、消息气泡、候选卡、Markdown 渲染等**与模型名无关**的场景，模型名不进 innerHTML。✅
- **版本号**：`index.html:8/531` 均为 `?v=45`；契约测试 `tests/test_frontend_management_contract.py:68-69` 断言 `v=45`、`tests/test_frontend_model_library_contract.py:14/50-52` `ASSET_VERSION = 45`。**index.html 与两处契约测试版本号完全一致**。
  - 注：task-06 文案写「`?v=43 → ?v=44`」，实际落到 `v=45`（较文案多跳 1）。属文档/实现微差，但**三处实际一致、无回归**，记为 LOW（见清单 L2）。
- **XSS 兜底**：`getModelGroups`（`app.js:4147-4161`）在 `/api/models` 未加载时降级到 `/api/health` 平铺清单，单 local 组，保证零回归。
- **结论**：前端 XSS 底线、optgroup 真实 id、版本号一致性均满足。✅

---

## 二、其它技术维度核验

### 数据模型 / 接口字段层级
- `GET /api/models` 返回 `{current, groups:[{source,label,models:[...]}]}`（`routes_models.py:103-109`），与 spec L104-130 示例字段层级一致；线上项 `capabilities.reasoning_efforts` 恒 `null`（:77），端侧恒 `list(REASONING_EFFORTS)`（:50），与 spec 契约一致。
- `.env` 解析规则（`model_catalog.py:48-130`）严格落地 spec「解析规则」表：去空白、单冒号校验、provider 小写、缺 Key 不注册、缺地址用默认表、协议仅 https/loopback、重复保留首个、`source="online"`。✅

### 模块拆分 / provider 分发
- 新增 `platform/model_catalog.py`（注册表 + 并集校验 + 探测）、`api/routes_models.py`（端点），均在正确层；`create_chat_model` 内部分发（`ollama.py:225-241`），调用点（chat_runner 等）按模块属性解析（task-03 已说明），未改调用点。✅

### is_model_available 并集校验
- `model_catalog.py:141-171`：先查线上注册表（异常隔离），再 `name in set(get_available_models())`（延迟 import 避免循环依赖，异常隔离）。单侧失败互不影响，正确实现本地 ∪ 线上并集。✅

### SSRF 与密钥安全
- `_is_allowed_base_url`（`model_catalog.py:220-227`）仅允许 `https://` 或 loopback `http://`（localhost/127.0.0.1/0.0.0.0/[::1]/::1）。云元数据地址（如 169.254.169.254）被拒。base_url 来自 `.env` 管理员配置，非用户输入。LOW 提示：允许 `0.0.0.0` 略宽（见 L4）。✅（主体成立）

### 重复实现
- grep 确认 `create_chat_model`/`get_online_models`/`get_online_model`/`is_model_available`/`probe_online_model` 各**唯一定义一处**（ollama.py:202 / model_catalog.py:48/133/141/174），无第二套实现。✅

### 依赖与配置
- `config.py:144` 新增 `ONLINE_MODELS = os.getenv("ONLINE_MODELS", "")`（沿用 os.getenv 风格，不 fail-fast）。✅
- `requirements.txt:28` 新增 `langchain-openai>=1.6.2`；`requirements.lock.txt:83-84` 锁定 `langchain-openai==1.6.2` 与 `openai==3.13.0`，与既有 `langchain-core==1.6.2` 共存无冲突（task-02 PoC 已验证）。✅
- `routes.py:9,24` 已 `include_router(routes_models.router)`。✅
- `routes_conversations.py:346-352` 脱敏 helper 存在，密钥处理习惯良好。✅

---

## 三、问题清单（分级）

### CRITICAL
- 无。

### HIGH
- 无。

### MEDIUM
- **M1（分支范围卫生）**：`git diff 79cfa21 --stat` 显示分支除本 spec 清单文件外，还改了 `backend/app/api/routes_tools.py(+40)`、`backend/app/skills/tool_service.py(+96)`、`tests/test_tool_registry.py(+292)`、`tests/test_frontend_skill_tool_contract.py(+113)` 等。经 grep 这些文件**不含** `api_key/create_chat_model/is_model_available/online/ChatOpenAI`，与模型分发/密钥无关（疑为分支上并行的其它特性工作）。它们不影响本 spec-035 技术结论，但建议在合入 main 前单独核算/评审，避免把无关改动随本分支一起合入。
  - 注：`tests/test_frontend_management_contract.py`、`tests/test_frontend_model_library_contract.py` 属本 spec（task-06 明确要求同步/新增），不在 M1 范围。

### LOW
- **L2（版本号文档/实现微差）**：实际版本号升到 `?v=45`（index.html + 两处契约测试一致），而 task-06 文案写「`?v=43 → ?v=44`」。三处实际一致、无回归，仅文档数字未同步，建议 task-07 收口时把 task-06 文案更正为 45。
- **L3（developer 模式异常回显理论风险）**：`routes_chat.py:189` 等 developer 模式以 `str(error)` 回显异常原文；若 `ChatOpenAI` 构造因 Key 问题抛错且异常消息回显 Key，则 developer 响应可能泄漏。langchain-openai 通常不回显 Key。建议：确认其异常不回显 Key，或在 developer 回显前统一经 `_redact_sensitive` 脱敏（低风险、仅 developer 模式）。
- **L4（SSRF 0.0.0.0 略宽）**：`_is_allowed_base_url` 允许 `http://0.0.0.0`。属 loopback 等价，且 base_url 来自 `.env` 管理员配置，实际风险低；如需收紧可仅放行 localhost/127.0.0.1/[::1]。
- **L5（端侧 reasoning_efforts 静态全量）**：`routes_models.py:50` 端侧 `capabilities.reasoning_efforts` 静态为完整 5 档，未做真实探测。与 spec-035 示例契约一致（spec 明确端侧恒 ready、线上恒 null），但相对 spec-026「不臆造能力」原则略宽松；属 spec 已裁决的契约，非缺陷，仅记以备追溯。

### INFO
- **I1（探测总预算起点）**：`routes_models.py:96` 的 `start` 在构建 local 组之前取值；若 Ollama 极慢（local 构建 >15s），online 探测会整体被判超预算而置 `unknown`。属边界情况，符合「15s 总上限、不阻塞页面」承诺，记录备查。

---

## 四、未能端到端验证的部分（环境缺口，非实现缺陷）

本机 Ollama 实际指向局域网 `192.168.31.180:11434` 且当前不可达 → 端侧组为空；且未配任何线上 Key → 线上组为空。因此以下**无法在本评审实测**，需在 Task07 由人工/backend-tester 用真实 Key + 可达 Ollama 补充：
- 端侧组真实渲染与下拉 optgroup 分组展示；
- 线上组 `status=ready/unreachable/unknown` 真实探测与徽标；
- `ChatOpenAI` 真实流式返回、Key 错误时的明确错误文案；
- 跨模块（对话/KB/文章/技能）选中线上模型跑通的真实端到端路径；
- 60s 探测缓存命中、direct 路由对线上模型回退 langchain 的真实行为。

---

## 五、结论与收口建议

**结论：通过。** 五类高风险点全部经 git 基线对照与源码逐行核验通过；数据模型、接口字段层级、模块拆分、provider 分发、并集校验、SSRF/密钥安全、防重复实现、前端 XSS 与版本号一致性均满足 spec 与 task 硬约束。无 CRITICAL/HIGH 阻塞项。

**是否建议 spec 收口**：建议收口。前置条件：
1. 认领并处置 M1（分支范围卫生，确认无关改动单独核算后再合 main）；
2. Task07 收口时顺手修正 L2 文档数字（44 → 45）；
3. 视情况处理 L3/L4 两个低危安全建议（非阻塞）。

环境缺口（第四节）不影响本门禁结论，但须在验收评审（Task07）用真实环境补验证。
