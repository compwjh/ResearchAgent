# SPEC-045 技术评审（Tech Review）

> 评审者 / 角色：架构师（评审/合并）子代理 `architect`，需求评审 + 技术评审总控
> 模型：自身（当前执行任务的 Agent，不写死模型代号）
> 分派方式：`Task(subagent_name="architect")`（Gate 2 / SDD-GATE-CHECKLIST.md:65,69）
> 评审对象：`docs/sdd/specs/045-evaluation-observability-hardening.md`（数据模型 / 端点接口 / 边界 / 执行配置 / Q7）＋ `docs/sdd/plans/045/`（README、HANDOVER 第 8 节、task-02..08）
> 评审依据：Gate 1/Gate 2（SDD-GATE-CHECKLIST.md:52-80）、ROLE-ONBOARDING.md:11-22,33-43、AGENTS.md:117、`backend-patterns` / `frontend-patterns` / `regression-guard` 项目增补章
> 关联输入：ADR 0002、两份 `045-*.md` 调研 notes 第 4/5 节、真实取证 `docs/sdd/plans/045/runs/**`、`docs/sdd/plans/045/runs/task-07/backend-review.md`
> 评审阶段：**实施收口前的技术评审总控**（spec 状态 `实施中`，本轮不转 `已完成`）；本文件覆盖 2026-11-08 13:24 设计阶段 `待确认` 版评审
> 评审日期：2026-11-08

---

## 结论

**通过。**

数据模型增量（七项）均为既有对象的字段/约束扩展、无新表无迁移无第二套实现；接口契约（无新增业务端点、分页默认行为不变、不新增 SSE 类型、`benchmark_summary` 经既有事件通道）守住；模块拆分与文件边界遵守前后端分端；执行配置五行齐全、模型与上下文预算合理；Q7 边界（不重构 SDK 接入、不改上报字段与瀑布图语义）守住。

- **P0 缺陷：无。P1 缺陷：无。**
- 后端独立评审 `runs/task-07/backend-review.md:8,45` 亦为「通过（Approve）」、P0=0 / P1=0、六个必查点全过、LOW 5 条为文档记录/收口残留。
- 本结论为**技术维度**评审，不代写验收评审、不替 tester 签字、不宣称准备度分数、不把 spec 状态改为 `已完成`。下列「已声明边界与残留」按 Q7/Q8、ADR 0002、task-07/task-08 边界如实记录，**不计为遗漏或失败**。

---

## 逐项结论（附 `文件:行`）

### 1. 数据模型增量合理 — 通过

spec:160-174 明确「文档阶段不建表、不改 schema；下表为实施阶段预期增量边界」，七项逐一核对落地与约束：

