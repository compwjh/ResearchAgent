# Spec 047 / C 项 —— `--force` 幂等真实重跑 E2E 人工验证详情

生成时间：2026-11-09（Asia/Shanghai）
分支：`feature/spec-047-evaluation-p2-and-observability-fixes`
状态：**已完成真实破坏性重跑，等待用户人工验收**

> **代行留痕（AGENTS.md「门禁执行硬规则」第 3 条）**：本轮交付只含 `.json` 证据文件与 `.md` 文档，
> **不含任何 `.py` / `.js` / `.html` / `.css` 代码文件**，符合唯一允许的代行条件，由主会话落盘。
> 另两处留痕：`docs/sdd/reviews/047-acceptance-review.md` §12、`docs/sdd/spec-status-changelog.md` 本轮追加条目。
> 用户授权原话：「授权你跑。等你修完了生成e2e 人工验证的详情」。

---

## 0. 一句话结论

原先只在 mock 契约里验证过的 `--force` 幂等修复，已在**当前部署版本的真实 Langfuse** 上连跑两次：
每次都删除 6 个同名 dashboard 并重建，widget 总数始终为 **40**、`totalItems=40`、**无孤儿 widget**，
且默认模式仍是「新建 0 / 跳过 6」。真实重跑 **未暴露任何代码缺陷，未改动一行业务代码**。

| 项 | 验证前 | 第 1 次 `--force` 后 | 第 2 次 `--force` 后 |
|---|---|---|---|
| dashboard 数 | 6 | 6 | 6 |
| widget 数 / `totalItems` | 40 / 40 | 40 / 40 | 40 / 40 |
| 孤儿 widget（无 placement 引用） | 0 | 0 | 0 |
| manifest 记录数 | 0（迁移后 40） | 40（新 ID） | 40（新 ID） |
| 结论 | — | **PASS**（8/8 检查） | **PASS**（9/9 检查） |

> 旧 DEFECT 的行为是「每次 `--force` 遗留 40 个孤儿并新建 40 个 → 40 / 80 / 120…」，现已真实证伪。

---

## 1. 前置条件与服务地址

| 项 | 值 |
|---|---|
| 主服务 | `http://127.0.0.1:8000`，`/api/health` 实测 **200** |
| Langfuse UI / API | `http://127.0.0.1:3000`，`/api/public/health` 实测 **200** |
| 项目 slug | `local-proj`（脚本 `setup_langfuse_dashboards.py` 输出 URL 中实际使用） |
| 启动命令（若服务已停） | `cd /Users/wjh/ResearchAgent && ./deploy/start.sh -d`；Langfuse 按其自身部署方式启动 |
| 停止命令 | `./deploy/stop.sh` |
| 凭据 | 取自仓库根 `.env`（`LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`），**不要打印、不要写进文档** |

打开入口（可点击）：

- 看板列表：<http://127.0.0.1:3000/project/local-proj/dashboards>
- 主服务健康：<http://127.0.0.1:8000/api/health>
- Langfuse 健康：<http://127.0.0.1:3000/api/public/health>

---

## 2. 人工验收：逐步操作

> 每一步都按「操作 → 点击后的提示 → 等待条件 → 下一步」给出。若某步不符合预期，跳到 §4。

### 步骤 1 — 确认服务在线

- **操作**：浏览器打开 <http://127.0.0.1:3000/api/public/health>，再打开 <http://127.0.0.1:8000/api/health>。
- **点击后的提示**：前者返回健康 JSON，后者返回含 `status` 的健康体；两者 HTTP 200（本次实测均为 200）。
- **等待条件**：无需等待；若连接被拒，先执行 `./deploy/start.sh -d` 并确认 Langfuse 容器/进程已起，再刷新。
- **下一步**：进入步骤 2。

### 步骤 2 — 打开看板列表，核对 6 个看板

