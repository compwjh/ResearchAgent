# Spec 035 验收评审（跨端验收总控 / tester）

- **评审角色**：测试（tester，跨端验收总控）
- **评审类型**：验收评审（SDD 三道门禁 · 第三道）
- **评审日期**：2026-09-13
- **关联 spec**：`docs/sdd/specs/035-online-model-provider.md`（状态：已确认）
- **关联前置门禁**：需求评审（035-requirement-review.md，**通过**）、技术评审（035-tech-review.md，**通过**）、前端回归（035-frontend-regression.md，**184 passed 无回归**）
- **分支**：`feature/spec-035-online-model-provider`（基线 `79cfa21`）
- **结论**：**通过**

> 本评审为跨端总控：汇总单端报告（后端 1702 passed；前端 184 passed）+ 亲跑 mock 集成验收（7/7 PASS）+ 边界与前端契约核对。判定一律基于代码事实（文件路径+行号或代码片段）。**「已验证」与「因环境缺口未验证」严格分离**，mock 通过不写成真实端到端通过。

---

## 一、单端结论汇总（可采信，未重跑）

| 端 | 结论 | 依据 |
|---|---|---|
| 后端全量回归（主会话代跑） | **PASS（含 2 存量失败，非本 spec）** | `env -u PYTHONPATH .venv/bin/python -m pytest tests -q --basetemp=/tmp/s035-final` → **2 failed, 1702 passed, 1 skipped**；2 失败为 `tests/test_chat_route.py::ChatApiTests::test_prompt_never_contains_secrets` 与 `::test_record_generation_called_once_with_route`，已在干净基线 `79cfa21` 用 `git worktree` 验证为**改动前即失败**（存量），不计入本次回归 |
| 前端回归（frontend-tester） | **PASS（184 passed，无回归）** | 035-frontend-regression.md：五项高频回归点（DOM↔CSS 契约、资源版本号 `?v=45`、XSS、降级、option.value 语义）全 PASS |
| spec-035 五个新测试文件（亲跑） | **PASS（71 passed）** | `test_online_model_dispatch / probe / registry / validation / models_api.py` 共 71 用例全绿 |
| 运行时 smoke（架构师已跑） | **PASS（结构无回归）** | 首页 200；`/api/health` 返回 `{"status":"ok","model":"qwen3.8:27b-mlx","models":[],"paper_discovery_enabled":true}`（结构同改动前）；`/api/models` 返回 `current`+`groups[local,online]`；静态资源 `app.js?v=45` |

> 注：工作树含 spec-034 在途改动（`routes_tools.py`/`tool_service.py`/`test_tool_registry.py`/`test_frontend_skill_tool_contract.py`），属其他特性，未归因、未触碰本 spec。

---

## 二、跨端集成验收（亲跑，7/7 PASS）

> 方法：临时脚本 `/tmp/s035_accept.py`，用 **monkeypatch + 假 Key（`sk-test-fake-key-not-real`）** 构造线上配置，**绝未发真实付费请求**（唯一允许的真实请求边界——`max_tokens=1` 最小 chat completion——本次也未触发，因 `/api/models` 默认不探测、探测被 mock）。运行：`.venv/bin/python -m pytest /tmp/s035_accept.py -v` → **7 passed**。

| # | 验收重点 | 结果 | 实测证据 |
|---|---|---|---|
| 1 | 配 `ONLINE_MODELS`+`DEEPSEEK_API_KEY` → 线上模型出现在 `/api/models` 的 online 组；`/api/health` 的 `models` 不受影响 | **PASS** | `routes_models.py:93-109` 返回 `groups[local,online]`；online 组含 `deepseek:deepseek-chat` 且 `capabilities.reasoning_efforts is None`；`/api/health` `models` 仍为 `List[str]`（含本地、不含 `provider:model`）。health 端点零改动（tech-review 风险点2：`git diff 79cfa21 -- routes_system.py` 为空） |
| 2 | `API_KEY` 置空 → 该线上模型不出现（场景 B / Q9） | **PASS** | `model_catalog.py:86-88` 缺 Key 即 `continue` 不注册；脚本 `test_missing_api_key_hides_online_model` 断言 online 组不含 `deepseek:deepseek-chat`、端侧组不受影响 |
| 3 | `create_chat_model("deepseek:deepseek-chat")`→ChatOpenAI；`create_chat_model("qwen3.5:9b")`→ChatOllama 且行为零变化 | **PASS** | `ollama.py:225-241` 命中线上注册表返回 `ChatOpenAI`；`:243-250` `ChatOllama` 分支逐字节不变（`trust_env=False` 三处 + `reasoning` 透传）。脚本 `test_create_chat_model_dispatch` 类型断言通过 |
| 4 | `/api/chat/reasoning-options?model=deepseek:deepseek-chat` → 200 + `supported:false`（不 404，边界 8） | **PASS** | `routes_conversations.py:309-310` 线上模型直接 `return {"supported":False,"efforts":[]}`；脚本 `test_reasoning_options_online_returns_false` 断言 200 + `supported=False, efforts=[]` |
| 5 | 选中线上模型发 `/api/chat` **不再被 400/404 拒绝**（关键接缝） | **PASS** | `routes_chat.py:63-71`：Ollama 不可达时仅当「非线上且非本地」才 502，否则放行。脚本模拟 Ollama down + 线上模型 → `/api/chat` 返回 **200 (text/event-stream)**，未知模型仍 **502**（对照用例通过） |
| 6 | 响应体与日志中**不含 api_key** | **PASS** | 脚本 `test_no_api_key_in_responses`：对 `/api/models`、`/api/health`、`/api/chat/reasoning-options` 断言响应文本不含 `sk-test-fake-key-not-real` 且不含小写 `api_key` 字段。`model_catalog.py:209-233` 探测日志仅记 `provider+http_status`，不记 Key/响应体；`get_online_models` warning 仅记 provider/model/base_url（`:68-115`），无 `api_key` |
| 7 | 前端契约：`option.value` 为真实 id、无 `innerHTML` 拼接模型名、无线上模型时退化为单组端侧 | **PASS** | `app.js:4043`/`4428` `opt.value = m.id`（真实 id）；`innerHTML` 9 处出现（:11/:267/:460/:1230/:2397/:2402/:4386 等）均与模型名无关，模型名走 `textContent`（:4083/:4086/:4209/:4273）;`getModelGroups`(:4147-4169) 无有效 groups 时回退单「端侧模型」组，`renderModelList`(:4255-4261) 全空显示「暂无可用模型」（见 035-frontend-regression.md 第 4-5 节） |

