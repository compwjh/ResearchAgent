# Spec012 索引卡死缺陷修订 + Spec043 顶部按钮批次 — 架构师合并裁决

| 项 | 值 |
|---|---|
| **裁决者** | 架构师子代理（ECC `architect`） |
| **裁决类型** | 合并裁决（Merge Decision） |
| **裁决时间** | 2026-11-06（本地） |
| **批次** | ① Spec012「索引任务重启后永久卡『索引中 0%』」缺陷修订<br>② Spec043 文献地图顶部操作按钮可读性与尺寸 |
| **上游文档** | 需求评审 `012-index-stuck-requirement-review.md`（通过，附意见）<br>技术评审 `012-index-stuck-tech-review.md`（通过，附意见，P0=0，P1=A-1/A-2）<br>后端回归 `012-index-stuck-backend-regression.md`<br>前端回归 `012-index-stuck-frontend-regression.md`<br>跨端验收 `012-index-stuck-acceptance-review.md`（通过，P0=0，准备度 10/10，§11 架构师已签字） |
| **裁决结论** | **同意收口（合并至本地 `main` 工作区提交），但未 push、未合远端** |
| **P0 / P1** | **P0 = 0 / P1 = 0**（tester 提出的唯一 P1「A-1 spec 风险区缺失」已由主会话补写、经我核实闭合） |

> **边界声明（先行）**：本次裁决**未执行** `git commit` / `git push` / 合并远端 / 部署 / 重启服务。仓库当前为 `main`，`## main...origin/main [ahead 1]`——该 1 个领先提交是既有 `fe5c0444`，**与本批次无关**。本批次全部改动仍为工作区未提交状态。

---

## 1. Gate 1–5 满足情况（逐条裁决）

### Gate 1 — 单端回归门禁

| 门禁 | 要求 | 我独立复跑实测 | 满足 |
|---|---|---|---|
| 后端 `tests/kb` | 0 failed | **524 passed, 0 failed** | ✅ |
| 后端 `tests/literature_maps` | 0 failed | **240 passed, 0 failed** | ✅ |
| 前端 `tests/frontend`（deselect perf 基线） | 0 failed | **408 passed, 1 deselected, 0 failed** | ✅ |
| `node --check` | exit 0 | `app.js` / `literature-maps.js` / 两个 kb 新测试 `.js` 全 **exit 0** | ✅ |
| 版本号齐升 | 四项 | `styles.css?v=69` / `app.js?v=71` / `literature-maps.css?v=28` / `literature-maps.js?v=42` | ✅ |

**裁决：Gate 1 通过。** 三项数字与派发单/tester 报告**逐字一致**，非引用。

> **执行纪律（本次实测教训，强制）**：`source .venv/bin/activate` 在子代理非交互 shell 下**静默失效**（实测 `which python` → `/opt/anaconda3/bin/python`），导致首次复跑出现 22 个 `ModuleNotFoundError: fastapi` 假失败。**后续后端验证一律用绝对路径 `./.venv/bin/python -m pytest`**。此为「可能被误判为测试失败」的已知陷阱，写入本项目纪律。

### Gate 2 — 运行时与用户价值闭环

| 验收点 | 要求 | 我独立 curl 实测 | 满足 |
|---|---|---|---|
| `/api/health` | 200 | **200** | ✅ |
| 全库篇数 | 64 | **64** | ✅ |
| `indexing` 计数 | 0 | **0** | ✅ |
| `failed` 计数 | 0 | **0** | ✅ |
| 零片段 `indexed` | 0 | **0** | ✅ |
| 目标文档 `1b967ed8…` `chunkers.v2` | `indexed` + 有片段 | **`{indexed, 135, 100, null}`** | ✅ |

**裁决：Gate 2 通过。** 核心用户价值点（`indexing 0%` → `indexed / 135 片段`）闭环成立。

### Gate 3 — 跨端验收与交付准备度

| 验收点 | 要求 | 实测 | 满足 |
|---|---|---|---|
| tester 跨端验收结论 | 通过 | **通过**（P0=0） | ✅ |
| 人工验收交付准备度 | ≥9/10 | **10/10** | ✅ |
| Spec043 顶部按钮取值 | 与 spec 零偏差 | 逐项一致（`12px / 600 / 9px 14px / min-height 36px / #4a4560 / #fff / #d8d2ff / 8px`；≤760px 下 44px） | ✅ |
| 对比度 | ≥8:1 | **≈9:1**（原 3.01:1） | ✅ |
| 真实浏览器 E2E | 有截图 | `docs/sdd/plans/012/artifacts/2026-11-06-live-e2e-literature-maps.png`（313,486 B） | ✅ |

