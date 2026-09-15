# 036 需求评审 — Tool 模块查看内部 Python 代码

| 项 | 内容 |
|---|---|
| **评审者** | architect 子代理（本会话，独立于 spec 编写者视角复核） |
| **角色** | 开发主管（Tech Lead）—— 需求侧评审：问题定义 / 范围划死 / 验收可测性 / 安全隐私 / 与 spec-023 边界 |
| **模型** | 自身（当前执行任务的 Agent，不写死模型代号） |
| **分派方式** | `Task(architect)` |

**被评审对象**

- `docs/sdd/specs/036-tool-source-code-viewer.md`（状态：待确认）
- `docs/sdd/plans/036/README.md`、`task-02-backend-tool-code-api.md`、`task-03-frontend-tool-code-dialog.md`、`task-04-review-regression-acceptance.md`

**评审方式**：不采信文档自述，逐条回源码复核 + 自行实跑 `inspect` 复现 spec 的可行性表。

---

## 0. 复核证据（本次实测，非文档转述）

| 复核项 | 命令 / 位置 | 结果 |
|---|---|---|
| 5 个注册 entry 可解析性 | `env -u PYTHONPATH .venv/bin/python` + `build_default_tool_registry()` + `inspect` | **5/5 成功**，`file:lineno` = 94 / 398 / 994 / 139 / 953，行数 = 71 / 161 / 61 / 112 / 133，体积 2721–7314 B —— **与 spec:27-31 的表逐字一致**（注：行号为当前工作树快照；HEAD 提交时 `kb_ask` 为 952，spec-035 在途改动上移 1 行至 953，验收以接口返回值为准，禁止写死） |
| 解析结果类型 | 同上 | 5/5 `inspect.isfunction == True`（无 module / 无类） |
| `entry` 刻意不暴露 | `backend/app/skills/models.py:45-63` | 注释「用于审计与复用追踪，**不进入 API 响应**」；`to_dict()` 只返回 `name/description/enabled` ✅ spec 背景陈述属实 |
| 5 个 Tool 与 entry | `backend/app/skills/registry.py:21-182` | `search_paper_catalog` / `download_and_import_paper`(=`import_candidate`) / `fetch_paper_detail` / `kb_search` / `kb_ask` ✅ |
| 既有三端点 + 错误体 | `backend/app/api/routes_tools.py:40-64`；`routes_kb.py:178-200` | `_document_error(status, code, message, *, request=..., retryable=False)` → `{error_code,message,retryable,request_id}` ✅ 与 spec:54 一致 |
| 服务与鉴权现状 | `deploy/start.sh:16`；`grep -rl "HTTPBearer\|OAuth2\|api_key\|Authorization" backend/app/` | `HOST` 默认 `127.0.0.1`（**可被环境变量覆盖**）；**无任何鉴权实现**；`routes_kb.py:40` 单用户 `OWNER_ID` |
| 前端既有事实 | `frontend/index.html:448/455/462`；`frontend/app.js:3748/3850/3868/3877` | `#st-tool-list`、`#st-skill-dialog`、`#st-detail-body`、`stState.detailSeq`、`openSkillDetail` 序号 + AbortController ✅ spec/plan 引用的 DOM 与范式均真实存在 |
| 前端契约测试 | `tests/test_frontend_skill_tool_contract.py:1-20` | 静态契约（断言 id 存在 / `textContent` / CSS 作用域），可作为本功能同类断言落点 |

---

## 1. 逐条判定

### 1.1 问题定义与价值 —— 判定：**通过**（1 条 P1 待回填，见 Q-03）

