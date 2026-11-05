# 收口评审总控结论 — spec 011 / 036 / 039-test-completion-and-infra

| 项 | 内容 |
|---|---|
| **评审者** | `architect` 子代理（评审 / 签字 / 合并裁决角色） |
| **评审时间** | 2026-11-05（Asia/Shanghai） |
| **基线** | `main` @ `546072e5`，运行时 `http://127.0.0.1:8000/`（`/api/health` 200） |
| **运行时证据** | `docs/sdd/reviews/011-036-039-closure-live-e2e.md`（主会话落盘，仅证据、非评审） |
| **收口口径** | `docs/sdd/00-sdd-spec-template.md:99`（§规范化流程 6 收口）+ `:118`（收口自检）；`regression-guard` 项目增补 |
| **执行边界** | 本轮为**历史已完成实现的状态补录收口**（实现代码 2026-08～09 完成且此后未变），按「Task 收口只跑受影响领域测试」执行，**不重跑全量回归**；不执行 `git add/commit/merge/push`；不改任何业务代码；不改三个 spec 状态行 / 评审记录段 / 变更日志 / `spec-status-changelog.md`（由主会话统一回填） |

---

## 〇、总裁决

| Spec | 名称 | 裁决 | 一句话理由 |
|---|---|---|---|
| **011** | 本地个人论文知识库（RAG） | **同意转 `已完成`** | 需求评审本轮补做并通过、验收签字本轮完成，三份评审齐备，真实 E2E 在案 |
| **036** | Tool 模块查看内部 Python 代码 | **同意转 `已完成`** | 证据与原评审已完整，缺口纯为 spec 文档未同步；本轮 7/7 实时 200 复核通过 |
| **039-test-completion-and-infra** | 测试补全与测试基建整理 | **有条件同意转 `已完成`**（附 3 项强制条件，见 §3.4） | T1/T2/T3/T5 已验证达标；**T4 明示未完成**、且在 `plans/039/` 下无 task 文件与 spec 级评审；另存在**编号撞号**必须一并纠正 |

**P0（阻塞收口）：0 项。**
**P1（须在本轮收口动作中一并处置）：5 项**（详见 §4）。
**P2（记录待后续改善，不阻塞）：6 项。**

---

## 一、DoD 核对总表

图例：✅ 通过｜⚠️ 有条件/需澄清｜❌ 未满足｜— 不适用

| DoD 项 | 011 | 036 | 039-test-infra |
|---|---|---|---|
| **① 三份评审（需求/技术/验收）真实落盘且结论为「通过」** | ⚠️→✅ 需求 `011-requirement-review.md`（本轮补，**通过**）；技术 `011-tech-review.md`（通过，R1–R9）；验收 `011-acceptance-review.md`（通过，V1–V21） | ⚠️ 需求 `036-requirement-review.md`（通过）；技术 `036-backend-tech-review.md` + `036-frontend-tech-review.md`（通过）；验收 `036-acceptance-review.md`（通过）。**但 spec `:166/:167` 仍写「待评审（未执行）」，文件名亦不符合模板 `NNN-tech-review` 约定** | ⚠️ `039-requirement-review.md` / `039-tech-review.md` / `039-acceptance-review.md` 三份**全部属于另一个 spec**（`039-api-e2e-manual-acceptance-protocol`），其中前两份打回/BLOCKED；test-infra spec **本身无任何 spec 级评审** |
| **② 验收签字** | ✅ 本轮完成（2026-11-05，开发主管 = `architect`，签字放行） | ✅ 已有双签（验收总控 PASS 2026-09-13 + tech-lead 签字放行 2026-09-13） | ❌ 无 spec 级验收签字（`039-acceptance-review.md` 是协议 spec 的） |
| **③ 变更日志（spec 内 Changelog）** | ✅ 完整（`spec:189-219`，含全部偏差留痕） | ✅ 完整（`spec:171-176`，含需求评审回填） | ⚠️ 仅执行记录（`spec:92-99`、`:126-137`），**无「已完成」收口条目** |
| **④ 状态台账（`spec-status-changelog.md`）** | ❌ **无 011 条目**（需主会话追加：`实施中` → `已完成`，2026-11-05） | ✅ 已有（`:397`，2026-09-13「已确认 → 已完成」） | ❌ **无 test-infra 条目**；仅 `:516` 记录 `待确认 → 已确认`。注：`:465-469` 的 039 条目属协议 spec，**不可混用** |
| **⑤ 引用路径真实存在** | ✅ 已逐个 `Read` 校验：spec / tech-review / acceptance-review / retro / 证据 / SSE 产物均存在 | ✅ 已校验：4 份评审 + `plans/036/task-02..04` + `retro/2026-09-13-spec-036-tool-source-code-viewer.md` 均存在 | ⚠️ `plans/039/README.md` 是**协议 spec** 的任务索引（`:3` 状态 `阻塞`），test-infra spec 的验证材料只有 `plans/039-test-infra-validation.md`；**引用易被误读为「039 阻塞」** |
| **⑥ 复盘** | ✅ `retro/2026-08-30-spec-011-process-retro.md` | ✅ `retro/2026-09-13-spec-036-tool-source-code-viewer.md` | ❌ **无复盘文档**；且全程按用户授权跳过需求/技术评审门禁（`spec:124`「本 spec 经用户授权直接执行，跳过『待确认 → 评审』门禁」） |
| **⑦ 当前部署版本真实 E2E** | ✅ 自然语言 `POST /api/kb/ask` → HTTP 200 SSE、3 条真实引用、`document_id=d4dfd2a620384ad5bece27320661f8f0`、`chunk_id=747530eb-08c9-590d-b1ba-a625cbec0443`、终态 `done`、产物 `artifacts/spec011-kb-ask-e2e-20261105.sse` | ✅ `GET /api/tools/{name}/code` **7/7 实时 HTTP 200**，`code` 非空、`file` 为仓库相对路径（详见 §2） | ✅ `check_test_layout.py` exit 0 / `check_test_naming.py` exit 0 / `pytest --collect-only` **3875 collected, 0 errors** |
| **⑧ 未越出「明确不做」** | ✅ 边界闭合，两处范围变更均留删除线+日期+原因 | ✅ M-01～M-08 全部落地；暴露面前提 M-05 未被放宽 | ⚠️ T4（补具体用例）**未做**，属 spec 自身验收项之一 |

