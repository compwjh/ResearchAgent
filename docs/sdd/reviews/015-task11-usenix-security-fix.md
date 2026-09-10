# Spec015 Task11 USENIX 安全修复自测报告

## 结果状态和摘要

通过（定向自测）。USENIX source 现在读取 `ConferenceSource.discovery_routes` 的 accepted 路线配置，并为查询、列表/详情 URL 和 PDF probe 增加线程安全 TTL 缓存；所有未命中的 USENIX 请求按配置最小间隔排队。PDF 可用性探测改为调用统一 `download_candidate()`，使用固定 `www.usenix.org` allowlist、手动逐跳重定向校验、DNS/peer seam、响应头/64 MiB/120 秒边界和严格 `%PDF-` 检查；probe 只写入系统临时目录并在返回前清理。

## 改动文件

- `backend/app/services/usenix_publication_source.py`
- `tests/test_usenix_publication_source.py`

## 测试命令、退出码和结果

- `.venv/bin/python -m pytest -q tests/test_usenix_publication_source.py`：退出码 0，`6 passed`
- `.venv/bin/python -m py_compile backend/app/services/usenix_publication_source.py`：退出码 0
- `git diff --check`：退出码 0

新增覆盖：重复查询缓存命中与节流、伪 `%PDFx` 回退 prepublication、超限响应、恶意重定向及 `follow_redirects=True` client 不被自动跟随。

## 产物路径

- 本报告：`docs/sdd/reviews/015-task11-usenix-security-fix.md`
- 进展日志：`.codebuddy/agent-logs/junior-dev-spec015-task11-usenix-security-fix-20260905.md`

## 决策依据

- 复用 `paper_download.download_candidate()`，避免 source 内出现第二套下载/SSRF 逻辑。
- allowlist 固定为 `www.usenix.org`；route 模板只提供受控路径，仍需经过 URL 安全校验。
- 仅缓存成功页面与稳定的无效/超限 PDF probe；网络、策略、超时等异常不缓存，保留可重试性。

## 风险与阻塞

- 未修改 Task11 其他阻塞项（API 默认年份、跨来源身份/出版阶段合并）。
- 真实 USENIX 外网、DNS rebinding 和真实 peer 证据仍需集成环境验收；fixture 通过注入 resolver/peer seam 验证安全边界。

## 主 Agent 后续动作

- 读回 source 与测试，运行 Task11 全链路、下载安全、批量导入及旧 KB/API 回归。
- 将本报告与本修复纳入同一验收提交后申请 Tech Lead 复评。

## 开始、结束和总耗时

- 开始：2026-09-05 03:25（Asia/Shanghai）
- 结束：2026-09-05 03:34（Asia/Shanghai）
- 总耗时：约 9 分钟

## 模型与工具统计

- 模型：gpt-5.6-luna（high，本次调度）
- 工具：文件读取/补丁编辑/定向 pytest/py_compile/git diff 检查
