# 2026-11-10 遗留项修复批次 — 后端 BLOCK 只读复验（任务 U）

- **评审角色**：backend-reviewer
- **任务**：只读复验，确认任务 U 是否解除 docs/sdd/reviews/20261110-lingering-fixes-backend-review.md 的 BLOCK
- **基线**：efec3c06（= 当前 HEAD，staged 为空）；范围为当前工作树相对该 commit 的净改动
- **评审范围**：backend/**、deploy/**、scripts/**、tests/ 下后端用例，以及作为契约数据的 spec-014 / plan-014 / deploy/reranker/README.md
- **边界**：frontend/** 与 tests/frontend/** 交 frontend-reviewer，不越界；tests/e2e/ 下 Playwright 用例仅记录存在不深入
- **只读声明**：除新增本复验报告与强制要求的进展日志外，未修改任何业务代码、测试、spec、数据；未执行任何 git 写操作（无 add/commit/push/merge/reset/stash/clean）。验证命令仅产生 .pytest_cache / __pycache__ 标准测试产物
- **进展日志**：.codebuddy/agent-logs/spec-014/task-00/backend-reviewer/20261110-044956.md
- **原报告**：docs/sdd/reviews/20261110-lingering-fixes-backend-review.md（205 行，Block：1 CRITICAL / 2 HIGH / 3 MEDIUM / 2 LOW，文末列 7 条强制约束）

## 结论：**BLOCK 已解除（Approve，附强制约束清单）**

原报告「四、阻塞项与强制约束清单」7 条逐条有代码事实支撑地落地，`docs/sdd/specs/**` 一字未改；1 CRITICAL、2 HIGH、3 MEDIUM、2 LOW 均有对应修复与测试门禁。剩余 2 项 MEDIUM 为**残留风险（非违规）**、3 项 LOW 为覆盖/一致性缺口，均不阻塞；其中「掩盖真实故障」与「打满线程池」两类风险见第四节专项判定，不得表述为已彻底消除。

---

## 一、逐项确认（7 项，附 文件:行号）

### 1. CRITICAL-1 available 语义 — 已修复

- **三文档质量探针已恢复**：`retrieve.py:40-49` 常量 `_RERANKER_HEALTH_PROBE`（query + 3 条相关度明显不同的文档）；`:299-308` `_health_probe()` docstring 明示 spec-014:72 = HTTP liveness **且** 排序质量探针通过；`:320-321` 先发 `GET /health`；`:337-343` 再发 `POST /v1/rerank`；`:350-353` 调 `_probe_scores()`，仅当 index 1 严格大于另两条才 `available=true`。
- **`_probe_scores()` 已恢复**：`retrieve.py:370-392`，含 dict/results schema 校验（:372-376）、非 bool 整数且唯一/在 0,1,2 内（:382-383）、非 bool 数值（:384-385）、`math.isfinite`（:387）、三 index 完整（:390-392）。
- **质量集同源，非两套实现**：`deploy/reranker/probe.sh:43-48` 的 query/documents 与 `retrieve.py:42-49` 逐字一致；`probe.sh:94-109` 的 index/isfinite/居首判定与 `_probe_scores()` + `:351` 等价（三分数全同时 `scores[1] <= max(...)` 同样判失败）。
- **spec 未被擅改（实测）**：`git diff efec3c06 -- docs/sdd/specs/` 输出为空；`git diff --exit-code efec3c06 -- docs/sdd/specs/014-kb-reranker.md` 退出码 0；`git status --porcelain -- docs/sdd/specs/` 为空。Read 核对 `spec-014:72` 字段定义、`:102` 质量探针、`:124` 门禁声明、`:131` 熔断、`:149` A7 均为原文。`config.py`、`routes_kb.py` 亦未被改动。
- **端点级证据**：`tests/kb/test_kb_reranker_health_probe.py:410-423` 质量损坏时断言 `reranker_detail.available=false`、`reason=quality_probe_failed`、`reranker=false`，消除 health 与 `kb.rerank` 事件矛盾。

### 2. CRITICAL-2 熔断与硬上限 — 已修复

- **`cacheable` 排除已回退**：`reranker.py` 全文 172 行无 `cacheable`；`:169-171` 所有失败路径无条件落到 `_remember(key, reason, now(), ...)`。覆盖：`http_status`（4xx/5xx，:142-143）、`invalid_json`（:147-148）、`invalid_schema`/`invalid_index`/`invalid_score`（:150 经 `_scores`）、`ConnectTimeout`→connection（:157-159）、`TimeoutException`→timeout（:160-161）、`ConnectError`→connection（:162-163）、`HTTPError`→connection（:164-166）、`Exception`→unexpected（:167-168）。
- **≥30s 保证**：`reranker.py:19` `MIN_NEGATIVE_TTL=30.0`；`:73` `_remember` 用 `max(MIN_NEGATIVE_TTL, ttl)`；成功路径 `:153-154` `_cache.pop(key, None)` 清负缓存。
- **60s read / 2s connect 硬上限**：`reranker.py:22` `MAX_CONNECT_TIMEOUT, MAX_READ_TIMEOUT = 2.0, 60.0`；`:133-135` `read = min(_positive(...), 60.0)`、`connect = min(..., 2.0)` 并构造 `httpx.Timeout(read, connect=connect)`；`config.py:87-91` 默认 2.0/60.0 且相对基线零 diff（冻结值未破）。测试 `test_read_timeout_cap_does_not_exceed_spec_limit:539-552` 以 `read_timeout=600.0` 断言 `seen == [60.0]`。

### 3. HIGH：ConnectTimeout 归类与两模块 HTTPError 一致性 — 已修复

- `retrieve.py:354-356` 单独捕获 `httpx.ConnectTimeout` → `connection`（`reranker_health():440-445` 仅 `timeout` 走 4s，故为 30s 熔断）；`reranker.py:157-159` 同样 → `connection`（≥30s 熔断）。
- `httpx.HTTPError`（ReadError / RemoteProtocolError）：`retrieve.py:361-363` → `connection`；`reranker.py:164-166` → `connection`，两处一致。
- 4 例门禁：`test_connect_timeout_is_classified_as_connection_and_cached:331-341`、`test_read_error_is_classified_as_connection_consistently:343-348`、`test_connect_timeout_is_connection_and_cached:523-529`、`test_read_error_is_connection_and_cached:531-537`。

### 4. 慢响应不假降级 — 成立，但存在残留风险（见第四节）

- **两档 read cap**：`retrieve.py:54-56` 常量 2.0 / 6.0 / 30.0；`:311-315` 分别钳制并构造 `liveness_timeout`（read=6.0）与 `quality_timeout`（read=30.0）；`:321` GET 用 liveness、`:343` POST 用 quality。`:52-53` 注释记录本机实测单请求 1.5–2.3s、5 并发最长 18.3s。
- **实测覆盖由测试锁住**：`:212-225` 真 sleep 2.2s 仍 available；`:227-233` 18.3s 并发仍 available；`:235-243` 断言 `/health` read=6.0、`/v1/rerank` >18.3 且 ≤30.0；`:245-251` 2.2s 慢 /health 通过；`:253-259` 7.0s /health 仍 timeout；`:261-266` 31.0s 质量推理仍 timeout（有上限，非无限等待）。
- **timeout 4s 短缓存 + 30s 正/负缓存 + single-flight**：`retrieve.py:61` `TRANSIENT_TTL=4.0`、`:39` `HEALTH_TTL=30.0`；`:421-430` 缓存命中直接返回、`key` 已在 `_health_inflight` 则 `wait(0.1)` 不重复起探针；`:436-447` `finally` 写缓存（timeout→4s，其余含成功/不可达/质量失败→30s）、清 inflight、`notify_all`。
- **避免 30s 假降级**：成立 —— 一次偶发慢响应若超时只缓存 4s（`:268-288` 断言 ttl∈[3,5]、advance 2.0 命中、advance 3.0 恢复），慢但成功则写 30s **正**缓存（`:222-225` 断言缓存里 available=True）。
- **避免持续故障下每次 health 重跑推理**：成立 —— single-flight 把 N 次并发合并为 1 次，且 `timeout` 也写 4s 缓存而非零缓存；`:290-307` 连接失败 30s 内 `fake.calls==1`、advance 31 才重新探测；`:309-322` 质量失败 30s 内不重跑 POST。
- **新取舍的掩盖风险**：有，不阻塞，详见第四节 M-2 与 L-1。

### 5. MEDIUM：conftest / 27 例测试 / seed 三项 — 已修复

- **显式 opt-in + 目录级 conftest**：`tests/conftest.py:51-56` 为普通 `@pytest.fixture`（无 autouse），顶层不再 import backend（`:27-29` 只 import time/pytest）；`tests/kb/conftest.py:12-14` 与 `tests/system/conftest.py:12-14` 各以目录级 `autouse=True` 引用 `clean_warmup_registry`。
- **在飞线程竞态防护真实有效**：`tests/conftest.py:35-48` `_drain_and_reset()` 用 `is_warmup_started()` 判断 + 有界 5s 等待 `readiness_snapshot()` 全终态再 `reset_warmup()`。依赖的真实 API 已核对：`warmup.py:116-117` `is_warmup_started()`、`:111-113` `readiness_snapshot()`、`:87-96` snapshot 返回含 `status` 的 dict、`:50` `_TERMINAL_STATUSES=(ready,failed)` 与 conftest `:31` 一致；`warmup.py:141-159` 重量项超时后后台 worker 只写 `box`、不再 `mark_done`，故 reset 后不会被残留线程污染。
- **27 例严格、未锁违规、未放宽**：文件 557 行 = HealthProbeTests 17 例（`:197-423`）+ RerankNegativeCacheTests 10 例（`:426-552`）。断言两档 cap（`:235-243`）、短缓存 TTL（`:268-288`）、各类失败熔断（`:464-537`：timeout/connection/5xx/4xx/invalid_json/invalid_score/unexpected/ConnectTimeout/ReadError）、质量 POST（`:219/:233/:316/:408/:423`）、端点级质量失败（`:410-423`）。原报告点名的两例「零缓存」门禁（旧 `:168-179`、`:258-276`）**已删除并重写**为「短缓存」与「30s 熔断」断言；无恒真、无静默失效守卫（`fake.calls` 逐项比对、`_cached_entries` TTL 数值、`read_timeouts` 数值）。
- **seed 快照条件化 / 连接对称释放 / 源库缺失可诊断**：`scripts/seed_demo_research_reports.py:280-302` `_has_pending_seed_rows()` 缺库打印 `backup: skip probe ...` 且只读探测出错保守返回 True；`:305-343` `snapshot_databases()` 跳过缺失源库并打印诊断、同名加 `name-` 前缀、`src`/`dst` 两个 connect 均置于 `try` 且 `finally` 成对 `close`（`:332-341`）；`main():474-479` 仅在确有待删 seed 数据时落盘快照，否则打印 `backup: skipped`。`tests/system/test_seed_demo_snapshot_guard.py` 7 例（`:34/:47/:63/:88/:107/:129/:139`）逐条对应，含 `:63-85` 用 spy 令第二个 connect 抛错并断言 `src` 已被关闭。

### 6. LOW：start.sh / 2 例清理契约 / 名实 / 文档同步 — 已修复

- `deploy/start.sh:72-76` 与 `:84-88` 把 `[ -x ... ] && stop.sh || true` 改为 `if [ -x ... ]; then if ! stop.sh; then echo 警告 >&2; fi; fi`；`:140` 前台 cleanup 用 `|| echo 警告`（非 `|| true`）。`git diff --numstat` = `20 3`（3 行删除即旧 `|| true` 两处及关联行）。
- **补 2 例清理契约**：`tests/system/test_deploy_start_reranker_degradation.py:151-160`（子脚本失败分支）、`:163-178`（runtime URL 无效分支），用 `_write_failing_stop():136-148` 造 stop.sh `exit 1`，断言 `stop.marker` 存在、stderr 含「Reranker 清理失败」、仍 `RERANKER_ENABLED=false`。文件由原 4 例增至 6 例。
- **`quality_probe_failed` 名实一致**：`retrieve.py:306-307` docstring 明确「/health 协议异常或排序质量探针未通过」；`:329/:334/:336/:345/:349/:351-352` 的返回路径与之吻合；`README.md:80` 与 `plan-014:99` 同步。
- **README 同步**：`deploy/reranker/README.md:8` 改为「任务 U 之后该字段重新代表 HTTP 与三文档排序质量探针均通过」；第 5 节 `:71-89` 全量同步（`:73` 修订说明、`:75` 质量语义、`:77` 两档 cap、`:78` 4s 短缓存、`:79` 检索侧熔断与异常归类、`:80` reason 集合与名实、`:88-89` 排查步骤含 30s/4s 等待）。
- **plan-014 同步且历史原文保留**：`docs/sdd/plans/014/task-06-reranker-health-status.md:87-117` 追加节与最终实现逐项对齐；`git diff efec3c06 --numstat -- docs/sdd/plans/014/` = `32 0`（**纯追加、0 删除**）→ 1–85 行历史原文保留；`:89` 明文声明「上方 1–85 行…保留不改」；`:108` 记录 `|| true` 已改为显式告警；`:117` 记录 27 例 / 6 例 / README 第 5 节。

### 7. 测试真实性与 ruff — 通过

- 两条用户指定 pytest 命令原始输出见第六节：**27 passed / 13 passed**，退出码均 0。
- `ruff check` 13 个后端相关改动/新增 py 文件 → `Found 15 errors`，全部位于 `backend/app/memory/repository.py` 既有行（`:24 F401`、`:274/:278 SIM118×10`、`:348 SIM102`、`:1753/:1797/:1805 F811×3`）；用 `git show efec3c06:同文件 | ruff check --stdin-filename 同路径 -` 复跑同为 **15 errors**，规则与行号逐条一致 → **lint 零新增**。`retrieve.py` / `reranker.py` / `seed_demo_research_reports.py` / 3 个 conftest / 新测试均 0 error。
- 补充回归 `tests/kb/test_kb_reranker.py tests/system/test_reranker_config.py tests/research/test_seed_demo_research_reports_clean.py` → `20 passed, 25 subtests passed`（证明 60.0 冻结值与既有 KB/seed 用例未回归）。

---

## 二、原 BLOCK「四、阻塞项与强制约束清单」7 条逐条核对

| # | 原约束 | 落地证据（文件:行） | 状态 |
|---|---|---|---|
| 1 | 契约二选一并留痕 | 选「恢复实现」；spec 目录相对 efec3c06 零 diff、git diff --exit-code=0；README:8/71-89 与 plan-014:87-117 同步，不再靠自述豁免 | 通过 |
| 2 | 恢复 rerank_hits 熔断 | reranker.py:169-171 全量 _remember；:73 max(30.0, ttl)；测试 :464-537 覆盖 timeout/ConnectTimeout/invalid_*/unexpected/4xx/5xx/ConnectError | 通过 |
| 3 | 检索路径等待设上限 | reranker.py:22 MAX_READ_TIMEOUT=60 / MAX_CONNECT_TIMEOUT=2；:133-135 钳制；config.py:87-91 默认值未改（冻结值不破）；测试 :539-552 以 600s 配置断言钳到 60s | 通过（见 M-1 残留） |
| 4 | 统一异常归类 | retrieve.py:354-356 / :361-363 与 reranker.py:157-159 / :164-166 一致；4 例归类测试 | 通过 |
| 5 | 消除 health 与观测矛盾 | retrieve.py:295-353 恢复质量探针；README:75/80、plan-014:99 同步；端点级测试 :410-423 | 通过 |
| 6 | 测试随实现同步 | 旧「零缓存」两例已删除重写；27 例（17+10）更严格，无放宽/恒真；补 ConnectTimeout、invalid_*、503、ReadError 边界 | 通过（见 L-2 缺口） |
| 7 | MEDIUM 项同批处理 | conftest 显式 opt-in+目录级+竞态防护；seed 三项；start.sh 去 || true 并补 2 例清理契约 | 通过 |

