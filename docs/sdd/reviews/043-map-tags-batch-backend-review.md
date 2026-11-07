# Spec043 七项合并批次 — 后端增量代码评审（主模型代行）

## 元数据

- 评审者：主会话（架构师自身）
- 角色：`backend-reviewer`（**代行，非独立评审**）
- 模型 / 分派方式：主会话模型；无独立分派
- 时间：2026-11-07（Asia/Shanghai）
- 评审对象：`backend/app/literature_maps/infrastructure/store.py`、`backend/app/api/routes_literature_maps.py`、`backend/app/api/routes_conversations.py`、`backend/app/research/application/intake.py` 及 3 个新测试文件、1 个既有测试适配。

> **代行原因（三处留痕之一）**：实现分派（`hy3`）成功，但评审分派连续失败 —— 线上 `hy3` 三次 `429 Too Many Requests`；本地 `qwen3.5:9b` 两次返回 `Task completed` 却零落盘（报告与进展日志均不存在）。按 `SDD-GATE-CHECKLIST.md` Gate 2 失败处置第 4 条，评审文档属**纯文档改动**，允许主模型代行；另两处留痕见 spec「评审记录」与 `spec-status-changelog.md`。前端评审由 `frontend-reviewer` 独立完成（`043-map-tags-batch-frontend-review.md`），本报告不替代。

## 逐条判定（依据 `git diff` 与真实代码行）

| # | 项 | 判定 | 依据 |
|---|---|---|---|
| 1 | **revision 硬约束（P0）** | 通过 | `git diff -- store.py` 中 `_increment_map_revision` 仅出现在**注释**（说明不调用），无 `UPDATE literature_maps SET revision=revision+1`；新增 6 个标签方法均在 `:975-1115`，`update_map_details:639` / `update_view:645` 未被触碰；`routes_literature_maps.py:450-460` 的 `PUT /{map_id}/tags` 只调 `store.set_map_tags`。测试 `test_map_tags_store.py` 双用例覆盖 `revision` 不变。 |
| 2 | **owner 隔离与状态码（P0）** | 通过 | `routes_literature_maps.py:286-290` `_assert_tag_owned()` 用 `store.list_tags(OWNER_ID)` 判定，不存在/跨 owner 抛同一 `TAG_NOT_OWNED` 不泄露存在性；`:364-370` 映射 404，`TAG_LIMIT`/`TAG_NOT_FOUND` 保持 422（spec 边界 2），409 重名、400 非法值、201 创建。`store.py:355-356` 唯一索引 `UNIQUE(owner_id, name COLLATE NOCASE)`。 |
| 3 | **6 端点与路由顺序** | 通过 | `routes_literature_maps.py:385` `GET ""`、`:408` `GET /tags`、`:418` `POST /tags`、`:428` `PATCH`、`:439` `DELETE`、`:450` `PUT /{map_id}/tags`，全部在 `:470` 附近的 `GET /{map_id}` **之前**；`:391-401` 列表 `tags` 只读派生且 `**item.to_dict()` 保留 `status`/`node_count`（`test_map_list_node_count.py` 已加严断言 `tags == []`）。 |
| 4 | **队列 `skipped_items` 投影** | 通过 | `store.py:2076-2109` 从 `cursor.items` 收集 `status=="skipped"`，含 `node_id`/`skip_reason`/`retryable`/可选 `title`；`:1322` 无队列返回 `[]`；`counts` 与 `failed_items` 未改；`routes_literature_maps.py:627-633` `return _envelope(**queue)` 原样透传；`_envelope` 为 `{"schema_version": ..., **values}`，无字段白名单。 |
| 5 | **第 7 项 A+B（P0）** | 通过（附观察） | `routes_conversations.py:129-145` `_is_single_paper_conversation()` 复用既有 `_read_map_conversation_binding`，binding 非空→True，异常→True（fail-closed 跳过 Intake），`:2186` 短路后消息进入既有 RAG 链路；`:1452` 仅在**未明确点名 Skill** 时强制 `decision=none`，不误伤点名调用。`intake.py:125` `_SINGLE_PAPER_MARKERS`、`:144-163` `_explicit_verb_match()` 遍历窗口内所有动词，避免「研究问题/研究目标」名词误触发；实测「帮我分析一下这个领域的研究现状」→ `after="一下"` 不在名词后缀 → 仍 `explicit`（开放式请求未被过度抑制）；「帮我做深度研究」由 `深度研究` 关键字判 `explicit`，行为不变。分类器纯正则、零 LLM 调用。 |
| 6 | **测试诚实性** | 通过 | 无删用例 / skip / xfail / 放宽断言；`test_map_list_node_count.py` 的 diff 是**新增** `tags` 字段与 `assert item["tags"] == []`，属加严；`test_single_paper_rag_intent_routing.py` 用真实 `classify` + 真实 binding seam，未 mock 被修复函数。主会话复跑：后端 `306 passed`、前端 `427 passed`。 |

## P0 / P1 / P2

- **P0 = 0**（上述 3 个 P0 项均以真实代码行核实）。
- **P1 = 0**。
- **P2 = 2（观察项，不阻塞）**：
  1. `routes_conversations.py:129-145` binding 读取异常时返回 `True`，其 fail-closed 语义依赖下游 `:1286` RAG 链路再次读 binding 并抛 `MAP_CONVERSATION_CONTEXT_UNAVAILABLE`；建议在人工验收步骤 6 实际触发一次绑定失败，确认提示可见、不静默降级。
  2. `routes_literature_maps.py:286-290` `_assert_tag_owned()` 每次调用全量 `list_tags(OWNER_ID)`，标签量增长后有优化空间；当前 ≤20 绑定上限下不构成性能问题。

## 结论

**GO（通过，附意见）**。必须修复项：无。建议项：上述 2 个 P2 观察项纳入验收步骤与后续优化清单，不在本批次扩大范围。

## 证据诚实声明

本轮为**主模型代行的只读评审**，基于 `git diff`、真实 `文件:行` 与主会话复跑的真实测试输出；未修改任何业务代码、未跑子代理侧的测试、未做部署动作。真实 API 与浏览器 E2E 由主会话另行执行并落盘于 `docs/sdd/plans/043/artifacts/`，本报告不把其结论冒充为评审证据。
