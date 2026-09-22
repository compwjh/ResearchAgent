# Spec032 真实 API 端到端证据（Spec039 Task06）

> 运行日期：2026-09-20（Asia/Shanghai）  
> 服务：`http://127.0.0.1:18080`  版本：当前工作树部署实例  
> 结论：`BLOCKED`。本文件只记录真实请求和真实响应，不把状态机完成误写成报告质量合格。

## 运行 A：自然语言单消息 Intake（通过）

请求：`POST /api/conversations/messages`，HTTP `200`，SSE `done.status=completed`。

```text
帮我做一个深度研究，主题是 USENIX Security 2024 中的身份认证、访问控制与权限保护。
目标是从 USENIX Security 2024 官方目录中选择至少 5 篇相关论文，比较它们要解决的安全问题、
研究方法、攻击模型和主要结论，时间范围：2024-2024。来源只使用 USENIX Security 官方目录。
如果官方页面没有提供关键词，请明确标记为官方未提供，不要自行生成。
```

关键响应事实：

- `conversation_id=50a1e0dae7fd49b485ce0687f9c5a78e`
- `message_id=bca8a9c6945b4dbdbfc0602eca56e44f`
- `research_session_id=e27c4b2fac9a49aab4562a5eb3346659`
- `intake.status=intake`，`missing=[]`，主题、目标、时间范围均为 `user_explicit/confirmed`。
- `type=plan`，`status=plan_pending_approval`，`subject_version=1`，来源为 `usenix`，范围为 `2024–2024`。

这证明自然语言主入口可以在明确使用 `时间范围：2024-2024` 语法时完成 Intake；不能用表单替代它。

## 运行 B：批准计划与执行（状态成功，内容质量阻塞）

请求：

```text
POST /api/research-sessions/e27c4b2fac9a49aab4562a5eb3346659/commands
{"command":"approve_plan","subject_version":1,"idempotency_key":"ap-spec039-spec032-002"}
```

响应：HTTP `200`，`approval.status=approved`，`status=queued`，创建：

- `research_task_id=deffe805ceca5d1ea16b516101e21e3f`
- 会话链接已建立，计划版本为 `v1`。

随后读取 `GET /api/research-tasks/deffe805ceca5d1ea16b516101e21e3f` 和事件流。初次读取时任务仍在
`running`、WorkItem 为 `queued`；等待后台执行完成后再次读取得到：

- `status=completed`，`search_id=a2051bb58f364b75b77cd742d90a9cd1`；
- `s1/s2/e1/c1/syn` 全部 `completed`；
- 实际执行时间约 02:15:42–02:18:11（约 149 秒），期间应保持页面等待，不重复提交。

因此 API 状态机已经贯通；不能交付的原因转为报告内容质量：最终报告只有 6 个目录证据对象 ID，没有可读的论文标题、摘要、关键词、研究方法或安全问题比较。

## 运行 C：已有真实完成任务复核（状态通过，产物质量失败）

为确认报告端点和持久化链路，复核此前同一当前服务的任务：

- `GET /api/research-tasks/b0402bf4192c5c21bc06c84c7da3f891`：HTTP `200`，`status=completed`。
- `search_id=12064955a5a949dbbcd2e1fb3f43cc57`。
- `GET /api/research-tasks/b0402bf4192c5c21bc06c84c7da3f891/report`：HTTP `200`。
- `report_id=artifact:945c60d256514c9797b3b9fc22874c7b`。
- `selections` 数量为 `10`，证据级别为 `catalog`。

但 Markdown 仅重复“该论文在 USENIX Security 2024 官方目录中提供元数据”和内部证据对象 ID，未提供可读的论文标题、摘要、关键词、研究方法或安全问题比较。因此它证明了“任务和 Artifact 可落盘”，不证明“报告达到用户验收质量”。

## API E2E 结论