---

## 三、验收场景 A–E 逐条

| 场景 | 期望 | 结论 | 说明 |
|---|---|---|---|
| A：配置正确 → 模型库分两组、线上卡片「已连通」、选中后对话真实返回 | 分组 + ready + 真实对话 | **部分验证（结构 PASS，真实连通/真实对话因环境缺口未验证）** | `/api/models` 双组结构已 mock PASS；`status=ready` 需真实探测（env 缺口 C1）；真实 ChatOpenAI 流式返回需真实 Key（env 缺口 C2） |
| B：`API_KEY` 置空 → 线上模型不出现，端侧不受影响 | 不出现 | **PASS** | 集成验收点 2 |
| C：Key 错误 → 卡片「连接失败」，对话明确错误，不崩溃 | unreachable + 明确错误 | **部分验证（逻辑在代码，真实错误文案因环境缺口未验证）** | `probe_online_model` 非 2xx→`unreachable`（:222）、`/api/models` 仍 200（:93-109）；developer 模式异常回显见技术评审 L3（LOW，非阻塞） |
| D：`ONLINE_MODELS` 非法 → 服务正常启动，非法项跳过记日志 | 跳过+warning | **PASS** | `model_catalog.py:67-72/77-82/113-115` 非法项跳过+warning；`test_online_model_registry.py` 覆盖空值/无冒号/多冒号/空项/重复/大小写/缺Key/未知provider/非https非loopback |
| E：无线上配置 → 模型库退化为改动前形态（仅端侧），无回归 | 降级无回归 | **PASS** | 前端 `getModelGroups` 降级单组端侧 + `/api/models` online 空组；架构师 smoke 实测无线上配置时 `/api/models` 返回 `groups[{local},{online:[]}]`、`/api/health` 结构不变 |

---

## 四、边界 15 条逐条核验

