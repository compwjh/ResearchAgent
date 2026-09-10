# Spec015 Task08 测试盘点（QA）

- 执行角色：测试（QA）
- 盘点时间：2026-09-05 01:07–01:15（Asia/Shanghai）
- 关联任务：`docs/sdd/plans/015/task-08-tests-ranking-and-security.md`
- 关联 Spec：`docs/sdd/specs/015-security-paper-discovery.md`
- 约束：只读盘点与验证；未修改业务代码、测试代码、配置或 Git 历史；未执行 commit、push、reset、stash、clean。
- 进展日志：`.codebuddy/agent-logs/tester-spec015-task08-inventory-20260905-0107.md`

## 1. 结论

本轮是 Task08 的测试盘点，不是 A1–A15 通过签字。当前离线自动化基础较完整，但 Task08 仍 **不具备验收放行条件**：

1. 普通全量 pytest 当前为 `511 passed, 1 skipped, 5 warnings, 38 subtests passed`，高于历史动态基线 `max(351, 505)=505`；但同一工作树的覆盖率全量运行出现 3 个失败，故 A15 不能仅凭普通全量绿灯通过。
2. 覆盖率全量运行结果为 `507 passed, 1 skipped, 3 failed`，总覆盖率 `84%`，达到总量 80% 门槛但模块覆盖不均；`routes.py` 76%、`paper_browser_manager.py` 78%、`paper_import_batch_service.py` 77%、`paper_import.py` 79% 等低于 80%。
3. 未发现不少于 12 条查询、每条至少 3 篇相关论文、候选快照、人工标签、冻结时间/hash 或 nDCG@10/Recall@10 结果文件；`rg` 只在计划/历史文档中找到这些词，未找到可执行数据集或指标脚本。Task04 仍标记 `待执行`，当前搜索服务 `_score` 使用 `SequenceMatcher`，没有 embedding/rerank 质量验收证据。
4. 安全单测覆盖若干 URL、PDF、重定向和敏感信息边界，但没有完成 Spec015 要求的全矩阵；浏览器 fake 的两个认证 PDF 测试在当前沙箱默认 DNS 下被 `DNS 解析失败 → DOWNLOAD_BLOCKED` 截断，未到达 fake 200/403 响应。
5. 旧知识库已有若干单元兼容测试，但没有覆盖“真实旧物理文件名 + 列表、检索、重建、删除”完整端到端链路。前端只有 3 个静态契约测试，没有真实浏览器/窄屏/首屏开关行为证据。
6. `.venv` 无 `playwright` 模块且当前没有可核验 ACM/IEEE 合法账户，因此 A10/A11 真实登录续传不可执行；Task02 的 DBLP/OpenAlex 证据保留，但 DBLP Venue Search 曾因 429/503 阻塞，未形成 Task08 新鲜公开 PDF/登录闭环证据。

## 2. 已执行命令与结果

| 检查 | 命令/结果 | 判定 |
|---|---|---|
| 普通全量回归 | `.venv/bin/python -m pytest -q` → `511 passed, 1 skipped, 5 warnings, 38 subtests passed`，68.81s，退出码 0 | 测试数量超过 505 动态历史值；不等于 A15 全部通过 |
| 覆盖率全量 | `COVERAGE_FILE=/tmp/spec015-task08.coverage .venv/bin/python -m pytest --cov=backend/app --cov-report=term-missing:skip-covered -q` → `507 passed, 1 skipped, 3 failed`，总计 6299 statements/84% | 总覆盖率通过；失败和低覆盖模块阻塞 |
| 覆盖率低于 80% 模块 | `coverage report --sort=cover` | `main.py 62%`、`kb/parse.py 70%`、`article_search.py 72%`、`kb/tasks.py 73%`、`kb/retrieve.py 75%`、`paper_download.py 75%`、`download_paper_skill.py 75%`、`routes.py 76%`、`paper_import_batch_service.py 77%`、`article_download.py 78%`、`observability/trace.py 78%`、`paper_browser_manager.py 78%`、`paper_import.py 79%` |
| 论文定向回归 | `.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py tests/test_paper_*.py` → `120 passed, 2 failed, 9 subtests passed` | 2 个 browser fake 测试受 DNS 环境阻断；其余论文测试通过 |
| JS 语法 | `node --check frontend/app.js` | 通过 |
| Python 编译 | `.venv/bin/python -m compileall -q backend/app frontend` | 通过 |
| 差异空白 | `git diff --check` | 通过 |
| 冲突标记 | `rg -n '^<<<<<<<|^=======|^>>>>>>>' --glob '!vendor/**' --glob '!.venv/**' --glob '!.git/**' .` | 0 命中 |
| Playwright 环境 | `.venv/bin/python -c 'import playwright'` | 失败：`ModuleNotFoundError` |

