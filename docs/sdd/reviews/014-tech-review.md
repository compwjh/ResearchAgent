# 技术评审：spec-014 知识库本地 Rerank 重排

- 评审者：当前协作 Agent
- 角色：独立开发主管（Tech Lead）
- 实际模型：当前协作 Agent（未冒充 spec 执行配置中的本地 Ollama 模型）
- 分派方式：主会话通过协作 Agent 独立分派
- 评审对象：`docs/sdd/specs/014-kb-reranker.md`（实现前可行性评审）
- 评审时间：2026-09-02
- 评审方式：读取真实配置、检索、路由、前端、部署脚本与相关测试；未修改 spec、task 或业务代码

## 结论：通过（附意见）

“llama.cpp 专用 `/v1/rerank` + 单批请求 + 严格协议校验 + RRF fail-open”技术方向正确，能替换当前无效的逐条 ChatOllama 打分，同时不需要修改 Qdrant schema 或重建索引。Task 02 的真实模型探针是必要的 Go/No-Go；探针通过前不得进入代码实现。

## 代码事实核对

- `backend/app/services/kb/retrieve.py:144-146` 当前先截断最终 `top_k` 再 rerank，spec 改为“RRF 候选 20 → rerank → 最终 top_k”与代码缺陷准确对应。
- `retrieve.py:166-186` 当前对每个 hit 串行 `chat.invoke()` 并用正则取第一个数字；异常虽会回退原顺序，但既非专用 rerank 协议，也没有可解释原因。
- `retrieve.py:125-142` 的 dense/sparse 已共享相同 paper/chunker/citation filter；实现必须保留，不能因重排改回混召回。
- `backend/app/core/config.py:30-32` 当前只有 `KB_CANDIDATE_POOL` 与空的 `RERANKER_MODEL`，新增配置需要安全解析，不能让非法环境变量导致模块导入失败。
- `backend/app/api/routes.py:370-405` 当前 health 的 `reranker` 只取模型名是否非空，扩展为真实服务状态合理；health 失败仍应返回 200。
- `routes.py:486-540` 当前 KB 问答在同步 generator 内检索并保持 SSE 事件顺序；rerank 错误必须在检索层消化，不能进入现有 error 事件分支。
- `frontend/app.js:777-786` 使用 `textContent` 渲染状态，没有用户数据 `innerHTML` 注入风险；增加 detail 时应继续使用安全文本渲染。
- `deploy/start.sh:31-36` 当前前台模式 `exec uvicorn`、后台模式只记录 uvicorn PID；若新增 reranker 子进程，必须重新定义前后台清理与所有权，否则 Ctrl+C 或启动失败会留下孤儿进程。
- 当前 `git status` 显示 spec-013 修改至少覆盖 `config.py`、requirements、agent/流程文档，并新增 observability、Langfuse 和 direct Ollama 文件；这些都未提交，任何 reset/clean/stash 都存在丢失工作风险。
- 2026-09-02 实测 `ollama list` 中存在 `qwen3.8:27b-mlx`、`qwen3.8:27b`、`qwen3.5:9b` 和用户现有 reranker；但 `MODEL_REGISTRY.md` 尚未登记 `qwen3.8:27b-mlx`。

## 评审意见

| 维度 | 判定 | 说明 |
|---|---|---|
| 改动面 | 通过 | 配置、独立客户端、retrieve、health/UI、部署脚本和测试边界清楚，且 task 已按小批文件拆分。 |
| 协议可行性 | 附意见 | llama.cpp `/v1/rerank` 方向成立，但 `RERANKER_MODEL` 同时被描述为 HTTP model 标识和服务启动模型来源，需由 Task 02 实测后固定为无歧义契约。 |
| 兼容性 | 通过 | API 采用增量字段；Hit 新字段带默认值；禁用与异常保持 RRF；不写回向量库。 |
| 容错 | 附意见 | 单请求不重试、严格 schema 校验正确；还需防止服务长期不可达时每个问答都重复付出连接超时。 |
| 进程管理 | 附意见 | 自动选端口后必须可靠传给 FastAPI；前台 Ctrl+C、后台 stop、探针失败都必须只清理由本次启动拥有的 reranker 进程。 |
| 健康探针 | 附意见 | 质量探针不能每次 health 或问答都推理；30 秒缓存需并发安全、使用单调时钟，禁用时零网络请求。 |
| 安全与隐私 | 通过 | 仅 localhost、无 API key、无全文日志、前端 `textContent`；配置 URL 仍需拒绝非 loopback host。 |
| spec-013 集成 | 附意见 | 只接受明确 commit；集成后需验证 Langfuse/Reranker 四种组合，且冲突标记全仓扫描为 0。 |
| 模型与预算 | 附意见 | 分工符合质量优先策略，实际模型均已安装；registry 与现行 `qwen3.8:27b-mlx` 配置不一致，须先补登记。 |

