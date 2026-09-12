# Spec027 Task06 复用与范围审计

## 结论

**通过，无 P0/P1。** `research` 限界上下文只经既有 Spec015 目录搜索/RAG 接缝和既有 Ollama 平台接缝；未发现第二套论文采集、目录、缓存、索引、RAG、下载、导入或模型客户端。Task06 未修改业务代码。

## 证据

- `backend/app/research/application/search_catalog_adapter.py:102-164` 延迟装配并调用 `CatalogSearchGraph` 与 `CatalogRagAdapter`；固定样本分别得到 `SOURCE_DEGRADED` 和 `fixed-catalog-1`。
- `backend/app/research/application/model_router.py:26` 仅从 `backend.app.platform.ollama.get_available_models` 解析模型；`orchestrator.py:86` 的资源探针也回到同一平台模块。
- `backend/app/research` 源码扫描未发现 `urllib`、`aiohttp`、`requests`、`playwright`、独立下载/索引客户端或第二模型 HTTP 客户端导入。
- 研究库只存 `catalog_paper_id` 等引用字段；无论文 title/abstract 复制。前端报告选集同样只投影白名单字段。
- `pause`/`resume` 在研究代码与前端研究模块中无命中；符合 Spec027 明确不做并移交 Spec028。
- Task02–05 报告已复用：Task02 Runtime Gate、Task03 后端评审复审、Task04 前端 GO、Task05 后端/前端固定样本交接报告；历史 P0/P1 均已有关闭证据。

## 收口时发现并处理的问题

全量 pytest 首轮唯一失败为 `tests/test_kb_upload_closure_matrix.py::test_inventory_hashes_are_stable_and_write_entrypoints_are_registered`：`backend/app/main.py` 的当前 SHA 为 `ff806b...fc4355c`，冻结清单仍为 Spec020 改动前的 `79be3c...5301d8`。`git blame`/`git log` 证明差异来自已提交 Spec027 commit `5fef125` 增加 `common.recover_research_tasks()` 的启动收敛，而非 Task06 临时改动。

按冻结清单既有惯例，只更新 `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` 中该文件 SHA 和排序 digest；未重写 Spec015/018/022 业务代码。定向复验随后为 2 passed。

## 未升级为缺陷的环境项

- 真实 `USENIX` 返回 `USENIX_UNAVAILABLE`，真实 `DBLP` 返回 `DBLP_NETWORK_ERROR`/`DBLP_UNAVAILABLE`；固定 Adapter 样本通过，未伪造外部来源成功。
- localhost Ollama `/api/tags` 可达并列出 11 个模型，但 `qwen3.5:9b` 最小 chat 3 秒超时；未把模型清单当作推理成功。