- 需求成立：`models.py:45-51` 的「entry 刻意不进 API 响应」是**真实存在的既定决策**，因此用户「无法知道 Tool 实际执行了什么」这一痛点是真实的，不是伪需求。本 spec 是该决策的**部分反转**（只反转「入口函数源码可读」，不反转「列表/详情接口不暴露 entry」），反转范围可界定。
- 展示范围未滑向整文件/调用链：spec:8-9、:75 明确「非整文件、非调用链」；实测 5 个 entry 解析终点均为**单个函数**（`isfunction=True`），体积 2.7–7.3 KB，无需分页 —— 与 spec:33 的「体积适中」一致。
- **但**：spec 只在「明确不做」里用**文字**承诺「不展示整个模块文件」，**没有任何机械约束**保证解析终点不是模块；实测反例见 Q-03（同一算法遇到模块 entry 会返回整文件 182 行）。

### 1.2 范围划死 —— 判定：**通过（附条件）**（漏 2 条项目级硬约束，见 Q-02）

挡住的东西（spec:73-81）：整文件源码 / 调用链 / 编辑保存热重载 / 执行求值 / 语法高亮与新增依赖 / 改 `ToolEntry.to_dict()` / 把 `entry`·`parameters` 塞进列表接口 / 改启停与状态文件 / 碰 Skill 侧 —— **覆盖到位，且与 task-02:83-87、task-03:63-66 逐条对应，无矛盾。**

漏掉的（必须补）：

1. **资源版本号**：`frontend/index.html:8` 与 `:518` 现为 `styles.css?v=43` / `app.js?v=43`；本功能会改这两个文件，**必须升位**（项目高频回归清单第 2 条）。spec 与 task-03 全文 grep `?v=` / `版本号` **零命中**。
2. **XSS**：`code` 是后端返回的源码文本，写入 `<pre>` 必须走 `textContent`，禁止 `innerHTML`（项目回归清单第 3 条）。spec 与 task-03 全文 grep `textContent` / `innerHTML` **零命中**；`tests/test_frontend_skill_tool_contract.py` 已有同类静态契约，扩一条即可覆盖。
3. 另有一条**该写死而未写死**的边界：**禁用（`enabled=false`）的 Tool 是否仍可查看代码**。spec:67 只说「不读取 `enabled`」，属隐含推论，未写死（见 Q-07）。

### 1.3 验收可测性 —— 判定：**1 条判据与代码事实冲突 + 1 条不可机械判定 → 需修正**（Q-01、Q-10）

- **场景 A（spec:88）可机械判定** ✅：逐 Tool `curl` + `sed -n '{lineno}p'`。
- **场景 C（spec:90-91）可机械判定** ✅：`GET /api/tools` 的字段集合恒等于 `{name,description,enabled}`。
- **场景 A 的「`lineno` 是函数定义行」判据与事实冲突** ❌：实测 `kb_ask` 的 `inspect.getsourcelines` 起始行 = **952，内容是装饰器行 `@router.post("/kb/ask")`**，而 `def kb_ask` 在 **953**（`backend/app/api/routes_kb.py:952-953`，`co_firstlineno=952`）。另 4 个是 `def` 行（94 `def search(` / 398 `def import_candidate(` / 994 `def fetch_paper_detail(` / 139 `def hybrid_search(`，已 `sed` 逐行核对）。→ 若验收者按「第 lineno 行必须含 `def`」判定，`kb_ask` 会被误判为**失败**（假阴性），验收结论不可信。
- 同源措辞错误：spec:46 写「含签名与**装饰器外**的 def 行」，而返回源码**首行就是装饰器行**（实测），措辞与事实相反。
- **场景 B（spec:89 串台）在无头沙箱内不可机械判定** ⚠️：需要浏览器时序（慢响应覆盖新结果）。task-04:41-42 自己已承认「可用静态核对 + 接口验证代替浏览器」，但 spec 把它写成与 A/C 并列的验收场景，**验收报告将无法给出可信判据**。建议显式标注为「不可机械判定项」，并给代理判据（静态断言 `app.js` 的 `openToolCode` 含 `seq` + `AbortController` 且丢弃过期响应 + 可选浏览器复验）。
- 「看起来能测其实测不了」的项就是上述 B；A/C 与 spec:58-71 的其余边界（未知 name、不可解析 entry、无绝对路径、既有接口结构不变）均可机械判定 ✅。