---

## 二、036 复核（只复核，不改 spec）

### 2.1 证据复核结果

| 复核项 | 结果 |
|---|---|
| `GET /api/tools` 返回 Tool 数 | 7 个：`paper_discovery`、`search_paper_catalog`、`download_and_import_paper`、`fetch_paper_detail`、`kb_search`、`kb_ask`、`session_search` |
| `GET /api/tools/{name}/code` 逐一实时请求 | **7/7 HTTP 200**；`code` 均非空（684 / 4003 / 9887 / 2721 / 4207 / 5872 / 1763 字节）；`file` 均为仓库相对路径（`backend/app/...`） |
| 行号判据（M-01） | 以接口返回值为准，不写死行号 —— 与 `036-acceptance-review.md` §3「952→953 漂移已修正为动态取值」口径一致 |
| 路径泄漏（M-04） | 证据文档 §2 未出现 `/Users`、`/private`、`.venv`；`code` 字段为源码正文 |
| 结论 | **复核通过**。spec `:5`（`已确认`）与 `:167`（验收评审「待评审（未执行）」）属**文档不同步**，非实现缺口 |

### 2.2 裁决

**同意转 `已完成`。** 实现、三评审、双签、变更日志、复盘、台账（`spec-status-changelog.md:397`）、真实 E2E **七项齐备**，唯一缺口是 spec 自身的状态行与评审记录段未同步 —— 属纯文档同步，由主会话回填。

### 2.3 须在回填时一并纠正的表述（P1-2）

- spec `:167` 验收评审写「待评审（未执行）」，而同文件 `:165` 需求评审已写真实结论、`036-acceptance-review.md` 已存在且双签。回填时应写为：`036-acceptance-review.md`（**通过**；场景 A/B/C 全达成，7/7 实时 200，验收总控 PASS + tech-lead 签字放行，2026-09-13）。
- spec `:166` 技术评审写「待评审（未执行）」，实际存在**两份**分区评审 `036-backend-tech-review.md`、`036-frontend-tech-review.md`（均通过）。回填时应指明这两份文件名（文件名不含 `tech-review` 标准串，须显式写出，否则后续读者按模板名找不到）。
- **不得**把 036 的技术/验收评审描述为「独立子代理评审」：`036-acceptance-review.md:5` 明写 `tester` 分派连续 `502 ENOTFOUND`/`429` 失败，改为主会话非采信式复核。此为既有偏差，保留如实表述。

---

## 三、039-test-completion-and-infra 裁决（重点）

### 3.1 编号撞号（P1-3，必须在收口时纠正）