| 增量 | spec 定义 | 落地证据（`文件:行`） | 约束守住 |
|---|---|---|---|
| `eval_042` 五类指纹 | spec:167 `dataset_sha256`/`judge_model_digest`/`prompt_sha256`/`seed`/`tie_break_rule` | `runs/task-02/eval-baseline/report.json:53,56,58,60,63`（`seed=42`）、`runs/task-02/evidence.md:76-84`、`task-03:29-35,95`、`HANDOVER.md:93` | 不保存 trace 原文/prompt 原文/raw completion/凭据（spec:167 引 spec-042:236）；judge `seed` 固定且 `temperature:0 / think:False / num_predict:160` 语义不变（spec:168、task-03:32） |
| score 幂等键 | spec:169 重跑不产生重复 score、POST 仍恰好一次不自动重放 | `backend/eval_042/runner.py:563` 接 `post_score_idempotent`（task-04:85、evidence.md:114）、`langfuse_export.py:170-216` 兼容注入（task-04:86）、真实重跑 `runs/task-02/evidence.md:89-93`（979→979，**delta=0**）、`eval-rerun/report.json` | 「先查后写、命中复用既有 score_id」非「先删后写/自动重放」（task-04:30-32,58-60）；`offline_guard.py:199-218` 未知写入结果仍报失败 |
| 报告目录锁 | spec:170 多进程共用 `--output-dir` 不互相覆盖 | `runs/task-02/eval-baseline/.report.writer.lock`、`eval-rerun/.report.writer.lock`（真实生成，evidence.md:73）、`report.py` `fcntl.flock` 包住 checkpoint 双文件投影与回滚（HANDOVER.md:45、task-04:33-35,87） | `os.replace` 原子性 + 既有回滚语义不变（task-04:43,69-71）；标准库实现、不引第三方依赖（task-04:62） |
| ContextVar 采样 | spec:171 单次 trace/请求级决策、`LANGFUSE_SAMPLE_RATE` 语义不变 | `config.py:47`（`_sample_decision` ContextVar）、`:65-99`（`decide_sampling`/`should_sample`/`reset_sample_decision`）、`trace.py:97`（`start_trace` 调 `decide_sampling()`）、`routes_chat.py:82`（q10-red-green-summary.md:52）、`task-05:34-35,102-103` | 采样率 <1 时同一 trace 各阶段共用一次决策（RED `[False,True,…]` → GREEN 一致，q10-red-green-summary.md:63,76）；默认 1.0、不改 `LANGFUSE_ENABLED` 默认 false（task-05:75） |
| 事件表 retention | spec:172 时间/行数清理 + VACUUM、`raw_events.payload` 上限、**不迁移历史数据** | `config.py:229-239`（`EVENT_RETENTION_ENABLED=True`/90 天/10 万行/VACUUM）、`retention.py:3-12,32-38,70-102`、真实 DB `deleted=0` `rows remaining (12,12)`（task-07:158）、`tests/memory/test_event_retention.py` 6 用例（backend-review.md:42-45） | 保守阈值、F15 不夸大为现有故障（task-07:27-29）；fail-open、VACUUM 在事务外、不与长跑争锁（backend-review.md:43-45）；无 DDL/无回填（backend-review.md:43） |
| `processing-steps` 游标分页 | spec:173 / :182 增加可选 `cursor`/`limit`、**无参默认行为不变** | `routes_conversations.py:2457-2467`（无参分支原样保留 `{"steps": [...]}`）、`:2469-2497`（带参分支 `{steps,next_cursor,has_more}`）、`repository.py:1691-1724`（keyset `(started_at, step_id)`、多取一行判 `has_more`）；真实 API `runs/task-07/paging-api-evidence.txt:2-18`（无参 `['steps'] count=25`、`limit=0/abc/坏 cursor` 均 400 稳定错误体、逐页 `set_equal=True`）；`backend-review.md:24-38` | 前端 `frontend/app.js` 无参拉取点不变（backend-review.md:28-29）；越界 400 + `INVALID_LIMIT`/`INVALID_CURSOR` 稳定错误体、`binascii.Error` 不漏 500（backend-review.md:37、paging-api-evidence.txt:6-14）；owner 隔离 `JOIN messages … AND m.owner_id=?`（backend-review.md:35） |
| 兼容层 | spec:174 单一模块收拢私有 SDK 符号、不新增公开依赖、不改上报字段与瀑布图语义 | `backend/app/platform/observability/sdk_compat.py:1-40`（三处私有符号 `create_span_attributes` / `_otel_tracer` / `_otel_span._start_time`、导入期 `ImportError` 容错 + 显式告警）、`task-05:106-108`（`spans.py:46,49` 改调兼容层）、真 SDK 冒烟 `sdk-smoke.json:18-41` 锁 `langfuse==4.15.1` 符号形状 | 缺失时显式降级 + 告警而非静默跳过（Q7，sdk_compat.py:9-14,26-35）；不保证不退化、只保证退化可发现 + 修复点唯一（ADR 0002:82-84） |

补充：残留的 `raw_events.payload` 上限归入 09 项（spec:172,196），由 `redaction.py:27,86-95` `bounded_payload`（4000 字符、复用既有 `{"truncated": true}` 口径，不造第二套额度）落地，红绿取证 `q10-red-green-summary.md:135-137`（50031→≤4000）。全部增量为「复用既有 + 字段/约束扩展」，符合 `regression-guard` 增补第 5（SQLite 单事务幂等）、第 9（禁止重复实现，backend-review.md:37 明「复用既有两 store 的 prune、复用 `append_event` 与 `encode_cursor/decode_cursor`」）与 `backend-patterns` 分层（API 校验编排 / service / store，`backend-review.md:37` 明 `platform/` 纯函数不向 `domain/` 引 FastAPI/HTTP/Playwright/env、UTC 时间戳统一）。