| 边界 | 结论 | 依据 |
|---|---|---|
| 1 未配 ONLINE_MODELS → 线上组空、只显端侧、不报错 | **PASS** | `get_online_models()` 空串返回 `[]`（:56-57）；`/api/models` online 组空数组仍 200 |
| 2 配了缺 API_KEY → 不注册不展示 | **PASS** | 集成点 2；`model_catalog.py:86-88` |
| 3 Key 有但 base_url 不可达 → 展示+unreachable+可选中；调用失败明确错误 | **部分验证** | 展示/可选中：集成点 5（chat 接受线上模型）+ probe 逻辑返回 `unreachable`；真实「明确错误文案」因 env 缺口 C2 未端到端验证（developer 回显见 L3） |
| 4 格式非法 → 跳过+warning、服务正常启动 | **PASS** | `test_online_model_registry.py`；`:67-115` |
| 5 provider 大小写不一致 → 统一小写 | **PASS** | `:75` `provider.lower()`；registry 测试覆盖 |
| 6 线上 id 与本地同名 → `provider:` 前缀隔离、本地优先 | **PASS** | `id=provider:model` 设计天然隔离；`is_model_available` 先查线上再查本地（:174-188） |
| 7 模型库全空 → 「暂无可用模型」 | **PASS**（结构） | `app.js:4255-4261` 空态；Ollama 不可达 `local=[]` 仍 200（:35-38）。真实渲染因 env 缺口 C1 未 e2e |
| 8 reasoning-options 线上 → 200+`supported:false` 不 404 | **PASS** | 集成点 4 |
| 9 探测超时/异常 → unreachable、`/api/models` 仍 200 | **PASS**（逻辑） | `probe_online_model` 异常→`unreachable`（:227-232）；端点恒 200；真实超时行为因 C2 未 e2e |
| 10 60s 内重复打开 → 命中缓存不重复请求 | **PASS**（设计） | `_PROBE_CACHE` TTL 60s（:21-22, :203-207） |
| 11 别名对线上模型生效、value 仍真实 id | **PASS** | `app.js:4043` `opt.value=m.id`；registry 测试 |
| 12 XSS：展示名走 textContent、禁 innerHTML | **PASS** | `app.js` 模型名全 `textContent`；035-frontend-regression 第 3 节 |
| 13 当前模型是线上模型 → 刷新后恢复 | **PASS**（逻辑） | `/api/models` 回写 `current`（`routes_models.py:100-102`）+ 前端 `activeModel` 语义不变（:4306-4307）。真实刷新恢复因 C2 未 e2e |
| 14 .env 删除当前线上模型 → 回退首个可用、不崩溃 | **PASS**（逻辑） | `_resolve_current` 回退首个（:83-90）；registry 测试 |
| 15 OLLAMA_ROUTE=direct + 线上模型 → 强制回退 langchain | **PASS** | `chat_runner.py:156-162` 检测 `get_online_model(model) is not None` 时强制 `resolved="langchain"` |

---

## 五、环境缺口清单（如实记录，非实现缺陷，不得伪造证据）

| 编号 | 缺口 | 影响范围 | 是否阻塞 |
|---|---|---|---|
| C1 | 本机 Ollama 指向局域网 `192.168.31.180:11434` 且当前**不可达** → 端侧模型列表为空 | 端侧组真实渲染、端侧下拉 optgroup、端侧真实对话未能端到端验证 | 否（结构已 mock 验证，属环境限制） |
| C2 | **未配置任何线上 Key** → 线上 `status=ready/unreachable` 真实探测、`ChatOpenAI` 真实流式调用、Key 错误时明确错误文案、跨模块（对话/KB/文章/技能）真实端到端路径、60s 缓存命中、direct 路由真实回退行为均未能端到端验证 | 场景 A 的「已连通/真实对话」、场景 C 的「连接失败+明确错误」、边界 3/7/9/13/14 的真实运行路径 | 否（逻辑已代码核对 + mock 验证；真实环境需人工补验） |

> 声明：本报告所有「PASS（部分验证）/PASS（逻辑）」均已在「已验证」列明是 mock 或代码事实验证，**未**将 mock 通过写成真实端到端通过。真实端到端请在可达 Ollama + 真实 Key 环境下由人工补验（建议场景 A/C + 边界 7/9/13/14）。

---

## 六、阻塞项

**无。** 无 CRITICAL/HIGH 阻塞；技术评审遗留 LOW 项（L2 版本号文档数字 44→45 实际为 45 一致、L3 developer 模式异常回显理论风险、L4 SSRF 0.0.0.0 略宽、L5 端侧 reasoning_efforts 静态全量）均非阻塞，且不影响验收结论。建议收口时酌情处理（见技术评审第五章）。

---

## 七、验收结论

**通过。**

spec-035 在「已验证」维度满足全部硬约束：
- 跨端集成验收 7/7 PASS（mock 构造线上配置，绝无真实付费请求）；
- 后端全量回归 1702 passed（2 个失败为存量，与本 spec 无关）；
- 前端回归 184 passed、五项高频回归点全 PASS；
- 边界 15 条中可验证项全部 PASS，仅真实端到端（C1/C2）因环境缺口未验证，已严格分离、非实现缺陷。

「明确不做」10 条经技术评审核对成立（UI 不填 Key、embedding/rerank 不接线上、不解析 reasoning_content、不改 /api/health、不做负载均衡/计费/限流等、不补端侧 size 元数据、不做搜索排序、不自动探测未声明模型、不改 MODEL_REGISTRY.md、不改 get_available_models 的 List[str] 返回值）。

---

## 八、签字栏

| 角色 | 签字 | 日期 |
|---|---|---|
| 测试（tester / 跨端验收总控） | 已出具本报告 | 2026-09-13 |
| **开发主管（架构师）** | **同意验收，签字放行** | 2026-09-13 |

> 签字说明：验收结论「通过」，跨端集成 7/7 PASS；后端全量 1702 passed（2 个失败经 `git worktree` 干净基线 `79cfa21` 验证为存量）、前端 184 passed。
> 「环境缺口（C1 Ollama 不可达 / C2 未配线上 Key）导致的真实端到端未验证」已如实记录，不作为阻塞项，但**列为上线前必须补验项**（见复盘 `docs/sdd/retro/2026-09-13-spec035-online-model-provider.md`）。
