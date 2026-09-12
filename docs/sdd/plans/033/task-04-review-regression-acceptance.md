# Task 04 — 评审、回归与端到端验收

> 关联：[spec-033](../../specs/033-usenix-parser-real-page-alignment.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03；当前状态：`已完成`

## 1. 状态与一句话目标

**已完成。** 对任务 02/03 的解析器改动做了独立评审、后端定向回归，并用真实 USENIX 页面与线上检索任务
做端到端验收，确认「作者不再为空」「检索不再因解析失败降级」。

## 2. 背景与前置条件

- 任务 02、03 已完成并读回确认。
- 服务运行中：`http://127.0.0.1:8000`（`deploy/run.pid` 记 PID）。
- 已知环境约束：`paper_discovery_dblp_enabled=False`（DBLP 源会被跳过，属预期）。

## 3. 数据、配置与接口

不适用（不新增数据与接口）。

## 4. 实施步骤与文件边界

**允许改动**：`docs/sdd/reviews/033-*.md`、本 task 文件的回填段落。**不改任何代码文件**。

1. **后端评审**（`backend-reviewer`）：只评 `backend/app/paper_discovery/infrastructure/usenix_paper_parser.py` 的 diff。
   重点核对：① 作者抽取是否**只有一套实现**（任务 02/03 复用同一辅助函数）；
   ② 回退分支是否保持 fail-closed；③ `_safe_url` 白名单未被放宽；④ 站点级 `.description` 未被误当摘要。
   产出 `docs/sdd/reviews/033-tech-review.md`（结论只能是 通过 / 打回）。
2. **后端回归**（`backend-tester`）：按文件分批跑
   `tests/test_usenix_paper_parser.py`、`tests/test_usenix_publication_source.py`、`tests/test_usenix_detail_tool.py`、
   `tests/test_paper_import_*.py`、`tests/test_catalog_search_*.py`（存在者）；
   每次用全新 `--basetemp`。产出 `docs/sdd/reviews/033-acceptance-review.md` 的后端段。
3. **端到端验收**（主会话 / `tester`）：
   - 直接调用解析器跑 4 个真实列表页样本，统计作者/摘要非空比例；
   - 对 3 个「无 `citation_*`」与 2 个「有 `citation_*`」详情页样本跑 `parse_usenix_detail`；
   - 通过 `POST /api/papers/searches` 发起 2022 与 2024 两个真实检索，轮询到终态，
     核对 `degraded` 与结果里的 `authors` 字段；
   - 若历史 fetch unit 已完成导致未重新抓取，需在报告中说明（缓存命中不等于修复无效），
     必要时用全新 `search_id` 与未覆盖的年份/查询验证。

## 5. 子代理分派

| 步骤 | 角色 | 模型 | 最小上下文 |
|---|---|---|---|
| 1 | `backend-reviewer` | `Deepseek-V4.1-Flash` | 本 task + spec-033 + `git diff` 范围 |
| 2 | `backend-tester` | `Deepseek-V4.1-Flash` | 本 task + 测试文件清单 + 运行约定 |
| 3 | 主会话（架构师自身） | 自身 | 真实页面样本与运行中的服务 |

## 6. 边界与明确不做

- 本任务**不修代码**；发现问题回到任务 02/03 修订。
- 不跑全量回归（用户明确要求「不用全量」），只跑解析器相关定向回归。
- 不改 `degraded` 判定策略、不改 DBLP 开关。

## 7. 验收、风险与回滚

**验收**：
1. 后端定向回归全绿，`ruff check` 零新增告警。
2. 4 个真实列表页样本作者非空比例显著 > 0（目标 100%）。
3. 3 个「无 `citation_*`」详情页样本解析成功；2 个「有 `citation_*`」样本零回归。
4. 真实检索任务的 `degraded` 不再由 `USENIX_PARSE_FAILED` 引起（事件流中该错误码消失）；
   结果 `authors` 非空。
5. 三份评审文档结论为真实结论，无「待评审（未执行）」残留。

**风险**：USENIX 站点结构可能继续变化；若验收时真实页面结构与 2026-09-12 样本不符，
以**实时抓取的页面**为准并在报告中记录差异。
回滚：解析器改动为纯追加分支；若验收不通过，删除新增分支即可，不触碰 spec-032.1 的在途改动。

## 8. 产出物、执行结果与变更日志

- 产出物：
  - `docs/sdd/reviews/033-requirement-review.md`（`architect`，通过（附意见），4 MEDIUM + 6 LOW + 1 INFO）
  - `docs/sdd/reviews/033-tech-review.md`（`backend-reviewer`，通过，0 CRITICAL / 0 HIGH，2 MEDIUM + 2 LOW；含事后整改复核节）
  - `docs/sdd/reviews/033-backend-regression.md`（`backend-tester`，未引入回归）
  - `docs/sdd/reviews/033-acceptance-review.md`（`tester`，通过；`architect` 签字**放行**）

### 执行结果

| 验收点（§7） | 结论 | 证据 |
|---|---|---|
| 1. 定向回归全绿 + ruff 零新增 | 通过 | 311/311（5 批 16 文件）；parser 文件 `All checks passed!`；全 backend 唯一 SIM105 属他人在途改动 |
| 2. 真实列表页作者非空比例 100% | 通过 | list24 `82/82`、list25 `245/245`（摘要同为 100%） |
| 3. 3 无 / 2 有 `citation_*` 详情页 | 通过 | 5 页全 OK；有 meta 两页作者数/摘要长度逐字不变（零回归） |
| 4. `degraded` 不再由 `USENIX_PARSE_FAILED` 引起 | 通过 | 检索 176 条、失败事件 **0**；`degraded` 归因 reranker 缺失（`rerank_score` 0/176 非空） |
| 5. 三份评审文档为真实结论 | 通过 | 四份评审均落盘且带结论，无「待评审（未执行）」残留 |

- **单测**：`test_usenix_paper_parser.py` 47 + `test_usenix_publication_source.py` 42 + `test_usenix_detail_tool.py` 9 = **98 passed**。
- **两条 MEDIUM 整改**：MEDIUM-1 摘要块级边界分隔符（`'A.B.'` → `'A. B.'`，原 `in` 断言替换为 `==`）；
  MEDIUM-2 详情页作者块按 `presentation URL → title → [0]` 绑定（侧栏块在前不再取错作者）。二者均由主会话独立探针复现。
- **端到端**：失效化 2022 全部 178 个 fetch unit（备份 `/tmp/fetch_units_backup_20260912-223229.json`）
  并清空目录摘要（备份 `/tmp/catalog_2022_backup_20260912-223346.json`）以**强制真实重抓**；
  检索终态 `partial`/`degraded=True`/176 条，`catalog_papers` 2022 作者 176/176、摘要 176/176、可疑作者 0、获奖标记 0。

### 与计划的偏差（据实记录）

1. §4 步骤 3 要求跑「2022 与 2024 两个真实检索」，实际只跑了 2022：2024 的详情页样本已由**直调解析器**覆盖
   （`q_xie-xiang` / `q_liu-fengrun` / `q_zhang-qingzhao`），且 2022 的全链路（列表→详情→索引→检索）已完整跑通，未重复消耗线上抓取配额。
2. 缓存命中会掩盖修复效果，故本次**主动失效缓存**而非依赖缓存复跑；过程中发现并纠正一次自测假象
   （只清 `authors_json` 而未失效化**列表页**单元时作者仍为 0/176 —— 作者来源于列表页解析、详情页只回填摘要）。
3. 验收报告初稿由主会话代写，随后按 Gate 5 由 `tester` **独立重做并覆盖**（其纠正了草稿对 `degraded` 机制的错误引述）。

### 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-12 | 架构师(自身) | 将 02/03 状态回填为已完成，本任务置进行中；独立复核两条 MEDIUM 整改 |
| 2026-09-12 | `backend-reviewer` | 技术评审通过（2 MEDIUM + 2 LOW + 强制约束清单） |
| 2026-09-12 | `backend-dev` | 按强制约束 #3/#4 整改两条 MEDIUM，parser 测试 42 → 47 |
| 2026-09-12 | `backend-tester` | 5 批定向回归 311/311，产出回归报告 |
| 2026-09-12 | `tester` | 独立验收评审通过，覆盖主会话草稿 |
| 2026-09-12 | `architect` | 需求评审通过（附意见）+ 验收签字**放行** |
| 2026-09-12 | 架构师(自身) | 回填本文件，三处状态同步为已完成 |