---

## 三、剩余问题清单（不阻塞，按严重度）

### [MEDIUM] M-1 检索路径首个 60s 并发窗口仍可能打满 FastAPI 线程池

- **文件:行**：`backend/app/knowledge_base/infrastructure/reranker.py:117-119`（请求前查缓存）、`:136-141`（发起 POST）、`:170`（失败后才写缓存）；`:133-135`（read cap 60.0）；`backend/app/platform/config.py:91`（默认 60.0）
- **Issue**：负缓存是在请求**结束后**才写入（`_remember` 在 `:170`），而缓存检查在请求**开始前**（`:117-119`），且 `rerank_hits` 没有 single-flight。reranker 端口存活但 hang 时，第一个请求要等满 60s 才写缓存，这 60s 内所有并发 KB 问答都看到空缓存、各自再发起一个 60s 请求。Starlette/FastAPI 默认线程池约 40 个 token，约 40 个并发 KB 问答即可占满，影响面超出 KB 检索。熔断恢复后，每 30s 负缓存过期仍会重复出现这样的并发窗口。
- **为何不阻塞**：60s 读取上限本身是 `spec-014:131` 契约值且 `config.py:91` 为冻结值，任务 U 未违反；原 BLOCK 的核心成因「持续故障下**每个**问答都重复等待 60s」已被全量熔断消除。
- **Fix（建议立后续工单）**：给 `rerank_hits` 加按 `(endpoint, model)` 的 single-flight（复用 `retrieve.py:421-447` 的同款 Condition/CAS 结构，避免第二套实现），或在发起请求前先写一条短乐观负缓存、成功后立即 pop；并补一例「并发 N 次 hang 只发生 1 次网络请求」的测试。