### 1.4 安全 / 隐私 —— 判定：**定级 LOW，3 条必须写死**（Q-04、Q-05、M-05）

**定级依据（据此不做过度设计）**：无鉴权（grep 无命中）、单用户（`routes_kb.py:40` `OWNER_ID`）、默认仅本机（`deploy/start.sh:16` `127.0.0.1`）、功能纯只读（spec:56 不执行/不 eval/不写文件/不改状态）。**不要求**给源码做脱敏、不要求加鉴权、不要求加限流 —— 那对本机单用户应用是过度设计。

必须写死的 3 条：

1. **「只接受注册名」已写死** ✅（spec:42「取自注册表（**不接受用户输入**）」、:52「路径参数 `name`（注册名）」、task-02:51「**不接受外部传入的任意点分路径**」）。实现上不可被绕过：`name` 只作为注册表**精确匹配**的键，不参与路径拼接（`tool_service.py:57-61` 的 `get_tool` 即为 `template.name == name` 的等值遍历）→ 结构上无法遍历到注册表之外的对象，`%2F`、`..`、绝对路径等输入只会落空成 `TOOL_NOT_FOUND`。**但** spec 未显式要求「精确相等、不做前缀/模糊/大小写归一化、不存在时不得回退文件系统查找」→ Q-05（防未来加模糊匹配时静默扩大暴露面）。
2. **`file` 相对路径 + 越界 `TOOL_CODE_UNAVAILABLE` + 不泄漏路径** ✅ 已写死（spec:43、:63-64；task-02:56-59，且明确「不要硬编码 `/Users/...`」）。**缺口**：错误体的 `message` 文案未约束 —— `inspect.getsourcefile()` 天然返回**绝对路径**，若实现把 `str(exc)` 或该路径拼进 `message`，就会经错误体泄漏 `/Users/...`（spec:64 只约束了「越界时不泄漏」，没约束「异常文案不含路径」）→ Q-04。
3. **其它泄漏面评估**：① `code` 为仓库源码原文，若源码内含密钥/口令会一并暴露 —— 本机单用户且用户本就有仓库读权限，**不构成新增风险，不要求脱敏**；② `entry` 暴露内部模块结构是本功能的**目的**，可接受（且已限定取自注册表）；③ **唯一真实新增面**是「本功能把源码可读性从『本机文件系统』提升到『HTTP 接口』」，因此必须写死「不得为此新增/放宽网络暴露与鉴权策略」（Q-09 台账 + M-05）。`HOST` 可被 env 覆盖（`deploy/start.sh:16`）这一事实应由 spec 记一句前提说明，而不是靠假设。

**并发 / 事务 / 外键**：本功能无 DB 读写、无状态写入、无迁移（spec:37「不新增持久化字段」、:80「不改状态文件」）→ **不适用**，spec 未提是合理的，不是漏项。仅需注意「每请求实时解析、无缓存」不会引入并发问题（已 import 的模块走 `sys.modules`，代价可忽略），且 task-04:70 已明确「以实时解析为准，不写死行号」✅。

### 1.5 与 spec-023 的边界 —— 判定：**通过**

- spec:67-68、:79-81 明确：不改既有三接口响应结构、不改 `ToolEntry.to_dict()`、不改启停逻辑与状态文件、不碰 Skill 侧任何行为与弹窗；task-02:44-45、task-03:34、:65-66 逐条复述一致 → **不会被误解为要改 Skill 侧或启停逻辑**。
- `tool_service.py` 属 spec-023 资产，本 spec 只允许**新增** `get_tool_entry(name)`，且 task-02:47-49 明确「**不要**把 `entry` 塞进既有 `get_tool()` 的返回」→ 属纯增量，不构成对 023 冻结决策（Q1–Q10）的修改 ✅。
- 附注（非本 spec 缺陷，建议顺手更正）：`docs/sdd/specs/023-skill-tool-management.md:22` 术语表仍写 Tool「当前注册表 **4 个**」，实际已是 **5 个**（`registry.py:21-182`，`fetch_paper_detail` 由 spec-032.1 加入）。036 的读者若对照 023 会困惑。

