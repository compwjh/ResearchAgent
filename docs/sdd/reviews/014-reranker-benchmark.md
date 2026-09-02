# Spec 014 Reranker 测试与质量基准报告

## 执行信息

- 执行角色：tester（`gpt-5.6-luna`，high）
- 工作目录：`/private/tmp/PyCharmMiscProject-spec014`
- 执行时间：2026-09-02（Asia/Shanghai）
- 报告状态：已完成（2026-09-02；补充验证以架构师本机网络授权结果为准）；本报告只记录已执行结果，未执行项目明确标注。
- 约束：未修改生产代码、测试代码、spec-013 文件或原知识库数据；原知识库仅以只读方式打开。

## 质量集冻结（先于首次查看 rerank 排名）

以下问题、目标片段标识和标签在 2026-09-02 21:31:15 CST 冻结。冻结时只查看了 Qdrant 原始片段与 RRF 基线候选，没有查看 rerank 排名；冻结后不得删除题目、改目标或改相关性标签。目标标签为“该片段是回答问题时应优先引用的相关片段”，每题一个目标片段。

数据源：`/Users/wjh/PyCharmMiscProject/data/kb/qdrant`，collection `papers`，只读点数 1132；元数据文件 `papers.json` SHA256 `0155ee17bac37424126d0eb4119a56c842c5b58d4c53375451b207ddc90f65c2`，Qdrant `meta.json` SHA256 `54f781bc39d6f64b862e1ed4c8bf1d624786aecbca0c2b7cf15b8495dd58d3b1`。

| # | 固定问题 | 目标片段标识（paper_id / chunker / chunk_index / page） | 目标片段 SHA256 |
|---:|---|---|---|
| 1 | What is an agentic skill and how does it differ from ordinary tool use? | `a8caef6843134a2397cd5960864ae29e / v1 / 4 / 1` | `71c0cbdd5fd69bb00266bbe2704a7ece05f576e557de43a7482fc5ad8414188f` |
| 2 | What are the seven design patterns for agentic skills? | `a8caef6843134a2397cd5960864ae29e / v1 / 41 / 7` | `5ba65c33b16cc8ddf401d650cda8a372a0cc284c29eb2f861f1a10691756d38a` |
| 3 | How does Proposer-Builder Separation work in Ethereum? | `f1ea7d6e35be4e73a26b0b2b247e0e36 / v1 / 12 / 2` | `9db0de97913ce45b54f50074b098ab869a868c119544bf8c8b6e573a378ed611` |
| 4 | What evidence shows PBS achieves its intended objectives? | `f1ea7d6e35be4e73a26b0b2b247e0e36 / v1 / 7 / 1` | `e35701cb03449fe806503922506d0899893aa945234f1313d7a672781f8b5d70` |
| 5 | What is the purpose of proof-carrying disclosures in Derecho privacy pools? | `628d96cc46bc48b5bb8c5e422f0ed8d0 / v1 / 8 / 2` | `f8107b2478def4777663f7625f7c63bd8b8ccb1e057cfabf88acc15f2a96559c` |
| 6 | What are the proving and verification times reported by Derecho? | `628d96cc46bc48b5bb8c5e422f0ed8d0 / v1 / 10 / 2` | `e68a4d4e815cc3462ea65df67c34dccb59a420f5742e7d6f23be4a940b4dfb4e` |
| 7 | How does the peel-chain heuristic identify change outputs in Bitcoin? | `d4dfd2a620384ad5bece27320661f8f0 / v1 / 20 / 4` | `9239173595242397c95904ad47a3338e4c18252a98a2bdd641148d01620509ce` |
| 8 | What ground truth dataset is used to validate Bitcoin clustering heuristics? | `d4dfd2a620384ad5bece27320661f8f0 / v1 / 21 / 4` | `df4b616081e4b0f27a1a8142669e5eca3370cd1b839fd51f1123d6fc43e5bd92` |
| 9 | Why are HTLC contracts vulnerable to bribing attacks? | `1b11eaec883642c5a702a6d00565d5bd / v1 / 14 / 2` | `27b3ef9b4579bdc684b54d1da043b39e8864893a7c10808cdb2f14e05ae3ede5` |
| 10 | How does MAD-HTLC improve security over conventional HTLCs? | `1b11eaec883642c5a702a6d00565d5bd / v1 / 8 / 1` | `9ef7382ff2728831973ecea491fe07e24eae8c59ed313ef355fe6a80be2535f9` |

冻结集合之后只允许追加实测结果，不允许修改以上十题及标签。

## 1. 单元与回归测试

### 已执行

命令：

```bash
.venv/bin/python -m pytest -q --disable-warnings
```

结果：**268 passed, 1 failed, 5 warnings, 29 subtests passed；269 tests collected；退出码 1；3.17s**。

失败项为既有 `tests/test_api.py::AgentApiTests::test_download_with_use_skill_records_skill_name`，期望 `/api/agent/articles/download` 为 200，实际为 503。该失败不在 reranker 测试范围内；报告不将其改判为通过。