### [MEDIUM] M-2 health single-flight 无界等待，且 httpx read timeout 不是请求总时限

- **文件:行**：`backend/app/knowledge_base/infrastructure/retrieve.py:421-430`（`while True` + `_health_condition.wait(timeout=0.1)` 无界循环）、`:313-315`（`httpx.Timeout(connect, connect=connect, read=6.0/30.0)`）、`reranker.py:135`（read=60.0）
- **Issue**：`wait(timeout=0.1)` 只是单次唤醒间隔，不是总等待上限；只要 `_health_inflight` 中的探针不结束，并发 `/api/kb/health` 请求的线程就在该循环里无限阻塞。而 `httpx` 的 `read` timeout 语义是**相邻两次 socket 读之间的最大间隔**，不是整个请求的总时限：若损坏/恶意后端每隔小于 30s（检索侧 60s）发一个字节，read timeout 永不触发，探针永不收敛，inflight 永不清 → 所有并发 health 请求持续占线程。`README.md:77`、`plan-014:101` 把 30s 表述为「硬上限」，严格说略有夸大。
- **为何不阻塞**：single-flight 是 `spec-014:134` 强制要求，30s/60s 是 `:131` 契约上限；该缺口为契约内的固有代价，非任务 U 引入的新违规，且需异常后端行为才触发。
- **Fix（建议立后续工单）**：给 `reranker_health()` 的等待加有界 deadline，超时后返回上一次已知 detail（或 `available=false, reason=timeout`）而非无限等；给探针与检索请求加**总时限**（如 `anyio.fail_after` 或自定义 deadline 配合 `client` 关闭）；补一例「后端按间隔慢速吐字节」验证总时限生效。

