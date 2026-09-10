# Spec015 Task08 安全矩阵测试切片

- 执行角色：初级开发（junior-dev）
- 关联 spec：`docs/sdd/specs/015-security-paper-discovery.md`
- 关联任务：`docs/sdd/plans/015/task-08-tests-ranking-and-security.md`
- 输入盘点：`docs/sdd/reviews/015-task08-test-inventory.md`
- 执行时间：2026-09-05（Asia/Shanghai）
- 进展日志：`.codebuddy/agent-logs/junior-dev-015-20260905-021500.md`
- 约束：仅扩展两个测试文件与本报告/日志；未修改生产代码，未执行 commit、push、reset、stash、clean。

## 结论

**切片部分完成，整体不放行。** 离线安全矩阵新增用例均已落盘；定向回归为 `25 passed, 1 xfailed, 5 warnings`。唯一 xfail 是加密 PDF：当前生产 `_validate_pages` 只检查页数，没有拒绝 `is_encrypted=True` 的文件。按 Task08 边界保留严格 xfail 作为生产 seam 阻塞，不代行修改生产代码。

## 覆盖矩阵

| 类别 | 新增覆盖 | 期望稳定错误码 | 结果 |
|---|---|---|---|
| SSRF 地址 | multicast、reserved、广播、IPv6 ULA/link-local/multicast/documentation/unspecified | `DOWNLOAD_BLOCKED` | 通过 |
| 混淆地址 | 十进制、八进制、十六进制、短 IPv4/非四段表示 | `DOWNLOAD_BLOCKED` | 通过 |
| 跳转目标 | HTTP、非 443、userinfo、认证 query、两跳循环与次数上限、空 Location | `DOWNLOAD_BLOCKED` / `INVALID_URL` | 通过 |
| PDF 内容 | 损坏/截断魔数内容、零页 validator | `INVALID_PDF` | 通过（零页复用既有测试） |
| 加密 PDF | PyMuPDF AES-256 离线样本 | `INVALID_PDF` | xfail：生产 seam 缺失 |
| 流式下载 | `httpx.ReadError` 断流并确认 partial 清理 | `PDF_NOT_FOUND` | 通过 |
| 响应头 | 超过头部字节上限，包含 Cookie/Authorization 的敏感 fixture | `DOWNLOAD_BLOCKED` | 通过 |
| 清理/脱敏 | 失败后临时目录为空；异常文本不含 Cookie、Authorization、password、secret | 对应稳定码 | 通过 |

## 改动文件

- `tests/test_paper_download_security.py`：补危险地址、混淆地址、跨协议/端口/认证跳转和循环上限矩阵，并检查 URL 安全异常不回显敏感值。
- `tests/test_paper_download.py`：补循环重定向、超大响应头、断流、损坏/截断 PDF、加密 PDF fixture 与失败清理断言；测试 helper 支持按用例启用真实页验证。

## 执行证据

```text
.venv/bin/python -m pytest -q tests/test_paper_download_security.py tests/test_paper_download.py
25 passed, 1 xfailed, 5 warnings
```

```text
.venv/bin/python -m compileall -q tests/test_paper_download_security.py tests/test_paper_download.py
node --check frontend/app.js
git diff --no-index --check /dev/null tests/test_paper_download_security.py
git diff --no-index --check /dev/null tests/test_paper_download.py
```

上述编译、JS 语法和新增文件空白检查均通过；`git diff --no-index` 因比较未跟踪文件与空文件本身返回差异状态，但未输出空白错误。

## 阻塞与后续动作

`test_encrypted_pdf_is_rejected_without_exposing_password` 使用严格 xfail，当前观察到加密 PDF 被成功保存而非返回 `INVALID_PDF`。生产实现需在页解析边界检查加密状态并保持失败清理/固定错误消息；该切片不修改生产代码。修复后应移除/验证 xfail，并重跑本定向回归及 Task08 全量验收。

本报告不替代 tester 的正式 `015-acceptance-review.md`，也不对 A1–A15 或真实 ACM/IEEE 登录链路作通过声明。