### Reranker 专项测试

已执行命令：

```bash
.venv/bin/python -m pytest -q tests/test_kb_reranker.py tests/test_reranker_config.py tests/test_kb_services.py
```

结果：**86 passed, 5 warnings, 29 subtests passed；退出码 0；0.80s**。覆盖客户端映射、乱序 index、稳定同分、非法 schema/index/score、连接/超时、禁用与负缓存降级，以及候选池 20 条与 RRF 集成映射。

全量覆盖率命令：

```bash
COVERAGE_FILE=/tmp/spec014-task07.coverage .venv/bin/python -m coverage run --source=backend -m pytest -q --disable-warnings
COVERAGE_FILE=/tmp/spec014-task07.coverage .venv/bin/python -m coverage report -m
```

结果：执行仍为 **268 passed、1 failed、269 collected、退出码 1**（同一既有 503 失败）；coverage **87%（2169 statements, 279 missed）**，达到 80% 门槛，但因存在失败用例，A11 总体不通过。

### 全量复测（2026-09-02 21:41:42 CST）

按用户反馈曾单独复跑通过后，再次执行以下命令验证稳定性：

```bash
.venv/bin/python -m pytest -q --disable-warnings
COVERAGE_FILE=/tmp/spec014-task07-rerun.coverage .venv/bin/python -m coverage run --source=backend -m pytest -q --disable-warnings
COVERAGE_FILE=/tmp/spec014-task07-rerun.coverage .venv/bin/python -m coverage report -m
```

本次全量 pytest 仍失败：**268 passed, 1 failed, 5 warnings, 29 subtests passed；269 collected；退出码 1；3.34s**。coverage pytest 同样为 **268 passed, 1 failed；退出码 1；4.09s**，coverage **87%（2169 statements, 279 missed）**。失败仍为 `tests/test_api.py::AgentApiTests::test_download_with_use_skill_records_skill_name`，断言实际 HTTP 503、期望 200；完整输出见 `/tmp/spec014-task07-pytest-rerun.txt` 与 `/tmp/spec014-task07-coverage-rerun.txt`。

因此当次受限环境复测未达到 269 passed；质量集和前述 rerank 标签未作任何修改。后续架构师在本机网络授权环境的补充验证见报告末尾。

## 2. 真实 Q8_0 服务与协议探针

### 已执行

真实模型文件：`/private/tmp/spec014-models/qwen3-reranker-0.6b-q8_0.gguf`，由 Task 02 验证，SHA256 `22c9979ce4fbcdc5acdc310c6641c32797eff1aa980b8f7a2db8a8ea23429a48`，大小 639153184 bytes。

启动方式：隔离 worktree 的 `deploy/reranker/start.sh`，显式传入上述模型、`RERANKER_SERVER_BIN=/Applications/Ollama.app/Contents/Resources/llama-server`，监听 `127.0.0.1:11435`。启动输出：`Reranker 已启动：http://127.0.0.1:11435（PID 99143）`。

启动脚本内真实固定三文档质量探针通过：`health ready; ranking valid`。请求未发送 `model` 字段，符合 Task 02 的 API 实测契约。之后以前台长驻方式重新启动同一二进制完成基准，并在测试结束发送 SIGINT；进程退出码为 0，11435 已释放。

### 生产 FastAPI 联合启动

已在 §4 记录停服后的 mock-free `/api/kb/ask` 降级验证；生产部署脚本的完整联合启动/前台交互不属于本次隔离基准，待 Task 08/09 集成阶段执行。

## 3. 固定质量集 RRF / rerank 对比

### 已执行（仅 RRF 冻结前基线候选）

在 `RERANKER_ENABLED=false`、`KB_DIR` 与 `QDRANT_PATH` 指向上述只读数据、`chunker=v1`、`candidate_pool=30` 的条件下，已读取十题各自的 RRF 前 20 候选并完成目标片段冻结；目标片段均在对应 RRF 前 20 中。

### 已执行

在同一只读 Qdrant 索引、同一问题、`chunker=v1`、候选池 30、rerank 候选 20、`top_k=20` 下，先以 `RERANKER_ENABLED=false` 得到 RRF，再以真实 llama.cpp `/v1/rerank` 得到 rerank。逐题目标排名和 MRR@5 如下（排名为 1-based；`—` 表示不在 top5）：

| # | RRF 目标排名 | Rerank 目标排名 | RRF MRR@5 | Rerank MRR@5 | 变化 |
|---:|---:|---:|---:|---:|---:|
| 1 | 2 | 2 | 0.500 | 0.500 | 0 |
| 2 | 8 | 1 | 0.000 | 1.000 | +7 |
| 3 | 2 | 2 | 0.500 | 0.500 | 0 |
| 4 | 7 | 6 | 0.000 | 0.000 | +1 |
| 5 | 9 | 13 | 0.000 | 0.000 | -4 |
| 6 | 2 | 2 | 0.500 | 0.500 | 0 |
| 7 | 4 | 4 | 0.250 | 0.250 | 0 |
| 8 | 6 | 1 | 0.000 | 1.000 | +5 |
| 9 | 2 | 1 | 0.500 | 1.000 | +1 |
| 10 | 7 | 5 | 0.000 | 0.200 | +2 |