| 检查 | 结果 | 证据 |
|---|---|---|
| 服务可访问 | PASS | `/api/health`、`/api/ready` 均 HTTP 200 |
| 自然语言 Intake | PASS | 运行 A，`missing=[]` |
| 计划与审批 | PASS | 运行 A/B，计划 v1、approval approved |
| 研究任务真正推进 | PASS | 运行 B，5 个 WorkItem 全部 completed |
| 任务终态可查询 | PASS | 运行 B `completed` |
| 产物存在 | PASS | 运行 B `artifact:4bf874b6b1c94426b57d9d212cf588d5` |
| 报告内容达到验收标准 | FAIL | 运行 B 缺少标题/摘要/关键词/方法比较 |

**准备度：6/10，状态：`BLOCKED`。** 任务调度已经完成，但需要先修复报告合成/目录元数据传递，再生成可交给用户的 `READY_FOR_USER` 案例。

---

## 运行 D：修复后真实 API E2E（成功）

> 本节追加记录，不覆盖运行 A–C 的失败证据。运行 D 使用同一当前工作树、同一部署端口和新的实体 ID。

运行环境：`http://127.0.0.1:18080`，`qwen3.8:27b`，`RERANKER_ENABLED=false`，服务健康检查 HTTP `200`。

### D1. 自然语言 Intake

请求：`POST /api/conversations/messages`，HTTP `200`，SSE `done.status=completed`。

```text
帮我做一个深度研究，主题是 USENIX Security 2024 的身份认证与访问控制。
目标是从 USENIX Security 2024 官方目录选择至少 5 篇论文，比较安全问题和研究方法，
时间范围：2024-2024。只使用 USENIX 官方目录；关键词没有提供时写官方未提供。
```

真实关键字段：

- `conversation_id=9d6ef3d8e5b34db2945a02d09ba98e81`
- `research_session_id=2c440ac8b34641fbbfaa7b36fe59b5c1`
- `intake.missing=[]`
- `plan.status=plan_pending_approval`、`subject_version=1`、来源 `usenix`、时间范围 `2024–2024`。

### D2. 计划批准与任务执行

请求：

```text
POST /api/research-sessions/2c440ac8b34641fbbfaa7b36fe59b5c1/commands
{"command":"approve_plan","subject_version":1,"idempotency_key":"spec039-report-fix-rerun-004"}
```

响应 HTTP `200`，`approval.status=approved`，`status=queued`，并创建：

- `research_task_id=78820a4d960d599dbfad6a013f36770c`
- 事件流最终 `terminal.status=completed`、`selected_count=5`。
- `s1/s2/e1/c1/syn` 均完成；详情补抓失败只作为可降级事件，未丢弃目录候选。

### D3. 报告和选集产物

报告端点：

`http://127.0.0.1:18080/api/research-tasks/78820a4d960d599dbfad6a013f36770c/report`

响应 HTTP `200`，`status=completed`，`report_id=artifact:339d5e66f23a4deb9dc07e9759148613`，`selections` 为 **5** 条。
Markdown Artifact 的持久化记录为：

- `artifact_id=339d5e66f23a4deb9dc07e9759148613`，类型 `markdown`，创建时间 `2026-09-20T03:34:57Z`；
- HTML：`f47918aa20a7414b8450688a50544c20`；引用清单：`f6467efd6e854ade830caadae58925e6`。

报告内容统计：5 个论文标题、5 个摘要、5 个关键词字段（官方缺失时明确“官方未提供”）、5 个官方 URL；未再出现只有 `catalog:<id>` 的占位报告。论文标题包括：

1. `The Challenges of Bringing Cryptography from Research Papers to Products: Results from an Interview Study with Experts`
2. `Inference of Error Specifications and Bug Detection Using Structural Similarities`
3. `Formalizing Soundness Proofs of Linear PCP SNARKs`
4. `Single Pass Client-Preprocessing Private Information Retrieval`
5. `How WEIRD is Usable Privacy and Security Research?`

### D4. 修复点和失败证据保留

