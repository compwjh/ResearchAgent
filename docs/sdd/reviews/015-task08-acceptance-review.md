# Spec015 Task08 最终验收复核（QA）

- 评审者：tester（QA）
- 角色：测试
- 模型：`qwen3.5:9b`（本地 Ollama）
- 分派方式：`Task(tester)`；本轮只读复核
- 执行时间：2026-09-05（Asia/Shanghai）
- 关联任务：[`task-08-tests-ranking-and-security.md`](../plans/015/task-08-tests-ranking-and-security.md)
- 关联 Spec：[`015-security-paper-discovery.md`](../specs/015-security-paper-discovery.md)
- 进展日志：`.codebuddy/agent-logs/tester-spec015-task08-final-20260905.md`

## 结论

**不通过（阻塞，Tech Lead 待签字）。**

离线安全矩阵、加密 PDF 校验、回归稳定性修复和论文导入专项均已复核通过；全量 pytest 无失败且总覆盖率为 84%。但 Task08 的关键验收闭环仍缺失：没有冻结排序集及 nDCG/Recall@10，Task04 仍为“待执行”且论文搜索初排仍使用 `SequenceMatcher`；没有旧 KB 真实物理文件端到端矩阵；没有本轮真实公开 PDF、GUI 或 ACM/IEEE 合法登录续传证据。因此不能将 A14、A10、A11 或 A15 标记为通过，也不能将 Task08/Spec015 收口。

## 本轮执行证据

| 检查 | 命令/结果 | 判定 |
|---|---|---|
| 全量回归 | `./.venv/bin/python -m pytest -q -rs` → **520 passed, 1 skipped, 5 warnings, 38 subtests passed**，39.18s，退出码 0 | 通过（但未达到“521 passed”预期；跳过项见下） |
| 跳过原因 | `tests/test_ollama_direct.py:367`：Ollama 不可达或无可用模型，跳过真实调用 | 环境阻塞，不能伪造为通过 |
| 全量覆盖率 | `COVERAGE_FILE=/tmp/spec015-task08-final.coverage ./.venv/bin/python -m pytest --cov=backend/app --cov-report=term-missing:skip-covered -q` → **520 passed, 1 skipped**，总覆盖率 **84%**（6303 statements） | 总量门槛通过；若干模块低于 80%，见下 |
| 论文/安全/导入定向回归 | `tests/test_paper_download_security.py tests/test_paper_download.py tests/test_paper_browser_manager.py tests/test_paper_import*.py tests/test_frontend_paper_contract.py -o addopts=''` → **95 passed, 5 warnings** | 通过 |
| Python/JS 静态检查 | `compileall -q backend/app frontend`、`node --check frontend/app.js`、`git diff --check` | 通过 |
| 冲突扫描 | `rg -n '^<<<<<<<|^=======|^>>>>>>>' . --glob '!vendor/**' --glob '!.venv/**' --glob '!.git/**'` | 0 命中 |
| Git 产物扫描 | `git ls-files` 未发现 browser profile、profile lock、项目运行 PDF、HAR、trace、video 或日志；仓库仅有既有 vendor 测试 PDF | 通过 |
| Playwright 环境 | `.venv/bin/python` 中 `import playwright` → `ModuleNotFoundError` | 真实 GUI/登录阻塞 |

覆盖率总量达到 80% 门槛，但模块覆盖仍不均：`routes.py` 76%、`main.py` 62%、`paper_browser_manager.py` 79%、`paper_import_batch_service.py` 77%、`paper_import.py` 79%、`article_search.py` 72% 等。该项不单独否决总覆盖率，但应在后续质量债务中处理。

## 安全矩阵与加密 PDF

**通过（离线 fixture）。** `tests/test_paper_download_security.py:27-112` 覆盖仅 HTTPS/443、allowlist、userinfo/fragment/认证 query、loopback/private/link-local/multicast/reserved/IPv6/IPv4-mapped、十进制/八进制/十六进制/短 IPv4、DNS 公共地址筛选、peer IP 复核、跨协议/端口/认证重定向以及多跳上限。`tests/test_paper_download.py:140-177` 覆盖响应头上限、敏感值不回显、断流、伪造/损坏/截断 PDF、失败清理和加密 PDF。

加密 PDF 已由 `backend/app/services/paper_download.py:118-132` 在页解析边界以固定 `INVALID_PDF` 拒绝；`tests/test_paper_download.py:171-177` 证明不泄漏 password/owner 且临时文件清理。此前严格 xfail 已移除，本轮专项回归全部通过。上述证据是离线安全实现证据，不等同于真实外站连接或真实浏览器认证证据；DNS rebinding 的真实 peer 绑定、ACM/IEEE 认证重定向仍需真实环境复验。