### 2. 接口契约守住 — 通过

- **无新增业务 HTTP 端点**：spec:178「沿用 spec-042 边界」，spec:180-185 仅列受影响既有接口；`task-08:32`「不新增业务端点、不改公开接口」、`task-07:47,81`、`task-03:68`、`task-04:61` 逐任务重申。真实取证走的均为既有端点：`POST /api/chat` / `POST /api/kb/ask` / `GET /api/messages/{id}/processing-steps` / Langfuse `/api/public/{traces,observations,scores}`（`sdk-smoke.json:44-83`、`paging-api-evidence.txt:1`、`trace-attribution-fix.json:6`）。
- **分页默认行为不变**：`routes_conversations.py:2457-2467` 无参分支与改动前镜像逐字一致、未追加任何键（backend-review.md:26-31）；契约测试 `tests/conversation/test_processing_steps_pagination.py:48-58` 断言 `set(body) == {"steps"}`；真实 API `paging-api-evidence.txt:2-3` 无参 `['steps'] count=25`。带参分支独立、互不污染（backend-review.md:30）。
- **不新增 SSE 事件类型**：`task-07:140-143`「`event_type` 取后端既有白名单值，复用前端 `EVENT_TYPES` 已支持的类型，不新增 SSE 事件类型、不新增业务端点」；事件回执 `runs/task-07/benchmark-summary.event.json:4` 为 `event_type=task`（既有白名单）、`status completed → completed`；`task-06:46,76` 不改 `research_events` `safe_payload` 白名单形状与 SSE 协议；`trace-attribution-fix.json:85` SSE 帧型 before/after 一致（meta/stage/citations/token/debug/done）。
- **`benchmark_summary` 经既有事件通道**：spec:109-115 实施阶段裁决 A 打通「把真实测量结果按前端既有白名单映射为 `benchmark_summary`，经既有 `ResearchStore.append_event` 事件通道送达前端；不新增业务端点、不新增 SSE 事件类型、不改 `diff` 口径、不填占位指标值、不改前端文件」；`task-07:129-148` 五条硬约束；真实 `benchmark-summary.json:2-7` 四项指标（中位 TTFT 38478.927 / 吞吐 19.735 / 真实 `getrusage` 峰值 106070016 / 失败率 0）、`benchmark-summary.event.json:2-15` seq 40 事件回执、`benchmark-card-browser.txt` Chromium 四 `.research-benchmark-metric` 可见、`sectionHidden=false`、死 UI 文案消失（`task-07:160-161`）。
- 安全维度（`regression-guard` 增补）：脱敏「按值级、不按 key 名」取舍有真实链路测试刻画（见残留 4）；`benchmark_summary` 结构 + 数值白名单「等价或更严于原规则、非规则松动」（backend-review.md 附加核查）、恶意 payload 独立复核无凭据绕过（backend-review.md:45）；SSRF 白名单沿用 `eval_042` 既有 `offline_guard`（`045-evaluation-module-survey.md:142,145`），本期未新增外发 URL 直连。

### 3. 模块拆分与文件边界遵守前后端分端 — 通过