### 2.1 当前失败隔离

- `tests/test_api.py::AgentApiTests::test_download_with_use_skill_records_skill_name`：当前环境单独运行也返回 HTTP 503、期望 200；该测试依赖被 mock 的 skill status/执行链，说明现状需要由实现方诊断共享配置或路由错误，不能标为环境噪声后忽略。
- `tests/test_paper_browser_manager.py::test_authenticated_pdf_request_uses_context_request_and_safe_result`：`dl.acm.org` 默认 DNS 解析失败，安全层提前返回 `DOWNLOAD_BLOCKED`。
- `tests/test_paper_browser_manager.py::test_authenticated_pdf_request_maps_forbidden_without_response_details`：同一 DNS 阻断，未到达 fake 403，实际错误码为 `DOWNLOAD_BLOCKED` 而非测试预期 `LOGIN_REQUIRED`。

Task07 历史记录曾在注入测试 resolver 后使两个 browser fake 测试通过；该 workaround 证明 fake seam 可测，但不能替代真实外网、真实登录或安全连接绑定验收。本轮未改测试注入 resolver。

## 3. A1–A15 证据盘点

| 验收点 | 当前证据 | 结论/缺口 |
|---|---|---|
| A1 独立入口 | `tests/test_paper_discovery_api.py` 覆盖 health flag 与 disabled API；`test_frontend_paper_contract.py` 仅检查稳定 DOM target | 离线部分通过；没有真实浏览器证明首屏隐藏、Tab 切换和关闭后的可见性/在途请求 |
| A2 默认范围 | 配置/搜索逻辑有默认年份与内置会议，定向测试可覆盖部分输入校验 | 缺少断言“CCS、USENIX Security、IEEE S&P、NDSS + 最近五个完整年份”的单一冻结契约和 GUI 证据 |
| A3 自定义会议 | 仅有 `GET /api/papers/conferences/search` 对已存在配置的匹配测试；`POST /api/papers/conferences` 未注册 | 阻塞；无 DBLP Venue Search 成功样本、新增/修改/停用/内置删除保护闭环 |
| A4 语义检索 | DBLP/OpenAlex 搜索、规范化和稳定 tie-break 单测存在；当前实现 `_score` 为字符串 `SequenceMatcher` | 不通过；Task04 embedding/rerank 尚未实现或验收，无标题/研究方向质量证据 |
| A5 主会过滤 | `test_dblp_publication_source.py` 有 USENIX 混流样本和去重断言 | 部分通过；没有 CCS、SP、NDSS 四会 fixture 矩阵，也没有真实跨年份结果快照 |
| A6 降级 | OpenAlex/DBLP 失败单测及 API 稳定错误码存在 | 部分通过；没有 reranker 故障链路（Task04 未执行）、Playwright 故障后的真实公开 PDF 链路和 UI 原因展示验收 |
| A7 单篇导入 | `test_paper_download.py`、`test_paper_import.py` 用 MockTransport/fake indexer 覆盖下载、命名、补偿和旧路径 | 离线部分通过；无真实公开 PDF 下载、真实知识库检索和服务运行证据 |
| A8 批量导入 | batch store/service/API 覆盖逐项隔离、waiting_login、重试、租约恢复、并发 CAS、20 条上限 | 离线通过倾向；无真实 UI 状态展示与服务重启运行证据 |
| A9 去重幂等 | batch identity/幂等键、单篇下载前去重及并发测试存在 | 离线通过倾向；缺真实数据库/文件/索引三介质端到端第二次提交证明 |
| A10 ACM 登录 | parser/browser fake 与敏感字段断言存在；`.venv` 无 Playwright、无合法账号 | 阻塞；必须用户在可用 headed Playwright 中登录并续传，不能用 fake 代替 |
| A11 IEEE 登录 | 同 A10 | 阻塞；无合法账号和真实受保护 PDF 续传证据 |
| A12 命名兼容 | 身份、Unicode/非法字符/超长、旧 `file_name` 路径和 KB 旧状态有单元测试 | 部分通过；缺旧物理文件名贯穿列表、检索、重建、删除的集成矩阵 |
| A13 安全异常 | URL allowlist、协议/端口、凭证/query、若干危险 IP、手动重定向、MIME/魔数/大小/超时、脱敏单测存在 | 部分通过；缺完整攻击矩阵（见 §4），真实下载/peer 绑定未验 |
| A14 排序质量 | 未找到冻结查询/候选/标签/指标产物；Task04 待执行 | 未执行，硬阻塞；不得从 tie-break 单测推断 nDCG/Recall 通过 |
| A15 回归交付 | 普通全量 511 通过；覆盖率运行 3 失败；静态检查通过 | 不通过；还缺服务启动/health、完整检索导入链路、GUI、真实 PDF/登录和 A14 |