## A1–A15 验收判定

| 验收点 | 判定 | 依据/缺口 |
|---|---|---|
| A1 独立入口 | 部分通过 | API/静态 DOM 契约通过；无真实浏览器证明关闭开关首屏不闪现、Tab/ARIA 与在途请求行为 |
| A2 默认范围 | 部分通过 | 配置和定向测试存在；缺单一冻结契约及 GUI 首屏证据 |
| A3 自定义会议 | **阻塞** | Task02/Task03 记录 DBLP Venue Search 仅有 429/503，无成功 live 样本；自定义会议新增闭环未验收 |
| A4 语义检索 | **阻塞** | `docs/sdd/plans/015/task-04-semantic-ranking-and-rerank.md` 仍为 `待执行`；`backend/app/services/paper_discovery_search.py:246-252` 使用 `SequenceMatcher`，无 embedding/rerank 质量证据 |
| A5 主会过滤 | 部分通过 | DBLP 混流/去重 fixture 通过；缺四会完整冻结结果和新鲜 live 快照 |
| A6 降级 | 部分通过 | OpenAlex/DBLP 和浏览器 fake 的稳定错误码通过；缺 Task04 reranker 故障链路及公开 PDF 实链路 |
| A7 单篇导入 | 部分通过 | 下载、命名、补偿、加密 PDF 和安全边界离线通过；缺真实公开 PDF 下载、真实 KB 检索对账 |
| A8 批量导入 | 部分通过 | 状态机、等待登录、重试、租约恢复、并发 CAS 定向测试通过；缺真实服务重启/UI 状态证据 |
| A9 去重幂等 | 部分通过 | identity/batch 单元与并发测试通过；缺真实数据库、文件、索引三介质第二次提交闭环 |
| A10 ACM 登录 | **阻塞** | Playwright 未安装，无可核验合法账户；未执行 headed 登录、SSO/验证码、受保护 PDF 续传 |
| A11 IEEE 登录 | **阻塞** | 同 A10 |
| A12 命名/旧记录兼容 | 部分通过 | 旧 `file_name` 路径与 API 列表/删除/reindex 单测通过（如 `tests/test_kb_services.py:230-252`、`tests/test_kb_routes.py:326-348`）；缺真实旧 `papers.json` + 旧物理 PDF 的列表、检索、重建、删除端到端矩阵 |
| A13 安全异常 | 部分通过 | 本轮安全矩阵与加密 PDF 通过；真实 DNS rebinding/peer 绑定和浏览器异常路径未执行 |
| A14 排序质量 | **阻塞** | 未发现 ≥12 查询、每条 ≥3 候选、冻结时间/hash、人工标签、逐查询 nDCG@10/Recall@10 和灾难性退化报告；不得以 tie-break 单测替代 |
| A15 回归交付 | **不通过** | 自动化全量绿灯且覆盖率 84%，但有 1 项 Ollama 跳过，且缺 A14、真实公开 PDF、GUI、ACM/IEEE 与完整旧 KB 端到端证据 |

## 冻结排序集与 Task04 核对

本轮以 `rg --files` 和源码/任务文档核对，未发现 Spec015 专属冻结数据文件、候选快照、人工标签、SHA-256/hash、指标脚本或 nDCG/Recall 结果。仅发现 Spec014 的历史 `docs/sdd/reviews/014-reranker-benchmark.md`，其 10 题知识库 reranker 基准不能替代 Spec015 要求的至少 12 条论文研究方向查询。Task04 计划仍显示 `待执行`，所以 A14 必须保持阻塞。

## 真实链路与敏感信息

- 本轮没有把 fake browser、历史 live 片段或本地 KB PDF 冒充公开 PDF 成功链路。
- `.venv` 无 Playwright；`data/browser-profile/security-papers/.profile.lock` 权限为 `0600`，目录受 `.gitignore` 保护，但没有真实 headed 浏览器执行证据。
- `git ls-files` 未跟踪 profile/Cookie/PDF/HAR/trace/video；源码敏感词扫描只命中预期的示例配置和安全拒绝逻辑，未发现运行凭证入库。
- 日志/trace 导出曾报告本地 OTEL 端口不可达，但不影响 pytest 退出码；未发现认证信息回显。

## Tech Lead 签字

- 开发主管：待签字
- 结论：待 Tech Lead 复核失败归因与阻塞项；在签字前不得将 Spec015 状态改为 `已完成`，不得进入 Task09 部署收口。
