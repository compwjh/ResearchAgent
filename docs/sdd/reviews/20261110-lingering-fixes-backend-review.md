# 2026-11-10 遗留项修复批次 — 后端 / 部署 / 测试只读评审

- **评审角色**：`backend-reviewer`
- **基线**：`efec3c06`；改动取自工作区 `git status` / `git diff HEAD`（staged 为空）
- **评审范围**：`backend/**`、`deploy/**`、`scripts/**`、`tests/` 下后端用例，以及作为契约数据的 `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` 与 spec-014 / plan-014 / VERIFICATION 文档
- **边界**：`frontend/**` 与 `tests/frontend/**` 改动交 `frontend-reviewer`，不越界评审；`tests/e2e/test_research_lifecycle_e2e.py` 属前端 Playwright 流程断言调整，按边界不深入评审（仅记录其存在）。
- **只读声明**：除新增本评审报告与强制要求的进展日志外，**未修改任何业务代码、测试、spec、数据**；未执行任何 git 写操作（无 push / merge / reset / stash / clean / add / commit）。验证命令产生的 `.pytest_cache`、`__pycache__` 为标准测试产物，非源文件改动。
- **进展日志**：`.codebuddy/agent-logs/spec-regression/task-00/backend-reviewer/20261110-035345.md`
- **验证方式**：
  - `./.venv/bin/python -m pytest -q` 运行本批次 6 个相关测试文件 → **30 passed**（8.79s）。
  - `./.venv/bin/ruff check`（项目 `ruff.toml`）：改动文件共 15 errors，全部位于 `backend/app/memory/repository.py` 的既有行；对 `efec3c06` 基线同文件同配置复跑同为 **15 errors** → **lint 零新增**。
  - 冻结清单 digest 用 `.venv/bin/python` 按测试同款算法实算 → 与 JSON 新值逐字一致。
  - 全量 `./.venv/bin/python -m pytest tests/ -q` 因工具命令时限未取到最终汇总（后台日志 `/tmp/ra-pytest-full-20261110.log`）；批次摘要声明「三种顺序回归 544 passed」，本报告不据此下负向结论，全部判定以逐文件代码事实为准。

## 结论：**需修改（Block）**

存在 1 项 CRITICAL：任务 N 实质性违反 `docs/sdd/specs/014-kb-reranker.md` 未修订的强制约束（`available` 字段定义与「至少缓存负状态 30 秒」的熔断要求），并伴随 `rerank_hits` 60 秒无熔断的可用性回归。另有 2 项 HIGH、3 项 MEDIUM、2 项 LOW。修复方向见文末「阻塞项与强制约束清单」。

---

## 一、评审要点逐条结论

### 要点 1 — N 的语义变更风险（最高优先）

**结论：VERIFICATION.md:73 未违反；spec-014 被违反；会掩盖真实故障；会打满后端；6s cap 只对心跳合理。**

- `available=true` 现仅表示 `GET /health` 返回 2xx 且响应能解析为 JSON 对象（`backend/app/knowledge_base/infrastructure/retrieve.py:298-314`），不再跑 `/v1/rerank` 三文档质量推理（旧的 `_probe_scores()` 及其 `math.isfinite` 校验已整段删除）。质量校验改由启动时 `deploy/reranker/start.sh:85-87` 调 `deploy/reranker/probe.sh` 完成（`probe.sh:37-111` 的三文档探针真实存在）。
- **会掩盖真实故障**：若 llama-server 进程存活但模型在运行中损坏（`/health` 正常、`/v1/rerank` 返回垃圾排序或超时），`/api/kb/health` 仍返回 `reranker=true, available=true, reason=null`（`backend/app/api/routes_kb.py:134-135`）。运维按 `deploy/reranker/README.md:8`、`:57`、`:86` 与 `docs/sdd/plans/014/task-06-reranker-health-status.md:111` 的「拿到 available=true 才算精排已启用」判定，会误判为精排健康。
- **`deploy/VERIFICATION.md:73` 未违反**：原文只约束「Reranker 被禁用时只能记录为 RRF 降级，不能伪称已启用精排」。`retrieve.py:345-346` 在 `enabled=false` 时直接返回 `available=false, reason="disabled"` 且零网络请求，未伪称启用。
- **spec-014 主文档被违反**（关键，且该文档第 124 行声明「以下约束漏做即不得进入下一门禁」）：
  - `docs/sdd/specs/014-kb-reranker.md:72`：`available` = 「HTTP 与**排序质量探针**是否通过」；
  - `:102`：「质量探针使用至少 3 条相关度明显不同的文档；若分数完全相同或最相关文档未排第一，服务判为不可用」；
  - `:131`：「**Fail-open 与熔断**：当前问答不重试；连接/读取超时上限 2 秒/60 秒。**不可达或质量探针失败后至少缓存负状态 30 秒，避免每个问答重复等待**」；
  - `:149`（A7）：health 能区分禁用、不可达、**质量探针失败**和可用；
  - `:134`：「30 秒内并发请求只触发一次探针，`reranker == enabled && available`」——此项仍成立（single-flight 保留）。
  - `docs/sdd/plans/014/task-06-reranker-health-status.md:87-113` 以「追加记录 / 按新语义理解，不改写原文」的方式自述豁免，**spec 主文档的字段定义与熔断约束并未修订**，属于自述式偏离而非契约变更。
