# 2026-11-11 任务 W 残留 5 项工单收口 — 后端只读复验

- **评审角色**：backend-reviewer
- **任务**：只读复验，确认任务 W 是否修完 `docs/sdd/reviews/20261110-lingering-fixes-backend-recheck.md` 第三节「剩余问题清单」的 5 项残留工单（M-1 / M-2 / L-1 / L-2 / L-3），并判定有无新违规
- **基线**：`c73d3d66`（= 当前 HEAD，staged 为空）；范围为当前工作树相对该 commit 的净改动（6 个已跟踪文件 M + 2 个 untracked 新文件）
- **评审范围**：`backend/**`、`deploy/reranker/**`、`tests/kb/` 后端用例，以及作为契约数据的 `spec-014` / `plan-014` / `deploy/reranker/README.md`
- **边界**：`frontend/**`、`tests/frontend/**`、`tests/e2e/**` 交 frontend-reviewer，不越界
- **只读声明**：除新增本报告与强制要求的进展日志外，未修改任何业务代码、测试、spec、数据；未执行任何 git 写操作（无 add / commit / push / merge / reset / stash / clean）。验证命令仅产生 `.pytest_cache` / `__pycache__` 标准测试产物与 `/tmp` 临时 stub 目录（已清理）
- **进展日志**：`.codebuddy/agent-logs/spec-014/task-06/backend-reviewer/20261111-015304.md`
- **原报告（保留）**：`docs/sdd/reviews/20261110-lingering-fixes-backend-recheck.md`（205 行，第三节列 5 项残留、第四节专项风险判定、第五节 9 条强制约束）

## 结论：**5 项已修完、可收口（Approve，附强制约束清单）**

5 项按用户逐项核对口径均有代码事实与测试门禁支撑；边界 8 类路径相对 `c73d3d66` **零 diff**；`37 passed` / `bash -n` / ruff 与基线对比 **零新增**；`probe.sh` 三种调用形态在真实 llama-server 上实测通过。**无 CRITICAL / HIGH 违规**。剩余 2 项 MEDIUM（1 项为任务 W 新引入的取舍副作用，1 项为原 M-2 残留的部分收敛）与 2 项 LOW，均不阻塞收口；但按原报告第四节的纪律，**不得表述为「打满线程池风险已彻底消除」**，也不得表述为「health 与 `kb.rerank` 事件已完全一致」。

---

## 一、逐项核对（8 项，附 文件:行号 证据）

### 1. M-1 检索侧 single-flight — 已修完

- **按 `(endpoint, model)` claim flight**：`reranker.py:157` `key = (endpoint, model)`；`:173` `flight, leader = _claim_flight(key)`；`:51-58` 在 `_rerank_condition` 内一次性 `get` / `set`，仅 `flight is None` 时创建并返回 `leader=True`（CAS 语义）。锁内只有 dict 操作，不调用用户函数 —— `document_getter` 在 `:162-165` 调用，位于锁外。`:66-67` `_finish_flight` 以 `is flight` 身份二次确认才 `pop`，`:68` `notify_all`。
- **有界等待 3.0s**：`reranker.py:48` `_RERANK_INFLIGHT_WAIT_CAP = 3.0`；`:175` `flight.done.wait(_RERANK_INFLIGHT_WAIT_CAP)`；超时 `:176` 返回 `_fail(original, "timeout")`（fail-open，保持原 RRF 顺序）。注释 `:45-47` 明示依据「正常单请求 1.5–2.3s，留余量取 3.0s」，并声明「这不是网络超时：60s/2s 硬上限与 config.py 冻结默认值均不变」。
- **leader 网络请求用 `try/finally` 发布结果**：`:182` `try`（`:191-192` `with httpx.Client(...) ... client.post`）→ `:225-227` `finally: if leader: _finish_flight(key, flight, published)`；`:181` `published` 默认 `"unexpected"`，成功路径 `:206` 置 `None` 后 `:207-208` 返回，失败路径 `:222-223` 赋 reason 并 `_remember`。`:61-68` `_finish_flight` 先无条件 `flight.reason = reason` / `flight.done.set()` 再进 Condition，因此 `clear_negative_cache()`（`:71-76` 清 inflight + `notify_all`）也不会让等待者永久挂起。
- **5 并发首次 hang 只有 1 次真实网络调用**：`tests/kb/test_kb_reranker_health_probe.py:754-793` 用同一 `MockTransport` 记录 `calls`，5 线程并发；`:780` 断言 hang 期间 `len(calls)==1`，`:784` 最终仍为 1，`:785-789` 断言 ≥4 个等待者在 `3.0s+1.0s` 内快速失败且 `reason=timeout`，`:790-793` 断言 leader 仍写 ≥30s 负缓存。本次实测 37 passed（含此例）。
- **冻结值与 spec 语义未改**：`reranker.py:19` `DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT, MIN_NEGATIVE_TTL = 2.0, 60.0, 30.0`、`:22` `MAX_CONNECT_TIMEOUT, MAX_READ_TIMEOUT = 2.0, 60.0`、`:113` `_remember` 仍 `max(MIN_NEGATIVE_TTL, ttl)`、`:184-186` 仍 `min(..., 60.0)` / `min(..., 2.0)` 构造 `httpx.Timeout(read, connect=connect)`。`git diff c73d3d66 -- reranker.py` 的 hunk 起点为 `:31`、`:114`、`:125`，上述常量行未出现在 diff 中。`backend/app/platform/config.py:87-92`（默认 2.0 / 60.0）与 `docs/sdd/specs/014-kb-reranker.md:131`（「连接/读取超时上限 2 秒/60 秒」「不可达或质量探针失败后至少缓存负状态 30 秒」）经 `git diff --exit-code c73d3d66 -- ...` = `0` 确认零改动。
- **判定**：M-1 工单目标（消除「首个 60s 窗口内并发各自阻塞、打满 FastAPI 线程池」）已达成。但 3.0s 上限带来高负载误降级副作用，见第三节 **M-W1**。

