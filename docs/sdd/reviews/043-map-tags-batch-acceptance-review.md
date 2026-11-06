# Spec043 七项合并批次 — 跨端验收评审

## 元数据

- 评审者：主会话（架构师自身）
- 角色：`tester` 跨端验收总控（**代行，非独立验收**）
- 模型 / 分派方式：主会话模型；无独立分派
- 时间：2026-11-07（Asia/Shanghai）
- 评审对象：`docs/sdd/specs/043-literature-map-topic-exploration.md`「2026-11-06 用户二次裁决与最终冻结范围（七项全部确认，不拆分）」段及其 Gate 2 强制约束清单。

> **代行原因（三处留痕之一）**：`tester` 分派 `hy3` 返回 `429 Too Many Requests`；此前 `backend-reviewer` 的本地轻档三次零落盘。按 `SDD-GATE-CHECKLIST.md` Gate 2 失败处置第 4 条，验收报告属**纯文档产出**，允许主模型代行；另两处留痕见 spec「评审记录 / 变更日志」与 `spec-status-changelog.md`。本报告所有判定均引用主会话**真实执行**的命令与产物，不引用未执行的计划。

## 七项逐项判定

| # | 项目 | 结论 | 证据 |
|---|---|---|---|
| 1 | 次级按钮视觉可用性 | **通过** | `frontend/literature-maps.css` diff（`#literature-maps-view` 作用域、9→11px、hover/focus）；`tests/frontend -q` 427 passed 含 `test_frontend_map_header_actions_readability.py`。验证层级：静态契约 + 自动化，未做像素级对比度实测（记 P2）。 |
| 2 | 地图级标签分类系统 | **通过** | `20261107-map-tags-live-e2e.json`：创建 201 / 大小写不敏感重名 409 / 绑定 200 / 列表含 `tags` / 旧字段保留 / 越权 422 / 删除 200 / 列表清空；`20261107-browser-live-e2e.json`：⋯ 菜单创建并绑定 → 卡片徽标 1 个 → 标签筛选 7→1 → 取消恢复 7；`revision` 不变由 `test_map_tags_store.py` 双用例覆盖。 |
| 3 | 详情面板三列同底 | **通过** | `20261107-browser-live-e2e-supplement.json`：选中节点后三列 bottom `[1020,1020,1020]`，详情 `#literature-map-detail` `scrollHeight=1778 > clientHeight=729`、`overflow:auto`；`test_frontend_map_layout_viewport.py` 14 passed，画布高度前后均 563.95 无增长。 |
| 4 | 「可用」筛选为空 Bug | **通过** | 真实浏览器 `select[11]` 选「可用」→ **5 张**（修复前恒 `0/7`）；`test_frontend_map_card_count_and_availability_badge.js` 第 8 组已按新语义改写。 |
| 5 | 「跳过 2」无原因 Bug | **通过** | 真实 API `0baabeae…/analysis-queue` 返回 `skipped_items` 2 条且带 `skip_reason`；真实浏览器页面含「跳过项」与「缺少摘要，不能生成摘要级分析；请先获取摘要。」；`test_frontend_map_analysis_queue.py` 新增断言通过。 |
| 6 | 「主题相似」勾选无感 | **通过（附观察）** | `literature-maps.js:6380-6395` 切换状态提示 + 相似度边计数，`:6461` 附近说明，`literature-maps.css` 虚线可见度提升、图层未删；427 passed 覆盖。验证层级：静态契约 + 自动化，未做真实浏览器勾选前后边数计数（记 P2）。 |
| 7 | 单篇全文 RAG 误判深度研究 | **通过（附观察）** | `test_single_paper_rag_intent_routing.py` 14 passed（真实 `classify` + 真实 binding seam + 真实 store 落盘 binding），硬门槛 `test_research_intake_intent_routing.py` 12 passed；`tests/research` 相关文件累计全绿，`ruff` 两文件 All checks passed。**观察**：未执行需 LLM 全链路的真实会话消息 API E2E，见下方 P2-3。 |

## 附加判定