### [LOW] L-1 兜底异常被记为 quality_probe_failed 并缓存 30s，掩盖代码级故障类型

- **文件:行**：`backend/app/knowledge_base/infrastructure/retrieve.py:366-367`、`:434-435`（两处 `except Exception` 均返回 `quality_probe_failed`，后者还吞掉异常且无 logger 留痕）
- **Issue**：`_health_probe()` 已分类 ConnectTimeout/TimeoutException/ConnectError/HTTPError 与 TypeError/ValueError/OverflowError，剩余未预期的**代码级**异常仍被归为「质量探针未通过」；`reranker_health():440-445` 会对该 reason 写 30s 缓存。运维按 `README.md:88-89` 会去排查模型，而非应用缺陷，且 30s 内无法自愈。`reranker.py:167-168` 的 `unexpected` 则名实相符。
- **Fix**：兜底分支改用 `unexpected` 一类明确 reason（或至少在 `reranker_health()` 的 except 里 `logger.exception` 并缩短该 reason 的 TTL），补一例注入意外异常的测试。

### [LOW] L-2 检索侧 10 例熔断测试未锁住 ≥30s TTL 下限

- **文件:行**：`tests/kb/test_kb_reranker_health_probe.py:441-456`（`_two_calls` 固定传 `negative_ttl=1`、`clock=_FakeClock(100.0)` 不推进）、`:458-462`（`_assert_cached` 只断言 `len(calls)==1`）
- **Issue**：测试名均称「30s negative cache」，但只验证「第二次命中缓存」，未验证 TTL 下限。实现侧 `reranker.py:73` 的 `max(MIN_NEGATIVE_TTL, ttl)` 保证了 ≥30s，但该下限没有门禁：若改成 `now + ttl`，这 10 例仍全绿。属覆盖缺口，非违规、非放宽断言（health 侧 `:290-307` 已用 `clock.advance(31)` 锁住 30s）。
- **Fix**：补一例在检索侧 `clock.advance(29)` 仍命中缓存、`advance(31)` 后重新发请求的断言。