- **fail-open 与 `kb.rerank` 事件仍可诊断**：`retrieve.py:439-457` 的 `_record_rerank_result()` / `_record_rerank_event()` 把 `rerank_result.reason` 原样写入 `metadata["degraded_reason"]`，`reranker.py:14-17` 的 `RerankReason` Literal 未变（新增 `cacheable` 只是内部布尔，见 `:127`）。故运行时真实故障在事件里可诊断，**但 health 端点与观测事件会给出互相矛盾的信号**（health 说 available=true，事件说 degraded）。
- **慢响应不进负缓存会导致持续故障下反复探测打满后端**：见 CRITICAL-1。`rerank_hits` 沿用 `RERANKER_READ_TIMEOUT_SECONDS=60.0`（`backend/app/platform/config.py:90-91`），且 `reranker.py:128-129` 的 `httpx.Timeout` **没有任何 cap**（6s cap 只加在心跳 `_health_probe`，`retrieve.py:290-292`）。timeout 不再写 30s 负缓存 → reranker 端口在监听但 hang 时，**每个 KB 问答同步阻塞最长 60 秒且无 30s 熔断去重**，FastAPI 默认线程池会被打满，影响面超出 KB 检索。这正是 `spec-014:131` 要求熔断要避免的场景。
- **6s cap 是否合理**：对**心跳**合理——本机实测 1.5–2.3s 正常慢响应，旧实现把 read timeout 统一钳到 2.0s 是假降级根因；`_RERANKER_HEALTH_CONNECT_TIMEOUT_CAP=2.0` / `READ_TIMEOUT_CAP=6.0`（`retrieve.py:41-42`）留有余量且有上限，`test_health_response_beyond_cap_is_still_timeout` 用 7.0s 验证了上限仍生效。但它**不覆盖实际检索路径**，不足以缓解上述 60s 风险。

### 要点 2 — 负缓存策略

**结论：有遗漏的真实失败被误判为「立即重试」；ConnectTimeout 映射为 timeout 后不缓存的副作用确实存在；两模块异常归类不一致。**

- 当前策略：`retrieve.py:369-373` 仅在 `available` 或 `reason ∈ {connection, model_not_prepared}` 时写 30s 缓存，否则 `pop`；`reranker.py:158-162` 仅在 `cacheable`（`>=500` 或 `ConnectError`）时 `_remember`，否则 `pop`。
- **遗漏**：`reranker.py` 中 `invalid_json` / `invalid_schema` / `invalid_index` / `invalid_score`（模型输出损坏，属**确定性/持续性**故障）、`unexpected`（`:155-156` 的兜底，含 `httpx.ReadError`、`RemoteProtocolError`、`ProxyError` 等真实故障）、4xx（`:137` 只在 `>=500` 设 `cacheable`）全部改为立即重试。基线是「所有失败无条件 `_remember` 30s」。这既违反 `spec-014:131`，也让模型持续损坏时每次检索都要付一次推理往返。
- **`ConnectTimeout` 副作用存在**：`httpx.ConnectTimeout` 是 `TimeoutException` 子类，被 `retrieve.py:315` 与 `reranker.py:151` 的 `except httpx.TimeoutException` 先捕获 → `reason="timeout"` → 不缓存。当 reranker 不可达但网络表现为 SYN 黑洞 / 防火墙 DROP（连接超时）而非 ECONNREFUSED（`ConnectError` → 缓存）时，无 30s 熔断，每次请求重新等待连接超时。
- **归类不一致**：`retrieve.py:319-320` 把 `httpx.HTTPError`（含 `ReadError` / `RemoteProtocolError`）归为 `connection`（可缓存）；`reranker.py:155-156` 把同一类异常归为 `unexpected`（不缓存）。同一后端故障在 health 与检索两条链路上得到相反的缓存决策。
- 正面：`503` 在心跳映射为 `model_not_prepared`（`retrieve.py:301-302`）、其他 5xx 映射为 `connection`（`:303-304`），在检索路径 `>=500` 可缓存（`:137`），语义基本自洽；成功路径 `reranker.py:147-150` 会清掉负缓存，`else` 分支 `pop` 残留条目，设计一致；`30s` 正缓存与 single-flight 保留（`retrieve.py:352-376`）。