1. **节点分组功能零回归**：通过。C 及等价删除方向永久排除；`git diff -- backend/app/literature_maps/infrastructure/store.py` 为**纯新增 239 行、零删除**，分组 CRUD / `update_view` / `update_map_details` / 导出逻辑未触碰；既有中文「分组」零改动；`tests/literature_maps` 306 passed 中相关全绿。
2. **测试诚实性**：通过。无删用例 / skip / xfail / 放宽断言；`test_map_list_node_count.py` 改动为**新增** `tags` 字段与 `assert item["tags"] == []`（加严）；`test_frontend_map_card_count_and_availability_badge.js` 为语义改写。
3. **命令与退出码**：后端 `pytest tests/literature_maps tests/research/test_single_paper_rag_intent_routing.py tests/research/test_research_intake_intent_routing.py -q` → **exit 0 / 306 passed**；前端 `pytest tests/frontend -q` → **exit 0 / 427 passed**；`node --check frontend/literature-maps.js` → **exit 0**；`py_compile` 5 个后端文件 → **exit 0**。
4. **部署与运行时**：`./deploy/stop.sh` + `./deploy/start.sh -d`（PORT=8000），新 PID 29829；`health=200`、`home=200`、`css?v=30=200`、`js?v=44=200`；`GET /api/literature-maps/tags` → 200 `{"schema_version":"literature-map-v1","tags":[]}`（证明新后端代码已加载）。
5. **关键产物**：`docs/sdd/plans/043/artifacts/` 下 `20261107-map-tags-live-e2e.json`、`20261107-browser-live-e2e.json`、`20261107-browser-live-e2e-supplement.json` 与 5 张 `20261107-browser-0*.png` 均存在。

## 人工验收准备度（十项检查）

| # | 检查 | 结果 |
|---|---|---|
| 1 | 目标与范围已冻结、无未确认决策 | 通过 |
| 2 | 产品使用步骤可操作（逐步点击/提示/等待/失败恢复/产物路径） | 通过 |
| 3 | 需求与技术评审通过 | 通过 |
| 4 | 分端代码评审有真实结论 | 通过（后端代行已留痕） |
| 5 | 后端定向与全量测试通过 | 通过（306） |
| 6 | 前端全量测试通过 | 通过（427） |
| 7 | 真实 API 成功案例落盘（请求/响应/实体 ID/最终状态/产物路径） | 通过 |
| 8 | 真实浏览器主链路与截图落盘 | 通过 |
| 9 | 服务重启与部署验证通过 | 通过 |
| 10 | 无 P0/P1、无 API E2E 失败、关键产物齐全 | 通过 |

**准备度 10/10（≥90% 达标）；P0=0、P1=0、API E2E 失败=0、阻塞项=0。**

## P2 观察项（不阻塞，不在本批次扩大范围）

1. 第 1 / 6 项未做像素级对比度与真实浏览器边数计数，由静态契约 + 自动化测试覆盖；人工验收时按 spec 产品步骤点一次即可确认。
2. `routes_conversations.py:129-145` binding 读取异常返回 `True`，依赖下游 `:1286` 抛出 `MAP_CONVERSATION_CONTEXT_UNAVAILABLE`；人工验收步骤 6 建议触发一次确认提示可见。
3. 第 7 项未执行需 LLM 全链路的真实会话消息 API E2E（会用 `POST /conversations/{id}/messages` 发「请重点回答：研究问题…使用RAG的模式」并检查 SSE 不含 `research_intake` / `deep-research-orchestration`）；当前由 14 个跨边界用例 + 12 个硬门槛用例 + 真实 binding 落盘覆盖，**不冒充为真实 API 成功案例**。
4. `routes_literature_maps.py:286-290` `_assert_tag_owned()` 全量 `list_tags` 有优化空间（≤20 绑定上限下无实际问题）。

## 结论

**通过。** 七项全部通过，无 P0/P1、无 API E2E 失败、无关键产物缺失；同意进入部署交付与人工验收。上述 P2 项列入后续观察，不退回实现阶段。

## 签字栏

- 架构师签字：**主模型代行（原因：`architect` / `tester` 分派通道 `hy3` 持续 429，本地轻档多次零落盘；按 Gate 2 失败处置第 4 条，纯文档签字允许代行并须注明）** — 2026-11-07。
- 本栏**已填写并注明代行**，符合 Gate 5「留空则不得转已完成」的要求。

## 证据诚实声明

本报告基于主会话真实执行的命令输出、真实 API 响应、真实 Chromium 测量与落盘产物；未自行跑子代理侧测试、未改业务代码、未做未执行的验证冒充。P2 观察项已如实列出，未把单元测试等价表述为真实 API E2E。
