# 验收评审：spec-015 Task03 会议配置与论文召回

> 评审角色：测试（子代理 tester，临时调度 `gpt-5.6-luna/high`）
> 关联：spec-015、`docs/sdd/plans/015/task-03-conference-registry-and-retrieval.md`
> 验收范围：Task03 内置会议 publication search、主会过滤、去重、OpenAlex 补全、搜索会话及 API；不覆盖 Venue Search/custom conference、Spec013/014、reranker。
> 进展日志：`.codebuddy/agent-logs/tester-spec015-task03-acceptance-20260904.md`

## 结论：通过（Task03 定向范围）

39 个 Task03 定向单测全部通过，后端 Python 编译检查通过；隔离 TestClient/函数级验证覆盖开关短路、4 个内置会议、启停、内置删除保护、搜索参数校验、统一错误体及 DBLP/OpenAlex 降级。自定义会议/Venue Search 按 Task02 放行条件未验收，不影响本 Task03 收窄范围结论。

## 验证记录

### 1. 定向单测与编译

| 检查 | 命令 | 结果 |
| :--- | :--- | :--- |
| Task03 单测（39 项） | `.venv/bin/python -m pytest -q tests/test_paper_discovery_search.py tests/test_paper_discovery_store.py tests/test_dblp_publication_source.py tests/test_openalex_enricher.py` | `39 passed in 0.09s` |
| Python 编译 | `find backend/app -type f -name '*.py' -print0 \| xargs -0 .venv/bin/python -m py_compile` | 退出码 0，无错误输出 |

覆盖的单测事实包括：SQLite WAL/FK/busy timeout/schema 元数据、内置会议种子与候选去重、DBLP 主会过滤和受控 stream/year 查询、查询/年份/limit/会议校验、搜索会话快照、OpenAlex DOI/标题补全及失败 warning。

### 2. API 最小验收

使用临时 SQLite 状态库、TestClient、假的 DBLP 响应和 OpenAlex `MockTransport`；未访问真实外部源。结果如下：

| 验收项 | 状态 | 证据 |
| :--- | :--- | :--- |
| `GET /api/papers/conferences` | 通过 | `200`，返回 4 个内置会议 |
| `PATCH /api/papers/conferences/{id}` 启停 | 通过 | `ccs` 停用 `200/enabled=false`，再启用 `200` |
| `DELETE` 内置会议保护 | 通过 | `409 BUILT_IN_CONFERENCE_PROTECTED`，不删除配置 |
| 搜索成功与服务端候选 | 通过 | `POST /api/papers/search` 返回 `200`、1 条候选、服务端 `search_id` |
| query 校验 | 通过 | 空白 query → `400 INVALID_QUERY` |
| years 校验 | 通过 | 空列表 → `400 INVALID_YEARS` |
| limit 校验 | 通过 | `101` → `400 INVALID_LIMIT` |
| conference 校验 | 通过 | 未配置会议 → `400 CONFERENCE_NOT_CONFIGURED` |
| 统一错误体 | 通过 | 上述错误及内置删除错误均含 `code`、`message`、`retryable`、`request_id` |
| DBLP degraded 可观察 | 通过 | 搜索 warnings 含 `DBLP_TIMEOUT`，仍返回 DBLP 候选，`degraded=true` |
| OpenAlex warning 可观察 | 通过 | OpenAlex 503 时 warnings 含 `OPENALEX_HTTP_ERROR`、`OPENALEX_UNAVAILABLE`，DBLP 候选保留 |
| 所有召回源失败 | 通过 | 无候选且 DBLP 不可用 → `424 DBLP_UNAVAILABLE`，`retryable=true`、含 `request_id` |
| 功能关闭零外部调用 | 通过 | `PAPER_DISCOVERY_ENABLED=false` 时搜索/会议列表均 `503 PAPER_DISCOVERY_DISABLED`；DBLP 调用计数为 0 |

### 3. 代码依据

| 能力 | 代码依据 |
| :--- | :--- |
| 请求时开关短路和错误体 | `backend/app/api/routes.py:66-75, 140-149, 194-209` |
| 会议启停及内置保护 | `backend/app/api/routes.py:152-191` |
| 搜索源选择、错误映射与降级返回 | `backend/app/api/routes.py:211-240` |
| query/years/limit 的 Pydantic 边界 | `backend/app/api/schemas.py:39-51` |
| 年份、会议、查询、limit 在外部调用前校验 | `backend/app/services/paper_discovery_search.py:132-182` |
| DBLP warning/error 结构与主会召回 | `backend/app/services/paper_discovery_search.py:96-105`、`backend/app/services/dblp_publication_source.py:83-101` |
| OpenAlex best-effort warning/error | `backend/app/services/paper_discovery_search.py:258-284`、`backend/app/services/openalex_enricher.py:82-98, 158-197` |
| 内置会议种子、WAL/FK/busy timeout、候选唯一约束 | `backend/app/services/paper_discovery_store.py:18-22, 40-71, 160-205` |

## 风险与建议（不阻塞本 Task03 结论）

- Venue Search、自定义会议新增/修改/删除未验收，当前 API 明确返回 `CUSTOM_CONFERENCE_UNSUPPORTED`；这是 Task02 条件放行范围，留待后续门禁。
- 本报告未测试 PDF 下载、导入批次、Playwright 登录、reranker、前端 Tab 或 Spec013/014 回归。
- API 最小验证使用隔离假源；真实 DBLP/OpenAlex 可用性与限流应在后续集成/运行时验收中继续覆盖。

## 开发主管签字

（由开发主管填写；本 agent 留空待签）
