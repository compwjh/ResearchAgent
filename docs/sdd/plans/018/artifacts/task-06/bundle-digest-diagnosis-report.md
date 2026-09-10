# Task 06 Bundle Digest 诊断报告

- 角色：backend-reviewer
- 模型：临时使用 Luna high
- 范围：只读分析；未执行真实重建，未修改业务代码或项目数据
- 时间：2026-09-10

## 结论

当前连续失败的剩余根因最可能是 dense 向量 digest 的容差仍不足，而不是 payload、sparse、anchor 或 `llm_used` 元数据不一致。

`_build()` 在写入 Qdrant 前计算 dense digest；本地 Qdrant 的 cosine collection 会对 dense 向量做单位归一化，并以浮点精度序列化；`_validate()` 对读回值再次归一化。当前 `_dense_vector_digest_input()` 量化到 4 位小数。1024 维向量中，只要某个分量接近 `x.xxxx5` 舍入边界，写入前与读回后的极小浮点误差就可能让该分量跨过边界，从而使整个文档/分块器的 aggregate digest 不相等，最终只报 `BUNDLE_DIGEST_OR_VECTOR_MISMATCH`。

## 证据 / 代码位置

### 1. Build 与 validate 对比的是同一逻辑值的不同存储阶段

- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py:1048-1051`：
  - payload/text digest 按 `points` 的 chunk 顺序计算；
  - dense digest 对写入前 `point.vector["dense"]` 调用 `_dense_vector_digest_input()`；
  - sparse digest 对写入前 `SparseVector` 转为 indices/values。
- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py:1247-1249`：校验逐点读回 dense/sparse 并计算逐点 digest。
- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py:1257-1258`：当前代码已按 `chunk_index` 排序 `by_point`，因此 Qdrant scroll 返回顺序不再是 aggregate digest 的主要问题。
- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py:1287-1293`：最终按排序后的点集合计算 payload、text、dense、sparse 和 anchor aggregate digest，并统一映射成 `BUNDLE_DIGEST_OR_VECTOR_MISMATCH`。

### 2. Qdrant 临时目录实验复现 dense 的边界假阳性

使用临时 Qdrant local 目录、1024 维随机 dense 向量、402 个点，按项目的 `_dense_vector_digest_input()` 比较写入前向量与 Qdrant 读回向量：4 位量化出现少量 mismatch（不同随机样本为 3～6 个点），一个实际差异示例是同一分量从 `0.0160` 变成 `0.0161`。将量化改为 3 位的小实验中，402 点未出现 mismatch。

该实验不读写项目的 `data/kb/qdrant`，也没有执行真实 rebuild。

### 3. 其他字段暂未发现同类序列化差异

在临时 Qdrant 402 点实验中：

- `_payload_digest_projection()` 的写入前/读回值比较：0 个 mismatch；
- SparseVector 的 indices/values digest 比较：0 个 mismatch；
- `QdrantCandidateIndexPort.scroll_points()` 的 `dict(item.vector or {})` 能保留 `dense` 列表和 `sparse` 的 indices/values；
- `anchor_digest` 是 payload 中的字符串，Qdrant 不会对其做数值归一化；
- v2 的 `llm_used` 在 `_build()` 阶段已强制要求为 true，若不满足会先得到 `V2_RULES_ONLY_LLM_NOT_USED`，不是当前 validation-only 错误。

## 最小修复建议

1. 将 `_DENSE_DIGEST_DECIMALS` 从 4 调整为 3，并更新注释，明确它是为了吸收 cosine 归一化及本地 Qdrant 浮点读回误差，而非精确重建向量。
2. 保留现有“单位归一化后量化”的策略，不直接放宽到向量相似度阈值；这样仍能检测明显的向量替换，同时避免存储层噪声改变 bundle digest。
3. 补一个真实存储语义回归样本：使用临时 Qdrant local collection、1024 维向量、至少数百个点，逐 ID 比较写入前和读回后的 digest。现有 `tests/test_kb_candidate_rebuild.py:974-1006` 只覆盖 4 维向量，无法覆盖 1024 维的舍入边界。
4. 在 `_validate()` 的 mismatch 分支保留可审计的内部字段诊断（例如分别记录 payload/text/dense/sparse/anchor 哪一项不等），但对外仍可返回稳定的 `CANDIDATE_VALIDATION_FAILED`；这能避免下次多次真实重建才能定位。

不建议删除 aggregate digest 校验，也不建议只比较点数或 query probe：这些会掩盖候选集合被改写的情况。

## 风险

- 3 位小数会降低 dense digest 的敏感度；建议回归一个明显改动（例如归一化向量某一分量增加 0.01）仍必须失败，并保留现有 tamper 测试。
- 如果下一次修复后仍失败，应先把 mismatch 分类记录出来，再判断是否存在 Qdrant 读回顺序、payload null 字段或 sparse 浮点序列化差异；不要继续盲目增加量化容差。
- 临时实验使用随机向量，不能替代一次真实 rebuild；修复后仍需在服务停止、Qdrant lock 释放的维护窗口执行生产重建。

## 主 Agent 后续动作

1. 先审阅并合入独立的 scroll 顺序修复；该修复解决 aggregate digest 的顺序依赖，但不能解决本报告的 dense 舍入边界问题。
2. 在 `candidate_rebuild.py` 最小修改 dense 量化精度，并增加 1024 维临时 Qdrant 回归测试。
3. 删除/清理本次失败 run 后，在服务停止状态运行一次真实 rebuild；记录新的 run id、validation errors、v1/v2 点数和 generation marker。
4. 若成功，启动服务并检查 `/api/health` 与 `/api/kb/health`；若失败，读取 validation artifact 中新增的分类字段定位下一个具体不一致。

## 测试建议

- `.venv/bin/python -m pytest tests/test_kb_candidate_rebuild.py -q`
- 新增的临时 Qdrant 1024 维读回 digest 回归测试。
- `git diff --check`
- 生产维护窗口：`LANGFUSE_ENABLED=false ./.venv/bin/python -m backend.app.knowledge_base.rebuild_index --confirm-replace`

