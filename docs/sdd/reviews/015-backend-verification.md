# spec-015 后端验证报告（backend-tester 复验）

- 执行环境：仓库根 `.venv`（fastapi 0.141.1 / jieba 等依赖所在）。
  - 此前误用**系统 Python** 导致 `ModuleNotFoundError: No module named 'fastapi'/'jieba'`，表现为 8 failed + 17 errors 的**伪失败**，非代码 bug。已修正为使用 `.venv` 解释器。
- 测试解释器：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest`
- 范围：后端 pytest 回归（排除前端契约测试 `tests/test_frontend_paper_contract.py`，归 frontend-tester）

## VERIFICATION REPORT

```
Build:     PASS  （`python -c "import app"` 冒烟通过，exit 0）
Types:     N/A   （未配置 pyright 门禁，跳过）
Lint:      SKIPPED（ruff 未安装在 .venv，需补装后再跑；不影响功能门禁）
Tests:     PASS  （610 passed, 38 subtests passed, 0 failed）
Security:  PASS  （A13 安全异常由 test_paper_download_security.py 覆盖）
Diff:      backend 24 文件 +7940 行新增；tests 30+ 文件新增（详见分支 diff）
```

**Overall: READY（后端门禁通过）**
- 不阻塞后端签字。
- A1/A2/A10/A11/A14/A16/A17/A18 为前端 UI / 真实登录 / 人工标注排序，**需前端/手工验收**，不在后端 pytest 范围内。

## 后端可测验收点 → PASS

| 验收点 | 覆盖测试（节选） |
|---|---|
| A3 会议配置回归 | `test_api.py` / `test_dblp_publication_source.py` / `test_usenix_publication_source.py` |
| A4 语义检索 | `test_paper_discovery_search.py` |
| A5 主会过滤 | `test_paper_discovery_normalization.py` / `test_usenix_paper_parser.py`（Workshop/Poster/Demo 排除） |
| A6 降级 | `test_paper_discovery_api.py` / search 相关（来源故障保留缓存/其他来源） |
| A7 / A7b 单篇导入 | `test_paper_download.py` / `test_paper_import.py` / `test_usenix_paper_parser.py` / `test_acm_paper_parser.py` / `test_ieee_paper_parser.py` |
| A8 批量导入 | `test_paper_import_batch_{api,service,store,identity}.py` |
| A9 去重幂等 | `test_paper_import_identity.py` / `test_paper_import_batch_*.py` |
| A12 命名兼容 | `test_paper_download_security.py` / `test_paper_import.py`（非法字符/Unicode/超长/同名安全处理） |
| A13 安全异常 | `test_paper_download_security.py`（非法 URL/内网/伪 PDF/超大/无权限均被拒） |
| A15 回归交付 | 全量 610 passed / 0 failed |
| A19 恢复与并发 | `test_paper_browser_manager.py`（租约/并发领用/恢复） |
| A20 复用审计 | `test_legacy_kb_integration.py` / `test_kb_services.py` / `test_kb_routes.py`（无第二套实现；搜索期无 PDF 请求） |

## 超出后端 pytest 范围（需前端/手工验收，不阻塞后端）

A1 独立入口 · A2 默认范围 · A10 ACM 登录 · A11 IEEE 登录 · A14 排序质量(nDCG@10) · A16 增量目录 · A17 来源进度 · A18 RAG 与分页

## 备注

- 子代理 `backend-tester`（qwen3.5:9b）执行至 90%（"准备生成 VERIFICATION REPORT"）后因上下文耗尽未回传最终报告；本结论由主会话基于**独立复跑**（610 passed / 0 failed）与套件覆盖合成，数字可靠。
- 仍有未提交改动（含 agent 工具化修复等）；建议后端评审 / tech-lead 签字后统一合入。
