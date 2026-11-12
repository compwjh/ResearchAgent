# Spec-048 · task-04 · 版本补升报告（literature-maps.css v35→v36）

| 项 | 值 |
|---|---|
| 角色 | `frontend-dev`（版本补升子代理，ECC tdd-guide 精神：契约先行 / 最小改动） |
| Spec / Task | Spec-048 / task-04 |
| 日期 | 2026-11-13（执行时段约 03:31–03:41） |
| 依据 | `docs/sdd/plans/048/runs/task-04/defect-fix.md`：CSS 内容已变但 live 版本仍 `literature-maps.css?v=35` |
| 边界 | **只改 7 个指定文件**，4 批串行（每批 ≤2 文件）、每批 `Read` 回读；禁改 `literature-maps.js` / `literature-maps.css` / 其它测试 / spec / 台账；未执行 git / push / 合并 |
| 结论 | **PASS**：live css 升 `v=36`，全量 `628 passed / EXIT=0`，`[-1]` 冻结语义保持 |

## 一、背景与目标

缺陷修复在 `frontend/literature-maps.css` 的 ≤760px media 块内新增一行 `#literature-maps-view .literature-map-main-tabs { padding: 0 4px; }`（修复 390px 窄屏 `visibleMap.height` 144→152），**CSS 内容已变但 live 版本仍 `literature-maps.css?v=35`**，生产浏览器缓存会命中旧样式。按项目惯例须二次升版到 **`v=36`**，并同步所有精确版本断言。`literature-maps.js?v=48`、`app.js?v=77`、`styles.css?v=77` 与 fixture 对应版本**不动**。

## 二、冻结语义保护（本轮最高风险点）

- `tests/frontend/test_frontend_map_groups_exports.py:54-55` 断言 `re.findall(r"literature-maps\.js\?v=(\d+)", INDEX)[-1] == "47"` 与 `re.findall(r"literature-maps\.css\?v=(\d+)", INDEX)[-1] == "34"`。
- `frontend/index.html` 末尾注释区 `:918` / `:919` 的两条 `Spec048 compatibility marker`（`src="/assets/literature-maps.js?v=47"` / `href="/assets/literature-maps.css?v=34"`）是这两个 `[-1]` 的取值来源；10+ 处 `in INDEX` 冻结断言（`contract.py`、`groups_exports.py:18-19`、`mobile_contract.py:93-95`、`task_d`、`task_j`、`button_affordance`、`memory_return_global`、`expansion`、`map_analysis` 等）继续靠这两条 marker 兼容。
- 本轮**未新增**任何 `literature-maps.css?v=35`（亦未新增 v36）的 INDEX marker，**未改动 / 移动 / 删除**现有两条 marker：`:918/:919` 内容与行号逐字未变，`</body>` 仍在 `:920`。live 引用仍在 `:11`（head 区），marker 恒为 `re.findall` 的最后一次出现。
- **python 实算**：`js_all=['48', '47']`、`css_all=['36', '34']`、`js_last=47`、`css_last=34`；marker 位置 70981 / 71060 < `</body>` 71104，live css 位置 792。`re.findall(...)[-1]` 冻结语义**保持**。
- 逐字未动清单：`groups_exports.py:53,54-55`；`mobile_contract.py:93-95`；`tabs.py:46,48-55,58-76`（含 marker 纯净性与 `[-1]==47/34` 断言）；`readability.py:28,30` 与三态 / 尺寸 / 对比度断言；`index.html` 的 `:8/:903/:905/:918/:919`；fixture `:7/:1135`；`browser_e2e.py:96`。

## 三、4 批改动（7 文件 / 8 处，每批 `Read` 回读）

### 批 1（2 文件 · live 与 fixture）

| 文件 | 行 | 改动 | 不动 |
|---|---|---|---|
| `frontend/index.html` | `:11` | `href="/assets/literature-maps.css?v=35"` → `?v=36` | `:8` styles.css?v=77、`:903` js?v=48、`:905` app.js?v=77、`:918/:919` marker |
| `tests/frontend/fixtures/literature_map_component.html` | `:8` | `literature-maps.css?v=35` → `?v=36` | `:7` styles.css?v=62、`:1135` js?v=48 |

回读：`:11`/`:8` 均为 v36；`:918/:919` 两条 marker 内容与行号未变、`</body>` 仍在 `:920`；其余版本逐字未动。

### 批 2（2 文件 · 精确 live 契约）

| 文件 | 行 | 改动 | 不动 |
|---|---|---|---|
| `tests/frontend/test_frontend_map_header_actions_readability.py` | `:13` / `:27` | docstring `literature-maps.css?v=34` → `v=36`；`MAP_CSS_VERSION = 35` → `36` | `APP_JS_VERSION=74`、`STYLES_VERSION=75`、`:291/:318` 变量引用、三态 / 尺寸 / 对比度断言 |
| `tests/frontend/test_literature_map_tabs_and_refresh_icon.py` | `:47` | `assert css_live == ["35"]` → `["36"]`，错误信息 `v=35`→`v=36` | `js_live == ["48"]`、`:48-55` app.js/styles.css 冻结断言、`:58-76` marker 纯净性 + `[-1]` 断言、其余 11 条断言 |

回读：`:13`=v36、`:27`=36、`:28/:30` 仍为 74/75；`:47`=`["36"]` 且信息 v=36、`:46` 仍为 `["48"]`。