- 11 项 → 7 份 task（spec:308-317、README:30-41），DAG `02 → (03∥04∥05∥06∥07) → 08` 无环、无职责重叠；`AGENTS.md:71-75` 单端改单端 agent、跨端拆两次分派。
- 分端边界逐任务写明：03/04 限 `backend/eval_042/**` + `tests/evaluation/**`，明「不碰 `backend/app/**`、`frontend/**`」（task-03:50-51、task-04:46-47）；05 限 `observability/**` + 新增兼容层 + `routes_{chat,kb,article}.py`（task-05:56-58）；06 跨 `observability/**` + `routes_*` + `repository.py` + `research_store.py`（task-06:59-63）；07 后端 `repository.py`/`routes_conversations.py`/`research_store.py`/`config.py`，前端 `index.html`/`research-tasks.js`/`styles.css` 分列，含 `.py` 与 `.js/.html/.css` 改动分别 `Task(backend-dev)`/`Task(frontend-dev)`（task-07:60-74）。
- 实际落地遵守：07 裁决 A 打通「前端零改动」（现有 DOM/normalize/render 契约已完整支持，不派 `frontend-dev`、不递增 `?v=`），如实判定「本任务无前端改动」（task-07:146-147,152-153），未制造跨端越界；`benchmark_summary.py`/`retention.py` 位于 `platform/` 纯函数层（backend-review.md:37）。
- 本轮真实链路修复（kb-ask 一请求两 trace → 一 trace）改动收敛在 `backend/app/api/routes_kb.py` + `backend/app/platform/observability/trace.py`（`git status --short` 只读核实两文件 `M`；`trace-attribution-fix.json:96-105` `scope_confirmation.not_touched` 明列未碰公开接口 `__init__.py`、SSE 帧、request_id 外部语义、SDK 形状/上报字段/瀑布图语义），新增测试 `tests/observability/test_kb_trace_attribution.py` 等按能力命名、不含 spec/task 编号（backend-review.md 附加核查、task-07:157）。聊天链路未回归（`trace-attribution-fix.json:60-77`）。
- 子代理分派纪律：设计阶段纯 `.md` 代行三处留痕齐备（`045-evaluation-module-survey.md:5-6`、`045-observability-module-survey.md:5-6`、spec:292-300、changelog:13）；实施阶段含代码改动均经 `backend-dev`/`tester`/`backend-reviewer` 分派（HANDOVER.md:117-119、changelog:3,5,7 台账），主会话只做编排与读回校验。

### 4. 执行配置的模型与上下文预算合理 — 通过

- spec:279-290 五行齐全（架构师 / 产品经理 / 开发主管 / 初级开发 / 测试），含选用模型 + 上下文上限 + 分派方式 + 职责（Gate 1:56-58）；架构师行填「自身（当前执行任务的 Agent，不写死模型代号）」、上下文 200k（spec:286），符合 Gate 1:57 与 ROLE-ONBOARDING.md:21,42（架构师与评审/合并 64k–200k、旗舰推理）。
- 设计阶段四行标「不适用（Q8 本期仅交付文档）」并逐行给原因（spec:287-290），符合 Gate 1:56「不适用写原因、不整行删除」；Q8 边界解除后实施阶段各角色实际启用，台账有逐条记录（changelog:3,5,7；HANDOVER.md:115-119）。
- 模型档位真源为 `.codebuddy/agents/<role>.md` 的 `model` 字段（MODEL_REGISTRY.md:55-61），当前 10 个 agent 均 `hy4`，系用户临时决策（changelog:3、HANDOVER.md:117-119 明「未写回 `AGENTS.md` 或任何流程文档，不作为正式配置固化」），与 MODEL_REGISTRY.md:72-80「临时档位不得固化为规范」教训一致，非配置缺陷。
- 上下文预算：本评审 200k 与 ROLE-ONBOARDING.md:42 一致；task 文档均要求「分派上下文最小化，只给 task 文档 + 路径行号 + 目标状态，不复制整份 spec」（task-03:58、task-05:66），避免上下文超限（首个 task-03 子代理曾因上下文超限留下导入期崩溃，task-03:104-109 如实保留并由第二个 `backend-dev` 收口）。

### 5. Q7 边界守住（不重构 SDK 接入、不改上报字段与瀑布图语义）— 通过

- Q7 裁决（spec:64,125-126、ADR 0002:82-84）：私有符号收拢到单一兼容层 + 缺失时显式降级告警；**不重构 SDK 接入方式、不改变上报字段与瀑布图语义**；更正「从根上不会坏」为「不保证不退化，只保证退化可发现（显式降级 + 告警）与修复点唯一」。
- 逐处核对：`sdk_compat.py:1-14` 明「不保证从根上不会坏」、修复点唯一；`task-05:37,41,70-73` 明「不改变上报字段、metadata 与 7 个 numeric score 名称」「不改变 `completion_start_time`、四段 phase（load/prefill/decode/overhead）的语义与顺序」「不重构 SDK 接入方式」；`task-06:74-76` 不推翻 spec-041「input/output 全量可见」用户裁决，只做值级凭据过滤。
- 真 SDK 冒烟锁形状：`sdk-smoke.json:18-41`（`langfuse==4.15.1`、`create_span_attributes` 可导入、`_otel_tracer` present、`_otel_span._start_time` 由 `sdk_compat.set_otel_span_start_time` 写）、`:89-95` 四段 phase span / `completion_start_time` / 7 numeric scores 全部 PASS；`trace-attribution-fix.json:96-105` `scope_confirmation.not_touched` 明列 SDK integration shape / reported fields / waterfall phase-span semantics 未触碰。
- 残留的 `spec-041:93` 升版回归要求仍保留（见残留 10），封装未宣称根治——与 Q7 裁决自洽，非缺口。