汇总：`MRR@5(RRF)=0.225`，`MRR@5(rerank)=0.495`，rerank 高于 RRF `+0.270`。题 2 的目标从 RRF top5 外（第 8 名）进入第 1 名，题 8 从第 6 名进入第 1 名，满足“至少一个 top5 外目标提升进入 top5”的硬条件；题 9、10 也有提升。十题真实返回均含完整 20 项、有限分数和有效 index。

## 4. 固定协议与性能资源

### 已执行

使用一次前台启动/停止脚本（同一 Q8_0 GGUF，`127.0.0.1:11435`）记录如下：

- 冷进程启动至 `/health=200`：`0.528s`；启动后的首个 20 文档 rerank：`0.378s`。说明：进程为冷启动，操作系统文件缓存未刻意清空。
- English probe：结果顺序 `[1, 0, 2]`，分数 `index1=0.994893`、`index0=0.0000350`、`index2=0.0000277`，HTTP 200。
- 中文 probe：结果顺序 `[2, 1, 0]`，分数 `index2=0.999382`、`index1=0.0000217`、`index0=0.0000171`，HTTP 200。
- 20 候选热请求 5 次：`0.378s, 0.349s, 0.369s, 0.357s, 0.367s`；中位数 `0.367s`，最大值 `0.378s`，每次返回 20 项，未触发 60 秒读取超时。
- 采样到的 llama-server 进程 RSS 峰值：`2,114,880 KiB`（约 `2.02 GiB`）；进程 SIGINT 正常退出码 `0`，日志未见 OOM。

### 已执行：停服降级

停掉 Reranker 后，以 `RERANKER_ENABLED=true`、`RERANKER_BASE_URL=http://127.0.0.1:11435` 启动隔离 FastAPI（端口 8001），并将 `KB_DIR`、`QDRANT_PATH` 指向原只读知识库。`GET /api/kb/health` 返回 200，内容中 `reranker=false`、`available=false`、`reason=connection`，同时 `qdrant=true`、`embedding=true`、`papers=5`、`chunks=1132`。随后真实 `POST /api/kb/ask`（回答模型 `qwen3.5:9b`，无 mock）返回 HTTP 200，SSE 产生 12,789 bytes，包含 `citations`、`token`、`debug` 和 `done`，总耗时 `73.839s`，FastAPI 正常退出码为 0；证明 Reranker 停服时问答仍能按 RRF 降级完成。

命令输出保存在临时日志：`/tmp/spec014-task07-pytest.txt`、`/tmp/spec014-task07-reranker-tests.txt`、`/tmp/spec014-task07-coverage.txt`、`/tmp/spec014-task07-cold.log`、`/tmp/spec014-task07-fastapi.log`；未写入项目数据。

## 5. 当前结论

Task 07 真实模型、冻结质量集和停服降级的实测条件均已完成：A1/A2/A3/A8/A9 通过，MRR@5 从 0.225 提升到 0.495，且存在 RRF top5 外目标进入 rerank top5；A6 的真实 SSE 降级通过。tester 受限环境曾两次记录 269 collected / 268 passed / 1 failed，覆盖率 87%；架构师随后在本机网络授权环境补充复测为 269 passed，故按最终真实结果 A11 通过，Task 07 执行结果为完成。mock 专项降级用例已由现有测试覆盖，但本任务未修改测试代码。

## 补充验证（架构师，本机网络授权）

执行者：架构师（主会话，非 tester）；执行时间：2026-09-02（本机网络授权环境）。命令：

```bash
.venv/bin/python -m pytest -q
```

真实结果：**269 passed, 5 warnings, 29 subtests passed；退出码 0；61.99s**。该结果满足动态回归基线 `269 passed`，因此以本机网络授权环境的真实结果为准，A11 回归测试与覆盖率门槛（前述 coverage 87%）通过，Task 07 执行结果标记为**完成**。

此前 tester 在受限网络环境执行的两次 `268 passed + 1 failed` 证据仍保留，失败项仍为 `tests/test_api.py::AgentApiTests::test_download_with_use_skill_records_skill_name`（HTTP 503/期望 200）；该记录不被删除或改写，差异归因于执行环境权限。

架构师随后在同一“本机网络授权”环境补充执行 coverage：

```bash
COVERAGE_FILE=/tmp/spec014-final.coverage .venv/bin/python -m coverage run --source=backend -m pytest -q
COVERAGE_FILE=/tmp/spec014-final.coverage .venv/bin/python -m coverage report -m
```

真实结果：**269 passed，退出码 0，用时 49.67s；2169 statements、283 missed、TOTAL 87%**。该结果进一步确认 A11 的全量测试与覆盖率门槛通过。