### 2. M-2 总时限与有界等待 — 已修完（按用户核对口径）

- **45.0s 依据**：`retrieve.py:75-79` 注释给出推导「`2×connect 2.0 + liveness 6.0 + quality 30.0 = 40.0s` 理论最长合法耗时 + 5s 调度/解析余量 → 45.0」；`:67-69` 两档 read cap 6.0 / 30.0 与 connect 2.0；`:79` `_RERANKER_HEALTH_TOTAL_TIMEOUT_SECONDS = 45.0`；`:346` `deadline = now_fn() + 45.0`（跨 liveness GET 与质量 POST 共用同一 deadline）。
- **`_request_json` 流式逐块校验能拦住「慢速吐字节」（body 阶段）**：`:315-326`，`:318` `with client.stream(...)`、`:319` `for chunk in stream.iter_bytes()`、`:320-321` 每块后 `now_fn() >= deadline` 即抛 `httpx.ReadTimeout("health probe total deadline exceeded", request=stream.request)`、`:323-324` 循环结束后再校验一次、`:326` 用 `b"".join(chunks)` 重建 `httpx.Response`。`tests/kb/test_kb_reranker_health_probe.py:532-555` 用 `_ClockDrivenStream`（`:175-193`，每块推进假时钟 3.0s、共 100 块，间隔 <30s read cap）断言 `reason=timeout`、`clock()-start <= 45+3`、4s 短缓存、`_health_inflight` 清空；`:175-180` 明示「模拟 read timeout 永不触发的后端」。
  - **如实记录的边界**：`:318` 的 `client.stream()` 在收到**完整响应头**前不会返回，此时 `iter_bytes()` 尚未开始，deadline 检查不执行；因此 header 阶段慢速吐字节不经过总时限校验。检索侧 leader 亦完全无总时限（见 **M-W2**）。按用户口径（body 慢速吐字节）该项已修完并有测试门禁。
- **等待者有真实时钟有界 deadline**：`:81` `_RERANKER_HEALTH_WAIT_CAP = 45.0 + 5.0 = 50.0`；`:465` `wait_deadline = time.monotonic() + _RERANKER_HEALTH_WAIT_CAP`；`:475-480` `remaining = wait_deadline - time.monotonic()`，`remaining <= 0` 时 `:479` 返回 `available=false, reason=timeout` 且不重复发起探针，`:480` `wait(timeout=min(0.1, remaining))`。刻意用真实 `time.monotonic` 而非注入的 `clock`，避免假时钟不推进导致死循环。`tests/...:566-592` patch `_RERANKER_HEALTH_WAIT_CAP=0.3`，断言 leader 挂起时 waiter 按 deadline 返回 `timeout` 且 `fake.calls == [("GET","/health")]`（等待者不重复探针）、inflight 最终清空。
- **正常 2.3s 推理不被误杀**：`tests/...:557-564` `_SlowDripRerankerServer(step=2.3, count=1)` 断言 `available=True`、`reason=None`、`clock()==102.3`；既有 `:281-294`（2.2s 真 sleep）、`:296-302`（18.3s 并发）、`:314-320`（2.2s 慢 /health）一条未删（numstat `241 0` 纯追加）。
- **45s 与 6s/30s cap 不冲突**：`:348-351` 仍分别钳制 `connect<=2.0`、`liveness_read<=6.0`、`quality_read<=30.0` 并构造两个 `httpx.Timeout`；`tests/...:304-312` 断言 liveness read=6.0、quality read ∈ (18.3, 30.0]；`:548` 断言慢速吐字节用例里 quality read 仍为 30.0。45s 是「整个探针（两次请求）的总时限」，6/30 是「相邻两次 socket 读的间隔上限」，二者并行生效且 45 > 40，保证正常路径不误杀。
  - **概念备注（非违规）**：`:77` 把 6/30 当作「单次请求理论最长合法耗时」并不严谨（read cap 不是请求总时长）；但 45s 作为独立总时限正是为兜住这一点，且由 `:532-555` 用例锁住收敛行为。

