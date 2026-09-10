# Spec015 Task08 回归稳定性修复报告

- 执行角色：初级开发（junior-dev）
- 执行时间：2026-09-05 01:07–01:21（Asia/Shanghai）
- 关联任务：`docs/sdd/plans/015/task-08-tests-ranking-and-security.md`
- 关联 Spec：`docs/sdd/specs/015-security-paper-discovery.md`
- 进展日志：`.codebuddy/agent-logs/junior-dev-spec015-task08-regression-20260905-0121.md`
- 范围：仅修改 `tests/test_api.py` 与 `tests/test_paper_browser_manager.py`；未修改生产 SSRF/浏览器安全逻辑，未执行 commit、push、reset、stash、clean。

## 结论

本切片回归稳定性修复通过。API 旧用例的 HTTP 503 根因是测试只 mock 了 `skill_status` 和 skill 执行器，却没有隔离路由在 `use_skill=True` 分支中调用的共享 Ollama 模型发现；Ollama 不可用时路由按设计返回 503。测试现在显式注入可用模型列表，保持生产端“依赖不可用返回 503”的契约不变。

浏览器 fake 用例通过 `_offline_public_dns()` 注入文档明确的公共测试 IP `93.184.216.34`。该注入只发生在测试 helper，生产 `PaperBrowserManager` 仍执行原有 allowlist、HTTPS、DNS 公网地址及重定向逐跳校验。

## 复现与修复证据

1. 覆盖率模式下原 API 用例复现为 `503 != 200`；独立脚本确认响应为 `无法连接 Ollama 服务`，且 `skill_status` mock 未被调用。原因是求值 `skill_status(get_available_models())` 时参数先触发真实 Ollama 请求。
2. 普通无覆盖率运行当时可能因本机 Ollama 可用而通过，证明该用例存在环境依赖和顺序/运行模式不稳定，不能作为修复依据。
3. `tests/test_api.py` 为目标测试增加 `get_available_models` mock，返回受控 worker 模型；没有放宽 503 断言，也没有跳过测试。
4. `tests/test_paper_browser_manager.py` 的 fake manager helper 默认接收离线 DNS resolver；显式 resolver 的安全边界测试保持原样。

## 验证结果

| 检查 | 命令 | 结果 |
|---|---|---|
| 精确回归 | `.venv/bin/python -m pytest -q tests/test_api.py::AgentApiTests::test_download_with_use_skill_records_skill_name tests/test_paper_browser_manager.py::test_authenticated_pdf_request_uses_context_request_and_safe_result tests/test_paper_browser_manager.py::test_authenticated_pdf_request_maps_forbidden_without_response_details` | `3 passed` |
| 论文/API 定向回归 | `.venv/bin/python -m pytest -q tests/test_api.py tests/test_paper_*.py` | `135 passed, 1 xfailed, 9 subtests passed` |
| 普通全量 | `.venv/bin/python -m pytest -q` | `520 passed, 1 xfailed, 38 subtests passed` |
| 覆盖率全量 | `COVERAGE_FILE=/tmp/spec015-task08-regression-full.coverage .venv/bin/python -m pytest --cov=backend/app --cov-report=term-missing:skip-covered -q` | `521 passed, 1 skipped, 38 subtests passed`；总覆盖率 `84%` |
| 静态空白 | `git diff --check -- tests/test_api.py tests/test_paper_browser_manager.py` | 通过 |

覆盖率全量仍显示若干模块低于 80%，但总覆盖率为 84%，且本切片相关失败均已消除。报告不将 Task08 的排序冻结集、真实 ACM/IEEE 登录或其他未执行验收项误标为通过。

## 复杂度自评

简单：本切片仅是两个测试隔离 seam 的小范围修改，不涉及生产状态、并发、锁或数据模型；复杂任务自检清单不适用。