### 要点 3 — S 的 `tests/conftest.py`

**结论：影响面偏大；同进程竞态窗口真实存在（低概率）；未掩盖产品缺陷，但产品侧另有既有缺陷。**

- 根级 `tests/conftest.py:23-30` 是 function 级 `autouse` fixture，**作用于全仓所有测试**（含 `tests/frontend/**` 的 Python 契约用例、`tests/e2e/**` 的 Playwright 用例），每个用例前后都 `from backend.app.platform.warmup import reset_warmup`，连带导入 `backend.app.knowledge_base.application` / `embed` / `ollama`（`warmup.py:35-42`）。`tests/e2e/conftest.py` 另有 session 级 `browser` fixture，二者叠加无冲突，但作用面超出「消除一个跨模块顺序依赖」所需。放置理由写在 `conftest.py:14-17`（污染源在 `tests/system`、受害者在 `tests/kb`，需根目录覆盖），逻辑成立但可用两个子目录 conftest 达到同样效果。
- **竞态**：`warmup.py:120-122` 的 `reset_warmup()` docstring 明确「不中断正在跑的线程」；`:204-213` 的 `start_warmup()` 起 daemon `_runner` 线程，`:191-201` 中重量项用 `join(timeout=...)` 限时、超时后线程仍在后台跑完。若上一用例的 `_runner` 尚未收敛就执行 fixture 的 `reset_warmup()`，残留线程会继续 `_registry.mark_done(...)`（`warmup.py:159`）把 `failed` 写回，污染下一用例 → **同进程竞态窗口真实存在**。`_WarmupRegistry` 全部方法用 `Lock`（`:64`、`:102-105`），故无数据竞争，但存在「重置被在飞线程覆盖」的逻辑竞态。当前 `tests/system/test_startup_warmup.py` 多数用例把 `_warm_*` monkeypatch 成立即抛错，`_runner` 很快结束，故未触发（30 passed / 摘要 544 passed 可佐证），但窗口不因当前通过而消失。并行（xdist）多进程各自独立内存，无跨进程问题。
- **是否掩盖产品缺陷**：污染源头是测试调用 `start_warmup()` 后不清理（`test_startup_warmup.py` 各用例自己已调 `reset_warmup()`），属**测试隔离问题**，不是产品缺陷，用 fixture 重置不算掩盖。但产品侧 `backend/app/api/routes_kb.py:165-177` 的 `_probe_embedding_ready()` 在注册表 `failed` 时**直接短路返回 False、不做任何重试**，生产里 embedding 首次预热失败会永久显示不可用直到重启——这是既有产品缺陷，本次未触及也不应要求本批次修复；把「全局状态干净」变成隐式测试约定，客观上降低了它被暴露的概率。

### 要点 4 — S 的冻结清单刷新

**结论：通过。依据充分、算法同款、逐字实算一致、未放宽任何断言。**

- 先例充分：`git show --stat 402b5ece` = `docs(sdd): 同步 upload-closure-matrix 冻结清单哈希`，同一文件 `2 insertions(+), 2 deletions(-)`，与本次改动形态完全一致。
- `docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json` 的 diff 只改 2 行值（`inventory_digest` 与 `routes_kb.py` 的 `sha256`），`entries` / `tests` / `closed_enums` / `review_status` 与所有断言一字未动。
- 实算：`shasum -a 256 backend/app/api/routes_kb.py` = `1d5b8122473fd17833efa8a094d2b8de1d229a26c3b62e4a5e231c862963cb65`，与 JSON 新值逐字一致；用 `.venv/bin/python` 按 `tests/kb/test_kb_upload_closure_matrix.py:85-88` 的同款算法（`f"{digest}  {path}"` 按 digest 排序、末尾补 `\n`、整体 sha256）重算得 `7327a7d062f5563b5efef8b9b8b7c6067a3384ba7bd2f5a803954f2e7b54fa90`，与 `inventory_digest` 新值逐字一致，且 8 个 `inventory_files` 的 sha256 全部与磁盘真实字节匹配。
- **测试非恒真**：`test_kb_upload_closure_matrix.py:80-84` 用 `hashlib.sha256(path.read_bytes())` 从**磁盘真实文件**重算并逐项断言，`:85-88` 的 digest 也基于 `actual_hashes`（真实哈希）而非 JSON 自填值；刷新值不能让测试自证通过。另有 `:89-96` 的 AST 符号登记、`:97-118` 的 retired-writes 静态扫描，均为强断言。
- `docs/**` 作为契约数据（用户要点 4 明确授权）核对，非越界评审前端；`tests/system/test_legacy_kb_integration.py` 虽在 system 目录，但属后端集成用例，路径偏差可接受。

### 要点 5 — L 的 `clean()`

