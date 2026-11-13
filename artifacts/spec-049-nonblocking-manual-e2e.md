# Spec-049 人工验收：刷新旋转与请求同步

> 文档只写结论、可复现步骤、事实依据与产物路径。

## 1. 服务地址与启动

| 项 | 值 |
|---|---|
| 地址 | `http://127.0.0.1:8000/`（实际端口 8000） |
| 健康检查 | `curl -s http://127.0.0.1:8000/api/health` → 200 `{"status":"ok"...}` |
| 启动命令 | `./deploy/start.sh -d` |
| 备用端口 | 8000 被占用时 `PORT=8300 ./deploy/start.sh -d`，随后把下面地址换成 `http://127.0.0.1:8300/` |
| 硬刷新 | `Cmd+Shift+R`，确认源代码首个 live 链接为 `literature-maps.js?v=49` / `literature-maps.css?v=36` |

## 2. 桌面路径（≥1024px）

| 步 | 操作 | 点击后提示 / 结果 | 等待条件 | 下一步 |
|---|---|---|---|---|
| 1 | 浏览器打开 `http://127.0.0.1:8000/`，硬刷新 | 三栏工作区渲染完成 | 左栏可见 | 步 2 |
| 2 | 左栏点「文献地图」 | 「地图」tab 默认高亮，画布卡片头部工具区有无文字转圈图标按钮 | 地图列表与画布可见 | 步 3 |
| 3 | 悬停图标，点一次 | tooltip「刷新状态」；点击后图标开始旋转；状态栏 / 列表刷新 | **等旋转停止**（在对应 API 响应结束后，不是固定 700ms） | 步 4 |
| 4 | 连续快速点击 3 次 | 每次都触发刷新、旋转不残留、按钮不卡死 | 所有请求结束、无永久旋转 | 桌面路径完成 |

## 3. ≤760px 窄屏路径

| 步 | 操作 | 点击后提示 / 结果 | 等待条件 | 下一步 |
|---|---|---|---|---|
| 1 | DevTools 设备模式设 ≤760px，用 hash 路由 `http://127.0.0.1:8000/#literature-maps-view` 进视图 | 两个 tab 横向可见可点、默认「地图」 | tab 可点击 | 步 2 |
| 2 | 点画布头部转圈图标按钮 | 触摸目标 44×44、图标旋转、无可见文字残留 | 等旋转结束 | 步 3 |
| 3 | 再点一次 | 旋转再次开始并正常结束 | 状态栏更新 | 窄屏路径完成 |

## 4. 自动化等价验证

- 真实 Chromium E2E：`docs/sdd/plans/049/runs/task-04/browser-e2e.json` → `31/31 PASS`。
- 关键 checks：`spin_removed_after_response=true`、`spin_not_fixed_700ms=true`、`no_unhandled_rejection=true`、`multi_click_3_real_requests=true`、`multi_click_no_spin_residue=true`、`mobile_touch_target_ge_44=true`。
- 单端 `628 passed / EXIT=0`；全量 `4571 passed / 2 skipped / 83.00% / EXIT=0`；部署 4×200。

## 5. 失败恢复

| 现象 | 恢复动作 |
|---|---|
| 图标永久旋转 | 检查 DevTools Console 是否有 unhandled rejection；截图 + 记录 API 响应状态，暂停验收并上报，不以硬刷页面凑通过 |
| 仍是固定 700ms 节奏 | 核对源代码 live 是否 `v=49`（`v=48` 为旧缓存）；硬刷新后重试；仍不符则记录阻塞 |
| 服务不可达 | `curl http://127.0.0.1:8000/api/health`；`connection refused` 用 `./deploy/start.sh -d`（占用改 `PORT=8300`）重启，仍失败记录阻塞、不宣称通过 |
| 窄屏侧栏点不到 | 用 hash 路由 `#literature-maps-view` 直接进视图 |

## 6. 产物查看路径

| 产物 | 路径 |
|---|---|
| 决策台账（NB1–NB10 结论） | `docs/sdd/plans/049/runs/decision-ledger.md` |
| 实现报告 | `docs/sdd/plans/049/runs/task-02/implementation.md` |
| 单端 / 全量回归 | `docs/sdd/plans/049/runs/task-04/frontend-regression.md`、`full-regression.txt` + `.exit` |
| E2E JSON 与截图 | `docs/sdd/plans/049/runs/task-04/browser-e2e.json`、`refresh-desktop.png`、`refresh-mobile.png` |
| 部署验证 / 最终汇总 | `docs/sdd/plans/049/runs/task-04/deploy-verification.json`、`final-verification.md` |
| 真实 API 成功案例 | `artifacts/spec-049-api-sample.md` |
| 三份评审 / 双签 | `docs/sdd/reviews/049-*.md`、`docs/sdd/plans/049/runs/task-04/merge-decision.md` |
| 复盘 / 状态台账 | `docs/sdd/retro/2026-11-13-spec049-nonblocking-followup-closure.md`、`docs/sdd/spec-status-changelog.md` |

## 7. 已知非阻塞项（9 项，保持现状、零改动）

首跑 E2E `28/29 FAIL` 记录（判定口径已修正，证据保留）、Langfuse `:3000` transient 告警、其它视图 404、185 个历史 lint、无真实 CI workflow / branch protection、覆盖率未设 `fail_under`、窄屏 2px 余量、marker 既有脆弱性、10 个工作区未跟踪文件。详见 `docs/sdd/reviews/049-acceptance-review.md` §6。
