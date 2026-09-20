# Spec031 Task05 前端复审报告（最终）

## 结论

**GO（P1 清零；保留 1 项非阻塞 P2）**。严格数值边界、空指标、敏感字段、URL、主机路径/相对路径 fail-closed、XSS、只读 active/shadow、DOM/CSS 作用域和资源版本均通过复核；Session、ProcessingTree、报告及既有 Spec034/030/029 前端合同未回归。

## 评审范围与约束

- Spec031 Task05、前端交接报告及当前工作树最终修复 diff。
- `frontend/research-tasks.js`、`frontend/index.html`、`frontend/styles.css`、`tests/test_spec031_frontend.py`。
- 对照 Spec034 Task04/07/08/09、Spec030、Spec029 前端合同。
- 只读评审；未修改业务代码、未运行全量回归、未启动服务、未提交。
- 评审模型：Luna high（临时执行 frontend-reviewer）。

## 关键复核结论

### 路由解释白名单与安全边界：通过

- `routingInsightText()` 只读取模型名、`fast/strong` tier、Worker 额度、受控资源 reason、有限 reason 和 fast→strong 升级字段；未知字段不进入渲染。
- `safeRoutingText()`（`frontend/research-tasks.js:298-310`）拒绝敏感关键词、HTTP/FTP/file URL，并统一拒绝任意 slash/backslash token。独立 hostile probe 验证 `/srv`、`/Applications`、`/data`、`/root`、`/usr`、`/opt`、`/mnt`、`/workspace`、`../`、`./`、`foo/../bar`、Windows drive、UNC、家目录、localhost 和环回地址均返回空；正常 `fast output invalid after one retry` 仍可展示。
- 动态摘要使用 `textContent`/DOM 节点构造；无新增 `innerHTML`，直接 `payload.prompt/answer/thought/chain_of_thought/owner_token/host_path` 不形成渲染路径。

### 数值边界与空指标：通过

`boundedNumber()`（`:317-323`）只接受 number 或严格非空数字字符串，拒绝 `null`、布尔值、数组、空白字符串、指数形式、`NaN`/`Infinity`；warm/cold 指标和 Worker 额度不再把空值伪装为 `0`。TTFT、吞吐、峰值内存、失败率均有上下界，失败率按 0–1 比例显示。

### 只读与 UI 兼容：通过

- active/shadow 仅以文本状态显示，无策略编辑/激活按钮，也未调用 Task04 控制面 API。
- 新增 `research-benchmark-*` DOM 与 CSS 均在 `#research-view` 作用域内；空摘要有显式空状态。
- Session 计划/审批、ProcessingTree、报告/引用/矩阵和采集 UI 结构未改写。
- `frontend/index.html:772` 使用 `/assets/research-tasks.js?v=10`，旧 `v=2/v=3/v=9` 兼容标记保留。

## P2（不阻塞 GO）

### P2-1：事件基准投影遗漏 `routing_benchmark`

`benchmarkSummaryFromState()`（`frontend/research-tasks.js:373-383`）在 task detail 分支读取 `routing_benchmark`，但事件分支仍只读取 `event.payload?.benchmark_summary || event.payload?.benchmark`（`:377`）。交接报告声明支持三种来源；若事件使用 `routing_benchmark`，界面会显示“暂无指标”。建议后续统一同一字段白名单投影。本项不阻塞当前 Task05，因为当前后端未承诺该字段进入旧事件流，且空状态处理正确。

## 验证结果

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---:|---|
| JS 语法 | `node --check frontend/research-tasks.js` | 0 | 通过 |
| Task05 + Spec034/030/029 前端合同 | `.venv/bin/python -m pytest --noconftest -q tests/test_spec031_frontend.py tests/test_frontend_spec034_task07_contract.py tests/test_frontend_spec034_task08_contract.py tests/test_frontend_spec034_task09_contract.py tests/test_frontend_spec034_task04_contract.py tests/test_spec030_frontend.py tests/test_spec029_frontend_acquisition_progress.py tests/test_frontend_spec028_task05_contract.py tests/test_spec028_recovery_api_ui.py` | 0 | **43 passed** |
| 差异空白检查 | `git diff --check` | 0 | 通过 |
| 修复回归 hostile probe | Node（严格数字 + URL/路径/UNC/host + 正常 reason） | 0 | 通过 |

## 评审边界

本报告仅覆盖 Task05 前端改动；GO 不替代 Task06 的后端/全量回归、浏览器 smoke、部署验证和 Spec031 最终验收。