## 4. 缺失的安全矩阵

现有 `tests/test_paper_download_security.py` 已覆盖 HTTPS、默认端口、allowlist、URL 用户信息/fragment/认证 query、127.0.0.1/私网/link-local/IPv6 loopback/IPv4-mapped/unspecified、部分混淆 IPv4、注入 DNS 地址、peer IP 和手动重定向 helper。`tests/test_paper_download.py` 覆盖部分 MIME/魔数、声明/流式大小、超时、页数校验和清理；browser fake 覆盖单跳重定向和敏感响应脱敏。

仍必须补齐或留下明确不可执行证据的最小矩阵：

- IP：multicast、reserved、更多 IPv6 private/link-local/unspecified、十进制/八进制/十六进制/短 IPv4 与 IPv4-mapped 变体的统一拒绝。
- 连接安全：恶意 DNS 先返回公共 IP、连接时变为私网的 rebinding；实际连接/peer IP 必须证明绑定或复核，不只测 `validate_url` 返回值。
- 跳转：HTTP 跨协议、非默认端口、带用户信息/认证参数、至少两跳 browser context 逐跳重校验，以及 `Location` 缺失/非法编码/循环/上限边界。
- PDF：HTML 伪装、错误 MIME、魔数异常已有部分样本，但零页、损坏 xref、加密 PDF、断流/截断体、头部过大和实际页解析失败需独立样本矩阵；确认临时文件和目标文件均清理。
- 浏览器：ACM/IEEE exact origin、认证请求重定向、用户取消、崩溃、allowlist 跳出、无权限响应，在真实 Playwright 和无凭证日志扫描中复验。
- 日志/产物：扫描 trace/HAR/video/download/profile、日志、API 响应和 Git，证明无 Cookie、Authorization、密码、完整带 query URL 或 profile 内容；当前仅有静态/单元脱敏证据。

## 5. 旧 KB、前端契约与真实链路盘点

### 旧知识库兼容

已有测试包含：`tests/test_kb_services.py` 的旧 `file_name` 记录加载、路径解析、删除、元数据缺失；`tests/test_kb_tasks.py` 的旧记录状态继承、已索引旧记录不误标中断、chunker 迁移；`tests/test_paper_import.py::test_legacy_path_resolution_remains_available`。这些是有效的单元证据。

缺口是用真实旧 `papers.json` + 旧 `{paper_id}.pdf` 物理文件跑 API/服务链路，逐项证明列表、检索、重建、删除都成功且不会覆盖新命名论文；也缺旧记录含坏元数据、缺文件、同名新记录时的稳定错误/隔离断言。