### 3. L-1 兜底异常 — 已修完

- **两处 `except Exception` 已改**：`retrieve.py:408-410`（`_health_probe` 内）→ `logger.exception("reranker health probe unexpected failure: reason=unexpected")` + `_health_detail(..., "unexpected")`；`:484-486`（`reranker_health` 内）→ `logger.exception("reranker health unexpected failure: reason=unexpected")` + `unexpected`。原基线 `retrieve.py:366-367` / `:434-435` 的 `quality_probe_failed` 兜底已替换（`git diff` 可证）。
- **`unexpected` 是 `RerankReason` 既有值**：`reranker.py:14-17` Literal 含 `"unexpected"`；`:155` / `:165` / `:220` 早已使用；`retrieve.py:339-341` docstring 明示「与 `reranker.RerankReason` 集合一致」并「不伪装成质量失败」。
- **`/api/kb/health` 响应结构与 30s 负缓存不变**：`:305-312` `_health_detail` 仍为 `enabled/available/backend/model/reason` 五字段；`:491-496` `ttl = 4.0 if reason == "timeout" else 30.0`，`unexpected` 走 30s。`tests/...:454-477` 端点结构门禁、`:494-510` 断言 `reason=unexpected` + `assertLogs` 含 `reason=unexpected` + 30s TTL + inflight 清空 + **日志不含 query 文本**（`:504`）、`:512-530` 端点级 `reason=unexpected` 且字段集合不变。
- **README 与 plan 同步、历史原文保留**：README 第 5 节 diff 全量同步（新增 `unexpected` 取值、`logger.exception` 排查指引「不要按模型质量损坏去排查」、任务 W 追加说明）；`docs/sdd/plans/014/task-06-reranker-health-status.md` 的 `git diff --numstat c73d3d66` = `16 0`，hunk 为 `@@ -115,3 +115,19 @@` 纯追加，1–115 行（含 1–85 历史原文、任务 U 追加节）保留不改；追加节 L-1 行明示「原始异常只进服务端日志」。

### 4. L-2 TTL 下限门禁 — 已修完

- `tests/kb/test_kb_reranker_health_probe.py:723-752` 新增 `test_negative_cache_ttl_floor_is_at_least_30_seconds`：`:737-740` 直接读 `reranker._cache` 断言 `expiry - clock() >= 30.0`（`NEGATIVE_TTL_SECONDS=30.0` 定义于 `:49`）；`:741` `clock.advance(29)` → `:746` `len(calls)==1` 仍命中；`:747` `clock.advance(31)` → `:752` `len(calls)==2` 重新发起请求。实现侧 `reranker.py:113` 的 `max(MIN_NEGATIVE_TTL, ttl)` 未改；plan 追加节记录负向变异 `MIN_NEGATIVE_TTL=1.0` 会使该用例 FAIL。
- **既有 10 例熔断断言一条未放宽**：`git diff --numstat c73d3d66 -- tests/kb/test_kb_reranker_health_probe.py` = `241 0`，删除行计数 `0`；10 例仍在 `:633/:641/:649/:657/:665/:673/:684/:692/:700/:708`（timeout / ConnectError / 5xx / 4xx / invalid_json / invalid_score / unexpected / ConnectTimeout / ReadError / 60s read cap）。L-2 为**新增第 11 例**，未改动任何既有断言。

### 5. L-3 共享质量集 — 已修完

