# Spec 043 UX 缺陷 — 后端回归报告

- 角色：backend-tester（ECC verification-loop）
- 日期：2026-11-06
- 解释器：`.venv/bin/python` → Python 3.11.16（项目根虚拟环境，已按要求使用）
- 范围：`tests/literature_maps/**`、后端三个改动文件；**未**运行前端测试，**未**运行仓库根全量 pytest（历史耗时 >20 分钟）
- 改动文件：`backend/app/api/routes_literature_maps.py`、`backend/app/literature_maps/infrastructure/store.py`、`backend/app/literature_maps/application/service.py`

## 1. 必跑命令与结果

| # | 命令 | 退出码 | 结果 |
|---|------|--------|------|
| 1 | `.venv/bin/python -m pytest tests/literature_maps/test_map_list_node_count.py tests/literature_maps/test_map_view_initialized_flag.py -q` | 0 | **9 passed** in 1.50s |
| 2 | `.venv/bin/python -m pytest tests/literature_maps -q` | 0 | **238 passed** in 11.44s |
| 3 | `.venv/bin/ruff check backend/app/api/routes_literature_maps.py backend/app/literature_maps/infrastructure/store.py backend/app/literature_maps/application/service.py` | 1 | Found 4 errors（**均为既有告警**，见 §3） |
| 4 | `.venv/bin/python -m pytest tests/literature_maps/test_map_view_initialized_flag.py -q` | 0 | **5 passed** in 1.74s；连跑 3 次全绿，无 flaky |

补充（未列入必跑，用于 Build 阶段冒烟）：

| 命令 | 退出码 | 结果 |
|------|--------|------|
| `.venv/bin/python -c "import backend.app.main"` | 0 | `import-ok` |

## 2. 用例级明细

### 2.1 `test_map_list_node_count.py`（4 passed）

| 用例 | 覆盖的验收点 |
|------|--------------|
| `test_list_node_count_matches_active_graph_nodes_and_keeps_legacy_fields` | `node_count` 与 `/graph` 活动节点数一致（32 == 32）；`set(item)` 精确等于 13 个字段，旧字段全保留且 `node_count` 为纯新增键；`requested_count` 语义不变（20） |
| `test_list_node_count_excludes_removed_tombstones` | 5 个节点移除 2 个后 `node_count == 3`，且与 graph 活动节点数相等（墓碑排除） |
| `test_list_node_counts_are_per_map_and_need_one_batch_query` | 两 map 计数各自正确（7 / 2）；通过 `set_trace_callback` 抓到 COUNT 语句**恰好 1 条**，且 `IN (...)` 绑定 id 恰为所列 map → **无 N+1** |
| `test_list_node_count_is_owner_scoped` | `active_node_counts("another-owner", [map_id]) == {}`（counts 不跨 owner 泄漏）；空 id 列表返回 `{}` 且不发查询 |

### 2.2 `test_map_view_initialized_flag.py`（5 passed）

| 用例 | 覆盖的验收点 |
|------|--------------|
| `test_update_view_marks_view_initialized` | PATCH view 后 GET 返回 `view_settings.view_initialized is True`；直读 SQLite `view_json` 亦为 True（store 层落盘，非仅投影）；不泄漏进 `filters` 桶 |
| `test_update_view_keeps_existing_view_settings_keys` | 首次保存后 view_settings 精确等于预期 6 键；后续仅改 viewport 的保存不丢 filters/layers/label_mode/node_style，标记保持 |
| `test_map_without_saved_view_has_no_view_initialized_key` | 未保存过视图的 map **无** `view_initialized` 键（按存在性透传，默认值不被污染） |
| `test_revision_conflict_rolls_back_and_does_not_mark_view_initialized` | `expected_revision=7` → **409 `MAP_CONFLICT`**；revision 仍为 0，`view_settings` 与 `view_json` 均无标记 → 冲突回滚干净 |
| `test_view_initialized_is_not_an_accepted_request_field` | 把 `view_initialized` 当请求字段提交 → **422**（`extra="forbid"` 封闭 body 未被打开），且不产生副作用 |

## 3. Lint 判定（重要）

命令 3 退出码 1，共 4 条 SIM 类告警：

```
service.py:1141:17  SIM105
service.py:1246:13  SIM105
store.py:2651:25    SIM114
store.py:3151:13    SIM102
```

**基线对比**：将 HEAD 版本导出（`git show HEAD:<path>`）后对同一规则集跑 ruff，得到**完全相同的 4 条**（行号 2626 / 3126，因本次新增 25 行代码而下移）。结论：

- 4 条均为**既有技术债**，与 Spec 043 改动无关；
- 本次新增代码（`active_node_counts`、`view["view_initialized"] = True`、`_export_view_settings` 透传、路由 `node_count` 组装）**零新增 lint 告警**；
- 依「不扩大改动面」原则，本阶段不顺手修改既有告警。建议另立技术债清理项。

## 4. 验收点结论