### 前端契约

`tests/test_frontend_paper_contract.py` 只有 3 项静态测试：DOM target、论文/批次 renderer 不使用 `innerHTML` 且字段用 `textContent`、CSS 长文本/滚动/focus/窄屏选择器。`node --check` 通过。

未覆盖真实 DOM 行为：开关关闭首屏无闪现、Tab/ARIA 状态同步、键盘会议选择、多个 batch 独立更新、waiting-login/retry 按钮可见、长标题/摘要窄屏布局和关闭开关后的在途响应。Task07 报告已有静态/Node 复核，但仍没有真实浏览器像素/交互证据。

### 真实网络与登录

Task02 历史报告提供 DBLP publication/OpenAlex 的部分 live 证据（同时记录 200、429、500、503、timeout），并明确 DBLP Venue Search 无成功样本；Task07/Task06 报告明确公开 PDF 真实链路、ACM/IEEE headed 登录续传未完成。当前 `.venv` `import playwright` 失败，且无可核验合法 ACM/IEEE 账户。本轮没有把 fake、HTTP 200 或历史 live 片段冒充 Task08 的 A10/A11/A15 通过。

## 6. 必须由 junior-dev 补测试的最小切片清单

以下仅是分派清单，未在本轮实现；每个本地模型任务应遵守“最多 2 个代码文件、≤150 行”限制，完成后由 QA 重跑。

1. **排序冻结集与指标（Task04 前置）**：新增冻结数据文件（≥12 个方向查询，每条 ≥3 个相关候选，包含候选快照、标签、冻结时间和 hash）及一个独立指标测试/脚本，输出逐查询与总体 nDCG@10、Recall@10、查询差异和灾难性退化；首次查看最终 rerank 前冻结，禁止改标签。若 Task04 未实现，先把测试标为阻塞，不伪造结果。
2. **排序异常/降级契约**：为 embedding 空文本、NaN/Infinity、维度异常、rerank HTTP/JSON/timeout、重复/越界 index、有限分数和稳定 tie-break 增加离线测试；验证一次搜索最多一次批量 rerank，失败保留初排并带 warning。
3. **SSRF 完整矩阵**：拆批补 multicast/reserved/IPv6/混淆地址、DNS rebinding + peer 绑定、HTTP/非默认端口/认证 URL/至少两跳重定向与循环上限，确保测试 fixture 不走公网。
4. **PDF/文件安全矩阵**：补零页、损坏/加密/截断/断流/头部大小上限、错误 MIME/魔数组合、临时文件清理和命名目录逃逸；将每个稳定错误码与不可泄露字段写入断言。
5. **旧 KB 集成回归**：使用临时真实旧 `papers.json`、旧物理 `{paper_id}.pdf` 和 fake Qdrant，覆盖 API/服务层列表、检索、重建、删除、缺文件/坏元数据/同名新论文隔离；不改现有兼容行为。
6. **前端契约扩展**：在无网络 fixture 下增加 feature flag 首屏、Tab/ARIA/键盘、批次隔离、waiting-login/retry、XSS 动态字段和窄屏可见性行为测试；真实 headed GUI 仍需另行人工执行。
7. **回归稳定性**：诊断 `test_download_with_use_skill_records_skill_name` 的 HTTP 503，并为浏览器 fake 测试提供明确的离线 resolver seam 或在测试环境固定解析；修复后普通 pytest 与 coverage pytest 必须都绿，不能仅增加重试或跳过。

## 7. QA 判定

Task08 测试盘点完成，结论为 **不具备验收放行条件（inventory blocked）**。当前可作为 junior-dev 补测的输入，不能将任务计划状态改为已完成，也不能将 Spec015 A14、A10、A11 或 A15 标记为通过。待补测试、冻结集、真实公开 PDF/服务运行证据和用户参与的 ACM/IEEE 登录证据全部落盘后，再由 tester 生成正式 `015-acceptance-review.md` 并交 tech-lead 签字。