### 1.6 执行配置 —— 判定：**通过**（7 项核对全过）

| 核对项 | 结果 |
|---|---|
| 角色行齐全 | ✅ 架构师 / 产品经理 / 开发主管 / 后端开发 / 前端开发 / 后端评审 / 前端评审 / 后端回归 / 前端回归 / 验收总控（本 spec 同时触及前后端，两端四角色齐全，无缺行） |
| 架构师行写「自身」 | ✅ spec:97「自身（当前执行任务的 Agent，不写死模型代号）」 |
| 不适用角色写「不适用（原因）」 | ✅ spec:98 产品经理「不适用（功能边界单一，产品步骤由架构师代拟）」 |
| 模型名均来自 `MODEL_REGISTRY.md` | ✅ `qwen3.8:27b-mlx`（`:26`）、`qwen3.5:9b`（`:33`）；**未误用**已弃用的 `qwen3.8:27b`（`:27`）—— 模板弃用名问题在本 spec 已修正 |
| 与 task-04 分派表一致 | ✅ `task-04:49-52` 的 `Task(architect)` / `*-reviewer` / `*-tester` / `tester` 与 spec 表逐行对应 |
| 与近期 spec 同构 | ✅ 与 `specs/033-...:176-184` 同格式（含「不适用」写法），无自创字段 |

### 1.7 职责分离 —— 判定：**通过（附意见）**（1 处机制重复，Q-08）

- spec 只写做什么 / 边界 / 验收（spec:35-91）；实施细节（import 拆分算法、路径校验、`st-code-*` DOM id、`secondary-button` class、`finally` 恢复按钮态）全部在 task-02:47-71、task-03:36-51 ✅。
- **spec 与 task 无矛盾**：端点路径、6 个响应字段、2 个错误码与 `retryable=false`、`language` 固定值 —— 三处（spec:39-55 / task-02:24-38 / task-03:13-14）完全一致 ✅。
- 重复项：spec:71 与 task-03:44-45 都写「自增序号 + `AbortController`」这一**实现机制**；spec 层宜只保留「连续切换无串台」的**行为判据**（见 Q-08，P2）。

---

## 2. 问题清单