**结论：删除语义安全、非原子性如实声明、幂等有效、无误删真实数据风险；条件与资源释放有 MEDIUM 意见。**

- **非严格原子如实声明**：`scripts/seed_demo_research_reports.py:316-320` 的 docstring 明确写「WAL 模式下 SQLite 对 ATTACH 的多个库**不保证原子提交**（各库分别提交），所以这里不是严格原子，中途失败仍可能出现『research 已删、memory 未删』」，并说明兜底是 `snapshot_databases()` 一致性快照 + `--clean` 幂等重跑。与 SQLite 官方语义一致，未夸大。
- **事务结构**：`:322-349` 用单个 `sqlite3.connect(_db_path(store))`，`ATTACH DATABASE ? AS memory`（`:324`，参数化绑定，符合「禁止 f-string 拼接 SQL」），`BEGIN IMMEDIATE`（`:325`），5 张表按 `task_id` 精确 DELETE（`:334-338`），`memory.conversations` 按 `seed-demo-%` 前缀删除（`:339-342`），`commit` / `rollback` / `close` 齐备。`tests/research/test_seed_demo_research_reports_clean.py:167-196` 用 `set_trace_callback` 断言单连接、单 `BEGIN`…`COMMIT`、≥6 条 DELETE 全在事务内，测试诚实。
- **`--clean` 入口保留**：`main():427-441` 中 `removed = clean(store)`、`print(...)`、`if args.clean: return`、`generate(store)` 均为 diff 的**上下文行（基线既有）**；本次仅在 `clean` 前插入快照调用（`:433-436`）。即脚本基线本来就是「先清旧 demo 再重新生成」、`--clean` 控制「清完即退出不再生成」，本次未改变该语义，摘要中「严格保留 `--clean` 入口」属实。
- **无误删真实数据风险**：前缀常量 `SEED_CONVERSATION_PREFIX="seed-demo-"` 不含 LIKE 通配符；`tests/...:130-164` 用 2 个 seed + 2 个真实 + `seed-demoX` / `xseed-demo-almost` 近似前缀 + 大写前缀验证只删目标行；`:199-207` 与 `:268-298` 验证幂等重跑返回 0 且计数不变。注意 `memory.conversations` 的 DELETE 在 `for` 循环**之外**（`:339-342`），故「research 已删 / memory 未删」的半提交状态重跑能补齐 → 幂等兜底真实有效。
- **快照正确性**：`snapshot_databases():279-305` 用 `sqlite3.Connection.backup()`（Online Backup API）产出含 WAL 已提交内容的自包含单文件；`:210-265` 用真实 WAL 场景（`wal_autocheckpoint=0`）做「单文件 cp 漏行 / backup 含行」对照，断言具体行数，测试诚实。`.gitignore:51` 已忽略 `data/backup/`，不会污染 git；时间戳用 `datetime.now(timezone.utc)`（`:434`），符合 UTC 约束。
- 问题见 MEDIUM-6（无条件快照、源库缺失硬失败、`dst` 连接释放不对称）。

### 要点 6 — M 的降级

**结论：通过。成功路径与用户显式禁用路径均不受影响；stop.sh 本体安全；4 例契约无恒真断言。**

- `deploy/start.sh:51-81`：仅当 `RERANKER_ENABLED=true` 才进入 reranker 块；成功且 runtime URL 合法时只 `export RERANKER_BASE_URL`、保持 `RERANKER_ENABLED=true`（`:63-65`）；子脚本成功但 URL 无效（`:66-71`）与子脚本失败（`:72-78`）两分支才 `export RERANKER_ENABLED=false`。用户显式 `RERANKER_ENABLED=false` 走 `:79-81` 的 else，不进入块、不改写，行为不变。
- `export` 只作用于脚本及其子进程（`:113` / `:136` 启动的 uvicorn），不影响父 shell；`RERANKER_STARTED` 仍为 false，前台 `cleanup()`（`:118-132`）不会误停；失败分支已显式调 stop.sh。
- `deploy/reranker/stop.sh:10-39`：校验 PID 文件存在、PID 纯数字、`ps` 命令行同时含 `MODEL_PATH` 与 `--reranking` 才允许终止（`:22-25`），先 `kill -INT` 轮询、再 `kill -TERM` 轮询、不发 `KILL`（`:27-37`），陈旧 PID 自动清理（`:18-21`）。符合 `spec-014:133`「只终止 PID 与启动标识均匹配的本项目进程」。`start.sh:70` / `:77` 用 `[ -x ... ] && "$RERANKER_STOP" || true` 保护，`set -euo pipefail` 下不会中断启动。
- `tests/system/test_deploy_start_reranker_degradation.py` 4 例：临时部署骨架 + stub uvicorn 打印 `UVICORN_ENV RERANKER_ENABLED=...`，分别断言子脚本失败（`:80-88`）、显式禁用（`:91-98`）、成功保持 enabled（`:101-118`）、无效 URL（`:121-133`）；断言含 `marker.exists()` / `not marker.exists()`、`=false` 在 stdout 且 `=true` 不在，非恒真、无静默失效。
- 遗留：4 例均未断言失败分支调用了 stop.sh 清理；`|| true` 会吞掉 stop.sh 的退出码（见 LOW-7）。

