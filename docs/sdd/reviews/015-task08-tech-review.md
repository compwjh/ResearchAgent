# Spec015 Task08 技术复核（Tech Lead）

- 评审角色：开发主管（Tech Lead）
- 评审模型：自身
- 评审时间：2026-09-05 01:26–01:28（Asia/Shanghai）
- 复核范围：Spec015、Task08 计划与 QA 盘点、安全矩阵、加密 PDF 修复、回归稳定性修复报告；论文检索/导入/下载/浏览器实现与测试；旧知识库兼容测试；前端静态契约；敏感运行产物与 Git 状态
- 评审约束：只读复核；未修改业务代码、测试代码或配置，未执行 commit、push、reset、stash、clean
- 进展日志：`.codebuddy/agent-logs/tech-lead-spec015-task08-review-20260905-012638.md`

## 结论

**阻塞，暂不通过。**

Task08 的离线安全矩阵、加密 PDF 拒绝、错误码脱敏和普通回归已达到当前切片的可复核状态；但 Spec015 的排序质量门禁与真实链路门禁仍未满足。Task04（embedding/rerank）和冻结排序集按用户授权标记 deferred，仍不能据此声称 A4/A14 通过；真实 GUI、公开 PDF 端到端、ACM/IEEE 合法账户登录续传和旧 KB 真实物理文件链路也没有证据。故不能签字放行 Task08 或将 Spec015 标记完成。

## 已复核通过的离线证据

### 1. 回归与静态检查

| 检查 | 实际结果 | 判定 |
|---|---|---|
| 普通全量 pytest | `521 passed, 5 warnings, 38 subtests passed`，退出码 0 | 通过回归门槛；不等于全验收通过 |
| 覆盖率全量 pytest | `520 passed, 1 skipped, 5 warnings, 38 subtests passed`，总覆盖率 `84%` | 总覆盖率通过；唯一跳过为 `tests/test_ollama_direct.py:367` 的 Ollama 不可达真实调用 |
| 安全/PDF 定向回归 | `26 passed, 5 warnings` | 通过 |
| 旧 KB/导入兼容定向回归 | `127 passed, 5 warnings, 4 subtests passed` | 单元/模拟证据通过 |
| 论文发现/批次定向回归 | `80 passed, 9 subtests passed` | 离线契约通过 |
| Python 编译 | `.venv/bin/python -m compileall -q backend tests` | 通过 |
| 前端 JS | `node --check frontend/app.js` | 通过 |
| 差异空白 | `git diff --check` | 通过 |
| 冲突标记 | 排除 vendor/.venv/.git 后无 `<<<<<<<`/`=======`/`>>>>>>>` | 通过 |

覆盖率运行中的 `Failed to export span batch due to timeout` 是收尾阶段观测导出提示，不改变 pytest 退出码和 84% 结果；应在服务运行验收时另行确认观测后端是否可用。

### 2. 安全矩阵、稳定错误码与加密 PDF

- `tests/test_paper_download_security.py` 已覆盖多播、保留地址、IPv6 ULA/link-local/multicast/documentation、混淆 IPv4、协议/端口、userinfo、认证 query、多跳循环和缺失 Location；危险目标统一断言 `DOWNLOAD_BLOCKED`，非法空跳转断言 `INVALID_URL`。
- `tests/test_paper_download.py` 已覆盖 `LOGIN_REQUIRED`、`PDF_NOT_FOUND`、`DOWNLOAD_TIMEOUT`、`PDF_TOO_LARGE`、`INVALID_PDF`，并验证响应头过大、断流、伪 PDF、损坏/截断 PDF 和失败后的临时文件清理。
- 加密 PDF 修复已落在 `backend/app/services/paper_download.py:118-135`：读取文档后先拒绝 `document.is_encrypted`，返回固定 `INVALID_PDF`；当前 AES-256 fixture 已通过，错误文本不含 `password`/`owner`，目录无残留。此前安全矩阵报告中的 xfail 已被修复报告明确关闭。
- `backend/app/services/paper_import.py:55-79` 以稳定错误码映射固定消息；批量 API 对条目错误也只输出固定消息，避免 transport/library 异常原文进入持久化或 API。当前测试对 Cookie、Authorization、password、secret 等敏感文本做了不泄漏断言。
- 这些是离线 fake/注入 resolver 证据，不等于真实 DNS rebinding、真实 peer 绑定、真实浏览器重定向和真实站点响应已验收。