- **操作**：打开 <http://127.0.0.1:3000/project/local-proj/dashboards>（或从左侧导航进入 Dashboards）。
- **点击后的提示**：列表应**恰好出现 6 个**看板，名称如下，无重名、无额外看板、无空看板：

  | # | 名称 | 应含 widget 数 | 直达链接（本次真实 ID） |
  |---|---|---|---|
  | 1 | 01 TTFT 分解与冷启动对比 | 8 | <http://127.0.0.1:3000/project/local-proj/dashboards/cmw8m6o5o00898o8s0imb2kdi> |
  | 2 | 02 分位数与慢请求 | 8 | <http://127.0.0.1:3000/project/local-proj/dashboards/cmw8m6oee00988o8s4buhk4v1> |
  | 3 | 03 吞吐与生成速度 | 6 | <http://127.0.0.1:3000/project/local-proj/dashboards/cmw8m6omy00a18o8stbmp45wu> |
  | 4 | 04 输入规模与延迟相关性 | 6 | <http://127.0.0.1:3000/project/local-proj/dashboards/cmw8m6osm00as8o8s2onwukhx> |
  | 5 | 05 耗时构成占比 | 6 | <http://127.0.0.1:3000/project/local-proj/dashboards/cmw8m6oyk00bj8o8satqwgvk6> |
  | 6 | 06 调用量与延迟趋势 | 6 | <http://127.0.0.1:3000/project/local-proj/dashboards/cmw8m6p4p00ca8o8snp6efxxo> |

- **等待条件**：页面骨架出现后再等 1–2 秒让列表加载完。若项目 slug 不是 `local-proj`，以 UI 左侧导航实际路径为准，看板**名称与数量**才是判据。
- **下一步**：进入步骤 3。

### 步骤 3 — 逐个打开看板，核对 widget

- **操作**：依次点击上表 6 个直达链接。
- **点击后的提示**：每个看板应渲染出对应数量的图表卡片（8 / 8 / 6 / 6 / 6 / 6，合计 **40**），卡片标题与名称见 `force-final-state.json` 的 `data`；不应出现「重复卡片」「空白看板」「404 / not found」。
- **等待条件**：图表数据走异步查询，**等待 5–10 秒**再判定；若图表显示「无数据」，先把页面右上角时间范围调到 `All time` 或最近 30 天再刷新。Langfuse ingestion 有异步延迟（045 证据实测 score 可见需约 8 秒），**不要在打开瞬间就下「数据丢失」结论**。
- **说明**：卡片**有图表容器但数值为空**属时间范围/数据问题，不是本次 `--force` 的幂等判据；判据是「卡片数量与看板数量」。
- **下一步**：进入步骤 4。

### 步骤 4 — 只读回查 widget 总数（关键幂等判据）

- **操作**：在仓库根执行（凭据从 `.env` 注入，不打印）：

  ```bash
  cd /Users/wjh/ResearchAgent
  set -a; . ./.env; set +a
  curl -s -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
    "$LANGFUSE_HOST/api/public/unstable/dashboard-widgets?page=1&limit=100" \
    | .venv/bin/python -c "import sys,json; d=json.load(sys.stdin); print('totalItems=', d['meta']['totalItems'], 'data=', len(d['data']))"
  ```

- **点击后的提示**：期望输出 `totalItems= 40 data= 40`。本次实测 `GET` **HTTP 200**、`totalItems=40`。
- **等待条件**：无；若返回 401，检查 `.env` 是否已 `source`；若返回连接错误，回到步骤 1。
- **下一步**：进入步骤 5（可选复验幂等），或直接跳到 §5 产物查看。

### 步骤 5（可选，破坏性）— 再跑一次 `--force` 复验幂等

> 这一步会再次删除并重建 6 个看板，看板/图表 **ID 会全部变化**。仅在你想亲自复验时执行。

- **操作**：

  ```bash
  cd /Users/wjh/ResearchAgent
  set -a; . ./.env; set +a
  .venv/bin/python scripts/setup_langfuse_dashboards.py --force
  ```