### [LOW] L-3 固定质量集在 Python 与 shell 两处逐字重复，缺一致性门禁

- **文件:行**：`backend/app/knowledge_base/infrastructure/retrieve.py:42-49` 与 `deploy/reranker/probe.sh:43-48`；校验逻辑 `:370-392` 与 `probe.sh:88-109`
- **Issue**：query/documents 常量与 index/isfinite/居首判定存在两份文本，当前逐字一致且判定等价，但无测试阻止未来单侧改动导致启动期探针与运行期 health 采用不同质量集。
- **不判 CRITICAL 的理由**：回归清单第 9 条列举的是下载/安全/导入/批任务/身份/embedding；此处是部署期 shell 脚本与运行期 Python 模块**跨执行边界**的同一常量（`deploy/reranker/start.sh` 在 venv/服务未就绪时运行，不能 import backend 包），且 `retrieve.py:40-41` 已注明同源意图。
- **Fix**：补一条读取 `probe.sh` 文本并与 `_RERANKER_HEALTH_PROBE` 逐项比对的测试，或抽为共享 JSON 资源由两侧加载。

---

## 四、专项风险判定（用户明确要求）

### 「掩盖真实故障」

- **主路径已消除**：`available=true` 现在必须同时通过 liveness 与三文档质量探针（`retrieve.py:320-353`），模型运行期损坏（`/health` 正常但排序异常）会报 `quality_probe_failed` 并写 30s 负缓存；端点级由 `tests/kb/test_kb_reranker_health_probe.py:410-423` 断言 `available=false` / `reranker=false`。health 端点与 `kb.rerank` 事件的矛盾信号不再存在。
- **残留（低概率，不阻塞）**：L-1 的兜底异常伪装；以及 `spec-014:134` 既有设计 —— `available=true` 正缓存 30s，30s 窗口内模型突然损坏不会即时反映（运行期验证是周期性而非实时）。后者不是任务 U 新增，也不改变 spec 契约。
- **结论**：**不存在足以维持 BLOCK 的「掩盖真实故障」**。