| 级别 | 位置 | 问题 | 建议 |
|---|---|---|---|
| **P1** | spec:60、spec:46 | `lineno` 判据与代码事实冲突：`kb_ask` 的 `lineno=952` 是**装饰器行**，`def kb_ask` 在 953（实测）。按「第 lineno 行是定义行」判定会把 `kb_ask` 误判失败；spec:46「装饰器外的 def 行」措辞与返回内容（首行即装饰器行）相反 | 判据改为「`lineno == inspect.getsourcelines(obj)[1]`；机械判定口径 = 第 lineno 行是 `def <name>`，**或** 是装饰器行且其后首个非装饰器行是 `def <name>`」；spec:46 改为「含装饰器行与签名（`inspect.getsource` 原文）」 |
| **P1** | spec:58-71（边界）、task-03 全篇 | 前端两条项目级硬约束缺失：① 改 `app.js`/`styles.css` 必须升 `index.html` 的 `?v=N`（现为 `?v=43`，`index.html:8,518`）；② `code` 必须用 `textContent` 渲染，禁止 `innerHTML` 拼接。全文 grep 零命中 | spec 边界各补一条；task-03 步骤补「升 `?v=43→44`」与「`textContent`」；扩 `tests/test_frontend_skill_tool_contract.py`（断言新弹窗 id 存在 + `st-code-body` 走 `textContent`） |
| **P1** | spec:46、:73-75；task-02:52-53 | 「不展示整个模块文件」只有文字承诺，无机械约束。实测反例：entry 为模块路径时，「从长到短 import」得到 `attr=[]`、`ismodule=True`，`inspect.getsource` 返回**整文件 182 行** | spec 边界新增：解析终点必须满足 `inspect.isfunction(obj) or inspect.ismethod(obj)` **且属性链非空**，否则 `TOOL_CODE_UNAVAILABLE`；task-02 步骤 2 同步修正（不得以模块对象为终点） |
| **P1** | spec:52、:64；task-02:63 | 错误 `message` 文案未约束 → 存在经错误体泄漏绝对路径的面（`inspect.getsourcefile` 返回绝对路径，`str(exc)` 亦可能含路径） | `TOOL_CODE_UNAVAILABLE` 的 `message` 为**固定文案**（如「该 Tool 的源码不可用」），禁止拼接 `str(exc)`/绝对路径/entry 之外的内部路径；异常详情只进服务端日志，不返回 stack |
| **P2** | spec:42、:52 | 未显式写死 `name` 匹配语义 | 补一条边界：「`name` 与注册名**精确相等**匹配；不做前缀/模糊/大小写归一化；不存在时**不得**回退文件系统查找或模糊兜底」 |
| **P2** | spec:45 | `language` 固定 `"python"` 但「明确不做」（:78）已排除语法高亮、前端不消费 → 冗余字段（YAGNI） | 删除该字段，或在 spec 注明保留理由（为将来高亮预留需写明，否则视为越界设计） |
| **P2** | spec:67 | 未显式写「**禁用（`enabled=false`）的 Tool 同样可查看代码**」 | 明写一条，防实现侧自作主张加 gating（只读审计视图不应受启停影响） |
| **P2** | spec:71 vs task-03:44-45 | 实现机制（seq + `AbortController`）在 spec 与 task 重复 | spec 只留行为判据「连续切换不同 Tool 无串台」，机制下沉 task-03 |
| **P2** | spec:89（场景 B）；`docs/sdd/spec-status-changelog.md:259`；`specs/023-...:22` | ① 场景 B 在无头沙箱内不可机械判定；② spec 台账**无 036 条目**且 035 条目明确写「036 空缺」，与现状矛盾；③ 023 术语表仍写 Tool「4 个」（实为 5 个） | ① 场景 B 标注「不可机械判定」+ 给代理判据；② 台账补登「036 新建 → 待确认」；③ 023 的 4→5 顺手更正 |
| **INFO** | spec:9；`frontend/styles.css:2312-2366` | 「复用 Skill 详情弹窗样式」经复核**可行**：`.st-detail-dialog` 系列样式均以该 class 为祖先选择器，新弹窗带同类名即命中；若新增 class，须确认 `styles.css` 有对应规则（项目回归清单第 1 条） | 保持复用；新增 class 时同步补 CSS |

---

## 3. Review Summary