- **点击后的提示**：stdout 首行 `[重建] 只读 widget 清单：40 个（仅备份，不用于删除）`，随后 6 行 `[重建] …`、6 行 `[完成] …`，末行 `新建 6 个，跳过 0 个。`，**进程退出码 0**。
- **等待条件**：等命令完全结束（约数秒）；不要中途 Ctrl-C，否则可能停在「已删 dashboard、尚未重建」的中间态（见 §4 恢复）。
- **下一步**：重复步骤 2–4，期望仍是 6 / 40，且 §5 的 `force-run-2-verification.json` 同类检查全为 `true`。
- **非破坏性替代**：只想验证默认模式幂等，可去掉 `--force`，期望 `新建 0 个，跳过 6 个。` 且 §4 的 ID 完全不变（本次已实测 `widget_ids_unchanged=true`）。

---

## 3. 验收检查清单（勾选后即可签字）

| # | 检查项 | 判据 | 本次自动实测 |
|---|---|---|---|
| 1 | 服务可访问 | `:8000/api/health`、`:3000/api/public/health` 均 200 | ✅ 200 / 200 |
| 2 | 看板数量 | 恰好 6，名称匹配 | ✅ |
| 3 | 看板无重复 | 无同名/额外看板 | ✅ |
| 4 | widget 总数 | `totalItems = 40` | ✅ |
| 5 | 无孤儿 widget | placement 引用 ID 集合 == 线上 widget ID 集合 | ✅ |
| 6 | 两次 `--force` 幂等 | 两次均 6 / 40，第二次相对第一次 ID 全轮换但数量不变 | ✅ |
| 7 | manifest 一致 | 40 条，ID 集合 == 线上 | ✅ |
| 8 | 默认模式零写入 | 新建 0 / 跳过 6 / ID 不变 | ✅ |
| 9 | 契约测试 | `9 passed`，退出码 0 | ✅ |
| 10 | 失败可恢复 | 备份 + 回滚文件 + 重建命令齐备 | ✅（见 §4 / §6） |

P0 = 0，P1 = 0，准备度 **10/10**（自动证据项）；第 10 项仍需你人工确认恢复步骤可执行。

---

## 4. 失败恢复

| 现象 | 原因 | 恢复动作 |
|---|---|---|
| `:3000` 打不开 / health 非 200 | Langfuse 未运行 | 启动 Langfuse 后刷新；主服务用 `./deploy/start.sh -d` |
| 看板少于 6 个 / 出现 404 | `--force` 中途被打断（已删未建） | 重跑一次不加 `--force` 的命令**不会补建**（同名跳过逻辑只在存在时跳过，缺失的会新建）：`set -a; . ./.env; set +a; .venv/bin/python scripts/setup_langfuse_dashboards.py`。它会补建缺失看板，已存在的跳过 |
| `totalItems > 40` | 出现孤儿 widget | **不要按名称或全量删**。只按 `docs/sdd/plans/047/runs/task-02/widget-manifest.json` 里记录的 ID 调 `DELETE /api/public/unstable/dashboard-widgets/{id}`；若孤儿属历史无 manifest 记录，先从 `force-baseline.json` / `force-final-state.json` 比对出差异 ID 再逐个确认 |
| manifest 内容异常 / 想撤销迁移 | 迁移文件写错 | `cp docs/sdd/plans/047/runs/task-08/widget-manifest.pre-adoption.json docs/sdd/plans/047/runs/task-02/widget-manifest.json`（恢复为 `widgets: []`）。**注意：这会让下一次 `--force` 回到「零删除旧 widget」的冷启动缺口，见 §6** |
| 想恢复验证前的**实体 ID** | — | **不可恢复**。`--force` 是硬删 + 重建，两次重跑后 6 个 dashboard 与 40 个 widget 的 ID 已全轮换；备份只保留定义与 ID 清单，可用于重建等价看板，但无法还原旧 ID。这是 `--force` 固有权衡，不是本次回归 |

回滚到「未迁移 manifest」状态后，如需再次真实 `--force`，必须先重做 §6 的一次性 adoption。

---

## 5. 产物查看路径

全部位于 `/Users/wjh/ResearchAgent`：