### 要点 7 — 代码质量 / 分层 / lint / 命名 / 测试诚实性

**结论：lint 零新增、分层未破坏、无 SQL 拼接、UTC、无重复实现、测试诚实；唯一顾虑是测试把违规行为锁成门禁。**

- **lint 零新增实证**：`./.venv/bin/ruff check`（`ruff.toml`）对本批次全部改动/新增文件报 15 errors，全部位于 `backend/app/memory/repository.py:24(F401)/274,278(SIM118×10)/348(SIM102)/1753,1797,1805(F811×3)`；该文件本次仅改 `:656` 一行 SQL 字符串，不触及任何报错行。对 `git show efec3c06:backend/app/memory/repository.py` 用同配置复跑同为 **15 errors**（末条同为 `:1805 F811`）。`retrieve.py` / `reranker.py` / `seed_demo_research_reports.py` / `tests/conftest.py` / 4 个新测试 / `test_legacy_kb_integration.py` 全部 0 error。
- **分层**：改动集中在 `backend/app/knowledge_base/infrastructure/`、`memory/repository.py`（store 层）、`deploy/`、`scripts/`，无 `domain/` 反向依赖 FastAPI/HTTP/环境变量；`retrieve.py` 仍只经 `reranker.py` 复用既有批量客户端，未出现第二套实现。
- **SQL / 时间 / 调试语句**：`ATTACH DATABASE ? AS memory` 参数化；`LIKE ?` 参数化；备份目录时间戳用 `timezone.utc`；无新增 `print` 调试语句（seed 脚本的 `print` 是既有 CLI 输出）；`cacheable` 命名清晰，`_RERANKER_HEALTH_CACHEABLE_REASONS` 用 `frozenset` 不可变，符合编码标准。
- **测试诚实性**：`tests/kb/test_kb_reranker_health_probe.py` 12 例（8 + 4）用进程内 `httpx.BaseTransport` fake 记录真实 `calls`、用 `request.extensions["timeout"]["read"]` 模拟真实读超时、用 `_FakeClock` 推进 TTL；`test_slow_but_successful_rerank_is_available_and_no_negative_cache:141-151` 断言 `fake.calls == [("GET","/health")]` 真实锁住「心跳不再跑推理」。5 / 2 / 4 例同为非恒真（具体行号集合、trace、WAL 对照、stub 环境变量）。RED→GREEN 逻辑可由「旧实现 read cap 2.0s + 必跑 /v1/rerank + 所有失败写负缓存」与这 12 例断言逐一对照复现，无伪造空间。
- **顾虑**：`test_timeout_from_slow_response_does_not_enter_negative_cache:258-276` 与 `test_timeout_is_transient_and_does_not_write_negative_cache:168-179` 把「timeout 完全不缓存」锁成 GREEN 门禁，而该行为正是 CRITICAL-1 的违规点；修复实现时这些用例必须同步重写（见 MEDIUM-5）。

---

## 二、问题清单（按严重度）

### [CRITICAL] N 违反 spec-014 强制约束，且移除熔断造成 60s 无上限的可用性回归

- **文件:行**：
  - `backend/app/knowledge_base/infrastructure/retrieve.py:283-324`（心跳改为只判 liveness）、`:369-373`（负缓存收窄）
  - `backend/app/knowledge_base/infrastructure/reranker.py:127-163`（`cacheable` 仅 `>=500` / `ConnectError`）
  - `backend/app/platform/config.py:90-91`（`RERANKER_READ_TIMEOUT_SECONDS=60.0`）
  - `docs/sdd/specs/014-kb-reranker.md:72`、`:102`、`:124`、`:131`、`:149`
  - `docs/sdd/plans/014/task-06-reranker-health-status.md:87-113`（追加节自述豁免）
  - `deploy/reranker/README.md:8`、`:57`、`:86`（仍把 `available=true` 当精排启用证据）
  - `tests/kb/test_kb_reranker_health_probe.py:258-276`（把违规行为锁成门禁）
