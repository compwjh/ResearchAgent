# Spec015 Task11 USENIX PDF probe P1 修复自测报告

## 结果状态和摘要

通过（定向自测）。USENIX source 的统一 PDF probe 不再使用 `validate_pdf_pages=False`；默认调用 `download_candidate()` 的页可读性校验，仍保留注入式 `pdf_page_validator` 作为 fixture seam。截断/损坏 PDF 会被映射为无效并继续正式 PDF → prepublication → arXiv 路线；原有缓存、节流、固定 allowlist、逐跳重定向及临时目录清理保持不变。

## 改动文件

- `backend/app/services/usenix_publication_source.py`
- `tests/test_usenix_publication_source.py`

## 测试命令、退出码和结果

- `.venv/bin/python -m pytest -q tests/test_usenix_publication_source.py`：退出码 0，`7 passed`
- `.venv/bin/python -m py_compile backend/app/services/usenix_publication_source.py tests/test_usenix_publication_source.py`：退出码 0
- `git diff --check`：退出码 0

新增真实 fitz PDF fixture，验证截断正式 PDF 被页校验拒绝并回退至可读 prepublication PDF；既有伪魔数、超限和重定向安全测试继续通过。

## 产物路径

- 本报告：`docs/sdd/reviews/015-task11-usenix-pdf-probe-fix.md`
- 进展日志：`.codebuddy/agent-logs/junior-dev-spec015-task11-usenix-pdf-probe-fix-20260905.md`

## 决策依据

- 生产默认 `validate_pdf_pages=True`，由统一下载器执行魔数、内容类型和页可读性检查。
- 注入式 validator 只用于已有 MockTransport fixture，不能改变生产默认路径。
- 页校验失败保持 `INVALID_PDF`，正式 PDF 不可读时继续 prepublication；两者均失败后才触发 arXiv。

## 风险与阻塞

- 未修改 API、schema、前端或其他 Task11 阻塞项。
- 当前为离线 fixture 验证；真实 USENIX 网络链路仍需主 Agent 全链路验收。

## 主 Agent 后续动作

- 读回 source/test，重跑 Task11 全链路、下载安全、批量导入及旧 KB/API 回归。
- 将本报告纳入 Task11 验收材料并申请 Tech Lead 复评。

## 开始、结束和总耗时

- 开始：2026-09-05 03:36（Asia/Shanghai）
- 结束：2026-09-05 03:40（Asia/Shanghai）
- 总耗时：约 4 分钟

## 模型与工具统计

- 模型：gpt-5.6-luna（high，本次调度）
- 工具：文件读取/补丁编辑/定向 pytest/py_compile/git diff 检查