| 产物 | 内容 |
|---|---|
| `docs/sdd/plans/047/runs/task-08/force-idempotency-e2e.json` | **总索引**：授权原话、命令与退出码、请求端点、两次 run 实体 ID、最终状态、检查项、产物清单、已知限制 |
| `…/task-08/force-baseline.json` | 执行前真实 GET 原始响应（6 dashboard + 40 widget 完整定义、ID、createdAt、placement） |
| `…/task-08/force-adoption.json` | 一次性 manifest 迁移的前置校验与审计（`placement_ids_equal_live_ids=true` 等） |
| `…/task-08/widget-manifest.pre-adoption.json` | 迁移前空 manifest 备份（回滚用） |
| `…/task-08/force-run-1.txt` / `force-run-1-verification.json` | 第 1 次真实 `--force` stdout（EXIT=0）与 8 项检查 |
| `…/task-08/force-run-2.txt` / `force-run-2-verification.json` | 第 2 次真实 `--force` stdout（EXIT=0）与 9 项检查 |
| `…/task-08/force-final-state.json` | 最终真实 GET 原始响应（HTTP 200）+ 当前 manifest |
| `…/task-08/default-mode.txt` / `default-mode-verification.json` | 默认模式「新建 0 / 跳过 6」与 ID 不变验证 |
| `…/task-08/contract-tests.txt` | `9 passed in 0.34s`，`PYTEST_EXIT=0` |
| `docs/sdd/plans/047/runs/task-02/widget-manifest.json` | 当前生效 manifest（40 条真实 ID） |
| `docs/sdd/plans/045/runs/task-08/dashboard-contract.json` | 045 时点的 `DEFECT` 历史证据，**按边界未改写** |
| `artifacts/spec-047-force-idempotency-manual-e2e.md` | 本文件 |

---

## 6. 已知限制与红线（如实声明）

1. **045 的 `DEFECT` 证据保持原样**。`dashboard-contract.json:92-104` 记录的是 045 时点的历史结论，
   按 Spec047 D4 与授权边界**未改写**；本次真实重跑的结论另行落盘在 `task-08/`，不翻案、不冒充历史证据。
2. **冷启动迁移缺口（本次真实发现并已用数据迁移解决，未改代码）**：Spec047 引入 manifest 时文件为空，
   而线上已有 013/045 时期创建的 40 个历史 widget。若直接跑 `--force`，`old_ids` 为空 → 零删除 →
   遗留 40 个孤儿并新建 40 个，DEFECT 会在首次重跑重现。本次在严格前置校验
   （`placement_ids == live_ids`、`names_match`、`totalItems=40`、无额外 widget）通过后，
   用脚本自身的 `record_widgets()` 把这 40 个真实 ID 一次性纳入 manifest。
   **未改代码**的原因：vendor `DashboardWidget` 无来源标记，脚本无法自动区分手工 widget，
   自动 adopt 会违反 D4「只按脚本自记录 ID 删、禁止按名称/全量删」的红线。
   全新环境若出现「manifest 空 + 线上已有历史 widget」，仍需人工执行同款 adoption。
3. **删除依据只有 manifest ID**。用户手工创建的 widget 不在删除范围；`DELETE` 为硬删不可回滚，
   Langfuse 无 `createdBy` / 来源过滤，因此禁止按名称或全量清理。
4. **不改业务代码、不 push、不合 main**。`origin/main` 仍为 `1b26c76c`，本轮改动只含证据 JSON、
   manifest 数据、评审/台账/文档，并在本地分支 commit。
5. **ID 必然轮换**。`--force` 语义就是删同名 dashboard 后重建，两次重跑后所有看板与图表 ID 都不同于执行前；
   045 的 `dashboard_ids_identical` 只约束**默认模式**幂等，不约束 `--force`。

---

## 7. 人工验收签字

| 项 | 填写 |
|---|---|
| 验收人 | ______________ |
| 验收日期 | ______________ |
| 结论 | ☐ 通过　☐ 不通过（原因：______________） |
| 备注 | ______________ |

> 请按 §2 步骤 1–4 走一遍，勾选 §3 清单后填写本栏。若选择执行 §2 步骤 5 复验幂等，
> 请在备注里注明复跑时间；复跑后 §2 表格里的直达链接 ID 会变化，以 §2 步骤 2 的**看板列表**为准。