- USENIX Worker 改为返回全局目录的稳定 32 位 `catalog_paper_id`；不再使用临时搜索候选 ID，报告元数据可由同一 `PaperDiscoveryStore` 回填。
- 评估器少于 5 篇时，只从同一 Search Worker 已召回集合提升到 5 篇；不从目录盲目扩展、不下载 PDF。
- `report_version` 由已批准计划版本绑定；模型误填论文日期字符串时由运行时纠正并重算 `output_hash`，其它报告字段仍严格校验。
- 运行 `96233710a0a25431b4399c101460beb4` 的真实失败 `AGENT_OUTPUT_INVALID` 及运行 `5377009654455e4285ee7fd0e336cc5a` 的旧报告不足证据均保留，未覆盖。

### D5. 中断恢复检查

对已有真实中断任务 `319542120c064dc3848a19a3b51fceaf` 调用：

```text
POST /api/research-tasks/319542120c064dc3848a19a3b51fceaf/recover
{}
```

HTTP `200`，返回 `status=recovery_required`、`task_status=interrupted`、`current_plan_version=2`、`queued=6`、`completed=5`、`leases=0`、`reservations=0`、`requires_checkpoint=false`。未知外部调用不会被自动重放，用户可据此刷新任务详情并决定下一步。

## 运行 D 结论

真实 API 主路径已成功，且最终 Artifact 是可读的 5 篇目录级研究报告。浏览器复核见 `spec032-manual-acceptance.md` 的运行 D；运行 E 已完成处理中提示的单独浏览器采样，Spec039 当前允许进入 `READY_FOR_USER` 人工验收阶段。

## 运行 E：修复后前端处理中状态采样与引用边界修复

为验证“用户不会只看到静态 Queued”以及小模型引用字段漂移，重新创建了真实会话：

- `conversation_id=8faac05c2b7143c69c3de3189c0d0a8a`
- `research_session_id=cc7cacb8bbb44a26b81c9311aab942f8`
- `research_task_id=66b4b4ef95345fb48d49262fd26b174b`

批准后立即在浏览器打开会话并展开“处理过程”，可观察到：

- 任务节点：`进行中`；
- Worker Agent：先显示已完成耗时，再显示后续 Worker `进行中`；
- Worker Skill / Tool：分别显示 `进行中` 或 `已完成`；
- 处理过程默认折叠，点击后按当前阶段展开。

该采样证明前端使用事件投影显示阶段，而不是只显示 `Queued · 0%`。同一次验证还暴露了小模型可能把多个 `catalog:<id>` 引用行复制成同一个 `candidate_id` 的边界；已在 `ReportSynthesizer.consume_validated_output` 增加唯一引用归属校正：只在引用属于一个已验证候选时修正 bookkeeping 字段，未知或歧义引用仍拒绝。针对性测试现为 `81 passed, 5 subtests passed`。

## 后续修复验证（2026-09-20）

运行 D 之后又定位并修复了三个小模型输出边界，均不改变来源、下载或安全语义：

1. 评估器把并行 `candidate_id[]/relevance_score[]` 数组误当成单个 ID；现在按 `catalog:<id>` 白名单逐篇展开。
2. 评估器返回一个代表性 `candidate_id`、多个 `evidence_refs`；现在按同一已召回证据集合逐篇展开。
3. 搜索 Worker 在模型未输出 JSON 前失败；现在只调用既有 `SearchWorker/CatalogSearchAdapter` 做受控只读恢复，不新增检索链路。
4. 合成器输出长于旧的 200 字摘要上限；现在对 section summary 使用 4000 字安全上限，仍拒绝路径、URL、凭据和敏感字段。
5. 模型合成失败时，已验证的目录候选可由固定渲染器生成完整元数据报告；不扩大候选集合，原模型错误仍写入日志/通知。

定向验证：`85 passed, 5 subtests passed`，并通过 `compileall`、`git diff --check`。任务 `36385d917db1559794a4529728ce6981` 已通过 API `GET /report` 返回 HTTP 200，报告包含 5 篇目录候选；该任务的非关键 coverage worker 仍为 partial，不能替代运行 D 的最终全流程完成证据。