- **Issue**：
  1. `available` 语义从「HTTP 与排序质量探针是否通过」降为「`/health` 可达」，而 `spec-014:72` 的字段定义、`:102` 的质量探针要求、`:149` 的 A7 验收项**均未修订**；`:124` 明文规定「以下约束漏做即不得进入下一门禁」。仅以 plan 追加节「按新语义理解，不改写原文」自述豁免，不构成契约变更。
  2. `spec-014:131` 要求「不可达或质量探针失败后**至少缓存负状态 30 秒，避免每个问答重复等待**」。基线 `rerank_hits` 对所有失败无条件 `_remember`；现在 `timeout` / `invalid_*` / `unexpected` / 4xx 全部不缓存，熔断被移除。
  3. 叠加 `config.py:91` 的 `read_timeout=60.0` 与 `reranker.py:128-129` 无 cap：reranker 端口存活但 hang 时，每次 `hybrid_search`（`retrieve.py:209-217`）同步阻塞最长 60s，且无 30s 负缓存去重 → FastAPI 线程池被打满，**影响面超出 KB 检索、可致全站不可用**。这正是 `:131` 要防的场景。
  4. health 端点（`routes_kb.py:134-135`）在模型质量损坏时仍报 `available=true`，而 `kb.rerank` 事件如实记 `degraded_reason`（`retrieve.py:439-457`）——两者矛盾，运维按 README 判定会误判为精排健康。
- **Fix**：见文末「阻塞项与强制约束清单」第 1–5 条。

### [HIGH] `ConnectTimeout` 归为 `timeout` 后不缓存，连接半死故障无熔断

- **文件:行**：`backend/app/knowledge_base/infrastructure/retrieve.py:315-320`、`backend/app/knowledge_base/infrastructure/reranker.py:151-156`
- **Issue**：`httpx.ConnectTimeout` 是 `TimeoutException` 子类，被 `except httpx.TimeoutException` 先捕获 → `reason="timeout"` → 不写负缓存。当 reranker 不可达但表现为 SYN 黑洞 / 防火墙 DROP（连接超时）而非 ECONNREFUSED（`ConnectError` → 缓存）时，每次心跳、每次检索都重新等待连接超时，无 30s 熔断。这是要点 2 明确询问的副作用，确实存在。
- **Fix**：单独捕获 `httpx.ConnectTimeout` 并归入 `connection`（可缓存）；仅 `ReadTimeout` / `WriteTimeout` / `PoolTimeout` 视为瞬态；或对所有 `TimeoutException` 使用短 TTL（如 2–5s）负缓存而非完全不缓存。

### [HIGH] `rerank_hits` 把持续性故障（`invalid_*` / `unexpected` / 4xx）误判为「立即重试」

- **文件:行**：`backend/app/knowledge_base/infrastructure/reranker.py:136-162`
- **Issue**：`invalid_json` / `invalid_schema` / `invalid_index` / `invalid_score` 表示模型输出持续损坏（确定性故障），`unexpected` 兜底覆盖 `ReadError` / `RemoteProtocolError` / `ProxyError` 等真实失败，4xx 也非瞬态；现在全部 `cacheable=False` → 每次检索重发请求并承担一次推理成本。原基线全部缓存 30s。既违反 `spec-014:131`，也与 `retrieve.py:319-320` 把同类 `httpx.HTTPError` 归为 `connection`（缓存）的决策互相矛盾。
- **Fix**：按「瞬态 vs 持续」而非「timeout vs 非 timeout」分类：仅 `ReadTimeout` 等少数瞬态用短 TTL / 立即重试；`invalid_*`、`unexpected`、`>=500`、`ConnectError`、`ConnectTimeout` 保持 ≥30s 负缓存，并统一两模块的异常归类。

### [MEDIUM] 根级 `tests/conftest.py` 作用面过大、与在飞 warmup 线程存在竞态窗口

- **文件:行**：`tests/conftest.py:23-30`、`backend/app/platform/warmup.py:120-122`、`:191-213`、`backend/app/api/routes_kb.py:165-177`
- **Issue**：function 级 autouse 作用于全仓（含 `tests/frontend/**`、`tests/e2e/**`），每用例前后导入整条 backend 依赖链；`reset_warmup()` 明确「不中断正在跑的线程」，而 `start_warmup()` 起 daemon `_runner`，上一用例的 `_runner` 未收敛即 reset 会被残留 `mark_done` 重新污染（逻辑竞态窗口真实存在，当前因多数用例 monkeypatch 预热项而未触发）。产品侧 `_probe_embedding_ready()` 在 `failed` 时短路、无自愈，是既有缺陷；全局 reset 会让「全局状态干净」成为隐式约定，降低其暴露概率。
- **Fix**：把 fixture 收窄到 `tests/system/conftest.py` + `tests/kb/conftest.py`（或在 `test_startup_warmup.py` 内加 teardown 并等待在飞线程收敛）；产品侧另立工单为 `failed` 短路加自愈/重试，不由测试 fixture 兜底。

### [MEDIUM] N 的测试门禁锁定违规行为，且边界覆盖有缺口