- **唯一源、无新依赖**：`deploy/reranker/quality-probe.json`（8 行，query + 3 documents）；`retrieve.py:48-50` `_QUALITY_PROBE_PATH = Path(__file__).resolve().parents[4] / "deploy" / "reranker" / "quality-probe.json"`；`:53-59` `_load_health_probe()` 用 **stdlib** `json.loads` + `Path.read_text`，`:62` 模块导入期一次性加载为 `_RERANKER_HEALTH_PROBE`；`probe.sh:17` `probe_file="$script_dir/quality-probe.json"`，`:44-73` 用既有 `python_bin` 读出并写 `request.json`，`:78` `--data-binary` 实际 POST。Python 侧只引入 `json` / `pathlib`，shell 侧无 jq、无新运行时依赖。
- **`probe.sh` 复用既有 `python_bin` 检测**：`:22-29` `.venv/bin/python` → `python3` → `:27-28` 明确报错 `exit 2`；`git diff c73d3d66 -- deploy/reranker/probe.sh` 显示该检测块为**上下文未改动**，新增的只是 `:15-21` 的共享文件存在性检查与 `:44-73` 的读取逻辑。
- **三种调用形态实测通过**（真实 llama-server 监听 `127.0.0.1:11435`，PID 43291；`RERANKER_API_MODEL=""` 清空外部设置）：
  - A `bash deploy/reranker/probe.sh`（默认 URL）→ `reranker probe passed: health ready; ranking valid`，exit 0
  - B `bash deploy/reranker/probe.sh http://127.0.0.1:11435`（位置参数）→ 同上，exit 0
  - C `cd /tmp && RERANKER_BASE_URL=http://localhost:11435 bash <绝对路径>/deploy/reranker/probe.sh`（env 覆盖 + 任意 cwd + 绝对路径）→ 同上，exit 0
  - `bash -n deploy/reranker/probe.sh` → exit 0
- **三文档内容与 `scores[1]` 严格居首语义逐字不变**：`git show c73d3d66:backend/.../retrieve.py` 的 `:42-49` 与 `quality-probe.json` 逐字一致；基线 `:351` `scores[1] <= max(scores[0], scores[2])` 与当前 `retrieve.py:393`、`probe.sh:126` 逐字一致；`tests/kb/test_kb_reranker_quality_probe_consistency.py:25` 定义 `STRICT_RANK_EXPRESSION` 并在 `:101-102` 对两侧源码 `assertIn`。
- **一致性测试解析两侧实际发出的 POST 体、禁止源码再硬编码**：`tests/kb/test_kb_reranker_quality_probe_consistency.py:106-122` 用 `httpx.MockTransport` 捕获 `json.loads(request.content)` 并断言等于共享文件；`:124-145` 起 `ThreadingHTTPServer` 真实 `subprocess.run(["bash", PROBE_SCRIPT, ...])`，`:54` `_StubHandler.do_POST` 记录实际 POST body，`:141` 断言等于共享文件；`:87-104` 对 `retrieve.py` 与 `probe.sh` 源码 `assertNotIn(shared["query"])` / 逐条 `assertNotIn(document)`，并 `assertIn("quality-probe.json", PROBE_SCRIPT)`。共 3 例。
- **文件缺失明确报错、不静默**：`probe.sh:18-21` 缺文件 `exit 2` + stderr 明确路径（实测 `MISSING_EXIT=2`：`reranker probe failed: shared quality probe set is missing: ...`）；`retrieve.py:53-58` 缺文件抛 `FileNotFoundError`（内存 patch 实测 `raised: FileNotFoundError | [Errno 2] ...`），格式错误抛 `ValueError` / `JSONDecodeError`。路径解析实测为 `/Users/wjh/work/ResearchAgent-2/ResearchAgent/deploy/reranker/quality-probe.json`。部署约束见 **L-W1**。

### 6. 边界 — 零 diff

```
git diff --exit-code c73d3d66 -- docs/sdd/specs backend/app/platform/config.py \
  backend/app/api/routes_kb.py frontend tests/frontend tests/e2e docs/sdd/reviews \
  docs/sdd/spec-status-changelog.md
=> BOUNDARY_EXIT=0
```

`git ls-files --others --exclude-standard` 仅 `deploy/reranker/quality-probe.json` 与 `tests/kb/test_kb_reranker_quality_probe_consistency.py`，均不在边界路径内。**本报告落盘前** `docs/sdd/reviews/**` 为 CLEAN；本报告是本次唯一新增的 reviews 文件（`ls docs/sdd/reviews/ | grep 20261111` 落盘前为空），属任务要求产物，不覆盖、不修改任何历史报告。

### 7. 测试真实性 — 通过

原始输出见第二节：`37 passed, 1 warning, 2 subtests passed in 11.63s`（34 例 health + 3 例一致性，与 plan 追加节一致）；`bash -n` exit 0；`.venv/bin/ruff check` 对 4 个改动/新增 py 文件 `All checks passed!`；对 3 个既有 py 文件用 `git show c73d3d66:<f> | ruff check --stdin-filename <f> -` 亦全部 `All checks passed!` → **lint 零新增**。

### 8. 新风险判定（逐条回答）

