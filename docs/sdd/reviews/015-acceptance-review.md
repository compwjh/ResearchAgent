# Spec015 最终验收评审（Task09 QA）

- 评审者：测试（QA）
- 执行模型：`gpt-5.6-luna`，high
- 分派方式：主会话分派的只读 QA 验收
- 执行时间：2026-09-05 01:30–01:36（Asia/Shanghai）
- 关联 Spec：[`015-security-paper-discovery.md`](../specs/015-security-paper-discovery.md)
- 关联任务：[`task-09-review-deploy-retro.md`](../plans/015/task-09-review-deploy-retro.md)
- 进展日志：`.codebuddy/agent-logs/tester-spec015-task09-acceptance-20260905-0136.md`
- 约束：未修改业务代码、测试代码或配置；未执行 commit、push、reset、stash、clean。

## 结论

**整体验收不通过，阻塞；Tech Lead 待签字。**

离线安全矩阵、PDF 校验、导入状态机、前端契约和全量自动化回归均有可复核证据；本轮实际运行时的首页、健康接口和会议列表也返回 200。仍不能收口的硬阻塞是：Task04 语义排序与冻结标注集未执行，DBLP Venue Search/自定义会议没有成功闭环，旧知识库物理文件端到端未验，且没有真实公开 PDF、GUI/窄屏或 ACM/IEEE 合法账户登录续传证据。不得将这些缺口以 fake、静态检查、历史片段或 521 计数替代。

## 环境与执行证据

### 实际运行时（本轮）

服务在 `127.0.0.1:8000` 可用，使用受控本机只读请求核验：

| 检查 | 真实结果 | 证据摘要 |
|---|---|---|
| `GET /api/health` | **200** | JSON 含 `status: ok`、`paper_discovery_enabled: true`；响应 327 bytes |
| `GET /` | **200** | 返回 ResearchAgent HTML，响应 13,748 bytes；含“论文检索”导航项和 `#papers-view` |
| `GET /api/papers/conferences` | **200** | 返回 4 个内置会议：CCS、IEEE S&P、NDSS、USENIX Security |

本轮只确认服务可用性和上述接口，不把服务监听或 200 响应扩展为真实搜索、PDF 下载、知识库检索或登录成功。

### 自动化回归（本轮）

| 检查 | 命令 | 结果 |
|---|---|---|
| 普通全量 | `./.venv/bin/python -m pytest -q -rs` | **520 passed, 1 skipped, 5 warnings, 38 subtests passed**，退出码 0；跳过 `tests/test_ollama_direct.py:367`，原因是 Ollama 不可达或无可用模型 |
| 覆盖率全量 | `COVERAGE_FILE=/tmp/spec015-task09-coverage ./.venv/bin/python -m pytest --cov=backend/app --cov-report=term-missing:skip-covered -q -rs` | **520 passed, 1 skipped**，退出码 0；`6303` statements，**84%** 总覆盖率 |
| 论文/安全/导入/浏览器/前端专项 | `tests/test_paper_download_security.py tests/test_paper_download.py tests/test_paper_browser_manager.py tests/test_paper_import*.py tests/test_frontend_paper_contract.py -o addopts=''` | **95 passed, 5 warnings**，退出码 0 |
| 静态与仓库检查 | `./.venv/bin/python -m compileall -q backend/app frontend`、`node --check frontend/app.js`、`git diff --check`、全仓冲突标记扫描 | 本轮均通过；冲突标记 0 命中 |

此前 Task08 报告中出现过 `521 passed` 的历史摘要；本轮普通和覆盖率均复跑为 520 passed，因此本报告不写成 521 passed，也不将唯一跳过项冒充通过。覆盖率虽达总量 80% 门槛，模块覆盖仍不均（例如 `routes.py` 76%、`main.py` 62%、`paper_import_batch_service.py` 76%、`paper_browser_manager.py` 79%）。

### 安全矩阵

专项 95 项通过，覆盖危险 IPv4/IPv6、混淆地址、HTTPS/443、认证 URL、逐跳重定向与循环上限、响应头上限、伪造/损坏/截断/加密 PDF、断流、稳定错误码、临时文件清理和敏感文本不回显。加密 PDF 的 `INVALID_PDF` 修复及既有 Task08 安全矩阵报告可追溯。

这些是离线 fixture/fake 或注入 resolver 的证据，不等于真实 DNS rebinding/peer 绑定、真实站点响应或真实浏览器认证已经完成。

## A1–A15 验收矩阵

