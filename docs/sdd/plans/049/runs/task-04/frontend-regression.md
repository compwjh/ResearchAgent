# Spec-049 / task-04 前端单端回归报告

结论：PASS —— 单端回归通过，阻塞项 0

单端绿灯不代表 Spec 可收口（全量回归 / E2E / 部署验证由后续阶段执行）。

## 1. 定向新增静态契约

- 命令：`.venv/bin/python -m pytest -q tests/frontend/test_literature_map_tabs_and_refresh_icon.py`
- 输出：`............ [100%]` / `12 passed in 0.19s`
- 退出码：0
- 通过数量：12

## 2. 前端单端全量

- 命令：`.venv/bin/python -m pytest -q tests/frontend/`
- 输出：`628 passed in 131.20s (0:02:11)`；首次前台调用返回「命令执行超时」（stdout 空、未取得退出码），同一命令后台完整执行取得本输出与退出码
- 退出码：0
- 通过数量：628

## 3. 按钮基线定向

- 命令：`.venv/bin/python -m pytest -q tests/frontend/test_frontend_button_affordance_contract.py::test_button_count_is_frozen`
- 输出：`. [100%]` / `1 passed in 0.22s`；基线 56
- 退出码：0
- 通过数量：1

## 4. 窄屏几何定向

- 命令：`.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_mobile_contract.py`
- 输出：`............ [100%]` / `12 passed in 20.58s`；390px 视口命中；`visibleMap.height >= 150` 字面位于 `test_frontend_map_layout_viewport.py:237`，由命令 2 全量覆盖
- 退出码：0
- 通过数量：12

## 5. 版本与 marker 冻结定向

- 命令：`.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_groups_exports.py tests/frontend/test_frontend_map_header_actions_readability.py`
- 输出：`.............. [100%]` / `14 passed in 1.23s`
- 退出码：0
- 通过数量：14

## 6. JS 语法

- 命令：`node --check frontend/literature-maps.js`
- 输出：空（无 stdout / stderr）
- 退出码：0
- 通过数量：不适用（非 pytest 命令）

## 7. 测试布局门禁

- 命令：`.venv/bin/python scripts/check_test_layout.py`
- 输出：`test layout: ok`
- 退出码：0
- 通过数量：不适用（非 pytest 命令）

## 8. diff 空白

- 命令：`git diff HEAD --check`
- 输出：空
- 退出码：0
- 通过数量：不适用（非 pytest 命令）

## 9. 冻结语义复核（只读）

- 命令 9A：`python3 -c "import re,pathlib;s=pathlib.Path('frontend/index.html').read_text();print(re.findall(r'literature-maps\.js\?v=(\d+)',s)[-1],re.findall(r'literature-maps\.css\?v=(\d+)',s)[-1])"`
- 输出 9A：`47 34`
- 退出码 9A：0
- 命令 9B：`grep -rn "in INDEX" tests/frontend | wc -l`
- 输出 9B：`211`
- 退出码 9B：0
- 通过数量：不适用（非 pytest 命令）

## 退出码汇总

1:0 / 2:0 / 3:0 / 4:0 / 5:0 / 6:0 / 7:0 / 8:0 / 9A:0 / 9B:0

## 前端单端通过数量

628 passed（命令 2 `tests/frontend/` 全量，Spec-048 基线 628）

## 阻塞项

0（无失败用例）