`docs/sdd/specs/` 下存在**两个 039**：

| 文件 | 主题 | 当前状态 | 评审归属 |
|---|---|---|---|
| `039-api-e2e-manual-acceptance-protocol.md` | 真实 API E2E 与人工验收协议 | 见 `spec-status-changelog.md:465-469`（`待人工验收`） | `039-requirement-review.md`（通过范围定义/交付阻塞）、`039-tech-review.md`（BLOCKED 打回）、`039-acceptance-review.md`（先 BLOCKED → 后 READY_FOR_USER） |
| `039-test-completion-and-infra.md` | **测试补全与测试基建整理**（本轮对象） | `已确认`（`spec:5`） | **无** |

`plans/039/` 目录与 `plans/039/README.md`（`:3` 状态 `阻塞`）**属于协议 spec**，不是 test-infra spec 的任务索引。

**风险**：若主会话只写「039 已转 `已完成`」，任何按 `NNN-*.md` 检索的读者都会把 `039-acceptance-review.md`（协议 spec 的）误读为 test-infra 的验收，而该文件正文含 `BLOCKED／不通过` 字样 —— 会把一个真实打回结论嫁接到已完成的 spec 上。

**要求**：`spec-status-changelog.md` 的新条目**必须书写 spec 全名**「Spec 039 测试补全与测试基建整理」，不得只写「039」；并在条目中显式声明「本条目与 `specs/039-api-e2e-manual-acceptance-protocol.md` 为不同 spec，二者编号相撞，评审文件命名归属以后者为准」。

### 3.2 已达标项（证据充分）

- **T1 分类目录**：7 个功能子目录（`paper_discovery` / `research` / `kb` / `memory` / `conversation` / `frontend` / `system`）+ 各 `__init__.py` 功能说明；`fixtures/`、`runtime/` 保留。✅
- **T2 违规改名**：42 个含 `specNNN` 文件 + 后续 18 个 basename 全部去除 `spec/task` 数字，`git mv` 保留历史。✅
- **T3 其余分类**：按功能归类，原名保留。✅
- **T5 收集数不变**：重组前后 `2613 collected` 无导入错误（`spec:99`）；当前 `main` **3875 collected / 0 errors**。✅
- **命名门禁固化**：`.codebuddy/skills/test-naming/SKILL.md` + `scripts/check_test_naming.py`（退出 0）+ `scripts/check_test_layout.py`（退出 0）。✅ **这是本 spec 最有价值的产出**：把此前「只在对话里口头要求、从未落盘」的规则变成可执行门禁，从根上消除复发。
- **阻塞已消解**：`plans/039-test-infra-validation.md:23-24` 的全量 `2057 collected, 37 errors` 已定位为当时 `chore/update-archify` 隔离基线的 `ModuleNotFoundError: ...source_registry`；当前 `main` 0 errors。✅ 该报告 `:26-32` 已如实写「不能修改 `backend/**` 绕过」，做法正确。

### 3.3 未达标项（如实记录，不得掩盖）

| 项 | 事实 | 影响 |
|---|---|---|
| **T4 未完成** | `spec:89` T4「补具体用例缺口」= `⏸ 待做`；`:108` 注明 A 类需先实现后端、建议并入 spec032 收口 | 违反 spec 自身验收方式 `:115`「T4 补齐的用例通过」 |
| **无 spec 级评审** | 三份 `039-*-review.md` 均为协议 spec；test-infra spec 没有需求/技术/验收评审 | 违反模板 `:99`「三份评审真实落盘」 |
| **无验收签字** | 无对应验收报告 | 违反 `AGENTS.md` 硬规则第 6 条精神 |
| **无复盘** | `retro/` 下无 039 test-infra 复盘 | 违反模板 `:118` 收口自检「复盘已落盘」 |
| **门禁跳过有授权** | `spec:5` 与 `:124` 明写「2026-09-19 用户授权『直接进行文件的改名和相关 skill 的沉淀，不需要评审』」「跳过『待确认 → 评审』门禁」 | 门禁跳过**有用户授权依据，不记为违规**；但授权只覆盖「改名 + skill 沉淀」，**不覆盖 T4 的功能用例补全** |

### 3.4 裁决：**有条件同意转 `已完成`**

同意转 `已完成` 的依据：本 spec 的**核心交付**（测试分类重组 + 命名规则沉淀为门禁 + 收集数一致性验证）已全部完成并经当前部署版本实测（3875/0 errors）。

**强制条件（三项，缺一不予放行）**：

