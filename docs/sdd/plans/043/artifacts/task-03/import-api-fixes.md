# Task03 导入桥接与 API 修复交接

日期：2026-10-19；角色：backend-dev；范围：`application/import_bridge.py`、`application/runtime.py`、`api/routes_literature_maps.py` 与地图导入/API错误测试。

## 状态

实现完成，待独立 backend reviewer/tester 复核；本轮未执行真实外部下载、生产数据库、API E2E、部署或 commit。

## 实际改动

- 生产组合根把现有 `import_candidate` 安全导入链注入地图桥接，复用 `common._paper_candidate_hosts` 固定 allowlist；地图读取不触发导入，只有用户点击导入端点才调用。
- 新增 `paper_import_adapter.py`，优先消费节点内服务端冻结的 catalog snapshot（catalog ID、official/prepublication PDF、DOI/arXiv/source）；没有官方 PDF 时才走既有 Semantic Scholar OA 元数据适配器。它不下载、不跟随 redirect、不扩展 host allowlist。
- 桥接仅接收节点冻结的 action `source_url`，拒绝客户端/内部 override、凭据、fragment、localhost 和私网/保留 IP；S2 landing page 不再被当作 `pdf_url`，实际 DNS、host、redirect、PDF 校验仍由既有下载链执行。
- 既有导入结果归一为安全句柄，`paper_id` 作为真实 `document_id` 回写 `store.update_node_import_result(map,node,owner)`；捕获 `PaperDownloadError`/`PaperImportError` 后持久化固定失败/等待登录状态；不把 Semantic Scholar ID 冒充 `catalog_paper_id`，不暴露异常文本。
- `ImportRequest` 保留为空动作模型（禁止 `source_url`），空 `{}` 可接受；路由调用 `service.import_node(map_id,node_id,owner_id)` 不传 URL override。
- 地图路由的 store 读写异常统一固定 `503/MAP_STORAGE_UNAVAILABLE`；404/409 语义保持，异常文本不进入响应。列表、地图详情、删除、job、events 等直接 store 入口均纳入错误边界。

## 验证

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/opt/anaconda3/bin/pytest -q tests/literature_maps`（临时 stub 仅满足本机缺失的 `langchain_ollama`） | 0 | 52 passed；含 landing/客户端 URL 拒绝、冻结官方 PDF 优先、无 OA 固定失败、身份冲突、导入异常持久化、API错误注入 |
| `/opt/anaconda3/bin/python -m ruff check ...`（6 个本轮应用/测试文件） | 0 | All checks passed |
| `/opt/anaconda3/bin/python -m py_compile ...` + `scripts/check_test_layout.py` | 0 | 语法与测试布局通过 |
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/literature_maps` | 0 | 50 passed；使用仓库已有 site-packages，并仅以临时 stub 补齐本机缺失的 `langchain_ollama`，未改仓库依赖 |

## 明确限制

- 未调用真实 Semantic Scholar/OA/下载器/知识库，不将 fake importer 测试当作真实 API E2E；生产 importer 会在用户点击后才解析/下载，依赖部署已有论文导入配置。
- 未运行全量回归、未启动服务、未读写 `.env`、未提交或推送；Spec/Task 状态与统一 changelog 由主会话收口。仓库 `.venv` 的 Python 链接仍指向已不存在的 PyCharm 路径，因此本轮用已有 site-packages 运行离线地图域测试；未将其当作真实 API E2E 或部署验收。

## 最终接缝修复（2026-10-19）

- 路由将 service 的 `INVALID_MAP_SCOPE` 固定映射为 400 和不含请求值的中文提示；存储异常仍固定为 503，保留既有 404/409 分支。
- HTTP 测试改为调用真实地图 service 组合根，以未知 source/conference 验证 400、固定错误码和无 raw input；未创建地图（service 在存储写入前完成 scope 校验）。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `PYTHONPATH=.venv/lib/python3.11/site-packages:/tmp/researchagent-test-stubs /opt/anaconda3/bin/pytest -q tests/literature_maps/test_map_api_errors.py` | 0 | 6 passed |

本次仍未执行真实论文下载、生产数据库写入、服务启动、全量回归、部署或 commit。

交接日志：`.codebuddy/agent-logs/spec-043/task-03/backend-dev/20261019-000000.md`
