# Spec043 Task10 后端独立评审

日期：2026-10-27（Asia/Shanghai）  
角色：backend-reviewer  
范围：Task10 后端样式实现；仅读取 backend 与对应测试，未修改实现或测试。

## 结论

首轮评审结论为 **Block**，发现两项 P1；经本轮复审，两项修复均验证通过，**Block 已解除**。首轮详细发现与证据保留于下文，本轮证据见“复审记录”。

## 问题清单

### [P1] HTTP 层把布尔透明度转换为合法数值后接受

文件：backend/app/api/routes_literature_maps.py:64、575

NodeStyleRequest 将 fill_opacity 声明为普通 float。当前 Pydantic 配置会把 true 解析为 1.0；路由随后传递 payload.model_dump()，因此 store 的 _validate_node_style 虽然会拒绝 bool，也只能收到 1.0，最终保存该值并递增 revision。复现：NodeStyleRequest(fill_mode="filled", fill_opacity=True).model_dump() 得到 {"fill_mode": "filled", "fill_opacity": 1.0}。这违反 node_style 对 bool 的严格拒绝约定。

修复方向：在 Pydantic 转换前拒绝 bool，或通过自定义校验确保原始输入 bool 无法转换为数值；新增 HTTP PATCH 布尔值拒绝用例。

### [P1] 新建地图的成功响应缺少默认 node_style

文件：backend/app/literature_maps/infrastructure/store.py:493-509、backend/app/api/routes_literature_maps.py:214-221

实际创建路径使用 create_map_with_job。该方法构造的 view_settings 没有 node_style；POST 路由立即对 result.map.to_dict() 序列化并返回，因此成功创建响应没有默认样式。相比之下，非原子兼容路径 create_map 明确包含 filled / 0.3。临时目录上的 API 复现返回 202 且有 map_id，但创建响应的 view_settings.node_style 缺失；随后 GET 经过 _map 才显示默认值。这使创建响应与已确认的“新图默认 filled、透明度 0.3”契约不一致。

修复方向：在 create_map_with_job 构造初始 map view_settings 时写入默认 node_style，并覆盖创建响应的默认值测试。

## 已通过检查

- SQLite v6→v7：SCHEMA_VERSION 为 7。initialize 在 BEGIN IMMEDIATE 后检查并增量添加 color_override，再执行修复、索引和版本 marker；异常路径显式 ROLLBACK。用 /private/tmp 临时数据库模拟 v6（去除该列并设置 marker=6），在迁移中途注入异常后确认新增列和 v7 marker 均回滚；恢复后重试两次，schema 为 7，旧节点 title、position 保留，color_override 为 null。结论：无损、可重试、幂等。
- node-styles 请求：NodeStylesRequest 使用 extra=forbid，expected_revision、node_ids、color_override 三项均必填；显式 null 可通过模型验证，非法 HEX 会被 pattern 拒绝，重复 ID 返回 INVALID_NODE_IDS，列表限制 1–200。
- 原子性及并发边界：store 在单个 BEGIN IMMEDIATE 事务中验证 map owner、revision、所有节点存在且未移除；校验全部完成后才更新颜色并递增 revision。未知或已移除节点在首次 UPDATE 前失败，异常由事务回滚；group_id 和未选节点不被更新。
- node_style store 校验：仅接受 fill_mode 与 fill_opacity 两键；检查允许模式、bool、有限数及 0–1 范围。HTTP 层存在上述 bool 转换缺陷；NaN 与正负无穷在 API 模型层被拒绝。
- GET 只读：地图详情 GET 调用 get_map/latest_job；graph/node/export 路径使用查询读取。_map 对旧记录补充样式默认值只修改载入内存的字典，不写回数据库。
- schema 分界与导出：graph/node 保持 literature-map-v1；导出使用 literature-map-export-v2。export_map、_export_view_settings 与 _export_node 显式构造白名单，新增导出 node.color_override 和 map.view_settings.node_style；不序列化 owner_id、recent_colors 或临时 preview。

