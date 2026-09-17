# Spec030 验收评审：跨论文证据矩阵与深度研究报告

- 评审对象：[`docs/sdd/specs/030-research-evidence-reporting.md`](../specs/030-research-evidence-reporting.md)
- 评审范围：Task02–Task06、实际 diff、唯一全量回归、运行时与浏览器 smoke
- 评审时间：2026-09-17（Asia/Shanghai）
- 评审角色：Task06 收口审计 / QA 视角
- 评审模型：Luna high（临时任务）
- 分派方式：主 Agent 子任务分派

## 结论：通过（PASS）

历史首轮审查曾因报告错误路径的 P1 阻塞，以下原始记录保留用于追溯；修复复验结果见文末“复验与签字”。

Task02–05 的固定样本和定向测试证明了支持/冲突/上下文/缺失矩阵、引用 manifest、三格式生成、安全 DOM、键盘和窄屏静态合同；浏览器页面 smoke 也通过。但报告版本读取错误路径存在本次代码引入的 P1：未知报告请求应返回 404，却在错误响应构造时因 `EvidenceReportError.message` 缺失而返回 500。

证据：

- `backend/app/api/routes_research.py:1475-1477` 捕获 `EvidenceReportError` 后读取 `exc.message`。
- `backend/app/research/application/report_generation.py:37-39` 初始化只调用父类，没有设置 `.message`。
- 真实请求 `GET /api/research-tasks/does-not-exist/reports/1?format=json` 返回 500，服务日志记录 `AttributeError: 'EvidenceReportError' object has no attribute 'message'`。

该问题违反接口失败语义和 fail-closed 约束，Task06 不代改业务代码；验收签字留空，Spec030 保持“实施中”。完整证据见 [`Task06 收口审计`](../plans/030/artifacts/task-06/acceptance-audit.md)。

## 验收矩阵

| 验收项 | 结果 | 依据 |
|---|---|---|
| 支持/冲突/上下文/缺失关系保留 | 通过 | `tests/test_spec030_contract.py:207-238`、`tests/test_spec030_matrix.py:26-41` |
| Citation manifest 逐 Claim 回查 | 通过（静态/定向） | `tests/test_spec030_contract.py:135-191`、`tests/test_spec030_report_generation.py:36-45` |
| 失效 Evidence 降级且历史保留 | 通过（定向） | `tests/test_spec030_matrix.py:56-71`、Task03 报告 |
| Markdown/HTML/JSON 语义一致 | 通过（定向） | `tests/test_spec030_contract.py:254-273`、Task04 报告 |
| XSS / DOM 边界 | 通过（静态） | `tests/test_spec030_frontend.py:35-39`；无 `innerHTML`，动态内容走 `textContent`/DOMPurify |
| 键盘与窄屏 | 通过（静态） | `frontend/index.html` 按钮/ARIA；`frontend/styles.css:3590-3629` |
| 版本不可覆盖 | 通过（定向） | `tests/test_spec030_report_generation.py:102-110` |
| 未知矩阵任务 HTTP | 通过 | 真实 smoke：404 `TASK_NOT_FOUND` |
| 未知报告 HTTP | **不通过，P1** | 真实 smoke：预期 404，实际 500 |
| 页面/资源浏览器 smoke | 通过（有限） | In-app Browser 页面 200；工作台、矩阵/报告控件存在；console error=0；无虚构报告数据 |
| 唯一全量回归 | **不通过** | 2495 passed、5 failed、67 subtests、退出码 1 |

## 全量回归记录

```text
.venv/bin/python -m pytest -q
退出码：1
结果：2495 passed, 5 failed, 67 subtests passed, 5 warnings，528.69s
失败：4 项既有 memory/evolution worker 异步/摘要断言；1 项既有 Spec034 资源版本断言仍要求 styles.css?v=53，而当前资源为 v54。
```

附加门禁：`node --check frontend/research-tasks.js`、指定后端 `py_compile`、`git diff --check` 均退出码 0。

## 签字

- 开发主管（tech-lead）：待 P1 修复和回归复验，不签字。
- QA/Task06：不通过（P1 阻塞）。

## 复验与签字（2026-09-17）

- 报告路由已统一使用 `str(exc)`，避免二次 AttributeError；矩阵未就绪为 `409/REPORT_NOT_READY`，未知报告版本为 `404`，非法格式为 `406`。
- 后端复核：PASS；Spec030 定向合同/矩阵/报告测试共 16 passed，py_compile 与 git diff --check 通过。
- 全量回归：`.venv/bin/python -m pytest -q` 退出码 0，2504 passed、1 skipped、67 subtests passed、5 warnings。
- 运行时 smoke：临时 18080 服务的 health/root=200，未知矩阵=404，未知报告=404，非法格式=406；服务随后已停止。
- 结论：Task06 与 Spec030 验收通过，允许进入提交与后续 Spec 门禁。

签字：

- 开发主管（tech-lead）：通过（PASS）。
- QA/Task06：通过（PASS）。