### 「打满线程池」

- **原 BLOCK 成因已消除**：任务 N 把 timeout / `invalid_*` / `unexpected` / 4xx 排除出负缓存，导致持续故障时每个 KB 问答都重跑推理并同步阻塞；任务 U 用 `reranker.py:169-171` 的全量 ≥30s 熔断替代，health 侧进一步用 single-flight（`retrieve.py:421-430`）把 N 次并发推理合并为 1 次，且 timeout 也写 4s 缓存（非零缓存）。README:79、plan-014:103 与此一致。
- **仍有残留（明确列出，不阻塞）**：**M-1**（检索侧首个 60s 并发窗口：缓存后写 + 无 single-flight，并发请求各自阻塞 60s）、**M-2**（health single-flight 无界等待 + httpx read timeout 非总时限，异常慢流后端下线程可无限占用）。两者都不是任务 U 引入的新违规 —— 60s 是 `spec-014:131` 契约上限、`config.py:91` 冻结值，single-flight 是 `:134` 要求。
- **结论**：**不得表述为「打满线程池风险已彻底消除」**；但该残留不足以维持 BLOCK，须作为后续工单与强制约束沉淀。

---

## 五、通过（附意见）— 强制约束清单

1. `docs/sdd/specs/014-kb-reranker.md` 保持零改动；今后若要调整 `available` 定义或熔断要求，必须走正式契约修订门禁，不得用 plan 追加节自述豁免（`spec-014:124`）。
2. `rerank_hits` 结尾 `_remember` 的无条件调用与 `max(MIN_NEGATIVE_TTL, ttl)` 下限不得再被 `cacheable` 式条件排除；新增任何失败分支必须同步补一例「第二次调用只发一次请求」的熔断门禁。
3. 两模块异常归类表保持一致（ConnectTimeout→connection；ReadError/RemoteProtocolError→connection）；改动任一处须同步另一处及 4 例归类测试。
4. `_health_probe` 必须保持「先 liveness GET、再质量 POST」，`_probe_scores` 的 index 1 严格居首判定不得放宽；固定三文档常量与 `deploy/reranker/probe.sh` 逐字一致（建议补一致性测试，见 L-3）。
5. `reranker.py:22` 的 60s/2s 硬上限与 `config.py:87-91` 冻结值不得上调；缩短 read cap 或引入 single-flight 须同步 spec/plan/README 与 27 例测试。
6. timeout 短缓存必须落在 3–5s 且非零、非 30s；30s 正/负缓存保留；`_health_inflight` 的清理必须留在 `finally`。
7. 针对 M-1/M-2 立后续工单：检索侧 single-flight 或乐观短负缓存；health 等待改为有界、并给 httpx 请求加总时限；补并发与慢速吐字节用例。
8. `tests/conftest.py` 的显式 opt-in + 目录级 conftest + `_drain_and_reset` 结构不得回退为全仓 autouse；seed 快照条件化、缺库可诊断、连接 `try/finally` 对称释放三项由 `test_seed_demo_snapshot_guard.py` 7 例守卫，不得删弱。
9. `deploy/start.sh` 两处失败分支的 stop.sh 告警不得回退为 `|| true`；`quality_probe_failed` 语义、README 第 5 节、plan-014 追加节随实现同步，plan 第 1–85 行历史原文继续保留。