1. **C1｜T4 显式外置**：spec 状态转 `已完成` 时，必须在状态行或 pending 段写明「T4『补具体用例缺口』**不在本 spec 收口范围**，A 类随 spec032 收口、B 类另立任务」；**不得**表述为「T4 已完成」或省略不提。同时把 `:115` 验收方式的「T4 补齐的用例通过」标注为「（T4 已外置，本项不适用）」。
2. **C2｜评审与复盘补齐或显式记缺**：因授权跳过门禁，**不要求补做实现前评审**；但 `spec-status-changelog.md` 新条目必须写明「本 spec 经用户授权跳过需求/技术评审门禁（`spec:5`、`:124`），未产出 spec 级评审报告与复盘，属**受权例外**，不作为其他 spec 的先例」，并把评审记录指向 `plans/039-test-infra-validation.md` 作为唯一验证材料。
3. **C3｜撞号纠正**：按 §3.1 要求，台账条目书写 spec 全名并显式声明与协议 spec 编号相撞。

**若拒绝接受 C1–C3**：裁决改为 **打回**，spec 保持 `已确认`（或转 `阻塞`），理由是「T4 未完成 + 无 spec 级评审 + 无复盘，不足以支撑『已完成』」。本评审倾向接受条件后转完成——因为已完成的**门禁固化与分类重组**是真实且有价值的交付，且 T4 本身在 spec 内已标注「建议并入 spec032 收口」，属预先声明的范围外延。

---

## 四、P0 / P1 清单

### P0（阻塞收口）— **0 项**

### P1（须在本轮收口动作中处置）

| # | 所属 | 项 | 处置要求 |
|---|---|---|---|
| **P1-1** | 011 | 历史偏差：`Task(tech-lead)` 分派 aborted 后**未重试**，需求评审被跳过（实现前未执行）；`tester` 未分派、验收由架构师代行；`junior-dev` 未分派、编码由架构师直接完成 | **不得抹除、不得改写**。spec `:178-185`、`:152-155`、`:193-200` 三处留痕保留原样；本轮需求评审已注明「事后评审，不能替代实现前拦截」。台账条目须保留「历史代行仍属既有偏差」的表述 |
| **P1-2** | 036 | spec `:166`/`:167` 评审记录写「待评审（未执行）」，与实际已通过的两份技术评审 + 已双签的验收评审矛盾 | 主会话回填真实结论并写明实际文件名（`036-backend-tech-review.md`、`036-frontend-tech-review.md`、`036-acceptance-review.md`） |
| **P1-3** | 039 | **编号撞号**：两个 spec 共用 `039`，`039-*-review.md` 三份全部属于协议 spec | 台账条目书写 spec 全名 + 显式声明撞号；不得用「039 验收通过」概括 |
| **P1-4** | 039 | T4 未完成（`spec:89` `⏸ 待做`），且 spec 自身验收方式 `:115` 含「T4 补齐的用例通过」 | 按 §3.4 **C1** 显式外置，不得声称全 DoD 达成 |
| **P1-5** | 039 | 无 spec 级评审、无验收签字、无复盘（门禁经用户授权跳过） | 按 §3.4 **C2** 在台账显式记为受权例外，指向 `plans/039-test-infra-validation.md` 为唯一验证材料 |

### P2（记录，不阻塞）

| # | 所属 | 项 |
|---|---|---|
| P2-1 | 011 | `P19`「流式输出过程中页面不卡顿」无量化判据，属主观项；建议后续补帧间隔指标或显式标注为人工目视项 |
| P2-2 | 011 | 「不做异步索引与进度条」如后续追加，须**新建 spec 编号**，不得回填 011 |
| P2-3 | 011 | reranker 仍未启用（`RERANKER_MODEL` 为空，降级 RRF 直出）；Qdrant 单进程约束建议在 `deploy/start.sh` 加注释警示（`011-acceptance-review.md` §三.1/§三.2 已提出，至今未落地） |
| P2-4 | 036 | 行号随源码漂移，验收以接口返回值为准的口径已写入，但 spec `:29-33` 的可行性表仍留着历史行号（94/398/994/139/952→953），后续易被误当基线 |
| P2-5 | 039 | `plans/039/` 目录归属协议 spec，test-infra 的材料散落在 `plans/039-test-infra-validation.md`；建议后续把 test-infra 材料移入独立目录（如 `plans/039b/`）以消除歧义 |
| P2-6 | 全局 | 三个 spec 的收口均无**独立**评审（011 代行、036 主会话代行、039 受权跳过）；这是本项目连续出现三次的系统性偏差，建议在流程层补「收口签字人不得是实现者」的硬约束 |