- **3.0s 等待上限在高负载下是否让并发等待者误降级（fail-open 正确性）**：**会误降级，但 fail-open 本身正确**。`reranker.py:175-176` 超时直接 `_fail(original, "timeout")` → `hits` 为原 RRF 顺序、`used=False`、`degraded=True`，`retrieve.py:259-260` 正常返回 `top_k`，不抛异常、不返回错误排序、不写错误负缓存。但 `retrieve.py:65-66` 记录实测「5 并发最长 18.3s」远大于 3.0s：正常高负载下 leader 成功但 >3.0s 时，4 个等待者跳过精排，且 `retrieve.py:567-580` 会把它们记为 `status=degraded, degraded_reason=timeout`，而同期 health 为 `available=true` → **虚报降级 / health 与 `kb.rerank` 事件信号不一致**。见 **M-W1**。
- **45s 总时限是否过长以致仍可能占线程**：**有界但偏长**。`retrieve.py:79/:81` 下 leader 最多占 45s、等待者最多占 50s，相对正常 2.3s 推理约 20 倍；若并发 `/api/kb/health` 请求数超过线程池容量，50s 窗口内仍可能占满线程池（只是 50s 后释放）。见 **M-W2**。
- **模块导入时读共享 JSON 的部署风险**：**缺失时明确报错、不静默**（Python `FileNotFoundError`、shell `exit 2` 均实测）；但属**导入期硬依赖**，`retrieve.py:62` 在模块导入时执行，若部署只拷贝 `backend/`（如独立 wheel / 精简镜像）导致 `parents[4]` 路径不存在，整个后端导入失败、影响面是全站而非仅 KB。当前 `deploy/start.sh` 从仓库根启动、backend 与 deploy 同树，故现部署形态安全。见 **L-W1**。
- **`unexpected` 是否在对外响应 / 事件里泄漏堆栈或 query（spec-014:132）**：**对外无泄漏**。`retrieve.py:410/:486` 只返回稳定字符串 `"unexpected"`；`/api/kb/health` 结构由 `tests/...:454-477` / `:522-530` 锁住；`kb.rerank` / `kb.retrieval` 事件 metadata 只含 `status/input_count/output_count/enabled/degraded_reason/error_type`（`retrieve.py:593-602`、`:268-283`），`error_type` 为 `type(error).__name__` 而非堆栈。`logger.exception`（`:409/:485`）的 traceback 只进**服务端日志**，符合 `regression-guard` 第 14 条；`tests/...:504` 明确断言日志不含 query 文本。与 `spec-014:132` 字面的张力见 **L-W2**。

---

## 二、验证原始输出

```
===== PYTEST =====
./.venv/bin/python -m pytest -q tests/kb/test_kb_reranker_health_probe.py tests/kb/test_kb_reranker_quality_probe_consistency.py
..................................... [100%]
37 passed, 1 warning, 2 subtests passed in 11.63s
PYTEST_EXIT=0
===== BASH -N =====
bash -n deploy/reranker/probe.sh            -> BASHN_EXIT=0
===== RUFF CURRENT (4 changed/new py) =====
All checks passed!                          -> RUFF_CURRENT_EXIT=0
===== RUFF BASELINE c73d3d66 (3 tracked py, stdin-filename) =====
reranker.py / retrieve.py / test_kb_reranker_health_probe.py -> 全部 All checks passed! (BASE_EXIT=0)
=> lint 零新增
===== PROBE.SH 三种调用形态（真实 llama-server @127.0.0.1:11435） =====
FORM A 默认              -> reranker probe passed: health ready; ranking valid (A_EXIT=0)
FORM B 位置参数          -> reranker probe passed: health ready; ranking valid (B_EXIT=0)
FORM C env+绝对路径+跨 cwd -> reranker probe passed: health ready; ranking valid (C_EXIT=0)
===== 共享 JSON 缺失路径 =====
SHELL  -> stderr: "reranker probe failed: shared quality probe set is missing: ...", MISSING_EXIT=2
PYTHON -> raised: FileNotFoundError | [Errno 2] No such file or directory: '/tmp/__missing_quality_probe__.json'
===== 边界 / 纯追加 =====
BOUNDARY_EXIT=0
241  0  tests/kb/test_kb_reranker_health_probe.py   (0 deleted lines)
16   0  docs/sdd/plans/014/task-06-reranker-health-status.md (纯追加，1-115 行原文保留)
```

---

## 三、剩余问题清单（不阻塞，按严重度）

### [MEDIUM] M-W1：3.0s 在飞等待上限在高负载下让并发等待者误降级，并产生 health / 事件矛盾信号（任务 W 新引入的取舍）