- **文件:行**：`tests/kb/test_kb_reranker_health_probe.py:168-179`、`:258-276`
- **Issue**：两例把「timeout 完全不写负缓存」断言为期望行为（`len(calls)==2` / `_cached_details(fake)==[]`），与 `spec-014:131` 冲突；按 CRITICAL 修复后这些断言必然变红，需同步重写。12 例未覆盖 `ConnectTimeout` 归类、`invalid_*` / `unexpected` 的缓存决策、心跳 `503` → `model_not_prepared` 缓存、`ReadError` 归类一致性。
- **Fix**：修复实现时同步重写上述断言（改为「短 TTL / 有限退避」而非「零缓存」），并补齐上述 4 类边界用例。

### [MEDIUM] `snapshot_databases()` 无条件执行、源库缺失硬失败、连接释放不对称

- **文件:行**：`scripts/seed_demo_research_reports.py:279-305`、`:427-441`
- **Issue**：
  1. `snapshot_databases()` 在 `main():435` **无条件**调用，不带 `--clean` 的正常 seed 也会在 `data/backup/<UTC-微秒>/` 落两份完整 SQLite 快照且永不清理；`.gitignore:51` 已忽略故不污染 git，但会持续占用磁盘（目录已有历史 `20261109-cleanup`）。
  2. `:294-295` 源库缺失即 `raise FileNotFoundError` 并中止脚本；基线 `clean()` 的 `sqlite3.connect` 会自动创建空库，故全新 checkout / 缺 `data/memory/memory.sqlite3` 的环境首次运行 seed 现在会直接崩。
  3. `dst = sqlite3.connect(target)`（`:298`）位于 `try` 之外，若该连接抛错，`src`（`:297`）不会关闭 → 连接泄漏，违反回归清单第 10 条「acquire/release 同 `try/finally`」的资源释放精神。
  4. `target = directory / source.name`（`:296`）在两库同名时会静默互相覆盖；当前 research/memory 文件名不同，属通用性隐患。
- **Fix**：仅在真正执行清理（或 `--clean`）前做快照；缺库时按「跳过该库快照 / 建空库」处理而非硬失败；把两个 `connect` 都纳入 `try/finally`（或 `contextlib.closing`）并给快照加唯一前缀。

### [LOW] 失败分支 `stop.sh` 退出码被吞掉，且 4 例契约未覆盖清理动作

- **文件:行**：`deploy/start.sh:70`、`:77`、`deploy/reranker/stop.sh:22-25`、`tests/system/test_deploy_start_reranker_degradation.py:80-133`
- **Issue**：`[ -x "$RERANKER_STOP" ] && "$RERANKER_STOP" || true` 会吞掉 `stop.sh` 的非零退出码；若「runtime URL 无效」分支时服务其实已启动、而 `stop.sh` 因命令行双校验不通过 `exit 1`（`:24`），会留下孤立的 llama-server 且无任何告警。4 例契约均未断言失败分支调用了 stop.sh。
- **Fix**：改为 `if ! "$RERANKER_STOP"; then echo "警告：Reranker 清理失败…" >&2; fi`；补一条断言失败分支触发 stop.sh 的用例。

### [LOW] `quality_probe_failed` 命名与语义脱节、文档内部不一致

- **文件:行**：`backend/app/knowledge_base/infrastructure/retrieve.py:306`、`:311`、`:313`、`:322`、`:324`、`deploy/reranker/README.md:8`、`:57`、`:86`、`docs/sdd/plans/014/task-06-reranker-health-status.md:105`、`:111`
- **Issue**：心跳已不做质量推理，但 `/health` 非 2xx（非 5xx）、JSON 解析失败、非 dict 等「协议异常」仍返回 `quality_probe_failed`。为保持 `reason` 集合不变的契约妥协可接受，但名称会误导排障；README 与 plan 追加节仍把 `available=true` 表述为「精排已启用」，与「仅 liveness」的新语义矛盾。
- **Fix**：在 `_health_probe()` 注明该 reason 现表示「`/health` 协议异常」；统一 README / plan / VERIFICATION 中关于 `available` 的验收表述（与 CRITICAL 修复一并处理）。

---

## 三、值得肯定的点