## 强制约束（实现必须遵守）

- **T1 Go/No-Go**：Task 02 必须用最终选定的 llama-server 二进制和目标 Q8_0 模型，连续完成中英文固定探针、20 候选热请求、有限分数及稳定排序验证；HTTP 200 或 `/health` 成功不能替代质量探针。失败则停止 Task 03–09，禁止回退到聊天 prompt 打分。
- **T2 模型来源契约**：Task 02 结束时必须明确并落盘 llama-server 的启动参数和模型来源（例如经验证的 `-hf repo:quant` 或绝对 GGUF 路径），以及 `/v1/rerank` 请求中 `model` 的实际合法值。若启动来源与 API model 标识不同，新增独立配置，禁止继续复用一个含义模糊的 `RERANKER_MODEL`。
- **T3 工作树隔离**：创建 spec-014 worktree 前记录当前绝对路径、分支、HEAD 和 `git status --short`；不对当前目录执行 reset/clean/stash。spec-014 文档与两份 014 review 只能按明确文件清单复制到新 worktree；spec-013 代码只通过其最终 commit 集成。
- **T4 批量与稳定映射**：一次问答最多发一个 rerank HTTP 请求；要求结果数量完整、index 为非 bool 整数且唯一/不越界、score 为非 bool 有限数值。服务返回顺序任意时按 index 映射；同分按原 RRF 位置稳定排序；失败整批回退原对象顺序。
- **T5 Fail-open 性能**：连接/读取超时按 2 秒/60 秒上限执行且当前问答不重试；服务不可达或质量探针失败后使用至少 30 秒的负状态缓存或等效熔断，避免每次问答重复等待连接超时。禁用、0/1 候选时必须零网络请求。
- **T6 URL 与日志安全**：`RERANKER_BASE_URL` 解析后只接受 `http` 且 hostname 为 loopback（`127.0.0.1`、`::1` 或解析到 loopback 的 localhost）；reason/log/span 不得包含 query、完整文档、异常堆栈、环境变量或命令行敏感内容。
- **T7 生命周期所有权**：自动选择端口后通过明确的 stdout 协议、状态文件或父进程环境把实际 URL 传给 FastAPI，禁止依赖子脚本 `export`。前台 Ctrl+C、后台 stop、启动探针失败和陈旧 PID 均需验证；只终止 PID 文件指向且命令行/启动标识匹配的本项目进程，不得 `pkill llama`。
- **T8 health 缓存**：`reranker` 必须等于 `enabled && available`；detail 保持固定字段。探针缓存使用单调时间和并发保护，30 秒内并发 health 请求只触发一次质量探针；缓存探针不得阻塞超过配置超时，disabled 不做探针。
- **T9 检索回归**：RRF 去重 key 保持 `(paper_id, chunker, chunk_index)`，dense/sparse 两路继续使用同一 filter；rerank 在最终 top_k 截断前执行，不写 Qdrant，不改变 citation、page/page_end、v1/v2 或 paper_id 语义。
- **T10 测试基线**：mock 测试必须覆盖正常乱序、合法同分、bool index/score、缺失/重复/越界、NaN/Infinity、HTTP/JSON/timeout、禁用与熔断；真实验收采用冻结问题集，测试数不低于 `max(253, spec-013 最终通过数)`，覆盖率不低于 80%。
- **T11 集成安全**：Task 08 只集成 spec-013 明确 commit，冲突逐文件解决并读回；验证 Langfuse 开/关 × Reranker 开/关四种组合，全仓（含 `.gitignore`）扫描冲突标记为 0 后才能进入验收。
- **T12 模型登记**：编码分派前把已由 `ollama list` 证实存在的 `qwen3.8:27b-mlx` 补入 `MODEL_REGISTRY.md`，并使 registry、spec 执行配置和 `.codebuddy/agents/junior-dev.md` 三处名称一致。

## 风险定级：高

风险不是数据迁移，而是三个运行时交叉点：外部模型协议是否真正有效、双进程启停/动态端口、与未提交 spec-013 的后续合并。Task 02 的硬 Go/No-Go、独立 worktree 和 T2/T7/T11 能把风险收敛，因此结论不打回；任何一个硬门禁失败都必须停在当前任务，不得绕过。

## 阻塞项

无当前硬阻塞。Task 02 质量探针若失败即成为后续实现硬阻塞；在其通过前不得开始业务代码修改。