## 验证记录

1. 精准 pytest：设置 MEMORY_DB_PATH 与 TMPDIR 到本次新建的 /private/tmp 临时目录，使用 /Users/wjh/ResearchAgent/.venv/bin/python，运行 tests/literature_maps/test_map_node_styles.py、tests/literature_maps/test_map_analysis_queue.py::test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry、tests/literature_maps/test_map_export.py::test_json_export_is_whitelisted_owner_scoped_and_directional。退出码 0，8 passed。未运行全仓回归。
2. v6→v7 中断回滚、重试、幂等性和旧字段保留：/private/tmp 临时数据库脚本，退出码 0，PASS。
3. HTTP/Pydantic 边界：布尔透明度解析为 1.0；NaN/正负无穷被拒绝；node_styles 显式 null 可通过模型验证。
4. 新图创建 API：临时数据库 POST 返回 202；创建响应 node_style 缺失，后续 GET 返回 filled / 0.3，复现上述缺陷。

初次精准测试未隔离 MemoryRepository 数据库，创建请求触发 SystemRuleUnavailableError（memory schema migration failed; startup is fail-closed），表现为 503，导致测试夹具读取 map_id 时 KeyError。将 MEMORY_DB_PATH 和 TMPDIR 指向 /private/tmp 新目录后，精准测试通过；没有读取 .env、访问生产数据库、网络或外部服务。

## 首轮汇总

| 级别 | 数量 | 状态 |
|---|---:|---|
| P0 | 0 | pass |
| P1 | 2 | block |
| P2 | 0 | pass |

首轮 Verdict: **Block — 两项 P1 必须修复后再复审。**


## 复审记录（2026-10-27）

复审范围：仅复查首轮两项 P1 修复及迁移回滚；根据当前实现与新增 TestClient 用例核对，未运行 Git 命令、全仓测试、部署或网络访问。

- 布尔透明度缺陷已解除：NodeStyleRequest 在 float 转换前检查原始值并拒绝 bool（routes_literature_maps.py:66-71）；HTTP 参数化测试分别覆盖 true 和 false，均要求 422，且验证 revision 保持 0、默认 node_style 不变（test_map_node_styles.py:180-196）。
- 创建响应缺省样式缺陷已解除：create_map_with_job 初始 view_settings 已包含 filled / 0.3（store.py:493-514）；新增 API 测试对照创建 POST 响应与后续 GET，二者均为同一默认值（test_map_node_styles.py:166-177）。
- schema 迁移 rollback 定向用例通过：test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry。
- 隔离：本次新建的 /private/tmp 临时目录承载 LITERATURE_MAP_DB_PATH、MEMORY_DB_PATH、MEMORY_DIR、PAPER_DISCOVERY_DB_PATH、KB_DIR、QDRANT_PATH、XDG_CACHE_HOME、HF_HOME、TRANSFORMERS_CACHE 与 TMPDIR；设置 PYTHON_DOTENV_DISABLED=1、LANGFUSE_ENABLED=false，pytest 禁用 cacheprovider。未访问生产数据库、.env、知识库、网络或外部服务。
- 精准命令：/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -p no:cacheprovider -q tests/literature_maps/test_map_node_styles.py::test_map_create_response_includes_default_node_style tests/literature_maps/test_map_node_styles.py::test_view_style_rejects_boolean_fill_opacity_over_http tests/literature_maps/test_map_analysis_queue.py::test_schema_upgrade_rolls_back_all_incremental_changes_and_can_retry
- 退出码：0；结果：4 passed（布尔参数化用例覆盖 true 与 false）。

### 复审汇总

| 级别 | 未解决数量 | 状态 |
|---|---:|---|
| P0 | 0 | pass |
| P1 | 0 | pass |
| P2 | 0 | pass |

复审 Verdict: **Approve — 首轮 Block 已解除。**
