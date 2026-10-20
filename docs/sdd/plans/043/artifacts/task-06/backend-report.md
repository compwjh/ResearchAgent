# Spec043 Task06 后端交接报告

## 状态

- 角色：`backend-dev`
- 结果：后端实现完成，等待 `backend-reviewer` 与 `backend-tester` 独立复核；未将 Task06 或 Spec043 标记为完成。
- 范围：仅修改 `backend/**` 与 `tests/literature_maps/`；未修改前端、Task05 业务代码、个人 KB、provider 或生产数据库。
- 开始时间：本角色日志首条时间标记为 `20261021-000000`；精确会话起止时间未单独采集。
- 结束时间：2026-10-21 00:42（Asia/Shanghai）；总耗时未采集，不估算。

## 实现摘要

1. 在 domain 增加 `MapGroup` 投影；SQLite schema 增量至内部版本 5，新增地图专属 `literature_map_groups` 表与索引，删除地图时先清理分组子记录。
2. 在 store 层实现 owner-scoped、同图 revision-CAS 的分组创建/修改/删除与节点归属：名称 trim 后 1–80 字，颜色仅 `#RRGGBB`（输出统一大写），分组最多 200 个；无改动请求不递增 revision；删组仅将关联节点置为未分组，不删除节点、边或论文原件；墓碑节点拒绝归属更新。
3. 在 service/API 层增加：
   - `GET/POST /api/literature-maps/{map_id}/groups`
   - `PATCH/DELETE /api/literature-maps/{map_id}/groups/{group_id}`
   - `PUT /api/literature-maps/{map_id}/nodes/{node_id}/group`
   - `GET /api/literature-maps/{map_id}/export`
4. JSON 导出固定为 `literature-map-export-v1`，只读且不触发 provider/model/download/index；输出地图配置、分组、未移除节点和两端均有效的边。节点/关系 provenance 均使用显式白名单，过滤任意内部字典、诊断异常、prompt、隐藏推理、内部路径、凭据和带敏感 query 的 URL；不输出 owner_id。响应使用固定安全文件名 `literature-map.json`。

## 改动文件

- `backend/app/literature_maps/domain/models.py`
- `backend/app/literature_maps/domain/__init__.py`
- `backend/app/literature_maps/infrastructure/store.py`
- `backend/app/literature_maps/application/service.py`
- `backend/app/api/routes_literature_maps.py`
- `tests/literature_maps/test_map_groups.py`
- `tests/literature_maps/test_map_export.py`

## 验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m py_compile backend/app/literature_maps/domain/models.py backend/app/literature_maps/infrastructure/store.py backend/app/literature_maps/application/service.py backend/app/api/routes_literature_maps.py` | 0 | 通过 |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_groups.py tests/literature_maps/test_map_export.py` | 0 | 4 passed |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_groups.py tests/literature_maps/test_map_export.py tests/literature_maps/test_map_api.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_revision_conflicts.py` | 0 | 14 passed |
| `.venv/bin/python -m pytest -q tests/literature_maps` | 0 | 136 passed |
| `.venv/bin/python scripts/check_test_naming.py` | 0 | 命名门禁通过 |
| `.venv/bin/python -m pytest --collect-only -q tests/literature_maps/test_map_groups.py tests/literature_maps/test_map_export.py` | 0 | 4 collected，无收集错误 |
| `git diff --check -- backend/app tests/literature_maps` | 0 | 通过 |
| `ruff check ...` | 未执行 | 当前环境未安装 `ruff`，未伪造结果 |

## 验收边界与阻塞

- 已覆盖：owner/同图限制、revision 冲突不写入、删组不删节点、墓碑节点限制、布局/分组字段不被导出改写、JSON 方向与数量、移除节点后仅保留有效节点/边、敏感 provenance 白名单。
- 未覆盖：PNG 生成与实际打开（前端职责）、真实部署 API E2E、浏览器导出核查、Task08 全量回归；这些不属于本端本轮验证，不能据此宣称 Task06 完成。
- Task05 的 KB partial/hostile provenance 阻塞未触及，也未放宽门禁。

## 后续动作

1. 主会话读取本报告和实际 diff，保持当前未提交改动与 Task05 用户修改隔离。
2. 分派独立 `backend-reviewer` 检查分层、CAS、白名单和边界；再由 `backend-tester` 按后端精准命令复核。
3. 通过后与前端导出实现接续；PNG/真实浏览器与 Spec 收口证据仍由对应角色/Task08 完成。

进展日志：`.codebuddy/agent-logs/spec-043/task-06/backend-dev/20261021-000000.md`

## 复审修复记录（2026-10-21）

- 复审结论为 BLOCK 的两项 P1 已修复：`add_nodes` 批量路径与 `_insert_node` 预览落库路径现在都要求 `group_id` 对应同一地图的现存分组；批量预检在任何写入前失败，事务整体回滚，不能产生孤儿或跨图归属。
- schema 初始化增加一次非破坏清理：历史节点若引用不存在或跨图分组则置为未分组，不删除节点、边或论文；恢复历史边时也会跳过不符合新边字段约束的污染值。
- 边写入增加受控校验：`basis` 仅接受 `title_abstract`/`title_only`，`model_version` 仅接受安全模型标识，`content_hash` 仅接受固定 64 位十六进制；导出 direct fields 与 provenance 投影再次使用同一安全白名单，非法旧值不能透传。citation 边的 `title`/`abstract` 等允许的空值字段仍保留。
- 为新同图分组不变量补齐受影响的既有预览测试 fixture；未修改 Task05 KB、provider、生产数据库、frontend 或公开范围。

本轮真实验证：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `.venv/bin/python -m py_compile`（全部本轮后端/测试触及文件） | 0 | 通过 |
| `.venv/bin/ruff check`（本轮触及后端/测试文件） | 0 | All checks passed |
| `.venv/bin/python -m pytest -q tests/literature_maps/test_map_groups.py tests/literature_maps/test_map_export.py tests/literature_maps/test_map_store.py tests/literature_maps/test_map_revision_conflicts.py tests/literature_maps/test_map_expansion.py tests/literature_maps/test_map_similarity.py` | 0 | 33 passed |
| `.venv/bin/python -m pytest -q tests/literature_maps`（单独顺序执行） | 0 | 138 passed |
| `.venv/bin/python -m pytest --collect-only -q tests/literature_maps/test_map_groups.py tests/literature_maps/test_map_export.py` | 0 | 6 collected |
| `.venv/bin/python scripts/check_test_naming.py` | 0 | 命名门禁通过 |
| `git diff --check -- backend/app tests/literature_maps` | 0 | 通过 |

一次并行启动整组地图测试时出现 1 项 503 隔离型失败；同一用例单独执行为 1 passed，随后整组测试顺序执行为 138 passed，未将并行瞬态失败伪报为通过。当前状态为 P1 修复已落盘、等待独立 backend-reviewer/backend-tester 复核；本报告不宣称 Task06 或 Spec043 收口完成。
