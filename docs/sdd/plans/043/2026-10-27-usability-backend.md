# Spec043 Task10 后端实现交接

日期：2026-10-27（Asia/Shanghai）  
角色：backend-dev  
范围：仅地图后端及后端 tests；未部署、未访问真实 DB/KB/网络来源、未下载模型、未提交 Git。

## 已实现契约

- SQLite schema 从 6 增量到 7：`literature_map_nodes.color_override TEXT NULL`，启动初始化中以 `BEGIN IMMEDIATE` 包裹 DDL、修复、索引和版本 marker，列存在时跳过，重复启动幂等。旧节点的 identity/position/group/其他字段保留且 override 默认为 `null`。[store.py:40](../../../backend/app/literature_maps/infrastructure/store.py:40)、[store.py:339-350](../../../backend/app/literature_maps/infrastructure/store.py:339)
- `MapPaper.color_override` 进入 `to_dict()`；graph/node 仍返回 `schema_version: literature-map-v1`，只增量增加 `color_override` 字段。[models.py:93-148](../../../backend/app/literature_maps/domain/models.py:93)、[service.py:278-286](../../../backend/app/literature_maps/application/service.py:278)
- `PATCH /api/literature-maps/{map_id}/node-styles` 请求严格为三个必填字段：`expected_revision`、`node_ids`（1–200，唯一）、`color_override`（`#RRGGBB` 或显式 `null`）。成功响应示例形状：

  ```json
  {
    "schema_version": "literature-map-v1",
    "map_id": "…",
    "revision": 3,
    "node_ids": ["…"],
    "color_override": "#ABC123",
    "nodes": [{"node_id": "…", "group_id": null, "color_override": "#ABC123", "…": "旧字段"}]
  }
  ```

  owner/map existence、revision、节点身份、未移除状态和颜色值均在同一事务内检查；任何失败不写入、不改 revision、不改 group_id 或未选节点。[routes_literature_maps.py:132-150,338-354](../../../backend/app/api/routes_literature_maps.py:132)、[store.py:686-736](../../../backend/app/literature_maps/infrastructure/store.py:686)

- `PATCH /api/literature-maps/{map_id}/view` 新增正式 `node_style`：`fill_mode` 为 `filled|outline`，`fill_opacity` 为有限 `0..1`；未知字段/越界被拒绝，`filters.node_style` 也被拒绝。新图默认 `{"fill_mode":"filled","fill_opacity":0.3}`，旧图读取同样补默认；样式保存在 `view_settings.node_style`，不写入 `filters`。[routes_literature_maps.py:60-76](../../../backend/app/api/routes_literature_maps.py:60)、[store.py:603-630](../../../backend/app/literature_maps/infrastructure/store.py:603)
- JSON export 升级为 `literature-map-export-v2`；保留既有白名单字段并增加 node `color_override` 与 map `view_settings.node_style`，不输出 owner、recent colors、预览/临时状态。[service.py:365-395](../../../backend/app/literature_maps/application/service.py:365)、[service.py:1650-1684,1788-1808](../../../backend/app/literature_maps/application/service.py:1650)

## 错误合同

- 缺字段、额外字段、非法 HEX/opacity：FastAPI 422；重复 node_ids：400，`detail.code=INVALID_NODE_IDS`。
- owner 不匹配或节点不存在：沿现有 `LookupError` 进入 404；revision 冲突：409，`detail.code=MAP_CONFLICT`；已移除节点：409，`detail.code=MAP_NODE_REMOVED`。这些路径不会产生部分批量更新。
- 旧 graph/node envelope 仍是 `literature-map-v1`；只有 export 独立变为 `literature-map-export-v2`。

