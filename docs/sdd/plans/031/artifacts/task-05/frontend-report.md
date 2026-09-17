# Spec031 Task05 前端交接报告

## 固定字段

- 结果状态摘要：**GO（前端定向合同与静态安全检查通过）**。
- spec：031 — 动态模型路由与资源调度优化
- task：Task05 — 实现路由解释与基准界面
- 角色：frontend-dev
- 执行模型：Luna high（临时执行）
- 验收范围：只读路由解释、事件时间线脱敏摘要、受控基准摘要卡；未新增后台 read API，未修改 backend，未运行全量回归，未提交/推送。
- 开始/结束：2026-09-17 15:55 CST – 16:05 CST（约 10 分钟）。

## 改动文件

- `frontend/research-tasks.js`
  - 新增 `routingInsightText()`：仅按白名单渲染模型名、`fast/strong` tier、有限 Worker 额度、有限资源降级文案、有限 reason 摘要和 `fast → strong` 升级。
  - 模型名/原因拒绝 URL、主机路径、prompt/answer/thought/chain/owner token 等敏感内容；未知字段不进入渲染。
  - 新增 `normalizeBenchmarkSummary()` 与 `benchmarkMetricText()`：仅接收 warm/cold 的 TTFT、throughput、峰值内存、失败率；所有数值有限且有上界，失败率按 0–1 比例显示为百分比。
  - 从已有 task detail / event payload 的 `benchmark_summary`、`benchmark`、`routing_benchmark` 投影基准，不调用新 API；无数据显示“暂无指标／探针不可用”。
  - 新增只读 `renderBenchmarkSummary()`，active/shadow 仅为文本标签，无激活或编辑动作。
- `frontend/index.html`
  - 增加 `research-benchmark-section`、`research-benchmark-metrics` 等稳定 DOM 契约。
  - `research-tasks.js` 资源版本从 `v=9` 升为 `v=10`，保留历史兼容标记。
- `frontend/styles.css`
  - 增加 `#research-view` 作用域的基准卡/指标样式，不改变现有 Session、ProcessingTree、报告结构。
- `tests/test_spec031_frontend.py`
  - 新增 Node 投影测试与静态 DOM/XSS/版本/敏感字段合同。

### Reviewer P1 修复（2026-09-17）

- `boundedNumber()` 现在只接受真实 finite `number` 或无空白十进制字符串（不接受 `null`、`undefined`、空串、`false`、`Infinity`、指数/十六进制/带空白字符串），无效值返回缺失 `null`；Worker grant、TTFT、throughput、失败率和峰值内存统一复用该解析器。
- `benchmarkMetricText()` 也重新执行同一边界解析，避免直接格式化未归一化值。
- 路由模型名/reason 的 fail-closed 规则新增 `/opt`、`/mnt`、`/workspace`、`/var`、`/private`、`/Users`、`~/`、Windows 盘符、UNC、`file://`、localhost、IPv4 和 `::1` 拒绝；命中后不渲染。
- 回归测试新增上述伪 0 输入及本地路径/主机/IP 敏感值夹具；未修改 `frontend-reviewer` 报告。

### 最后 P1 路径修复（2026-09-17）

- `safeRoutingText()` 对路由模型名/reason 统一拒绝任意 `/` 或 `\\` 路径 token，覆盖任意 Unix 绝对路径（含 `/srv`、`/Applications`、`/data`、`/root`、`/usr` 等未枚举目录）、相对路径 `../`/`./`、`foo/../bar`、Windows 盘符、UNC 与反斜杠片段；同时继续拒绝 URL、`file://`、localhost/IP。
- 该策略保留不含路径的正常 reason，例如 `fast output invalid after one retry`。
- 回归测试新增所有上述目录、相对路径、路径片段及正常 reason 夹具；未修改 `frontend-reviewer` 报告。

## 验证命令 / 退出码 / 结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/research-tasks.js` | 0 | 通过 |
| `node tests/test_frontend_spec034_task09.js` | 0 | `Task09 frontend Session/Fake-DOM contract: PASS` |
| `.venv/bin/python -m pytest --noconftest -q tests/test_spec031_frontend.py tests/test_frontend_spec034_task07_contract.py tests/test_frontend_spec034_task08_contract.py tests/test_frontend_spec034_task09_contract.py tests/test_frontend_spec034_task04_contract.py tests/test_spec030_frontend.py tests/test_spec029_frontend_acquisition_progress.py tests/test_frontend_spec028_task05_contract.py tests/test_spec028_recovery_api_ui.py` | 0 | **43 passed** |
| `git diff --check` | 0 | 通过 |
| 静态敏感字段扫描（`innerHTML`、直接 `payload.prompt/answer/thought/chain_of_thought/owner_token/host_path`） | 0 | 未发现直接渲染路径；敏感词仅存在于拒绝规则与测试夹具 |

最后 P1 修复后同一组前端验证仍为：`node --check` 退出码 0、既有 Task09 Node 合同退出码 0、**43 passed**、`git diff --check` 退出码 0。

## 边界与阻塞

- Task04 后端报告说明 `AdaptiveRoutingService` 的 production runtime 接入与 Task02 benchmark provenance 仍留给 Task06；本 Task 不补后端、不伪造指标。
- 当前事件安全白名单未承诺所有 `worker_grant/resource_reason` 字段进入旧事件流；前端支持已有 `granted`/安全投影字段，缺失时按无指标/无资源摘要处理。
- 未启动服务、Ollama 或浏览器 smoke；由主 Agent 在 Task06 做最终全量回归、部署和运行时验证。

## 三项前端自查

1. class 与 CSS：基准 DOM 的 `research-benchmark-*` class 均有 `#research-view` 作用域样式。
2. `?v=N`：`research-tasks.js` 已升至 `v=10`，旧 `v=2/v=3/v=9` 标记保留。
3. XSS：动态内容全部使用 `textContent`；未知字段 fail-closed；没有新增 `innerHTML` 或 `dangerouslySetInnerHTML`。

## 进展日志

- `.codebuddy/agent-logs/spec-031/task-05/frontend-dev/20260917-155533.md`