| 验收点 | 结论 | 依据 |
|--------|------|------|
| node_count 与 graph 活动节点数一致 | **PASS** | 2.1 第 1、2 例 |
| 墓碑排除（removed_at IS NULL） | **PASS** | 2.1 第 2 例 + SQL 断言含 `removed_at IS NULL` |
| 无 N+1（单条批量查询） | **PASS** | 2.1 第 3 例，COUNT 语句数 == 1 |
| owner 隔离 | **PASS** | 2.1 第 4 例 + SQL 含 `m.owner_id=?`、`m.deleted_at IS NULL` |
| 旧字段保留（node_count 纯新增） | **PASS** | 2.1 第 1 例字段集合精确断言 |
| view_initialized 写入 | **PASS** | 2.2 第 1 例（含 SQLite 直读） |
| view_initialized 透传 | **PASS** | 2.2 第 1、2、3 例 |
| view_initialized 不是请求字段（422） | **PASS** | 2.2 第 5 例 |
| conflict 回滚不写标记 | **PASS** | 2.2 第 4 例，409 + revision 0 + 存储无标记，连跑 3 次稳定 |
| 既有 233+ 用例无回归 | **PASS** | 命令 2：238 passed（含新增 9） |

## 5. VERIFICATION REPORT

```
VERIFICATION REPORT
===================

Build:     PASS   (import backend.app.main → import-ok, exit 0)
Types:     N/A    (Python 项目无独立静态类型门禁；未跑 pyright，非本阶段要求)
Lint:      PASS*  (改动代码 0 新增告警；文件级 4 条既有 SIM 告警，HEAD 基线一致 → 非本次引入)
Tests:     PASS   (238/238 passed in tests/literature_maps；定向新增 9/9 passed；覆盖为本阶段用例覆盖，未采集行覆盖率)
Security:  PASS   (无硬编码密钥/sk-/api_key 新增；SQL 全部参数化，owner_id + deleted_at 双条件作用域校验)
Diff:      3 backend files changed (routes_literature_maps.py +6/-2, store.py +25, service.py +4)

Overall:   READY
```

## 6. 阻塞项

无。

## 7. 备注与后续建议

1. **待部署验证**：当前运行中的服务进程仍是**重启前的旧代码**。本次全部验证经由进程内 `TestClient` 完成，已证明源码正确；线上 `GET /api/literature-maps` 是否返回 `node_count`、`GET /api/literature-maps/{id}` 是否透传 `view_initialized`，需服务重启后再做一次只读 GET 核对。本阶段按要求**未重启服务、未调用任何写接口**。
2. 建议为 4 条既有 SIM 告警单独立项清理，避免污染后续每次 ruff 门禁判定。
3. 若 CI 需要行覆盖率数字，建议后续单独引入 `pytest-cov` 采集，本报告未包含覆盖率阈值校验。

---

## 第二轮复核（P1 修复后）

- 角色：backend-tester（ECC verification-loop）
- 复核范围：本轮**新增导出测试**（`GET /api/literature-maps/{id}/export` 的 `view_initialized` 透传）后的后端状态
- 解释器：`.venv/bin/python`（Python 3.11.16，项目根虚拟环境）
- 方式：**只读核对**，未修改代码 / 测试 / spec / 台账；未运行前端测试、**未运行仓库根全量 pytest**
- 结论：**READY**

### R2.1 必跑命令与结果

| # | 命令 | 退出码 | 结果摘要 |
|---|------|--------|----------|
| 1 | `.venv/bin/python -m pytest tests/literature_maps/test_map_view_initialized_flag.py tests/literature_maps/test_map_list_node_count.py -q` | 0 | **11 passed in 1.45s**（预期 11 ✅） |
| 2 | `.venv/bin/python -m pytest tests/literature_maps -q` | 0 | **240 passed in 13.31s**（预期 240 ✅，无 skip / xfail / error） |
| 3 | `.venv/bin/ruff check backend/app/api/routes_literature_maps.py backend/app/literature_maps/infrastructure/store.py backend/app/literature_maps/application/service.py` | 1 | `Found 4 errors`（**4 条既有告警**，见 R2.2） |
| 4 | `.venv/bin/python -c "import backend.app.main; print('import ok')"` | 0 | `import ok` |

补充（稳定性复核，不计入必跑）：

| 命令 | 退出码 | 结果 |
|------|--------|------|
| `.venv/bin/python -m pytest tests/literature_maps/test_map_view_initialized_flag.py -q` | 0 | **7 passed in 1.56s**，连跑稳定，无 flaky |

### R2.2 Lint：4 条告警为既有基线，非本次引入

工作区实测（退出码 1）：

```
service.py:1141:17  SIM105  Use contextlib.suppress(RuntimeError) instead of try-except-pass
service.py:1246:13  SIM105  Use contextlib.suppress(RuntimeError) instead of try-except-pass
store.py:2651:25    SIM114  Combine if branches using logical or operator
store.py:3151:13    SIM102  Use a single if statement instead of nested if statements
```

**与 HEAD 基线逐条比对**（`git show HEAD:<path>` 导出到 `/tmp/ruff_head_baseline` 后跑同一规则集）：

