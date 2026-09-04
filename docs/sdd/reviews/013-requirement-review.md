# 需求评审：spec-013 本地 LLM 调用观测与性能评估平台

- **评审对象**：`docs/sdd/specs/013-llm-observability-platform.md`（当前状态：`待确认`）
- **评审时间**：2026-09-03 16:31–16:42（Asia/Shanghai）
- **评审角色**：tech-lead（开发主管，`Task(tech-lead)` 分派）
- **评审模型**：`qwen3.8:27b-mlx`（本地 Ollama，MLX 版）
- **分派方式**：主会话 `Task(subagent_name="tech-lead")`
- **进展日志**：`.codebuddy/agent-logs/tech-lead-013-requirement-20260903-163153.md`

## 结论：通过（附意见）

5 个评审维度全部满足判定要点，无阻塞项。附 5 条意见，其中 C1–C4 为**实现前必须执行**的强制约束（已沉淀见下节），C5 为流程提醒。

## 评审意见

| 维度 | 判定 | 说明（含 spec 行号与代码事实依据） |
| :--- | :--- | :--- |
| 1. 目标清晰可测 | ✅ 清晰 | L13 一句话目标可无歧义复述：记录每次调用 → 分阶段耗时瀑布 → 定位「首 token 慢」根因。L17–25 背景给出三个具体待回答的问题（冷加载 vs prefill、LangChain 层开销、KB RAG 各阶段占比，L21–23），并在 L25 点明「`ChatOllama` 丢弃了 Ollama 原生 timings 字段，必须新增直连客户端」——「凭什么算解决」闭环：解决 = 能回答这三个问题。实测佐证：`backend/app/services/ollama_direct.py` L123 已解析 `prompt_eval_duration` 等原生字段，与 L25 声称的字段真实存在一致。 |
| 2. 验收方式可测 | ✅ 可测（2 条容差待量化） | A1–A10 每条均对应可执行动作：A1 `curl http://127.0.0.1:3000`（实测 health 返回 `{"status":"OK","version":"4.27.0"}`）；A2/A3 发一次对话看 trace 详情；A4 看瀑布图五段；A5 冷/热两次调用对比 load 段；A6 双链路基准端点；A7 KB 提问看四阶段 trace；A8 六项统计视图；A9 `LANGFUSE_ENABLED=false` 后跑对话+KB 回归；A10 `pytest` 计数 ≥253（实测 task 03 基线 253，task 04 新增 `test_ollama_direct.py`+`test_observability.py` 共 39 例通过，全量只会更多）。**改进**：A4「长度与实测耗时一致」、A5「很长 / 接近 0」无量化容差，建议实现时补「误差 ≤10% 或 ≤50ms（取大者）」「热调 load_ms ≤50ms」类判据，避免验收分歧。 |
| 3. 边界完整 | ✅ 完整（9 条均可转测试） | L127–135 共 9 条，逐条可测试：①Ollama 停服 → 停 11434 后发请求断言错误提示且无 500；②流中断 → mock 断流断言部分上报+不完整标记；③缺 timings → 构造无 `load_duration` 的响应断言字段 0 + `timings_available=false`；④空 thinking → 非思考模型断言空串；⑤时钟误差 → mock `client_wall_ms < total_ms` 断言 overhead=0 无负值；⑥超长 → 造 30k 字 prompt 断言截断+标记；⑦Langfuse 停服 → stop-infra.sh 后对话正常；⑧开关关闭 → 代码已核实 `backend/app/core/config.py` L49 默认 `LANGFUSE_ENABLED="false"`，断言零网络；⑨采样率 0/1/越界 → 代码已核实 `backend/app/observability/config.py` L25–37 越界回退 1.0+warning，断言行为。空态/异常/降级三类齐全，单人场景无需多设备/权限边界。 |
| 4. 「明确不做」划死 | ✅ 划死（1 处重复行） | L139–147 名义 9 条，**L145 与 L146 逐字重复**（「不做自动告警与阈值通知（v4 的 Monitors 功能本次不启用）」），实质 8 条。覆盖面：部署方式（L139 Docker）、链路范围（L140 文章检索下载）、侵入性（L141 不改 LangGraph/KB 逻辑，包裹外挂）、默认行为（L142 `OLLAMA_ROUTE` 默认 `langchain`）、UI 组件（L143 不自研甘特图）、用户体系/权限（L144）、告警（L145）、历史数据（L147）。灰色地带核查：task 07「前端自研 Ollama 专用视图」是聚合统计页，与 L143「不自研甘特图（瀑布）」不冲突，spec L207 已记录用户拍板 A/B 双路径；「包裹外挂」与 A7 要求 KB 四阶段 trace 亦不矛盾（埋点在既有函数外包裹）。足以防蔓延。 |
| 5. 范围合理 / 风险收益 / 回滚可操作 | ✅ 合理 | 风险面：重建 venv（已核实 3.9→3.11.16 完成，`.venv-py39.bak` 目录实测存在可切回）+ 4 个常驻基础设施（实测 Langfuse 4.27.0 健康、ClickHouse ping OK）。收益面：解决用户核心痛点（对话慢、首 token 归因无据可查），Ollama 原生 timings 是现成钥匙（L25），无需自研采集协议。收益/风险匹配，且用户已拍板（L207–208 changelog 四项+两项）。**回滚点可操作性逐项核实**：L34 基线 commit `294138c` 在仓库真实存在（`docs(sdd): 补录 spec-012…`），当前分支 `feature/spec-011-knowledge-base-rag` 与 L33 一致；L49 `LANGFUSE_ENABLED=false` 已核实代码默认即为 false（`config.py` L49）；L51 `.venv-py39.bak` 目录存在；L52 `deploy/langfuse/stop-infra.sh` 文件存在。Go/No-Go 关卡（L54）已实际执行：task 02 判定 Go，最高风险项（ClickHouse 官方二进制）已落地运行。 |