1. **L 的快照设计诚实且可验证**：`snapshot_databases()` 用 SQLite Online Backup API 替代单文件 cp，并在 `tests/research/test_seed_demo_research_reports_clean.py:210-265` 用真实 WAL（`wal_autocheckpoint=0`）构造「cp 漏行 / backup 含行」对照，断言具体行数与路径，而非只断言「文件存在」。
2. **跨库非原子性如实声明**：`seed_demo_research_reports.py:316-320` 明确写出 WAL + ATTACH 不保证严格原子、中途失败可能半提交，并说明兜底；没有把「单事务」夸大成「跨库原子」。且 `memory.conversations` 的 DELETE 放在循环外，使幂等重跑能补齐半提交残留——该兜底经 `:268-298` 真实验证有效。
3. **M 精准定位了配置落差**：`config.py:78` 的 `RERANKER_ENABLED` 默认 `True` 与「子脚本失败」之间的落差是真实的（否则每次检索连默认端口并写负缓存）；两处 `export RERANKER_ENABLED=false` 干净降级，且成功路径、用户显式禁用路径均未被改动，4 例 stub 契约覆盖完整。
4. **N 对假降级根因的定位准确**：旧实现 `connect/read` 统一钳到 2.0s、每次心跳跑三文档完整推理、`timeout` 写 30s 负缓存，确实会把本机 2.23s 正常慢响应误判为全局降级；`GET /health` + 6s 上限 + 30s 正缓存 + single-flight + `reason` 集合与响应结构不变，方向正确（问题只在于把同一策略过度套用到 `rerank_hits` 且未修订 spec）。
5. **S 的冻结清单刷新有据可查**：`402b5ece` 同款先例、实算 digest 与测试同款算法逐字一致、只改 2 行值、未放宽任何断言；`test_legacy_kb_integration.py:209` 的 `flush` → `enqueue_flush` 经 `routes_kb.py:58/1097/1113` 核实为修复真实 `AttributeError` 红灯。
6. **文档透明度高**：`docs/sdd/plans/014/task-06-reranker-health-status.md:87-89` 明确标注「上方为历史决策原文，保留不改」，`deploy/reranker/README.md` 第 4/5 节给出完整运维验收旅程与外部资产恢复步骤（含 SHA256 与字节数），便于复核。
7. **工程卫生**：`ruff` 零新增（基线等价对比实证）、`ATTACH ?` 参数化、UTC 时间戳、无新增调试 `print`、无第二套实现、测试断言非恒真。

---

## 四、阻塞项与强制约束清单（Block 修复方向）

> 以下为「需修改」的阻塞项；修复完成前不应合并。每条均为可核对的硬约束。

1. **契约必须二选一并留痕**：要么正式修订 `docs/sdd/specs/014-kb-reranker.md` 的 `:72`（`available` 定义）、`:102`（质量探针）、`:131`（熔断）、`:149`（A7）及 task-06 验收标准，经评审门禁承认「质量校验移到启动 `probe.sh`、心跳只判 liveness」；要么恢复实现以符合现有 spec。**不得仅靠 plan 追加节「按新语义理解」自述豁免**。
2. **恢复 `rerank_hits` 的熔断**：`timeout` 可以改为「短 TTL（2–5s）/ 有限退避」，但 `invalid_json` / `invalid_schema` / `invalid_index` / `invalid_score` / `unexpected` / `>=500` / `ConnectError` / `ConnectTimeout` 必须保留 ≥30s 负缓存，满足 `spec-014:131`「避免每个问答重复等待」。
3. **给检索路径的等待设上限**：`reranker.py:128-129` 的 `httpx.Timeout` 需加 read cap（或缩短 `RERANKER_READ_TIMEOUT_SECONDS` 默认值并同步契约），确保 reranker 持续 hang 时单次 KB 问答不会阻塞 60s、不会打满 FastAPI 线程池。
4. **统一异常归类**：`ConnectTimeout` 单独归入 `connection`（可缓存）；`ReadError` / `RemoteProtocolError` 在 `retrieve.py` 与 `reranker.py` 两处必须得到一致的缓存决策。
5. **消除 health 与观测的矛盾**：区分「可达」与「质量」，避免 `available=true` 掩盖模型质量故障；同步修订 `deploy/reranker/README.md:8/57/86` 与 plan-014 追加节中「available=true 才算精排已启用」的表述。
6. **测试随实现同步**：重写 `tests/kb/test_kb_reranker_health_probe.py:168-179`、`:258-276` 中锁定「零缓存」的断言，并补齐 `ConnectTimeout`、`invalid_*`、心跳 `503`、`ReadError` 四类边界用例；`tests/kb/test_kb_reranker_health_probe.py` 的 12 例不得用「放宽断言」方式变绿。
7. **MEDIUM 项建议同批处理**：`tests/conftest.py` 收窄作用面 / 处理在飞 warmup 线程；`snapshot_databases()` 改为仅清理前执行、缺库不硬失败、两连接纳入 `try/finally`；`stop.sh` 失败告警与清理用例。

---

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 1     | block  |
| HIGH     | 2     | warn   |
| MEDIUM   | 3     | info   |
| LOW      | 2     | note   |

**Verdict: BLOCK — 1 CRITICAL issue (spec-014 强制约束违反 + 60s 无熔断可用性回归) must be fixed before merge; 2 HIGH issues should be resolved together.**