---

## 已声明边界与残留（如实写入，不作为遗漏或失败）

> 与 `045-requirement-review.md` 同源；此处按技术视角补齐代码/测试 `文件:行`，两条评审结论口径一致。

1. `human_agree_rate` 仍 `null`（P2 人工 gold 集明确不做）：`runs/task-02/eval-baseline/report.json:6`、`backend/eval_042/report.py:225-233`（ADR 0002:28-29）、`045-evaluation-module-survey.md:146`（测试锁 `human_agree_rate` 恒 null）。
2. `research_model_outcomes.quality_score` 与 Langfuse score 两套口径仍不统一（P2）：`045-evaluation-module-survey.md:226`（无映射代码）、spec:120,47、`task-07:82`「不因本次改动调整 `quality_score`」、`POST /api/research-routing/policies/{v}/evidence` 不改（spec:184）。在线实时评测不做：ADR 0002:45-48。
3. `redaction.py` 按值级脱敏、**不按 key 名过滤**：`backend/app/platform/observability/redaction.py:9-10,29-41,60-70`（精确凭据模式 `_SK_KEY_RE`/`_BEARER_RE`/`_AUTHORIZATION_RE`/`_CREDENTIAL_ASSIGN_RE`/`_URL_RE`，递归只改字符串值、保留 dict/list 结构）、`task-06:90-92`（避免误伤含 `token` 的学术文本）、`trace-attribution-fix.json:98`；真实链路已刻画：`sdk-smoke.json:203-221`（合成 `sk-proj-FAKECRED…` 真链路 `plaintext_credential_in_stored_trace=false`、`input_is_redacted=true`）、`q10-red-green-summary.md:124-158`（15 用例红转绿）、`git diff --stat -- redaction.py` 为空（backend-dev-trace 日志末段边界确认）。
4. `setup_langfuse_dashboards.py --force` 非幂等：`dashboard-contract.json:92-104`（DEFECT reported not fixed，`:96-99` 给出 `setup_langfuse_dashboards.py:274,280` + `schema.prisma:1542` 无 `dashboardId` 外键 + 未用 `DELETE /dashboard-widgets/{id}` 的证据链）；**默认重建已验证幂等** `:59-90`（6 dashboard/40 widget ID 与名称多重集完全不变、无重复 widget）；`--force` 未真实重跑、只读核验（`:11-14,102-103`）。属业务脚本、超出本 spec 文件边界，如实记录非失败。
5. `018` 冻结矩阵 `inventory_git_revision` 仍为 `8b0cde1`：`docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json:3`、`task-07:183`；冻结矩阵哈希两次重签均已验证 `2 passed`（`tests/kb/test_kb_upload_closure_matrix.py:15,43` 两用例、`backend-review.md:35` 按 `:83-88` 算法重算 `inventory_digest` `MATCH=True`、3 字段 `main.py`/`routes_kb.py`/`inventory_digest` 同步成因合理），revision 未授权改动保持原样。
6. 并列 `started_at` 时无参与分页行序可能不同但集合一致：`backend-review.md:33-38`（无参 `ORDER BY started_at, logical_sequence` `repository.py:1693`、分页 `ORDER BY started_at, step_id` `:1720`，实测集合一致但行序不同，测试 `:88` 用互异时间戳种子）、`task-07:179-180`（转入 Task 08 记录）。分页 keyset 正确、稳定、不重不漏，判已知边界非缺陷。
7. retention 默认启动期同步执行：`task-07:181-182`、`backend-review.md:42-45`（`config.py:234-239` `EVENT_RETENTION_ENABLED` 默认 `True`、启动期 lifespan `yield` 之前同步、低峰 fail-open；当前阈值 `deleted=0` 不删行，未来大规模清理应改异步，评审 R2）。默认保守、VACUUM 在事务外、不与长跑任务争锁。
8. Langfuse 读回 `GET /api/public/traces/{id}` 对 kb trace 返回空数组：`trace-attribution-fix.json:10`（`public_api_quirk`），改用 `GET /api/public/observations?traceId=` 与 `GET /api/public/scores`（按 traceId 过滤/核对）完成归属验证（`:6,36-54`）；`sdk-smoke.json:100-103,137-138,172-174` 同法。属 Langfuse v4 读回怪癖，非本 spec 缺陷。
9. `spec-041:93` 私有 SDK 符号升版回归要求仍保留：`docs/sdd/specs/041-langfuse-trace-detail-and-waterfall.md:93`、`045-observability-module-survey.md:175-179`、`ADR 0002:82-84`、`task-08:18,92`。本期已补真 SDK 冒烟（`sdk-smoke.json`），但「每次升版跑 1 次回归（含观测测试 + 一次真实对话触发）」的人肉要求不撤销。
10. Spec045 明确「不 push、不合 main」：spec:130、`task-08:76`、`task-07:83`；本轮 `git` 只读核实分支 `feature/spec-045-evaluation-observability-hardening`（HEAD `f8106ff9`）、`origin/main` 仍停 `1b26c76c`，工作区 12 项改动未提交/未推送/未合并；本评审未做任何 `git commit` / `push` / 合 main。

