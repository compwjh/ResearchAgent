# Spec015 Task08 加密 PDF 校验修复

- 执行角色：初级开发（junior-dev）
- 关联 spec：`docs/sdd/specs/015-security-paper-discovery.md`
- 关联任务：`docs/sdd/plans/015/task-08-tests-ranking-and-security.md`
- 输入报告：`docs/sdd/reviews/015-task08-security-matrix.md`
- 执行时间：2026-09-05（Asia/Shanghai）
- 进展日志：`.codebuddy/agent-logs/junior-dev-015-task08-encrypted-pdf-fix-20260905.md`
- 改动范围：`backend/app/services/paper_download.py`、`tests/test_paper_download.py`
- 约束：未执行 commit、push、reset、stash、clean；未修改其他业务代码。

## 修复结论

**通过。** 页数/结构校验现在在读取 PDF 后先检查 `document.is_encrypted`。加密 PDF 统一返回 `INVALID_PDF` 与固定的“PDF 无法读取”消息，不会把 PyMuPDF 或密码相关异常文本传给调用方；既有失败清理逻辑会删除重命名后的目标文件及其私有临时目录。

## 变更摘要

1. `backend/app/services/paper_download.py`：在 `_validate_pages` 的文档关闭边界增加加密状态拒绝，并显式透传稳定的 `PaperDownloadError`。
2. `tests/test_paper_download.py`：移除加密 PDF 用例的严格 xfail；断言 `INVALID_PDF`、不泄漏 `password`/`owner`、失败后无文件残留；清除该用例中误嵌入的重复超限断言。

## 验证证据

### 定向安全回归

```text
./.venv/bin/python -m pytest -q tests/test_paper_download.py tests/test_paper_download_security.py -o addopts=''
26 passed, 5 warnings in 0.13s
```

### 论文相关全量回归

```text
./.venv/bin/python -m pytest -q \
  tests/test_acm_paper_parser.py tests/test_download_paper_skill.py \
  tests/test_frontend_paper_contract.py tests/test_ieee_paper_parser.py \
  tests/test_paper_browser_manager.py tests/test_paper_discovery_api.py \
  tests/test_paper_discovery_search.py tests/test_paper_discovery_store.py \
  tests/test_paper_download.py tests/test_paper_download_security.py \
  tests/test_paper_import.py tests/test_paper_import_batch_api.py \
  tests/test_paper_import_batch_service.py tests/test_paper_import_batch_store.py \
  tests/test_paper_import_identity.py -o addopts=''
157 passed, 5 warnings, 9 subtests passed in 1.55s
```

### 静态检查

```text
./.venv/bin/python -m compileall -q backend/app/services/paper_download.py tests/test_paper_download.py tests/test_paper_download_security.py
git diff --no-index --check /dev/null backend/app/services/paper_download.py
git diff --no-index --check /dev/null tests/test_paper_download.py
```

编译与空白检查均通过；PyMuPDF/Swig 仅保留既有弃用警告。未发现冲突标记或敏感异常文本泄漏。

## 验收边界

本切片只修复下载器的加密 PDF 页数/结构校验及其回归测试；不扩大到浏览器登录、真实出版商权限、知识库索引或全 Spec015 端到端验收。