## 验证证据

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `/Users/wjh/ResearchAgent/.venv/bin/python -m py_compile backend/app/literature_maps/domain/models.py backend/app/literature_maps/infrastructure/store.py backend/app/literature_maps/application/service.py backend/app/api/routes_literature_maps.py` | 0 | 语法通过 |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/literature_maps/test_map_node_styles.py` | 0 | 6 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/literature_maps` | 0 | 173 passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python -m ruff check backend/app/literature_maps/domain/models.py backend/app/literature_maps/infrastructure/store.py backend/app/literature_maps/application/service.py backend/app/api/routes_literature_maps.py tests/literature_maps/test_map_node_styles.py tests/literature_maps/test_map_export.py tests/literature_maps/test_map_analysis_queue.py` | 0 | All checks passed |
| `/Users/wjh/ResearchAgent/.venv/bin/python scripts/check_test_layout.py` | 0 | test layout: ok |

新增定向测试覆盖：v7 重启幂等/旧字段保留、单/多节点样式 round-trip、owner/revision/重复/移除/原子回滚边界、view 默认和严格校验、export-v2 白名单。[test_map_node_styles.py:54-258](../../../tests/literature_maps/test_map_node_styles.py:54)

迁移失败回滚证据由既有迁移测试复跑并通过：`test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry` 在 literature_maps 173 项回归中通过；其失败注入后确认增量列/索引/版本 marker 未半写，重试后 schema 为 7。[test_map_analysis_queue.py:708-746](../../../tests/literature_maps/test_map_analysis_queue.py:708)

## 后续与边界

1. backend-reviewer 需独立核对迁移、事务原子性、owner/revision、导出白名单及 `literature-map-v1`/export-v2 分界。
2. backend-tester 需独立复跑上述精准命令，并补真实部署 API E2E（创建/读取→批量改色→view style→revision 冲突→重读→export）；本交接不宣称真实服务已验证。
3. 前端接入应把 `MAP_NODE_REMOVED`/409、网络未知结果待核验与显式 null 恢复分开处理；不要把最近色或临时预览写回后端。
4. 未执行服务启动、真实地图/PNG/全文 ready、浏览器验证；这些留给主会话的跨端验收与部署门禁。

## Task10 后端独立评审 P1 修复（2026-10-27）

### 修复内容

- `NodeStyleRequest.fill_opacity` 增加 Pydantic 转换前验证，拒绝 `true` 和 `false`，避免 bool 被隐式转成 `1.0` / `0.0`；现有有限 `0..1` 数值范围、未知字段及 revision 行为保持不变。[routes_literature_maps.py:60-70](../../../backend/app/api/routes_literature_maps.py:60)
- 原子 `create_map_with_job` 创建的初始 `view_settings` 持久化默认 `node_style: {fill_mode: filled, fill_opacity: 0.3}`，因此 POST 创建响应和后续 GET 一致，不依赖读取时补默认。[store.py:493-511](../../../backend/app/literature_maps/infrastructure/store.py:493)
- 新增真实 TestClient 回归：创建响应默认样式与 GET 对照；HTTP PATCH 对 true/false 均返回 422，revision 与默认样式不变。[test_map_node_styles.py:166-196](../../../tests/literature_maps/test_map_node_styles.py:166)

### 验证记录

所有测试使用 `/Users/wjh/ResearchAgent/.venv/bin/python`；`PYTHON_DOTENV_DISABLED=1`、`LANGFUSE_ENABLED=false`，`MEMORY_DB_PATH`、`MEMORY_DIR`、`PAPER_DISCOVERY_DB_PATH`、`TMPDIR`、`XDG_CACHE_HOME`、`HF_HOME`、`TRANSFORMERS_CACHE` 均隔离在 `/private/tmp/spec043-task10-backend-20261027/`。pytest 禁用 cacheprovider，py_compile 缓存也定向到该临时目录。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| 定向 RED：`python -m pytest -p no:cacheprovider -q tests/literature_maps/test_map_node_styles.py -k 'map_create_response_includes_default_node_style or view_style_rejects_boolean_fill_opacity_over_http'` | 1 | 预期复现：2 failed、6 deselected；创建响应缺 node_style、bool 请求返回 200。 |
| `python -m pytest -p no:cacheprovider -q tests/literature_maps/test_map_node_styles.py tests/literature_maps/test_map_api.py` | 0 | 10 passed。 |
| `python scripts/check_test_naming.py` | 0 | test naming check passed。 |
| `python scripts/check_test_layout.py` | 0 | test layout: ok。 |
| `python -m pytest -p no:cacheprovider --collect-only -q tests/literature_maps/test_map_node_styles.py` | 0 | 9 tests collected，无 collection error。 |
| `python -m py_compile backend/app/api/routes_literature_maps.py backend/app/literature_maps/infrastructure/store.py tests/literature_maps/test_map_node_styles.py` | 0 | 语法检查通过。 |
| `python -m ruff check --no-cache backend/app/api/routes_literature_maps.py backend/app/literature_maps/infrastructure/store.py tests/literature_maps/test_map_node_styles.py` | 0 | All checks passed。 |

本轮仅完成后端实现与定向验证；未运行全仓回归、部署、Git 操作、生产数据库、知识库或网络访问。