- **文件:行**：`backend/app/knowledge_base/infrastructure/reranker.py:48`（3.0）、`:172`（注释「leader 成功时等待者继续发自己的请求」）、`:175-176`（超时直接 `_fail(original,"timeout")`）；`backend/app/knowledge_base/infrastructure/retrieve.py:65-66`（实测 5 并发最长 18.3s）、`:567-580`（`_record_rerank_result` 把 `timeout` 记为 `degraded`）；`deploy/reranker/README.md` 第 5 节与 `docs/sdd/plans/014/task-06-reranker-health-status.md` 追加节 M-1 行。
- **Issue**：`wait` 仅在 ≤3.0s 内返回 True 且 `flight.reason is None` 时才会「继续发自己的请求」；leader 正常成功但耗时 18.3s（实测并发上界）时，4 个等待者已被判 `timeout` 并返回 RRF 顺序、跳过精排，同时 `kb.rerank` 事件记 `degraded_reason=timeout`，而 `/api/kb/health` 因 leader 成功为 `available=true`。这是**虚报降级**与「health / 事件信号不一致」，与原 CRITICAL-1 修掉的矛盾信号同型（方向相反：那是掩盖真实故障，这是制造假故障信号）。README / plan「leader 成功时等待者继续发自己的请求，不跳过精排」的表述未限定「3.0s 内」，与实现存在表述偏差。
- **为何不阻塞**：fail-open 正确性成立（不抛异常、不返回错排、不影响问答可用性、不写错误负缓存）；3.0s 是 README / plan / 代码注释均已披露的显式取舍；M-1 的工单目标（消除首个 60s 并发窗口打满线程池）已达成并被 `:754-793` 用例锁住；`spec-014:131/:134` 未规定在飞等待上限，不违反契约字面。
- **Fix（建议立后续工单）**：① 把 wait cap 调整为覆盖并发实测上界（或按并发度/负载动态取值）；② 或为「在飞等待超时」引入独立 reason（如 `inflight_wait_timeout`）且不记为故障级 `degraded`，避免污染观测；③ 补一例「leader 4s 后成功、等待者仍拿到精排结果」的回归用例；④ 同步 README / plan 表述，明确「仅 leader 在 3.0s 内成功时等待者继续发请求」。

### [MEDIUM] M-W2：总时限覆盖不全 + 45/50s 仍可占线程（原 M-2 残留的部分收敛）

- **文件:行**：`backend/app/knowledge_base/infrastructure/retrieve.py:318`（`with client.stream(...)` 在 deadline 检查之前）、`:319-324`（仅 `iter_bytes()` 循环内校验）、`:79`（45.0）、`:81`（50.0）、`:465-480`（waiter deadline）；`backend/app/knowledge_base/infrastructure/reranker.py:184-186` / `:191-192`（检索侧 `httpx.Timeout(read=60.0, connect=2.0)` + `client.post`，**无总时限**）。
- **Issue**：(a) `client.stream()` 等待**响应头**期间不校验 deadline，异常后端按 <6s 间隔慢速吐 header 字节可绕过 45s，leader 可无限占用、`_health_inflight` 长期不清，后续 health 请求全部走 50s waiter 后返回 `timeout`；(b) 检索侧 leader 完全没有总时限，`reranker.py` 的 60s read 仍是「相邻两次 socket 读的间隔」，慢速吐字节后端可让单个 leader 线程无限占用；(c) 即便收敛，45s leader / 50s waiter 相对 2.3s 正常推理约 20 倍，极端并发下 50s 窗口内仍可能占满线程池（只是有界释放）。`retrieve.py:77` 把 6/30 当作「单次请求最长合法耗时」的推导概念上不严谨。
- **为何不阻塞**：W 已给 health **body 阶段**加了 45s 总时限并由 `tests/...:532-555` 锁住，等待者已由「无限」改为真实时钟 50s 有界（`:566-592` 锁住），检索侧等待者已由「各自 60s」改为 3.0s（`:754-793` 锁住）；同一 key 始终只有 1 个 leader，故**不会**出现原 M-1/M-2 描述的「N 个并发各阻塞 60s 打满线程池」。给检索侧加总时限不改 60s/2s 冻结常量，但超出本次 M-2 的用户核对口径（口径只要求 health 探针与等待者），属原残留的部分收敛，非任务 W 新违规。
- **Fix（建议立后续工单）**：给 `rerank_hits` 的 leader 加与冻结常量解耦的总时限；把 deadline 校验前移到能覆盖 header 阶段的层次（自定义 transport / watchdog / `anyio.fail_after`）；补「header 阶段慢速吐字节」用例；按真实部署并发量评估把 45/50s 收紧到 20–30s，或在网关层给 `/api/kb/health` 加并发与超时保护。

### [LOW] L-W1：共享 JSON 是模块导入期硬依赖，部署形态需固化

