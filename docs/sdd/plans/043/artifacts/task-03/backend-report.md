# Spec043 Task03 后端交接报告

## 状态

后端 MVP 代码与离线精准验证完成；未执行真实 Semantic Scholar/Ollama API E2E、浏览器 smoke、部署或 commit。前端由独立角色负责，Spec/Task 状态与 changelog 不在本角色范围内。

## 实际改动

- `backend/app/literature_maps/domain/`
  - `models.py`：Map/Node/Edge/Job/Event 稳定对象、`literature-map-v1` 投影、S2/catalog identity 分离。
  - `identity.py` / `map_identity.py`：DOI → arXiv → Semantic Scholar 的确定身份归一化；不以标题自动合并。
- `backend/app/literature_maps/infrastructure/`
  - `store.py` / `map_store.py`：独立 `data/literature_maps/literature_maps.sqlite3`（可由 `LITERATURE_MAP_DB_PATH` 覆盖），WAL、增量 schema marker、参数化 SQL、owner 查询、revision、幂等、节点/边/事件/job 检查点、向量缓存、删除墓碑。
- `backend/app/literature_maps/application/`
  - `service.py` / `discovery.py`：创建、恢复、owner/project 校验、S2 搜索二次截断、年限/身份/相关性筛选、引用分页/预算/partial、相似层、view/job 操作。
  - `similarity.py`：dense cosine `>=0.75`、每节点 top-3、无向端点排序去重；无 pair 保留 0 边。
  - `runtime.py`：服务组合根与启动恢复；`import_bridge.py`：只接受既有导入 callable，不自建 downloader；未配置时返回固定 `IMPORT_BRIDGE_UNAVAILABLE`。
- `backend/app/api/routes_literature_maps.py`：注册冻结的 `/api/literature-maps` 创建/list/read/graph/node/view/jobs/events/stop/retry/import 路径；统一 schema/error 响应与 owner 边界。
- `backend/app/api/routes.py`：注册地图路由。
- `backend/app/main.py`：启动时恢复 queued/running 地图作业。
- `backend/app/api/routes_conversations.py`：项目删除前调用 owner-scoped map detach；解绑异常返回 503 并保留项目。
- `tests/literature_maps/`：新增能力命名测试，未调用真实外部 API。

## 复用与边界

- 复用 `SemanticScholarGraphClient.search_bulk/graph_edges`、既有 parser、共享限流/有限 retry；未创建新 provider 或 limiter。
- 复用现有 `embed_texts` 默认入口；地图只存模型/basis/content hash 关联的向量缓存，不写个人 KB Collection。
- S2 `paper_id` 始终存 `external_ids.semantic_scholar`；未把它写入 `catalog_paper_id`。
- 图读取只读本地；主动 import 只走注入的既有链，默认未配置桥接时明确 503，未伪造成功或触发下载。

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_identity.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_discovery.py tests/literature_maps/test_map_similarity.py tests/literature_maps/test_map_api.py` | 0 | 10 passed |
| `.venv/bin/python -m pytest -q tests/conversation/test_conversations_api.py -k 'project'` | 0 | 2 passed, 14 deselected |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `python -m compileall -q backend/app/literature_maps ...` | 0 | 语法编译通过 |
| `git diff --check` | 0 | 无空白错误 |

单测使用 fake client/embedder/executor；没有把 fake 结果当真实来源证据。未运行全量回归。

## 接口差异与待验项

- Task03 冻结合同中 Task04–07 的 preview/apply、group、analysis、conversation、export 扩展未实现；本报告不声明这些端点存在。
- 默认生产 import bridge 尚未接入具体既有候选快照/安全下载调用链；当前安全行为是固定 503，需后续任务在真实导入上下文中注入 callable。
- `source_ids/conference_ids` 在首版持久化为筛选快照；S2 通用搜索没有可安全冒充官方 conference 身份的字段，因此未用 venue 标签假装官方认证。
- 尚未真实验证 `POST → job completed/partial → graph → view 重开`、真实引用边、真实相似边、重启 API、项目删除部署版本与浏览器交互。

## 主会话下一步

1. 读取本报告和实际 diff，执行独立 backend-reviewer/backend-tester 门禁。
2. 与前端接口契约核对 `schema_version`、字段名、事件状态与空/partial 展示。
3. 在获得真实外部凭据和部署授权后，单独落盘 API E2E 请求/响应/实体 ID/终态/产物，不把本次离线测试升级为真实验收。