补充：设计阶段技术评审 P0-1（`deploy/langfuse/start-langfuse.sh:15` 硬编码失效路径）已由 `backend-dev` 分派修复并静态验证（changelog:9、:11），接手机器 `HANDOVER.md:87-88` 实跑 `start-infra.sh`/`start-langfuse.sh` 成功、6 端口监听、dual 模式 200，`runs/task-02/evidence.md:7-20` 真实取证——前置已消解，不再列为 P0。设计阶段 P1-1（06/10 验收归属）已在 spec:275-277、task-07:157-162 显式标注，闭环。

---

## P0 / P1 缺陷列表

| 级别 | 数量 | 说明 |
|---|---|---|
| P0 | 0 | 无 |
| P1 | 0 | 无 |

> 上述「已声明边界与残留」10 项均为 Q7/Q8、ADR 0002、task-07:178-184、task-08:90-92 内已声明并如实取证的设计取舍、第三方读回怪癖或后续阶段项，按 task-08:90-92「如实声明为已声明边界，不得写成遗漏或失败」处理。后端独立评审 `runs/task-07/backend-review.md:8,45` P0=0/P1=0、LOW 5 条为文档记录/可选加固/收口残留，与本结论一致。
> 本评审不打回，故无「回到某个 task」的缺口项。

---

## 评审边界声明（纪律）

- 本文件只做**技术评审**（数据模型 / 接口契约 / 模块拆分与文件边界 / 执行配置 / Q7 边界），与 `045-requirement-review.md` 需求维度分工；不代写 `045-acceptance-review.md`、不替 `tester` 签字、不宣称任何准备度分数、不把 spec 状态改为 `已完成`。
- 状态口径如实说明：spec 头部状态字段仍为 `已确认`（spec:5），而 `README.md:4` 与 `spec-status-changelog.md:3` 记为「已确认（实施中）」、spec:324 与用户本轮口径为「实施中」。该头部字段与流程阶段的措辞差异属主会话收口时应同步的台账项，按「禁止改 spec 状态」纪律本轮不改动，也绝不改为 `已完成`；本评审标题所称 `实施中` 为用户给定的流程阶段口径。
- 收口前仍须由主会话/tester 补齐的项（不在本评审结论内）：最终全量回归 + 覆盖率（当前 `runs/task-08/full-regression.txt` 为 39 行进度片段、非完整汇总）、`045-acceptance-review.md` 与 tester/architect 双签、部署验证、`docs/sdd/retro/` 复盘、changelog `实施中 → 已完成` 条目与本地 `git commit`（task-08:50-57,84-87；不 push、不合 main）。spec 当前保持 `实施中`。
- 逐项结论均基于 `Read` / `Grep` / `git` 只读事实并附 `文件:行`（Gate 2:72），无「应该没问题」式结论；本轮只读评审，未改业务代码/测试/spec 状态，未 `git commit` / `push` / 合 main。