**裁决：Gate 3 通过。**

### Gate 4 — 架构评审强制约束闭合（A-1 … A-10）

| 编号 | 级别 | 状态 | 依据 |
|---|---|---|---|
| **A-1** | **P1** | **已闭合** | spec `012-kb-recall-quality.md:257-264` 风险区 **6 条齐全**，与 `store.py:785-810` docstring 口径逐条一致；`store.py:806` 反向引用由悬空变为**有效** |
| **A-2** | **P1** | **已闭合且必要** | `application.py:856-884` 用「提交前采样 `before_status` / 提交后比对 `current_status`，仅相同才写 `indexing`」；`submitted[name]=bool(accepted)` 布尔契约未变 |
| A-3 | P2 | 已闭合 | `tests/kb/test_kb_startup_interrupted_recovery.py:347` 真实未 patch 端到端用例 |
| A-4 | P2 | 已闭合 | `tests/kb/test_kb_document_routes.py:476` 路由级 409 稳定错误体 |
| A-5 | P2 | 已闭合 | spec 冻结表 F2/`styles.css?v=68→69` 已登记（`:252-253`）+ changelog |
| A-6 | P2 | **形态偏离，接受** | 4 份 JSON 产物（`ops-recovery{,-retry,-final,-last}.json`）替代 `.md` 13 行台账；证据完整可机器对账；建议后续补 `.md` 索引（不阻塞） |
| A-7 | P2 | 已闭合 | 真实浏览器 7 按钮全展开无溢出 + 1440/1000/720 三档无溢出 |
| A-8 | P2 | **已闭合** | 与 A-1 同源，随风险区第 1 条一并落盘 |
| A-9 | P2 | 已闭合 | `tests/frontend/test_frontend_kb_failure_class_dom_contract.js` 4 组 DOM 反向契约断言 |
| A-10 | P3 | 已闭合 | 约定层；本次实测补强为「强制绝对路径 `./.venv/bin/python`」 |

**裁决：Gate 4 通过（A-1/A-2 均已闭合，A-6 形态偏离经架构师裁决接受）。**

### Gate 5 — 冻结边界与范围纪律

| 验收点 | 要求 | 实测 | 满足 |
|---|---|---|---|
| 冻结清单重登 | 按最终代码重登 | `upload-closure-matrix.json` **4 个键值变更**（`inventory_digest` + 3 个后端文件 sha256；`diff -U0` 计 8 行 = 4 删 4 增） | ✅ |
| sha256 一致性 | 与实测一致 | 我 `shasum -a 256` 实测：`main.py 85c9be…` / `application.py 4fe849…` / `store.py 0d7b28…` **逐字一致** | ✅ |
| 明确不做①持久化队列 | 不含 | 未引入 Celery / DB outbox / 分布式调度 | ✅ |
| 明确不做②切分/embedding/LLM/代次门 | 不含 | `index.py` 等不在 diff 清单 | ✅ |
| 明确不做③响应契约 | 不含 | `GET /api/kb/papers` / `health` / `POST /reindex` 契约未改（409 用例守护） | ✅ |
| **范围外：地图标签与卡片设置菜单** | 不含（作废存档） | 本批次**未实现/未纳入** | ✅ |
| **范围外：节点外观面板紧凑布局** | 不含（暂缓） | 本批次**未实现/未纳入** | ✅ |

**裁决：Gate 5 通过。**

---

## 2. P0 / P1 清点

| 级别 | 数量 | 明细 |
|---|---|---|
| **P0** | **0** | 无 |
| **P1** | **0** | tester 提出的「A-1 spec 风险区缺失 + `store.py:806` 悬空引用」**已闭合**（我 Read 核实风险区 6 条 + 口径一致 + 引用有效）。**无遗留 P1** |
| 已知基线阻塞 | **1** | `test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions`（`maxGestureWallMs` 1.4–1.9s vs 1s）。与本批次无因果（干净 HEAD 同样失败、fixture 自包含），**单独立项跟踪**，见 §3 |
| P2 形态（已裁决接受） | 1 | A-6 台账 4 JSON 形态 |
| P3 技术债 | 1 | `ruff` 存量 56 errors（0 条落在本批次改动文件） |

