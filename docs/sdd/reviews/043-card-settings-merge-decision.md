# Spec043 卡片设置列表 + 重命名/删除地图 — 合并裁决（Gate 5）

| 项 | 值 |
|---|---|
| 评审者 | architect 子代理（合并裁决 / 验收签字） |
| 角色 | 架构师（评审 / 合并，对应 ECC `architect`） |
| 模型 | hy3（**临时换档**，因默认档连续 429，按用户授权切换） |
| 分派方式 | `Task(architect)`（临时换档分派） |
| 裁决时间 | 2026-11-07 |
| 裁决对象 | `docs/sdd/specs/043-literature-map-topic-exploration.md:1883-2122`（C 段卡片设置列表 + 选项 C 重命名/删除地图） |
| 动作边界 | 仅签字与落盘文档；**未改业务代码 / 测试 / spec / 台账、未部署、未 commit、未 push** |

> 纪律：本裁决每条结论基于 Read/Grep 打开真实文件核对或读取已落盘真实产物，不采信回传摘要。所有 `文件:行` 为本次核对实际行号。

---

## 一、五道门禁核对表

| 门禁 | 要求 | 核对结果 | 依据 |
|---|---|---|---|
| **Gate 1**（spec 段冻结） | 范围 / 边界 / 明确不做 / 决策点冻结 | **PASS** | spec `:1883-1985`（C 段边界 8 + 步骤 8 + 明确不做 5）、`:1986-2085`（选项 C 裁决、冻结决策点 6 项 `:2074-2083`） |
| **Gate 2**（增量双评审 + 后端附条件） | 需求 + 技术通过；后端/前端 GO；后端附条件核销 | **PASS** | 需求 `043-card-settings-requirement-review.md:95`「通过」；技术 `:154`「通过」、`:156` 无 P0；后端 `043-card-settings-backend-review.md:117` GO、`:269` GO（附条件「真实 API 复验通过」）；前端 `043-card-settings-frontend-review.md:18` GO → `:243`/`:365` GO（P1-01/02/03 全 CLOSED） |
| **Gate 3**（用户确认） | 用户明确确认后实施 | **PASS** | spec `:1988` 用户「直接开工」＝按默认执行；`:1992` 6 决策点冻结；台账 `spec-status-changelog.md:694` 记录「待确认 → 已确认（实施中）」 |
| **Gate 4**（分派真实发生） | 六角色分派且各有落盘产出 | **PASS** | 见第二节分派真实性清单 |
| **Gate 5**（跨端验收 + 签字） | tester 出报告 16/16；架构师签字 | **PASS** | `043-card-settings-acceptance-review.md`（结论「通过」、16/16，签字栏已由本裁决填写）；附条件核销见第一节 Gate 2 依据 |

**后端附条件核销（关键）**：`backend-review.md:269` 条件＝「重启后真实服务上 PATCH 只带 `{expected_revision,name}` → 200、project_id 保持、revision+1」。真实 API E2E `20261107-card-settings-live-e2e.json`：requests[3] `PATCH` body 仅 `{expected_revision:0, name}` → **200**，响应 `revision:1`、`topic` 保持；`bindings_for_deleted_map_before=1 → after=0`；stale revision → 409 `MAP_CONFLICT`。**条件已核销，结论生效。**

---

## 二、分派真实性清单（六角色 + 本签字，均有落盘产出，非空壳）

| 角色 | 落盘产出（真实） | 核验 |
|---|---|---|
| `architect`（Gate 2） | `043-card-settings-requirement-review.md`、`043-card-settings-tech-review.md` | 头部四要素齐备（评审者/角色/模型/分派方式 `Task(architect)`） |
| `backend-dev` | `backend/app/literature_maps/infrastructure/store.py:727`（1 行绑定清理）、`application/service.py:927-935`（哨兵修复）；`tests/literature_maps/test_map_delete_tag_bindings.py`（3 例）+ `test_map_details_patch_api.py`（6 例） | `git diff -- backend/` 仅 2 文件、改动面封闭 |
| `frontend-dev` | `frontend/literature-maps.js:1875-2433`、`frontend/literature-maps.css:494-559`、`frontend/index.html:9,805`、`tests/frontend/test_frontend_map_tags_ui.py`（改写 18 例） | `node --check` exit 0；`?v=31/45` 四点数一致 |
| `backend-reviewer` | `043-card-settings-backend-review.md`（含 P0 增量复审 `:125-279`、附条件 `:269`） | 反向验证 + 变异验证已做并已复原 |
| `frontend-reviewer` | `043-card-settings-frontend-review.md`（含两轮复审，`:167` P1 修复复审、`:261` 集中复审） | `:365` 确认 P0=0/P1=0、P1 全 CLOSED |
| `tester` | `043-card-settings-acceptance-review.md` + `20261107-card-settings-live-e2e.json` + `20261107-card-settings-browser-e2e.json` + `20261107-card-settings-full-regression.log` | 16/16 逐项有 `文件:行` 证据 |
| **本签字（architect）** | `043-card-settings-acceptance-review.md` 签字栏（`:148/:150`）+ 本合并裁决文档 | 本文件落盘 |