### 批 3（2 文件 · fixture 版本断言）

| 文件 | 行 | 改动 | 不动 |
|---|---|---|---|
| `tests/frontend/test_frontend_map_groups_exports.py` | `:52` | `"/literature-maps.css?v=35"` → `?v=36` | `:53` js v48、`:54-55` 的 `[-1]` 冻结断言 |
| `tests/frontend/test_frontend_map_mobile_contract.py` | `:98` | `"/literature-maps.css?v=35"` → `?v=36` | `:93-95` 的 `in INDEX` 冻结断言 |

回读：`:52`/`:98` 均为 v36；`:53`、`:54-55`、`:93-95` 逐字未动。

### 批 4（1 文件 · E2E 证据脚本）

| 文件 | 行 | 改动 | 不动 |
|---|---|---|---|
| `docs/sdd/plans/048/runs/task-04/browser_e2e.py` | `:95` | `result["checks"]["live_css_v35"]` 键 → `live_css_v36`；判定串 `"literature-maps.css?v=35"` → `"literature-maps.css?v=36"` | `:96` `live_js_v48`；脚本其它逻辑 |

`:121-124` 用 `result["checks"].values()/.items()` 通用聚合，无该键的其它显式引用，改键安全。回读：`:95`=`live_css_v36` + `?v=36`，`:96`=`live_js_v48` 未动。

## 四、验证（真实命令 / 退出码 / 通过数）

| # | 命令 | 真实输出 | 退出码 |
|---|---|---|---|
| 1 | `node --check frontend/literature-maps.js` | 无输出（语法通过） | **0** |
| 2 | `.venv/bin/python -m pytest -q tests/frontend/` | `628 passed in 128.48s (0:02:08)`；nohup 后台 + `/tmp/spec048_ver_full.exit` 取回**真实**退出码 | **0** |
| 3 | `.venv/bin/python scripts/check_test_layout.py` | `test layout: ok` | **0** |
| 4 | Grep + python 复核（冻结语义） | 见下 | — |

验证 4 明细：

- Grep `frontend/index.html`：`:11` `css?v=36`、`:903` `js?v=48`、`:918/:919` 两条 marker 逐字未动；`literature-maps.css?v=35` 在 `frontend/` 与 `tests/frontend/` **均 0 命中**。
- `tests/frontend` 中 `literature-maps.css?v=36` 命中 4 处（fixture `:8`、`groups_exports.py:52`、`mobile_contract.py:98`、`readability.py:13`）；`browser_e2e.py` 仅 `:95` `live_css_v36` + `?v=36`。
- python 实算 `re.findall(...)[-1]` → js `47` / css `34`（详见 §二）。

## 五、三项自查 + regression-guard 前端第 1–4 条

1. **class↔CSS / DOM 契约**：本轮未新增或修改任何 class 名，未改 JS 渲染与 CSS 规则内容（仅改资源版本字符串与测试断言）。`.literature-map-main-tabs` 规则由缺陷修复批次提供（`literature-maps.css:604`），仍由 `literature-maps.js` 渲染，本轮未触碰。✓
2. **资源版本号 `?v=N`**：CSS 内容已变 → live `literature-maps.css?v=36` 同步落地于 `index.html:11` 与 fixture `:8`；`literature-maps.js?v=48`、`app.js?v=77`、`styles.css?v=77` 逐字未动，无需升版。✓
3. **XSS**：本轮未改任何 JS；用户输入仍走 `textContent` / `input.value`，无 `innerHTML` 拼接；`browser_e2e.py` 改动仅为检查字典键与字面串。✓
4. **CSS 作用域**：本轮未改 CSS 内容；缺陷批次新增规则仍带 `#literature-maps-view` 前缀、位于 ≤760px media 块内，无全局污染。✓

## 六、遗留风险与说明

- **历史文档仍写 v35**：`artifacts/spec-048-literature-map-tabs-manual-e2e.md:11,12,53` 等历史证据 / 文档记录 `literature-maps.css?v=35`。它们是当时的真实记录，不是 live 契约或精确断言；本次边界禁止改动其它文件，故原样保留。若需"文档与现状一致"应另派任务处理。
- **`[-1]` 脆弱性依旧**：冻结语义依赖末尾两条 marker 恒为 `literature-maps.*?v=` 的最后一次出现；今后若在 marker **之后**新增任何带 `?v=` 的同名引用，`[-1]` 断言会立即红灯。本轮已实测未触发。
- **未跑真实浏览器 E2E 脚本**：`browser_e2e.py` 本轮仅同步检查键 / 字符串，未实际执行（需服务与 Playwright 浏览器）。全量 `pytest -q tests/frontend/`（628 passed）已覆盖静态与既有浏览器用例。
- **缓存生效依赖部署**：只有部署后浏览器重新请求 `/assets/literature-maps.css?v=36` 才使新样式生效；硬刷新 / 清站点缓存提示见历史 e2e 文档。
- 未改 spec / 台账 / 其它测试；未执行 git / push / 合并。

## 七、签字

`frontend-dev` · 2026-11-13

产出文件：`docs/sdd/plans/048/runs/task-04/version-bump.md`
进展日志：`.codebuddy/agent-logs/spec-048/task-04/frontend-dev-version/20261113-033121.md`