---

## 3. 已知基线阻塞的处置（不掩盖、不放宽阈值）

**对象**：`tests/frontend/test_frontend_map_feasibility.py::test_synthetic_svg_supports_sparse_graph_interactions`

| 处置项 | 裁决 |
|---|---|
| 定性 | **已知环境基线阻塞**，与本批次**无因果**（三重否定：①`git diff --name-only HEAD` 不含 `frontend/literature-maps.js`；②fixture 为自包含单 `<script>` 直开 `file://`，不加载本批次任何资源；③干净 HEAD 同样失败） |
| 是否计入本批次 P0/P1 | **不计入** |
| 处置方式 | **单独立项跟踪**。须在负载稳定机器上重新标定机器基线，或改为**相对阈值**（相对基线自身基线 + 容差），后者属测试口径变更，**须独立评审** |
| **禁止项（硬约束）** | **不得**放宽 `maxGestureWallMs` 绝对值阈值至「能过」来掩盖；**不得**删除或 `skip` 该用例；**不得**把它写成「已修复」 |
| 门禁扣除方式 | 本批次门禁采用 `--deselect` 显式扣除并**在报告中明示为「已知基线扣除」**，不是豁免；扣除项必须逐批次重新声明，不得固化为默认跳过 |
| 已落盘 | spec 风险区第 6 条（`012:264`）已记录该基线与「单独立项、不放宽阈值」的裁决 |

---

## 4. 合并前须 `git add` 的新增文件清单

> 依据：`git status --porcelain` + `git ls-files --others --exclude-standard` **只读**核对（2026-11-06）。**白名单制**：只加下列文件，禁止 `git add -A` / `git add .`。

### 4.1 新增测试（本批次必加）

| # | 路径 | 说明 |
|---|---|---|
| 1 | `tests/kb/test_kb_startup_interrupted_recovery.py` | A-3 真实未 patch 端到端用例 + A-2 五条双向断言（瞬间终态不覆盖 / 陈旧 failed 重试转 indexing 等） |
| 2 | `tests/frontend/test_frontend_map_header_actions_readability.py` | Spec043 顶部按钮可读性/尺寸契约 |
| 3 | `tests/frontend/test_frontend_kb_failure_class_dom_contract.js` | A-9 DOM 反向契约断言（node 执行） |
| 4 | `tests/frontend/test_frontend_kb_failure_class_dom_contract.py` | 上者的 pytest 包装（门禁入口） |
| 5 | `tests/frontend/test_frontend_kb_index_interruption_notice.js` | 重启中断提示文案断言（node 执行） |

### 4.2 新增评审/证据文档（本批次必加）

| # | 路径 |
|---|---|
| 6 | `docs/sdd/reviews/012-index-stuck-requirement-review.md` |
| 7 | `docs/sdd/reviews/012-index-stuck-tech-review.md` |
| 8 | `docs/sdd/reviews/012-index-stuck-backend-regression.md` |
| 9 | `docs/sdd/reviews/012-index-stuck-frontend-regression.md` |
| 10 | `docs/sdd/reviews/012-index-stuck-acceptance-review.md`（含架构师签字） |
| 11 | `docs/sdd/reviews/012-index-stuck-merge-decision.md`（本文档） |
| 12 | `docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery.json` |
| 13 | `docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery-retry.json` |
| 14 | `docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery-final.json` |
| 15 | `docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery-last.json` |
| 16 | `docs/sdd/plans/012/artifacts/2026-11-06-live-e2e-literature-maps.png` |

### 4.3 已跟踪的修改文件（`M`，随提交一并纳入）

`backend/app/knowledge_base/application.py`、`backend/app/knowledge_base/infrastructure/store.py`、`backend/app/main.py`、`frontend/app.js`、`frontend/index.html`、`frontend/styles.css`、`frontend/literature-maps.css`、`docs/sdd/specs/012-kb-recall-quality.md`、`docs/sdd/specs/043-literature-map-topic-exploration.md`、`docs/sdd/spec-status-changelog.md`、`docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json`、`tests/kb/test_kb_startup_generation_gate.py`、`tests/frontend/fixtures/literature_map_component.html`、`tests/frontend/test_frontend_literature_map_contract.py`、`tests/frontend/test_frontend_literature_map_expansion.py`、`tests/frontend/test_frontend_management_contract.py`、`tests/frontend/test_frontend_map_analysis_contract.py`、`tests/frontend/test_frontend_map_groups_exports.py`、`tests/frontend/test_frontend_map_mobile_contract.py`