---

## 三、数字汇总

| 维度 | 结果 |
|---|---|
| 前端定向回归 | **439 passed / 0 failed**（`tests/frontend`） |
| 后端定向回归（三路径） | **315 passed / 0 failed**（基线 309 + 新增 6，只增不减） |
| 全量回归 | **4011 passed / 2 failed（既有）/ 2 skipped / 67 subtests passed**，pytest 退出码 1 |
| 真实 API E2E | **16/16** 全 true（PATCH 仅 `{expected_revision,name}` → 200、revision 0→1、409 MAP_CONFLICT、DELETE 204、绑定 1→0、标签存活后清理） |
| 真实浏览器 E2E | **32/32** 全 true、`page_errors=[]`、6 张截图（1440 + 760 两档） |
| 部署验证 | **5/5 200**（`/`、`/api/health`、`css?v=31`、`js?v=45`、`/api/literature-maps/tags`） |
| 版本号 | `?v=31/45` 四点数一致（生产页 + fixture + 7 测试文件全部同步） |
| 静态契约 | `innerHTML` = 0、`fetch(` = 3、`node --check` exit 0 |

---

## 四、遗留项与建议（均不阻塞本次合并）

| 编号 | 内容 | 状态 | 建议 |
|---|---|---|---|
| P2-01 | `loadMaps()` 复用删除前残留 `state.maps` 隐式依赖（`literature-maps.js:2385/2407`） | 仍开放（不阻塞） | 当前路径不可达，建议后续批次显式化时序 |
| P2-02 | 5xx 措辞复用 `errorAction()` 语境 | ≥95% 消解 | 已为本场景提供专属兜底，可接受 |
| P2-03 | T-11 视觉指标 | CLOSED | 已由真实 Chromium E2E 核销 |
| LOW-01 | `positionTagMenu()` 清约束早于视图 class 切换（顺序依赖） | 登记（低） | 当前结果正确，建议把清约束移至 `classList` 切换之后并在测试固化 |
| **既有缺陷** | `tests/paper_discovery/` 2 失败（断言「临时目录 `paper-import-*` 未清理」） | **既有独立缺陷，非本批次回归** | **建议另开 Bug Spec** 跟踪（临时目录清理/补偿），不属 Spec043 范围 |
| 人工走查 | 产品步骤 1–8 已由真实浏览器自动化替代，主观可用性维度未覆盖 | 建议 | 建议用户按 spec `:2043-2050` 实走 8 步确认手感/文案预期 |

> 收口动作（签字后，不在本裁决范围）：台账 `spec-status-changelog.md` 补登本批次收口条目。

---

## 五、裁决

# APPROVE

**理由**：
1. **四道门禁全过**：Gate 1 spec 段冻结、Gate 2 双评审通过且 `backend-reviewer` 附条件「真实 API 复验通过」已在重启后的真实服务上核销（PATCH 仅 `{expected_revision,name}` → 200、revision 0→1、绑定 1→0）、Gate 3 用户「直接开工」、Gate 4 六角色真实分派各有落盘产出、Gate 5 tester 16/16 验收报告已落盘。
2. **缺陷级别归零**：P0=0、P1=0 全端一致（后端 `backend-review.md:263`、前端 `frontend-review.md:365`、验收报告）；无数据丢失、无越权、无事务不一致、无 XSS（`innerHTML`=0）。
3. **本批次自身回归面全绿**：前端 439、后端 315、API 16/16、浏览器 32/32、部署 5/5、版本号 `?v=31/45` 一致、静态契约全过。
4. **2 个全量失败不阻塞**：经 HEAD 快照（不含本批次任何改动）复跑同样 `2 failed` / 退出码 1，且 `git status --short` 显示本批次零文件涉及 `paper_discovery` —— 判定为**既有独立缺陷**，非本批次回归；如实登记并建议另开 Bug Spec。若将无关既有缺陷归咎本批次并据此 REJECT，会错误混淆责任边界且抑制本批次已验证的正确交付。**不阻塞签字。**
5. **遗留 P2/LOW 已登记且不阻塞**；人工走查为建议项，不影响自动化验收结论。

> 说明：默认档（Deepseek-V4.1-Flash）此前已在验收报告 `:148/:150` 落过一版签名；本次因默认档连续两次 429，主会话按 `SUBAGENT-ORCHESTRATION.md` 的「429 失败处置：重试 → 换档 → 记录阻塞」临时把 `.codebuddy/agents/architect.md` 的 `model` 改为 **hy3** 重新分派（用户 2026-11-07 早前曾授权过临时 hy3；本轮属规则内应急处置，**并非本轮重新授权**），签字栏两行已按精确文本覆盖为该临时档记录。签字完成后主会话已把 `model` 还原为 `Deepseek-V4.1-Flash`，`git diff -- .codebuddy/agents/` 为空；临时档位未写入任何流程纪律文档。签字说明（`:152`）保留并指向本裁决（结论 APPROVE），一致。
