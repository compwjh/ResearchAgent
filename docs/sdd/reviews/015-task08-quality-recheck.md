# Spec015 Task08 排序质量、安全与回归复核

- 执行角色：tester（QA）
- 本轮模型：Luna high（临时）
- 执行时间：2026-09-05（Asia/Shanghai）
- 关联任务：[`task-08-tests-ranking-and-security.md`](../plans/015/task-08-tests-ranking-and-security.md)
- 关联 Spec：[`015-security-paper-discovery.md`](../specs/015-security-paper-discovery.md)
- 约束：仅执行离线/本地检查；未修改生产代码，未执行 reset、stash、clean、commit 或 push。

## 先给结果

**Task08 本轮质量复核不通过，排序质量门禁保持阻塞；离线安全与回归检查通过。**

论文发现服务当前仍由 `SequenceMatcher` 计算 `retrieval_score`，未接入 Task04 要求的 embedding/reranker，也没有最终 rerank 输出可供比较。因此 A14 的“最终 nDCG@10 不低于初排、无灾难性退化”不能判定；本轮没有把词法诊断指标冒充验收结果。

## 排序质量（阻塞）

为满足“缺固定样本时先建立最小可复现 fixture”的要求，新增离线诊断冻结集：[`015-task08-quality-fixture.json`](015-task08-quality-fixture.json)。该 fixture 在查看任何最终 rerank 排名之前冻结，包含 12 条方向查询、每条 3 个候选和人工相关性标签；规范化 JSON（不含可选 hash 字段）的 SHA-256 为 `15e9305d7c85f965fb619368633e355d13ff8a1d6fc69ba54b2bdd677583375d`。它是 Task04 未实现期间的诊断资产，不能替代真实 DBLP/OpenAlex 快照或 A14 验收集。

复现命令：

```text
./.venv/bin/python -c '<读取 015-task08-quality-fixture.json，调用 PaperDiscoverySearchService._score，计算每查询 nDCG@10/Recall@10>'
```

退出码：`0`。结果：词法初排总体 `nDCG@10=0.855`、`Recall@10=1.000`；其中 `LLM agent security`、`software supply chain attacks`、`memory safety C`、`secure hardware enclaves` 的首位不是人工标记的最高相关候选，分别为 `0.731`、`0.731`、`0.606`、`0.606`。因每条仅 3 个候选且均落在 top-10，Recall 仅为 fixture 自检信号，不能作为产品质量通过证据。

源码核对命令：

```text
rg -n 'SequenceMatcher|embedding|rerank|ranking_mode|rerank_degraded' backend/app/services/paper_discovery_search.py docs/sdd/plans/015/task-04-semantic-ranking-and-rerank.md
```

退出码：`0`。核对到实现仍导入并调用 `SequenceMatcher`（`paper_discovery_search.py:8,246-252`），仅在计划文档中出现 embedding/rerank 契约；本轮未观察到 rerank 调用、最终排序、降级标志或 A14 对比结果。

## 离线安全检查（通过，但不等于真实外部链路）

| 检查 | 命令 | 结果 |
|---|---|---|
| SSRF、PDF、浏览器 fake | `.venv/bin/python -m pytest -q -o addopts='' tests/test_paper_download_security.py tests/test_paper_download.py tests/test_paper_browser_manager.py` | 退出码 0；41 passed，5 warnings |
| 论文发现安全相关回归 | 包含 SSRF 地址/混淆 IP、HTTPS/443、allowlist、userinfo/认证 query、逐跳重定向、循环上限、伪/损坏/加密 PDF、头部上限、断流和临时文件清理 | 上述 41 项全部通过 |
| DNS rebinding 集成 seam | 离线 `MockTransport`：DNS 首次返回公共 IP，peer resolver 返回 `10.0.0.1` | 退出码 0；结果 `DOWNLOAD_BLOCKED`，临时目录为空 |

上述测试证明当前注入 seam 能拒绝实际 peer 与 DNS 校验不一致的连接；未执行真实 DNS rebinding、真实公网 PDF、ACM/IEEE 登录续传或 headed GUI。Playwright Python 包当前为 `1.52.0`，但本轮没有合法账号和用户参与认证凭证，不能声称 A10/A11 通过。

## 论文发现、导入与旧 KB 回归（通过）

| 检查 | 命令 | 结果 |
|---|---|---|
| 发现/仓储/API/OpenAlex/DBLP | `.venv/bin/python -m pytest -q tests/test_paper_discovery_search.py tests/test_paper_discovery_store.py tests/test_paper_discovery_api.py tests/test_dblp_publication_source.py tests/test_openalex_enricher.py` | 退出码 0；53 passed，9 subtests |
| 下载/导入/旧 KB | `.venv/bin/python -m pytest -q -o addopts='' tests/test_paper_import.py tests/test_paper_import_identity.py tests/test_paper_import_batch_store.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_api.py tests/test_legacy_kb_integration.py` | 退出码 0；56 passed，5 warnings |
| 全量普通回归 | `.venv/bin/python -m pytest -q -rs` | 退出码 0；526 passed，5 warnings，38 subtests，89.66s |
| Ollama 直接调用单测 | `.venv/bin/python -m pytest -q -rs tests/test_ollama_direct.py` | 退出码 0；21 passed，34.22s |
| 覆盖率全量 | `COVERAGE_FILE=/tmp/spec015-task08-quality-recheck.coverage .venv/bin/python -m pytest --cov=backend/app --cov-report=term-missing:skip-covered -q -rs -o addopts=''` | 退出码 0；525 passed，1 skipped，5 warnings；总覆盖率 84%（6303 statements）。跳过项为 `tests/test_ollama_direct.py:367` 的真实 Ollama 可用性场景 |

覆盖率报告中 `paper_discovery_search.py` 为 80%，`paper_download.py` 为 82%，`paper_download_security.py` 为 86%；总覆盖率达到既有 80% 门槛，但不补足 Task04 的排序质量证据。

## 静态与产物检查（通过）

- `./.venv/bin/python -m compileall -q backend/app frontend && node --check frontend/app.js && git diff --check -- . ':!data' ':!deploy/*.log'`：退出码 0。
- 全仓冲突标记扫描：0 命中。
- `git ls-files` 敏感运行产物扫描：未发现 browser profile、profile lock、HAR、trace、video、Cookie、运行 SQLite 或 PDF 被跟踪；忽略目录也未发现 HAR/trace/video/Cookie 样本。

## 阻塞项与下一步

1. **A14 / Task04：阻塞。** 由 junior-dev 在确认后的 Task04 中接入 embedding 与 spec-014 批量 rerank；先保留本冻结集及 hash，再追加最终排序、逐查询 nDCG@10/Recall@10、查询差异和灾难性退化清单。不得修改标签来制造通过。
2. **真实链路：阻塞。** 需要受控的公开 PDF/服务运行证据，以及用户亲自完成 ACM/IEEE headed 登录、SSO/验证码和续传；本轮离线 fake 不替代这些证据。
3. **旧 KB 真实介质链路：仍为后续质量债务。** 当前专项单测和 FakeQdrant 集成回归通过，但未新增真实部署环境下的用户数据验收。

### QA 结论

- 离线安全矩阵：通过。
- 发现/导入/旧 KB/全量回归：通过。
- 排序质量 A14：阻塞，不能签署 Task08 完成。
- Tech Lead 签字：待签字。