---

## 五、历史偏差如实说明（不抹除、不美化）

1. **011**：`Task(tech-lead)` 分派调用 aborted，**未按规定重试或换模型**即由架构师补位 → 技术评审为代行；需求评审直接被跳过，直到 2026-11-05 才补。`tester` 从未分派，验收报告为「实现者自验」。`junior-dev` 仅在 Markdown 渲染一项被分派且回传被截断，编码最终由架构师完成。**这些偏差在本轮签字后依然存在，签字只解除「签字栏为空」这一阻塞，不追认独立性。**
2. **036**：`tester` 子代理分派连续遇 `502 ENOTFOUND` / `429`，验收改为主会话直评；`036-acceptance-review.md:5` 已如实记录「不采信文档与回传摘要」。技术上做到了不采信式复核，但**流程上仍非独立**。
3. **039-test-infra**：用户 2026-09-19 明确授权「直接进行文件的改名和相关 skill 的沉淀，**不需要评审**」，门禁跳过有依据；但该授权范围**只覆盖改名与 skill 沉淀**，不覆盖 T4 的功能用例补全。首轮全量收集 `2057 collected, 37 errors` 是隔离分支基线缺 `source_registry.py` 所致，处理方式（不改 `backend/**` 绕过、如实记录阻塞）是正确的；本轮在 `main` 上复核为 3875/0 errors，阻塞确已消解。
4. **本轮本身**：三 spec 的实现代码在 2026-08～09 完成且此后未变，因此**未重跑全量回归**，仅按「受影响领域」做定向验证。这是**有意的口径选择**，已在证据文档 `:10-11` 声明；不作为「全量回归通过」的证据使用。

---

## 六、交给主会话的回填清单（本角色不代改）

| # | 文件 | 动作 |
|---|---|---|
| 1 | `docs/sdd/specs/011-knowledge-base-rag.md:5` | `实施中` → `已完成`；`:7` 待办标记完成；`:178` 需求评审改为指向 `011-requirement-review.md`（通过）；`:185` 签字栏状态改为已签（2026-11-05） |
| 2 | `docs/sdd/specs/036-tool-source-code-viewer.md:5` | `已确认` → `已完成`；`:166`/`:167` 按 **P1-2** 改真实结论与实际文件名 |
| 3 | `docs/sdd/specs/039-test-completion-and-infra.md:5` | `已确认` → `已完成`，**必须同时写明 §3.4 C1**（T4 外置）；`:115` 标注 T4 不适用；建议新增「评审记录」段写明 **C2** |
| 4 | `docs/sdd/spec-status-changelog.md` | 追加 **3 条**（011 2026-11-05；036 补 2026-11-05 同步条目；039 test-infra 2026-11-05）。**039 必须书写 spec 全名并声明撞号（P1-3）** |
| 5 | `docs/sdd/retro/` | 建议为 039-test-infra 补一份复盘，或在 011/036 复盘之外新建「2026-11-05 三 spec 收口复盘」，记录「无独立评审」的系统性偏差（P2-6） |

---

## 七、结论

- **011**：**同意转 `已完成`** —— 需求评审本轮补做并通过（`011-requirement-review.md`），验收签字本轮完成（`011-acceptance-review.md` §五，2026-11-05，开发主管 `architect` 签字放行）。历史代行偏差如实保留为 P1-1。
- **036**：**同意转 `已完成`** —— 7/7 实时 200 复核通过；唯一缺口为 spec 文档不同步（P1-2），实现与验收证据完整。
- **039-test-completion-and-infra**：**有条件同意转 `已完成`** —— 核心交付（分类重组 + 命名门禁固化 + 3875/0 errors）已验证；条件为 §3.4 **C1（T4 显式外置）、C2（评审缺失受权例外声明）、C3（撞号纠正）**。拒绝条件则改判**打回**。
- **P0 = 0**；**P1 = 5**（均可在台账回填动作中一次性处置）；**P2 = 6**（记录待改善）。
- 本轮**未**执行任何 `git add / commit / merge / push`；**未**改任何业务代码；**未**改三个 spec 的状态行、评审记录段、变更日志与 `spec-status-changelog.md`。

---

*评审文档路径：`docs/sdd/reviews/011-036-039-closure-review.md`*
*评审日志：`.codebuddy/agent-logs/spec-011/task-00/architect/20261105-182226.md`*