- **文件:行**：`backend/app/knowledge_base/infrastructure/retrieve.py:48-50`（`parents[4]` 推导）、`:62`（导入期 `_load_health_probe()`）；`deploy/reranker/probe.sh:17-21`（缺失检查）。
- **Issue**：缺失时两侧均明确报错（实测 Python `FileNotFoundError`、shell `exit 2`），**不静默**，这一点满足用户关注；但 `parents[4]` 把「仓库根 / backend / deploy 同树」固化为导入前提。若未来把 `backend/` 打成独立 wheel 或容器镜像只拷 app 代码，导入即失败且影响全站启动，而非仅 KB 降级。
- **Fix**：在部署清单 / 镜像构建 / `deploy/start.sh` 启动前置检查中加入 `deploy/reranker/quality-probe.json` 存在性校验并给出明确文案；若将来改变打包形态，改为包内资源（`importlib.resources`）或显式配置路径，并保持一致性测试两侧实际 POST 体门禁。

### [LOW] L-W2：`spec-014:132` 字面与 `logger.exception` 的张力

- **文件:行**：`docs/sdd/specs/014-kb-reranker.md:132`（「日志、reason、span 不得包含 query、完整文档、异常堆栈、环境变量或敏感命令行」）；`backend/app/knowledge_base/infrastructure/retrieve.py:409` / `:485`（`logger.exception` 输出 traceback）；`.codebuddy/skills/regression-guard/SKILL.md:526` 第 14 条（「原始异常只进服务端 `logger.exception`，对外/落库的事件 payload 用稳定 `error_code`」）。
- **Issue**：`logger.exception` 会把堆栈写入服务端日志，与 spec-014:132 字面「日志不得包含异常堆栈」存在张力；但这是原复验报告 L-1 Fix 明确建议的做法，且符合 regression-guard 第 14 条的分层（对外/落库只用稳定码）。`tests/...:504` 已断言服务端日志不含 query 文本；对外响应与事件无堆栈、无 query、无完整文档（第一节第 8 项）。
- **Fix**：在 spec 修订或 plan 追加节中明确 `spec-014:132` 的「日志」指对外可观测日志 / span / 事件 payload，服务端内部诊断日志按 regression-guard 第 14 条处理；或在保留可诊断性前提下把默认日志收敛为稳定码 + 异常类型名（`logger.error(..., exc_info=False)`），`exc_info` 仅调试开关开启时输出。**本项不构成对外信息泄漏**。

---

## 四、专项风险判定（用户明确要求「是否还有」）

### 「打满线程池」

- **显著收敛，但未彻底消除**。检索侧：负缓存「请求后写」造成的首个 60s 并发窗口内，并发问答现在最多等 3.0s（`reranker.py:175-176`），且 `(endpoint, model)` 唯一 leader（`:51-58`），不再出现「约 40 个并发各阻塞 60s」；health 侧：等待者由「`while True` 无限等」改为真实时钟 50.0s 有界（`retrieve.py:465-480`），探针由「read cap 非总时限、可无限不收敛」改为 body 阶段 45.0s 总时限（`:315-326`）。
- **残留**：leader 线程本身仍可被占满 —— 检索侧 leader 无总时限（`reranker.py:191-192`，60s read 为相邻读间隔）；health 侧 header 阶段慢速吐字节不校验 deadline（`retrieve.py:318`）；且 45/50s 在极端并发下仍可能占满线程池（只是 50s 后释放）。
- **结论**：**仍有残留，不得表述为「打满线程池风险已彻底消除」**；但其形态已从「无界 + N 个并发各阻塞」变为「有界 + 单 leader」，不足以维持 BLOCK。

### 「掩盖真实故障」

- **主路径已消除**：`available=true` 仍需 liveness GET 与三文档质量 POST 同时通过（`retrieve.py:357-395`），模型运行期损坏报 `quality_probe_failed`（`:393-394`）并写 30s 负缓存；`tests/...:479-492` 端点级断言 `available=false` / `reranker=false`。L-1 把代码级意外异常从 `quality_probe_failed` 改为 `unexpected` + `logger.exception`（`:408-410` / `:484-486`），运维不再被误导去排查模型质量，30s 负缓存语义不变；`tests/...:494-510` 锁住「reason 可诊断 + 日志留痕 + 不含 query」。
- **残留（新形态）**：M-W1 的 3.0s 等待超时会**虚报降级**（health 可用但 `kb.rerank` 记 `degraded_reason=timeout`）——这是「制造假故障信号」，不是「掩盖真实故障」；另有 `spec-014:134` 既有的 30s 正缓存窗口（模型突然损坏不即时反映），非任务 W 引入、不改变契约。
- **结论**：**不存在足以维持 BLOCK 的「掩盖真实故障」**；但存在 M-W1 的观测噪声，须随后续工单收敛，且在此之前不得宣称「health 与 `kb.rerank` 事件已完全一致」。

### 「对外信息泄漏」