| 验收点 | 判定 | 真实证据与阻塞 |
|---|---|---|
| A1 独立入口 | **部分通过** | 本轮首页 200 且 HTML 含“论文检索”Tab、`#papers-view`；health 返回 feature flag；前端静态契约和关闭/在途响应测试通过。缺真实浏览器首屏隐藏、Tab 切换、ARIA 呈现和开关关闭后的视觉/交互验收。 |
| A2 默认范围 | **部分通过** | 会议列表实际返回四个内置会议，配置/测试覆盖最近五个完整年份逻辑。缺真实 GUI 首屏确认默认勾选和年份值。 |
| A3 自定义会议 | **阻塞** | 当前可核验的是会议列表和已有配置搜索契约；Task02/Task03 记录 DBLP Venue Search 仅有 429/503，没有成功 live venue 样本；未伪造新增、修改、停用或内置删除保护闭环。 |
| A4 语义检索 | **阻塞** | Task04 仍为“待执行”；`backend/app/services/paper_discovery_search.py:252` 仍使用 `SequenceMatcher` 初排。无 embedding/spec-014 rerank 的论文质量证据，不能以排序 tie-break 单测替代。 |
| A5 主会过滤 | **部分通过** | DBLP 混流/Workshop 等离线 fixture 和去重测试通过；缺 CCS、USENIX Security、IEEE S&P、NDSS 四会的完整冻结/新鲜 live 结果矩阵。 |
| A6 降级 | **部分通过** | DBLP/OpenAlex 单源失败、浏览器不可用和稳定错误码的离线测试通过；缺 reranker 故障链路以及真实公开 PDF 在 Playwright 不可用时仍可导入的运行证据。 |
| A7 单篇导入 | **部分通过** | 下载安全、规范命名、补偿、加密 PDF 和知识库导入单测通过；本轮未执行真实公开 PDF 下载、物理文件对账和知识库检索确认。 |
| A8 批量导入 | **部分通过** | 批次/条目状态机、逐项隔离、waiting-login、重试、租约恢复和并发 CAS 的离线测试通过；缺真实服务重启与浏览器 UI 状态展示证据。 |
| A9 去重幂等 | **部分通过** | 身份键、批量幂等和并发测试通过；缺真实数据库、文件和索引三介质的第二次提交端到端证明。 |
| A10 ACM 登录 | **阻塞** | `.venv` 中 `import playwright` 为 `ModuleNotFoundError`；无可核验合法 ACM 账号/SSO/验证码和受保护 PDF 样本，未执行 headed 登录续传。 |
| A11 IEEE 登录 | **阻塞** | 同 A10；无可核验合法 IEEE 账号和真实受保护 PDF 续传证据。 |
| A12 命名/旧记录兼容 | **部分通过** | 非法字符、Unicode、超长、同名与旧 `file_name` 的单元/API 兼容测试通过；缺真实旧 `papers.json` + 旧 `{paper_id}.pdf` 贯穿列表、检索、重建、删除的端到端矩阵。 |
| A13 安全异常 | **部分通过** | 本轮专项 95 passed，安全矩阵覆盖 URL/SSRF/重定向/PDF/清理/脱敏；真实 DNS rebinding/peer 绑定和真实浏览器异常路径未验。 |
| A14 排序质量 | **阻塞** | 未发现 Spec015 专属不少于 12 条查询、每条至少 3 个候选、冻结时间/hash、人工标签、逐查询 nDCG@10/Recall@10 或灾难性退化报告；Task04 仍待执行。 |
| A15 回归交付 | **不通过** | 全量自动化和覆盖率本轮通过，服务首页/health/会议列表 200；但有 1 项真实 Ollama 调用跳过，且缺 A3、A4/A14、真实公开 PDF、旧 KB 端到端、GUI/窄屏、ACM/IEEE 登录等硬证据，不能放行。 |

## 明确阻塞与放行条件

1. 完成 Task04：先冻结排序查询/候选/标签及 hash，再实现并验证 embedding/rerank、异常降级和 nDCG@10/Recall@10。
2. DBLP Venue Search 恢复后，完成自定义会议搜索、选择、新增、修改、停用和内置删除保护的真实闭环。
3. 在具备 Playwright 和合法账户的 headed 环境完成 ACM/IEEE 登录续传，并补真实公开 PDF、知识库检索和服务重启/批量运行证据。
4. 补真实旧 KB 物理文件列表、检索、重建、删除矩阵，以及真实 GUI/窄屏验收。

在上述阻塞解除并由 Tech Lead 签字前，Spec015 必须保持 `实施中`，不得标记 `已完成`，不得进入最终提交收口。

## 签字

- 测试（QA）：**整体验收不通过（阻塞）**

## 2026-09-08 USENIX-only 增量验收复核

本轮按用户明确的“先跑通 USENIX，之后再扩展会议”范围复验 Task15–17。旧报告中 ACM/IEEE 登录、自定义会议、A14 排序质量和真实公开 PDF/GUI 证据不作为本阶段 USENIX 目录变更阻塞，继续保留为 deferred。

- QA 报告：`/private/tmp/015-task17-acceptance-final2.md`；fix-g 定向 105 passed，重点并发/过期租约/跨 DOI 合并/DBLP 与 USENIX partial 7 passed，前端契约 4 passed。
- 后端复审：`/private/tmp/015-task15-backend-review-h.md`，生产 SQLite 路径 PASS；失败/异常 owner-safe 释放、过期恢复和 stale owner 保护均有证据。
- 全量后端最终：650 passed、1 skipped、5 warnings、38 subtests；`node --check frontend/app.js`、`py_compile`、`git diff --check` 和冲突扫描通过。
- 结论：**USENIX-only 阶段通过**；Spec015 总状态保持实施中，待后续扩展阶段补齐 deferred 验收后再总收口。
- 开发主管（Tech Lead）：**待签字**