| # | 评审项 | 判定 | 关键依据 | 阻塞 |
|---|---|---|---|---|
| 1 | 问题定义与价值 | 通过 | `models.py:45-51` 反转点真实；实测 5/5 解析为单函数、2.7–7.3 KB；「只到入口函数」文字承诺到位 | 否 |
| 2 | 范围划死 | 通过（附条件） | spec:73-81 挡住整文件/调用链/编辑/执行/高亮/改 to_dict/改启停/碰 Skill ✅；漏 `?v=N` 与 `textContent` 两条硬约束 | **是（Q-02）** |
| 3 | 验收可测性 | 需修正 | 场景 A 的 `lineno` 判据与 `kb_ask` 事实冲突（952 是装饰器行、def 在 953）；场景 B 不可机械判定 | **是（Q-01、Q-10）** |
| 4 | 安全 / 隐私 | 通过（附条件） | 只接受注册名 ✅（等值匹配、不参与路径拼接，不可绕过）；`file` 相对 + 越界兜底 ✅；缺口 = 错误 `message` 可能泄漏绝对路径；定级 LOW（本机单用户、无鉴权、只读），不做过度设计 | **是（Q-04）** |
| 5 | 与 spec-023 边界 | 通过 | spec:67-68、:79-81 + task-02:44-49 明确不改既有三接口/to_dict/启停/Skill 侧；`get_tool_entry` 为纯增量 | 否 |
| 6 | 执行配置 | 通过 | 7 项核对全过；模型名全部命中 `MODEL_REGISTRY.md:26,33`，未误用弃用名 `qwen3.8:27b`（`:27`） | 否 |
| 7 | 职责分离 | 通过（附意见） | 实施细节下沉 task；spec/task 端点·字段·错误码三处完全一致；1 处机制重复（P2） | 否 |

- **P0：0 条**
- **P1：4 条**（Q-01 `lineno` 判据、Q-02 前端两条硬约束、Q-03 模块解析无机械约束、Q-04 错误文案泄漏面）
- **P2：5 条**（Q-05 名称匹配语义、Q-06 `language` 冗余、Q-07 禁用 Tool 可查看、Q-08 机制重复、Q-09 台账/023 计数）
- **INFO：1 条**（Q-11 弹窗样式复用可行性已复核）

---

## 4. Verdict

> **通过（附意见）** —— P0 = 0，需求方向与边界成立，可进入技术评审；但 **4 条 P1 必须在 spec 回填后、Task02 开工前关闭**（见第 5 节强制约束清单 M-01～M-04）。P2 建议在回填时一并处理，不单独阻塞。

**阻塞项（必须回填后方可开工）**

1. **M-01**：修正 `lineno` 判据与 spec:46 措辞（`kb_ask` 的 952 是装饰器行，实测）。
2. **M-02**：补前端 `?v=N` 升位与 `textContent`（禁 `innerHTML`）两条边界 + 静态契约断言。
3. **M-03**：补「解析终点必须是函数/方法且属性链非空」的机械约束（封死「整模块文件」）。
4. **M-04**：补「`TOOL_CODE_UNAVAILABLE` 的 `message` 为固定文案，不得含 `str(exc)`/绝对路径」。

**放行口径**：spec 状态由「待确认」转「已确认」前，须在 spec 内落一份「需求评审意见回填记录」；回填后由架构师（主会话）复检 M-01～M-04 逐条落地，再进技术评审门禁。

---

## 5. 强制约束清单（下游角色必守）

> 本清单为「通过（附意见）」的沉淀。回填进 spec 后，`backend-dev` / `frontend-dev` / `*-reviewer` / `*-tester` / `tester` 均须逐条遵守；`*-reviewer` 与技术评审须逐条给 PASS/FAIL。

**M-01（`lineno` 语义，P1）** — `lineno` 定义为 `inspect.getsourcelines(obj)[1]`（1-based 源码块首行）。**对带装饰器的函数，该行是装饰器行**（实证：`backend/app/api/routes_kb.py:952` = `@router.post("/kb/ask")`，`def kb_ask` 在 953）。验收判据必须是「第 `lineno` 行是 `def <name>`，**或** 是装饰器行且其后首个非装饰器行是 `def <name>`」；**禁止**使用「第 `lineno` 行必须含 `def`」这一判据。spec:46 的 `code` 定义改为「含装饰器行与签名的源码原文」。