### 4.4 **禁止纳入本批次**（无关未跟踪文件，勿 `git add -A`）

| 路径 | 原因 |
|---|---|
| `.playwright-cli/`（多个 `page-*.yml`） | 浏览器调试临时产物，与本批次无因果关系，不应入库 |
| `artifacts/jd-agent-infra-capability-map.md` | 与本批次无关的既存文档 |
| `nav.yaml` | 与本批次无关的既存文件 |

> **仓库卫生裁决**：以上三项须在提交时**显式排除**；若主会话认为需要入库，须另开提交并说明来源，不得混入本批次提交。

---

## 5. 边界声明

1. **未 push**：本次裁决**未**执行 `git push`，远端 `origin/main` 无本批次任何内容。
2. **未合远端**：未执行 merge/rebase 到远端；`main` 相对 `origin/main` 的 `ahead 1` 为**既有提交 `fe5c0444`**，非本批次产生。
3. **未 commit**：本批次改动仍为工作区未提交状态；是否提交、何时提交由主会话按 §4 白名单执行。
4. **未重启服务 / 未部署 / 未触发重排**：全部核实均为**只读**（Read / grep / curl GET / pytest / node --check / shasum / git 只读命令）。
5. **未改** spec / changelog / 实现代码 / 数据：本次仅写两处文档——`012-index-stuck-acceptance-review.md` 的 §11 签字栏（精准替换占位行，报告其余部分零改动）+ 本裁决文档。
6. **架构评审裁决权仅体现在文档**：本角色不 git push、不合 main；合并动作由主会话按本裁决执行。

---

## 6. 收口条件（附条件放行）

裁决为 **同意收口（附 4 项非阻塞条件）**：

| # | 条件 | 级别 | 负责 |
|---|---|---|---|
| C1 | 提交时严格按 §4 白名单 `git add`，**排除** `.playwright-cli/`、`artifacts/jd-agent-infra-capability-map.md`、`nav.yaml` | 必须 | 主会话 |
| C2 | perf 用例单独立项跟踪，**不得**放宽阈值 / 删除 / skip 掩盖 | 必须 | 独立任务 |
| C3 | 后续补 `docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery.md` 13 行索引指向 4 份 JSON（A-6 字面要求） | 建议 | 后续 |
| C4 | 后续单独立项向用户说明 `indexed_partial` 25 个 / `SOURCE_RANGE_UNRESOLVED` 语义，避免「部分完成」被误读为缺陷 | 建议 | 后续 |

**收口后需保留的硬约束（写入团队纪律）**：
- **A-2 谓词不得简化**：`current_status == before_status` 不可改为 `current_status != "failed"`——后者会让「用户点重试（陈旧 failed）」主流程退化为「仍显示索引失败」。
- **后端验证强制绝对路径**：`./.venv/bin/python -m pytest`，不依赖 `activate`。
- **防重启风暴上界**：每进程重启、每 `(document, chunker)` 至多 1 次自动重排；`auto_requeued_chunkers` 幂等标记为唯一保证，不得移除。
- **残余窗口已知且已接受**：`submit → mark_chunker_auto_requeued` 非原子，毫秒级、后果有界（重复重排一次）；彻底闭合需持久化队列——**用户已裁决不做**（spec 风险区第 1、3 条）。

---

## 7. 关联文档

- 需求评审：`docs/sdd/reviews/012-index-stuck-requirement-review.md`
- 技术评审：`docs/sdd/reviews/012-index-stuck-tech-review.md`
- 后端回归：`docs/sdd/reviews/012-index-stuck-backend-regression.md`
- 前端回归：`docs/sdd/reviews/012-index-stuck-frontend-regression.md`
- 跨端验收（含架构师签字 §11）：`docs/sdd/reviews/012-index-stuck-acceptance-review.md`
- Spec012 风险区：`docs/sdd/specs/012-kb-recall-quality.md:257-264`
- 恢复证据：`docs/sdd/plans/012/artifacts/2026-11-06-ops-recovery{,-retry,-final,-last}.json`
- E2E 截图：`docs/sdd/plans/012/artifacts/2026-11-06-live-e2e-literature-maps.png`
- 冻结清单：`docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json`
- 本裁决执行日志：`.codebuddy/agent-logs/spec-012/task-00/architect/20261106-063130.md`