---

## 六、验证原始输出

```
===== PYTEST CMD 1 =====
...........................                                              [100%]
=============================== warnings summary ===============================
.venv/lib/python3.11/site-packages/starlette/testclient.py:53
  /Users/wjh/work/ResearchAgent-2/ResearchAgent/.venv/lib/python3.11/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
27 passed, 1 warning in 6.76s
CMD1_EXIT=0
===== PYTEST CMD 2 =====
.............                                                            [100%]
13 passed in 8.57s
CMD2_EXIT=0
===== 补充回归 =====
20 passed, 25 subtests passed in 3.05s
SUP_EXIT=0
===== RUFF CURRENT WORKTREE (13 个后端相关改动/新增 py 文件) =====
Found 15 errors.  [1 fixable]
  全部位于 backend/app/memory/repository.py 既有行：:24 F401 / :274,:278 SIM118×10 / :348 SIM102 / :1753,:1797,:1805 F811×3
RUFF_CURRENT_EXIT=1
===== RUFF efec3c06 BASELINE (git show 同文件 | ruff --stdin-filename 同路径 -) =====
Found 15 errors. 规则与行号逐条一致
RUFF_BASE_EXIT=1
=> lint 零新增
===== plan-014 / deploy/start.sh numstat =====
32  0  docs/sdd/plans/014/task-06-reranker-health-status.md   (纯追加，1-85 行原文保留)
20  3  deploy/start.sh                                          (3 行删除即旧 || true 两处及关联行)
===== spec 目录 =====
git diff efec3c06 -- docs/sdd/specs/ : (空)
git diff --exit-code efec3c06 -- docs/sdd/specs/014-kb-reranker.md : SPEC_UNCHANGED_EXIT=0
```

---

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 2     | info   |
| LOW      | 3     | note   |

**Verdict: APPROVE（附意见）— 原 BLOCK 的 1 CRITICAL / 2 HIGH / 3 MEDIUM / 2 LOW 均有修复与测试证据，`BLOCK 已解除`。2 项 MEDIUM 为残留风险（非违规，须立后续工单）、3 项 LOW 为测试覆盖/一致性缺口；按第五节强制约束清单收口。**

- **报告路径**：docs/sdd/reviews/20261110-lingering-fixes-backend-recheck.md（新增，不覆盖历史报告）
- **原报告（保留）**：docs/sdd/reviews/20261110-lingering-fixes-backend-review.md
- **进展日志**：.codebuddy/agent-logs/spec-014/task-00/backend-reviewer/20261110-044956.md
- **只读声明**：本次复验除新增上述报告与日志外，未修改任何业务代码、测试、spec、数据；未执行任何 git 写操作。