### 3. 敏感产物检查

未发现已跟踪的 browser profile、Cookie、HAR、video、运行日志或下载产物；全仓冲突扫描也为 0。当前工作树确实存在被 `.gitignore` 忽略的运行文件（如 `data/browser-profile/security-papers/.profile.lock`、搜索/任务 SQLite、知识库/文章 PDF、`deploy/reranker/.runtime/run.log`），本轮未删除或改动它们。日志扫描未发现具体 Cookie、Authorization、密码或 secret 值，但这不能替代真实 Playwright profile 内容审计；后续收口仍需保持“产物不入 Git、profile 不上传”的检查。

## 放行阻塞项

### T8-B1：Task04 rerank 与冻结排序质量尚未执行（用户授权 deferred）

`docs/sdd/plans/015/task-04-semantic-ranking-and-rerank.md` 仍为 `待执行`。当前 `backend/app/services/paper_discovery_search.py:240-246` 的 `_score` 使用 `SequenceMatcher` 词法分数，搜索流程 `:123-132` 直接按 `final_score` 排序并保存；未发现论文搜索对 bge-m3 embedding、spec-014 批量 rerank、异常降级标志和观测 span 的实现证据。

同时未发现不少于 12 条方向查询、每条至少 3 个候选、首次查看最终排名前冻结的标签/快照/hash，或逐查询及总体 nDCG@10、Recall@10 报告。因此不得用已有 tie-break 单测推断语义质量通过，也不得修改/删题以制造指标通过。该项按用户授权记录为 deferred，但对 A4/A14 仍是明确阻塞。

### T8-B2：真实 GUI、公开 PDF 和 ACM/IEEE 登录续传不可验收

前端目前只有静态 DOM/XSS/CSS 契约与 Node 语法证据；没有 headed 浏览器对首屏 feature flag、Tab/ARIA、键盘会议选择、批次隔离、waiting-login/retry、窄屏可见性和关闭开关后的在途响应的真实交互证据。

`.venv` 中没有 `playwright` 模块，且本轮没有可核验的 ACM Digital Library / IEEE Xplore 合法账户和受保护 PDF 样本。fake parser/browser 测试不能替代 A10/A11；公开 PDF 真实下载、知识库真实检索和服务运行/health 也没有本轮证据。故 A10、A11 及 A15 的真实链路保持阻塞。

### T8-B3：旧知识库兼容仍缺真实物理文件端到端矩阵

旧 `file_name` 记录加载、路径解析、删除、缺失元数据、索引状态迁移等单元测试随定向回归通过；但尚未用真实旧 `papers.json` 与旧 `{paper_id}.pdf` 物理文件贯穿 API/服务层的列表、检索、重建、删除，并验证缺文件/坏元数据/同名新论文的隔离。因此 A12 只能记为离线部分通过，不能签署完整兼容性。

### T8-B4：自定义会议与全 Spec015 收口仍有前置缺口

QA 盘点和 Task02 记录显示 DBLP Venue Search 尚无可复现成功样本；当前没有自定义会议新增 POST 的完整闭环。A3 保持阻塞。A1/A2/A5–A9/A13 的离线证据可继续作为实现基础，但仍缺真实 GUI/外部源和端到端运行证据，不应升级为整体验收通过。

## 建议的下一步（不改变本次阻塞结论）

1. 在 Task04 真正执行前先落盘冻结排序集及 hash，再实现 embedding/rerank、有限分数/索引校验、降级契约和 nDCG@10/Recall@10 指标；由 tester 产出可追溯结果。
2. 在受控环境安装与计划版本匹配的 Playwright，由用户以合法 ACM/IEEE 账户完成 headed 登录、受保护 PDF 续传和公开 PDF 对照；记录无凭证日志与 profile 产物扫描。
3. 增补真实旧 KB 物理文件端到端回归、真实服务启动/health、窄屏 GUI 交互和四会/自定义会议证据，再由 tester 出具正式 acceptance review。

## 签字

- 开发主管（Tech Lead）：**当前协作 Agent，签字：阻塞，暂不通过**
- 签字时间：2026-09-05 01:28 +0800