**M-02（前端项目级硬约束，P1）** — ① 改动 `frontend/app.js` 或 `frontend/styles.css` 后，必须把 `frontend/index.html` 的 `?v=N` 从 **43 升到 44**（`index.html:8` 与 `:518` 两处同步）；② 源码文本（`code`）与 `entry`/`file:lineno` 一律用 `textContent` 写入，**禁止** `innerHTML`/模板字符串拼接；③ 新增 DOM id 必须同时扩 `tests/test_frontend_skill_tool_contract.py` 静态断言（id 存在 + `textContent` 用法 + 无 `innerHTML`）；④ 新增 class 必须在 `frontend/styles.css` 有对应规则（项目回归清单第 1、2、3 条）。

**M-03（解析终点类型约束，P1）** — 解析函数必须保证：属性链**非空** 且 解析结果满足 `inspect.isfunction(obj) or inspect.ismethod(obj)`；否则返回 `TOOL_CODE_UNAVAILABLE`。**禁止**以模块对象（`inspect.ismodule`）或类对象作为解析终点 —— 否则 `inspect.getsource` 会返回整个文件/整个类体，直接违反 spec「不展示整个模块文件」。task-02 步骤 2 的「从长到短尝试 import」算法须据此修正（不得让最长可导入模块成为终点）。

**M-04（错误文案，P1）** — `TOOL_CODE_UNAVAILABLE` 的 `message` 必须是**固定文案**；**禁止**拼接 `str(exc)`、异常 `repr`、绝对路径、`entry` 之外的任何内部路径；异常详情（含 stack）只进服务端日志。所有异常必须收敛为 `TOOL_NOT_FOUND` / `TOOL_CODE_UNAVAILABLE` 两类 404，**不得抛 500**（spec:66 已有要求，此处补文案面）。

**M-05（暴露面冻结，P1→实施约束）** — 本功能的前提是「`127.0.0.1` 本机单用户、无鉴权」；**禁止**为本次改动新增/放宽网络暴露（如 `HOST=0.0.0.0`）或改动鉴权策略，也不得改 `deploy/start.sh` 的默认绑定。spec 应记一句该前提，供后续部署变更时重新评估。

**M-06（名称匹配语义，P2）** — `{name}` 必须与注册名**精确相等**匹配；不做前缀/模糊/大小写归一化；不存在时**不得**回退文件系统查找或模糊兜底，直接 `TOOL_NOT_FOUND`。`entry` 只从注册表读取，**任何情况下不得接受请求方传入的点分路径**（含 query/body/header 变体）。

**M-07（只读与回归冻结，P2）** — 不执行/不 eval/不写文件/不改注册表与状态文件；`ToolEntry.to_dict()` 输出与既有三端点（`GET /api/tools`、`GET /api/tools/{name}`、`PATCH /api/tools/{name}`）响应结构**逐字不变**（须有测试断言）；禁用（`enabled=false`）的 Tool **同样可查看代码**；不加缓存（实时解析，避免行号漂移）。

**M-08（文档一致性，P2）** — 回填时同步：① `docs/sdd/spec-status-changelog.md` 补登「036 新建 → 待确认」（该文件 `:259` 现写「036 空缺」，与现状矛盾）；② `docs/sdd/specs/023-skill-tool-management.md:22` 术语表 Tool 计数 `4 → 5`；③ 场景 B 在 spec 内标注「无头沙箱内不可机械判定」并给出代理判据。

---

## 6. 评审边界声明

- 本次评审**只产出本文件**，**未修改任何代码文件**（未改 `backend/**`、`frontend/**`、`tests/**`），也未修改被评审的 spec 与 plan 文件（意见以本文件形式提出，回填由 spec 编写者执行）。
- **未使用** `git checkout` / `git restore` / `git stash` / `git reset` 等任何可能丢弃他人改动的命令；未做 `git commit` / `git push`。
- 工作区中其他角色的在途改动（如 `backend/app/platform/*`、`.codebuddy/agents/*`）与本评审无关，未触碰。
- 本次复核的实测命令均为只读（`inspect` 解析、`sed` 查看、`grep`），未写入任何数据文件。