- **无**。`unexpected` 对外仅为稳定字符串（`retrieve.py:410` / `:486`）；`/api/kb/health` 响应结构不变（`tests/...:464-475` / `:522-530`）；`kb.rerank` / `kb.retrieval` 事件 metadata 只含稳定字段（`retrieve.py:593-602` / `:268-283`），`error_type` 为异常类型名而非堆栈；`tests/...:504` 明确断言服务端日志不含 query 文本。服务端 `logger.exception` 的 traceback 只在服务端，符合 `regression-guard` 第 14 条；与 `spec-014:132` 的字面张力已列为 L-W2，属文档边界澄清，不是对外泄漏。

---

## 五、通过（附意见）— 强制约束清单

1. `docs/sdd/specs/**`、`backend/app/platform/config.py:87-92`、`backend/app/api/routes_kb.py`、`frontend/**`、`tests/frontend/**`、`tests/e2e/**`、历史 `docs/sdd/reviews/**`、`docs/sdd/spec-status-changelog.md` 保持零改动；后续同步 spec 契约必须走正式修订门禁（`spec-014:124`）。
2. `reranker.py:19` 的 `MIN_NEGATIVE_TTL=30.0`、`:22` 的 60.0/2.0 硬上限、`:113` 的 `max(MIN_NEGATIVE_TTL, ttl)` 不得上调或条件化；新增任何失败分支必须同步补「第二次调用只发一次请求」的熔断门禁（`tests/...:633-721` 10 例 + `:723-752` TTL 下限例不得删弱）。
3. single-flight 三要素不得回退：Condition 内一次性 CAS（`reranker.py:51-58`）、leader 网络请求用 `try/finally` 发布（`:182` / `:225-227`）、锁内不调用用户函数（`:162-165` 在锁外）；`clear_negative_cache()` 必须继续清 inflight 并 `notify_all`（`:71-76`）。
4. health 侧 45.0s 总时限、50.0s 等待上限、6.0/30.0 两档 read cap、4.0s `timeout` 短缓存、30s 正/负缓存不得放宽；`_request_json` 的 `iter_bytes()` 逐块 deadline 校验不得移除；等待者必须使用真实 `time.monotonic` 而非注入时钟。
5. 两处兜底 `unexpected` + `logger.exception` 不得回退为 `quality_probe_failed`；`/api/kb/health` 响应结构与 30s TTL 不变；对外响应 / 事件 / span 只放稳定 reason 与异常类型名，不放原始异常文本、query 或文档。
6. `deploy/reranker/quality-probe.json` 为唯一质量集；Python 与 shell 源码不得再硬编码 query/documents；`scores[1] <= max(scores[0], scores[2])` 逐字保留；`tests/kb/test_kb_reranker_quality_probe_consistency.py` 3 例（含两侧实际 POST 体解析）不得删弱；`probe.sh` 的 `python_bin` 三级检测不得换成 jq 等新依赖。
7. 部署必须携带 `deploy/reranker/quality-probe.json` 且保持 `<repo-root>/deploy/reranker/` 相对位置；`deploy/start.sh` 启动前置检查应覆盖该文件缺失场景；文件缺失时两侧继续明确报错，不得静默降级为空质量集。
8. 针对 M-W1 / M-W2 立后续工单：补「leader 慢成功时等待者仍拿精排结果」与「header 阶段慢速吐字节」两类用例，给检索侧 leader 加总时限，评估收紧 45/50s；在收敛前不得对外宣称「打满线程池风险已彻底消除」或「health 与 kb.rerank 事件完全一致」。
9. `docs/sdd/plans/014/task-06-reranker-health-status.md` 1–115 行（含 1–85 历史原文）继续保留，后续同步只用追加节；README 第 5 节随实现同步的纪律不变。

---

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 2     | info   |
| LOW      | 2     | note   |

**Verdict: APPROVE（附意见）— 5 项残留工单（M-1 / M-2 / L-1 / L-2 / L-3）全部按核对口径修完、可收口；边界零 diff、37 passed、lint 零新增、三种调用形态实测通过。2 项 MEDIUM 为残留风险 / 新引入取舍（非契约违规）、2 项 LOW 为部署与文档边界约束，按第五节强制约束清单收口。**

- **报告路径**：`docs/sdd/reviews/20261111-backlog-fixes-backend-review.md`（新增，不覆盖历史报告）
- **进展日志**：`.codebuddy/agent-logs/spec-014/task-06/backend-reviewer/20261111-015304.md`
- **只读声明**：本次复验除新增上述报告与进展日志外，未修改任何业务代码、测试、spec、数据；未执行任何 git 写操作（无 add / commit / push / merge / reset / stash / clean）；验证仅产生标准测试产物与已清理的 `/tmp` 临时目录。