## 强制约束（实现必须遵守）

- **C1（修订 spec，实现前完成）**：删除 L146 的重复行（与 L145 逐字相同）。
- **C2（修订 spec，实现前完成）**：L114 score 列表中的 `prefill_ms` 改为 `prompt_eval_ms`，与 L104 数据模型字段名及已实现代码（`backend/app/observability/spans.py` L41/L87 用的均为 `prompt_eval_ms`）保持一致，消除 spec 内部两处命名矛盾。
- **C3（task 05 前置硬卡点）**：task 04 的真实上报冒烟必须在 task 05 开工前通过——判定标准：发一次调用后，Langfuse UI（及 ClickHouse `traces` 视图）能看到对应 trace。已知现状：ingestion 207、事件已入 `events_full`/`events_core`，但 `traces`/`observations` 视图 0 行（疑 v4 GRANT 或 ingestion worker，`deploy/langfuse/clickhouse-grants.sql` 已存在可对照）。**未通过则停在 task 04 排查，不得带病推进业务埋点**（否则 task 05/06/07 的验收 A2–A8 全部无从谈起）。
- **C4（验收量化）**：A4 与 A5 在 task 08 验收前由 PM/测试补量化容差（建议：瀑布段长度与实测耗时误差 ≤10% 且 ≤50ms 取大者；热调用 `load_ms` ≤50ms、冷调用 `load_ms` ≥ COLD_START_THRESHOLD_MS=200ms），写入 task-08 验收判据。
- **C5（流程提醒）**：spec L164–166「产品使用步骤」仍待 PM 补充，Gate 1 的「产品步骤映射验收点」自检项在 PM 补段后才算关闭；补完后须逐条映射到 A1–A10 并回填。
- **C6（继承既有硬约束）**：直连客户端必须 `trust_env=False`（已核实 `ollama_direct.py` 与单测 `test_ollama_direct.py` L166–175 已落实，task 05 接入时不得回退）；埋点异常一律 no-op 降级不冒泡（边界⑦/L121，`observability/client.py` 已落实）。

## 风险定级：中

依据：技术可行性已被 task 02/03 部分验证（基础设施在跑、Python/SDK 就位、39 个单测通过），回滚路径四个动作全部实测可达；但未消除的风险是「trace 在 UI 不可见」的冒烟阻塞（C3）——它直接卡住 A2–A8 全部主链路验收，且根因未定位。风险集中在部署链路而非需求定义，故定级中（非高）；若 task 04 冒烟排查超过 1 个工作日无进展，应触发 L54 关卡回退决策，而非继续加码。

## 判定统计

| 项 | 数量 |
| :--- | :--- |
| 评审维度 | 5 / 5 通过 |
| 阻塞项 | 0 |
| 强制约束（C1–C6） | 6 条（其中 C1/C2 需先修订 spec） |
| 核实的代码/环境事实 | 基线 commit 存在、分支一致、Langfuse 4.27.0 健康、ClickHouse ping OK、Python 3.11.16、langfuse==4.15.1 锁定、39 单测通过、`.venv-py39.bak` 与 `stop-infra.sh` 存在、`LANGFUSE_ENABLED` 默认 false、采样率边界处理存在、KB 四阶段函数入口存在 |