| 规则 | HEAD 基线位置 | 工作区位置 | 判定 |
|------|---------------|------------|------|
| SIM105 | service.py:1141:17 | service.py:1141:17 | 完全一致 |
| SIM105 | service.py:1246:13 | service.py:1246:13 | 完全一致 |
| SIM114 | store.py:2626:25 | store.py:2651:25 | 同一处，行号 +25（第一轮新增 `active_node_counts` 导致，**非本轮**） |
| SIM102 | store.py:3126:13 | store.py:3151:13 | 同一处，行号 +25（同上） |

HEAD 基线输出：`Found 4 errors`，退出码 1 —— **与工作区条数、规则、代码位置一一对应**。结论：

- 4 条均为**既有技术债**，与 Spec 043 两轮改动均无关；
- 本轮仅新增测试文件（`tests/literature_maps/`，untracked），后端源码 diff 与第一轮完全一致（`git diff --stat` → routes `+6/-2`、service `+4`、store `+25`），**零新增 lint 告警**；
- 与第一轮报告 §3 判定保持一致。

### R2.3 本轮增量：新增用例明细

定向用例数 9 → **11**（+2），全量 238 → **240**（+2），增量严格对应：

| 新增用例 | 覆盖验收点 |
|----------|------------|
| `test_map_view_initialized_flag.py::test_export_omits_view_initialized_before_any_view_save` | 未保存过视图的 map，导出 `map.view_settings` **不含** `view_initialized` 键；其余白名单 5 键（filters / viewport / layers / label_mode / node_style）精确不变 → 标记「按存在性透传」，默认值不被污染 |
| `test_map_view_initialized_flag.py::test_export_reports_view_initialized_after_view_save` | 保存视图（`expected_revision=0` → 200）后导出 `view_initialized is True`；`viewport == {4.0, 5.0, 2.0}`、`label_mode == "all"`、`node_style` 真实值（非仅标记）；envelope 契约 `schema_version == literature-map-export-v2`、`revision == 1`、`nodes/edges == []` 未被破坏 |

对应实现（`service.py::_export_view_settings`）：`if settings.get("view_initialized") is True: exported["view_initialized"] = True` —— 测试与实现语义严格一致，且只读 GET，无写副作用。

用例总数核对（`grep -n "^def test_"`）：`test_map_view_initialized_flag.py` 7 例（原 5 + 新增 2）、`test_map_list_node_count.py` 4 例（不变）→ 11 ✅。

### R2.4 验收点复核（第二轮）

| 验收点 | 结论 | 依据 |
|--------|------|------|
| node_count 与 graph 活动节点数一致 / 墓碑排除 / 无 N+1 / owner 隔离 / 旧字段保留 | **PASS**（沿用，未回归） | 命令 2 全量 240 passed，node_count 4 例全绿 |
| view_initialized 写入 / 透传 / 非请求字段 / 冲突回滚 | **PASS**（沿用，未回归） | 命令 1 中相关 5 例全绿 |
| **导出接口按存在性透传 view_initialized** | **PASS**（本轮新增） | 新增 2 例：未保存→无 key 且 5 键精确；保存后→True 且值真实、envelope 契约不破 |
| 既有用例无回归 | **PASS** | 命令 2：240 passed（238 + 2 新增，无失败/跳过） |
| 后端可导入（build 冒烟） | **PASS** | 命令 4：`import ok`，exit 0 |
| Lint 无新增 | **PASS** | 命令 3 的 4 条与 HEAD 基线逐条一致 |

### R2.5 VERIFICATION REPORT（第二轮）

```
VERIFICATION REPORT (Round 2, post-P1-fix)
==========================================

Build:     PASS   (import backend.app.main → "import ok", exit 0)
Types:     N/A    (Python 项目无独立静态类型门禁；未跑 pyright，非本阶段要求)
Lint:      PASS*  (改动代码 0 新增告警；文件级 4 条既有 SIM 告警，与 HEAD 基线逐条一致 → 非本次引入)
Tests:     PASS   (定向 11/11 passed; tests/literature_maps 240/240 passed; 增量 +2 恰为新增导出用例；未采集行覆盖率)
Security:  PASS   (本轮仅新增测试文件；SQL 仍全参数化，owner_id + deleted_at 双条件作用域；无硬编码密钥/sk-/api_key 新增)
Diff:      本轮新增 2 个测试文件 (tests/literature_maps/*)；backend 源码 diff 与第一轮一致 (3 files: +35/-2)

Overall:   READY
```

### R2.6 阻塞项

无。

### R2.7 待部署验证（非阻塞，状态未变）

- 服务进程**尚未重启加载新后端代码**。本轮全部验证经由进程内 `TestClient` 完成，已证明源码行为正确；线上 `GET /api/literature-maps`（`node_count`）、`GET /api/literature-maps/{id}`（`view_initialized`）、`GET /api/literature-maps/{id}/export`（`view_initialized` 存在性透传）的真实响应需**服务重启后再做只读 GET 核对**。
- 按本阶段要求：**未重启服务、未调用任何写接口**，仅执行只读测试与只读 GET 断言。线上只读 GET 结果与源码不一致时，以「待部署验证」标注，不计入本轮 FAIL。
