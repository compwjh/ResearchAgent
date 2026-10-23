# Spec042 移动端地图回归失败诊断

## 范围与结论

- 角色：`frontend-tester`，只读诊断；未修改业务代码、测试、断言、skip 或运行中的服务。
- 候选：`145f9d6`（本候选提交只包含后端离线评估改动；前端地图文件与 Spec043 交付版本一致）。
- 旧全量结果：`3334 passed / 1 failed / 2 skipped / 67 subtests`，退出码 `1`。
- 唯一失败：`tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_drawers_single_pan_and_desktop_boundary[390]`。
- 本次诊断：同一测试以独立进程、独立临时根连续精确重跑 3 次，结果为 **3 passed / 0 failed**；本轮未重现失败。因此不能据此无证认定环境 flaky，也不能把候选标记为已通过。

## 旧失败证据

来源：`/private/tmp/spec042-final-regression-bm7F8l/full-regression.log`，以及 `docs/sdd/plans/042/final-regression-report.md` 的“最新候选追加回归”段。

- 失败参数为 `width = 390`。
- 测试在 `tests/frontend/test_frontend_map_mobile_contract.py:100` 的
  `page.locator('[data-map-id="map-fixture"]').click()` 超时。
- Playwright 日志显示 locator 已成功解析为地图列表按钮，但持续等待 `visible, enabled and stable`，随后反复记录 `element is not stable`，30 秒后 `Locator.click: Timeout 30000ms exceeded`。
- 旧失败发生在全量回归中；原始日志没有 trace、屏幕录制或逐帧 bounding-box 数据，不能从现有证据确定是 CSS 动画、DOM 重建还是宿主资源竞争单独导致。

## 精确重跑证据

以下三次均未使用 `force`、跳过断言或其他测试；每次都用新的 pytest cache/base 临时目录。

1. 命令：
   `.venv/bin/python -m pytest 'tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_drawers_single_pan_and_desktop_boundary[390]' -vv -o cache_dir=/private/tmp/spec042-mobile-diagnosis-run1/pytest-cache --basetemp=/private/tmp/spec042-mobile-diagnosis-run1/pytest-tmp`
   - 退出码：`0`
   - 结果：`1 passed in 2.90s`

2. 命令：
   `.venv/bin/python -m pytest 'tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_drawers_single_pan_and_desktop_boundary[390]' -vv -o cache_dir=/private/tmp/spec042-mobile-diagnosis-run2/pytest-cache --basetemp=/private/tmp/spec042-mobile-diagnosis-run2/pytest-tmp`
   - 退出码：`0`
   - 结果：`1 passed in 2.31s`

3. 命令：
   `.venv/bin/python -m pytest 'tests/frontend/test_frontend_map_mobile_contract.py::test_mobile_map_drawers_single_pan_and_desktop_boundary[390]' -vv -o cache_dir=/private/tmp/spec042-mobile-diagnosis-run3/pytest-cache --basetemp=/private/tmp/spec042-mobile-diagnosis-run3/pytest-tmp`
   - 退出码：`0`
   - 结果：`1 passed in 2.33s`

临时证据根均保留：
`/private/tmp/spec042-mobile-diagnosis-run1`、`/private/tmp/spec042-mobile-diagnosis-run2`、`/private/tmp/spec042-mobile-diagnosis-run3`。

## 代码时序证据与最小建议

当前测试在 `tests/frontend/test_frontend_map_mobile_contract.py:99-100` 先打开列表面板，随后立即点击地图列表项；它只等待 `is-open` class，不等待 CSS transform 完成。移动端面板在 `frontend/literature-maps.css:183-188` 使用 `transform` 的 `.18s` transition。

此外，fixture 通过 `window.LiteratureMaps.setActive(true)` 启动异步 `loadMaps()`；`frontend/literature-maps.js:1250-1254` 在请求完成后调用 `renderMapList()`，而 `renderMapList()`（`1080-1103`）会 `replaceChildren()` 并重新创建列表按钮。上述两处都可能与 click action 的稳定性检查相交，但现有旧日志没有足够数据证明哪一处实际触发了 30 秒持续不稳定。

若后续仍能重现，建议由 frontend-dev/frontend-reviewer 在不改变用户行为的前提下优先验证以下最小方向：让测试/产品路径等待“列表项存在且面板过渡结束”后再点击，或确保地图列表异步刷新不会在交互窗口重建当前按钮；修复前应先用 trace/bounding-box 或 DOM mutation 证据确认根因。本诊断不代改。

## 建议

三次精确重跑均通过，建议保留旧全量失败记录，待当前服务/机器预热与资源状态稳定后，对候选 `145f9d6` 按原隔离计划重新执行全量回归；在新的全量回归退出码为 `0` 前，Spec042 仍不应收口为通过。

## 交接日志

- 进展日志：`.codebuddy/agent-logs/spec-042/task-00/frontend-tester/20261023-061929.md`
- 本报告仅记录诊断证据；未修改生产代码、前端测试或断言。
