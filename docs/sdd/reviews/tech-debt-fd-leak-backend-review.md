# 后端评审报告 — FD 泄漏根因修复与启动软限制加固

- **评审角色**：backend-reviewer（独立复审，只读）
- **日期**：2026-11-05
- **工作区**：`/Users/wjh/ResearchAgent`，分支 `main`，HEAD `0c3f4831` + 未提交改动
- **解释器**：`.venv/bin/python`（Python 3.11.16）
- **范围**：仅 `backend/**`、`deploy/start.sh`、`tests/paper_discovery/**`、`tests/research/**`。前端改动（`frontend/app.js`、`frontend/index.html`、`tests/frontend/**`）**不在本报告范围**，交 `frontend-reviewer`。
- **进展日志**：`.codebuddy/agent-logs/spec-000/task-00/backend-reviewer/20261105-185141.md`
- **关联报告**：`docs/sdd/reviews/tech-debt-fd-leak-backend-regression.md`（backend-tester 回归，互补）

---

## 0. 结论

> **结论：通过（Approve，附 P1 强制约束）**
>
> **P0 阻塞：0 项**。核心根因修复方向正确、语义经实测等价、端到端 FD 零增长，可合入。
> **P1 阻塞：2 项**（不阻断本次根因修复合入，但须在下一批次内修复，见 §3）。

| 严重度 | 数量 | 状态 |
|---|---|---|
| P0 / CRITICAL | 0 | pass |
| P1 / HIGH | 2 | warn |
| P2 / MEDIUM | 3 | info |
| P3 / LOW | 2 | note |

---

## 1. 六项复审重点逐项结论

### 项 1：新 `_connect()` 事务语义是否等价 + 关闭连接；`except BaseException` 是否合适；连接建立失败时 `finally` 是否安全

**结论：通过（PASS）**

实现见 `paper_discovery_store.py:506-528`、`task_store.py:23-40`。两者同构：

```python
connection = sqlite3.connect(self.database_path)   # 在 try 之外
try:
    ...PRAGMA...
    try:
        yield connection
    except BaseException:
        connection.rollback(); raise
    else:
        connection.commit()
finally:
    connection.close()
```

逐点核对：

| 子项 | 判定 | 依据 |
|---|---|---|
| 与 `Connection.__exit__` 等价 | **是** | 实测：异常路径 rollback 后行数归零；正常路径 else 提交生效；`commit()` 之后再插入的新写入被 ctx `else: commit` 正确纳入（实测计数 = 2/2）。行为与 CPython `Connection.__exit__` 的 `if exc_type is None: commit() else: rollback()` 一致。 |
| 额外关闭连接 | **是** | 外层 `finally: connection.close()` 无条件执行，覆盖成功/异常/异常发生在 PRAGMA 阶段三条路径。 |
| `except BaseException` 是否合适 | **合适，优于 `except Exception`** | 需覆盖 `KeyboardInterrupt` / `SystemExit` / `asyncio.CancelledError`（后者在 3.8+ 继承 `BaseException`）导致的半开事务。若只捕 `Exception`，Ctrl-C 中断时会遗留未回滚事务 → 后续写入可能卡在锁上。回滚后 `raise` 原样透传，未吞异常。 |
| connect 失败时 `finally` 是否引用未定义变量 | **安全** | `sqlite3.connect(...)` 位于 `try` **之前**（`paper_discovery_store.py:514`、`task_store.py:30`），若它抛异常则 `try/finally` 尚未进入，`finally` 不会执行，不存在 `NameError: connection`。 |

> 说明：`Connection.close()` 本身会对未提交事务隐式回滚，因此即使 `else: commit()` 抛异常，`finally: close()` 仍保证不落脏数据（实测 E 场景确认）。

---

### 项 2：`__init__` 显式 `BEGIN` + `commit()` 与 ctx `commit()` 叠加；36 处调用点是否有误用

**结论：通过（PASS）**

**2a. 事务叠加无问题。** `__init__`（`paper_discovery_store.py:99-113`）在 ctx 内 `execute("BEGIN")`（L100）、显式 `connection.commit()`（L113），退出时 ctx `else` 分支再 `commit()` 一次。

实测四种组合均无异常，不存在 `sqlite3.OperationalError: cannot commit - no transaction is active`：

| 场景 | 结果 |
|---|---|
| A：显式 BEGIN + 显式 commit + ctx commit | OK（重复 commit 为空操作，SQLite 允许） |
| B：显式 BEGIN + 抛异常 | 异常原样透传，rollback 后 0 行 |
| C：显式 BEGIN + 无显式 commit | ctx `else: commit` 正常提交 |
| D：commit 后再 DML + ctx commit | 后续 DML 一并提交，无数据丢失 |

`commit()` 幂等是因为 `sqlite3` 默认 `isolation_level=""`（deferred），`commit()` 在无活动事务时为空操作。**结论：不构成双重提交风险，`__init__` 的 C-1「单事务迁移」语义保持不变**（`_migrate_to_v2/v3/v4` 仍在同一显式事务内，失败整体回滚）。

**2b. 36 处调用点无误用。** `grep '_connect()'` 命中 36 条，全部形如 `with self._connect() as connection:`，**无一例**把返回值当连接对象裸用（无 `connection = self._connect()` 后 `connection.execute(...)`，无把返回值 return 出去）。定义处 L507 与文档字符串 L508 除外。

`row_factory = sqlite3.Row`、三条 PRAGMA 均已移入 ctx 的 `try` 内（L516-519），每个连接仍正确初始化。

> 备注（非缺陷）：20+ 个调用点内部自带 `connection.execute("BEGIN")`，属既有显式事务风格；与新 ctx 组合经 §2a 实测验证兼容，无需改动。

---

### 项 3：`task_store.py` 3 处改动是否保持签名与提交语义

**结论：通过（PASS）**

| 检查点 | 结果 |
|---|---|
| `__init__(self, database_path: Optional[Path] = None)` | 签名未变（`task_store.py:13`），`AGENT_TASKS_DB` 环境变量覆盖逻辑未动（L15-16） |
| `save(self, task: ArticleTask) -> None` | 签名未变（L42），`ON CONFLICT(task_id) DO UPDATE` 语义未变（L46-47），参数化占位符 `?` 正确 |
| `get(self, task_id: str) -> Optional[ArticleTask]` | 签名未变（L51）；`fetchone()` 已物化结果集，`row` 在 with 外使用安全（L53-56），无「关闭后读游标」问题 |

3 处替换（L18 / L44 / L52）后，「退出即提交/回滚」语义与裸 `with sqlite3.connect()` 完全一致，额外获得 `close()`。

---

### 项 4：`deploy/start.sh` 降级行为与误改检查

**结论：降级路径通过（PASS）；但发现 **P1 回归风险**（无条件下调软限制），见 §3-P1-1**

| 检查点 | 结果 |
|---|---|
| `set -euo pipefail` 下降级是否真不中断 | **通过**。实测三场景（正常设 4096 / 非法值 `notanumber` / 超 hard `999999999`）均进入 `else` 告警分支，脚本后续语句正常执行，退出码 0。`if cmd; then` 结构本身豁免 `set -e`。 |
| 端口预检是否被误改 | 未改。仍在 `start.sh:37-43` |
| 单 worker（Qdrant 本地模式硬约束）是否被误改 | 未改。L86 与 L109 两条 uvicorn 命令**均无 `--workers`**，注释 L7-9 保留 |
| Reranker 启停是否被误改 | 未改。L45-75 原样，新增块插入在其**之后**（L77-82），不影响 `RERANKER_STARTED` 与 trap 清理逻辑 |
| `-d` 分支是否被误改 | 未改。L84-113 结构完整，PID 写入与 `cleanup` trap 逻辑未动 |
| hard limit 为 unlimited 时 `ulimit -n 4096` 是否可行 | **可行**。实测 hard=unlimited、`ulimit -n 4096` 成功 |
| 软限制原为 256（launchd 场景）是否能提升 | **能**。实测 256 → 4096 |

**P1 缺陷**：`ulimit -n "$RA_FD_SOFT_LIMIT"` 是**无条件赋值**而非「取最大值」。本机实测 `ulimit -Sn/-Hn = 1048575 / unlimited`，执行后软限制被**下调至 4096**（实测 before=1048575 → after=4096）。详见 §3。

---

### 项 5：新增测试是否能真正区分缺陷；命名是否合规

**结论：断言有效（PASS），但 RED 证据链有瑕疵（P2）**

**5a. 断言有效性——经两轮反向验证：**

| 验证方式 | 结果 |
|---|---|
| 正向：现实现跑测试 | `4 passed in 0.24s` |
| 反向①：运行时还原旧实现（`_connect` 返回裸 `sqlite3.Connection`） | `4 failed` —— 但失败原因是 `TypeError: '_RecordingConnection' object does not support the context manager protocol`（`task_store.py:18`），即**替身缺 `__enter__/__exit__` 引起的类型错误**，而非「连接未关闭」断言命中 |
| 反向②：用**语义等价的泄漏替身**（支持 `with`，`__exit__` 只 commit/rollback 不 close） | `4 failed`，全部精准失败在 `assert all(connection.is_closed ...)`，报错为 `2/2 个连接在正常退出后仍未关闭`、`4/4 个连接在退出后仍未关闭` |

**判定：断言确实能区分「连接未关闭」缺陷**，测试设计成立（monkeypatch `sqlite3.connect` 记录全部连接、覆盖正常与异常两条路径、含 `assert opened, "未观察到任何连接，补丁失效"` 防空转守卫）。

**5b. 证据链瑕疵（P2）**：backend-dev 报告的「修复前 RED 4 failed」实际成因是反向①的 `TypeError`（替身不支持上下文管理器），**不是**断言抓到泄漏。结论正确但证据口径不严谨，建议在报告中改述为反向②的结果。

**5c. 命名合规**：两个测试文件与 4 个用例**均按能力命名**，无 spec/task 编号：`test_store_closes_connection_after_successful_operation`、`test_store_closes_connection_when_operation_raises`、`test_task_store_closes_every_connection`、`test_task_store_closes_connection_when_operation_raises`。唯一命中的 `task-1`（`test_task_store_connection_release.py:54`）是业务数据 ID，非 spec 编号，合规。

**5d. 端到端佐证（本评审补充）**：200 次 `list_conferences()` 后 `state.sqlite3` 相关 FD 增量 = **0**（GC 前后均 0），修复端到端有效。

---

### 项 6：是否仍有同类未关闭模式

**结论：存在 1 处同类未修复（P1-2），2 处已正确；判为「本次范围外但必须跟进」**

| 文件 | `_connect()` 实现 | 判定 |
|---|---|---|
| `backend/app/platform/capability_store.py:44-50` | 返回裸 `sqlite3.Connection`，**从未 close**；L69、L97 用 `with _connect() as connection:` | **同类缺陷，未修复（P1-2）**。实测记录式替身：打开 10 次、显式 close **0 次**。因 CPython 引用计数立即回收，单进程压测看不到 FD 增长，但依赖 GC 而非确定性释放，与本次根因完全同型。调用方 `capability_scheduler.py:18` 探测间隔 24h，泄漏速率低，故定 P1 而非 P0。 |
| `backend/app/paper_discovery/infrastructure/paper_import_batch_store.py:145-178` | `_write_transaction()` 已有 `finally: connection.close()`（L177-178） | 已正确，无需改动 |
| `backend/app/research/infrastructure/research_store.py:1235-1260` | `@contextmanager` + `finally: connection.close()`（L1259-1260） | 已正确，无需改动 |
| `backend/app/literature_maps/infrastructure/store.py:80-90` | `connection()` + `finally: connection.close()` | 已正确，无需改动 |

**范围判断**：本次任务定义为「FD 泄漏根因修复」，`capability_store.py` 是**同一根因的第三个实例**，严格说属同类缺陷未收口。鉴于其泄漏速率低（24h 一次）、且不影响本次根因修复的完整性，**不阻塞本次合入**，但列为 P1 强制跟进项。

**值得注意的复发信号**：`research_store.py:1244-1249` 的文档字符串已记录 **spec-037 Bug 9 的同型事故**（「此前 89 个调用点…泄漏数万个文件句柄」）。同一缺陷已复发至少三次（research_store → paper_discovery_store → task_store → capability_store 仍未修），说明**缺乏跨 store 的统一连接工厂**。建议沉淀公共工具，见 §3-P2-1。

---

## 2. ECC 检查清单结果

| 类别 | 结果 |
|---|---|
| 安全（CRITICAL）：硬编码凭据 / SQL 注入 / XSS / 路径穿越 / CSRF / 鉴权绕过 / 依赖漏洞 / 日志泄密 | **全部通过**。所有 SQL 均用 `?` 参数化占位符；无 f-string 拼接 SQL；无硬编码密钥；无新增日志输出敏感数据 |
| 代码质量（HIGH）：大函数 / 大文件 / 深嵌套 / 缺错误处理 / 突变 / `print` 调试 / 缺测试 / 死代码 | **通过**。新增函数均 <20 行；嵌套 3 层（可接受）；异常处理完整；无 `print`；4 个新测试覆盖正常+异常路径 |
| React/Next.js 小节 | 不适用（本仓库后端为 Python/FastAPI） |
| Node.js/Backend：输入校验 / 限流 / 无界查询 / N+1 / 超时 / 错误泄漏 / CORS | **无回归**。本次改动未触碰端点、查询语义、外部 HTTP 调用 |
| 性能（MEDIUM） | **改善**。连接确定性释放，FD 峰值下降；`paper_discovery` 全套 `1006 passed in 60.87s` |
| 最佳实践（LOW） | 见 §4 |

**本项目专项**：
- SQLite 迁移：`__init__` 单事务语义**保持**（C-1 未破坏），迁移函数 `IF NOT EXISTS` 幂等未动。
- 外键 `RESTRICT`：未改动，`_migrate_to_v2` 注释 L184-185 明示不用 CASCADE。
- 禁止重复实现：**本次未引入第二套实现**；`task_store._connect()` 与 `paper_discovery_store._connect()` 属同构复制，见 §3-P2-1 的 DRY 建议。
- 分层边界：`domain/` 未被触碰，无 FastAPI / HTTP / 环境变量渗入 domain。
- 时间 UTC：未涉及时间逻辑改动。

---

## 3. 问题清单

### P1-1　`start.sh` 无条件下调 FD 软限制（回归风险）

- **文件**：`deploy/start.sh:78`
- **等级**：P1（HIGH）
- **事实**：
  ```bash
  if ulimit -n "$RA_FD_SOFT_LIMIT" 2>/dev/null; then
  ```
  `ulimit -n` 是**赋值**语义，不是「提升到至少」。实测本机 `ulimit -Sn = 1048575`，执行后降为 **4096**。
- **影响**：在软限制本已很高的环境（本机 1048575、部分 Linux 默认 65536）中，脚本会把可用 FD 上限**大幅下调**。虽然 4096 仍远高于修复后的实际需求，但这与「加固」意图相反，且属于隐蔽的能力回退——若未来单进程需 >4096 FD（并发下载、PDF 渲染、Playwright），会在无人察觉处触发 `Too many open files`。
- **修复方向**：先读现值，仅在现值更小时提升：
  ```bash
  current_fd_limit="$(ulimit -n 2>/dev/null || echo 0)"
  if [ "$current_fd_limit" -lt "$RA_FD_SOFT_LIMIT" ] 2>/dev/null; then
      if ulimit -n "$RA_FD_SOFT_LIMIT" 2>/dev/null; then
          echo "FD 软限制已提升：$current_fd_limit -> $(ulimit -n)"
      else
          echo "警告：FD 软限制保持 $current_fd_limit（无法提升到 $RA_FD_SOFT_LIMIT）。" >&2
      fi
  else
      echo "FD 软限制已足够（$current_fd_limit），无需调整。"
  fi
  ```
  注意 `[ -lt ]` 遇非数字会报错，需用 `2>/dev/null` 或先校验正整数。

### P1-2　`capability_store.py` 存在同类未关闭连接（同根因第三例）

- **文件**：`backend/app/platform/capability_store.py:44-50`（`_connect`）、`:69`、`:97`（调用点）
- **等级**：P1（HIGH）
- **事实**：`_connect()` 返回裸 `sqlite3.Connection`，两处 `with _connect() as connection:` 依赖 `Connection.__exit__`，**从不 close**。实测记录式替身：打开 10 次 / close 0 次。
- **影响**：与本次根因完全同型。当前探测间隔 24h（`capability_scheduler.py:18`），泄漏速率低，CPython 引用计数通常能兜住；但一旦 GC 延迟（循环引用、异常帧持有）或切换解释器实现，即开始累积。属确定的隐患。
- **修复方向**：复用 `task_store.py` 的 `_connect()` 同构写法（`@contextlib.contextmanager` + `finally: close()`）。**优先采用 §P2-1 的统一工厂。**

### P2-1　`_connect()` 实现已复制 3 份，建议收敛为公共工厂（复发根源）

- **文件**：`paper_discovery_store.py:506-528`、`task_store.py:23-40`、`research_store.py:1235-1260`
- **等级**：P2（MEDIUM）
- **事实**：三处 contextmanager 逻辑几乎相同（research 版用内层 `with connection:` 实现同样语义）。`research_store.py:1244-1249` 文档已记录 spec-037 Bug 9 的同型事故，说明该缺陷**至少复发三次**。
- **影响**：每新增一个 store 就有一次重犯机会（`capability_store.py` 即第四次）。这正是 `regression-guard` 第 9 条「禁止重复实现」关注的形态。
- **修复方向**：抽 `backend/app/platform/sqlite_connect.py` 提供 `sqlite_connection(path, *, row_factory, pragmas, timeout)` contextmanager，各 store 复用；并加一条 lint/测试守卫（grep 禁止出现裸 `with sqlite3.connect(...) as`）。

### P2-2　RED 证据口径失真

- **文件**：`tests/paper_discovery/test_store_connection_release.py:20-42`、`tests/research/test_task_store_connection_release.py:16-38`
- **等级**：P2（MEDIUM）
- **事实**：`_RecordingConnection` 未实现 `__enter__/__exit__`，因此还原旧实现时失败于 `TypeError` 而非断言。backend-dev 报告的「修复前 RED 4 failed」结论对但归因错。
- **修复方向**：报告改述为「用语义等价的泄漏替身验证，4 条均失败在 `assert is_closed`」；或给替身补 `__enter__/__exit__`（不 close）使旧实现下失败原因更贴切。

### P2-3　`tests/research` 全套执行超时

- **等级**：P2（MEDIUM）
- **事实**：`pytest tests/research -q` 两次超时（>默认命令时限）。`tests/paper_discovery` 全套 `1006 passed in 60.87s` 正常。
- **影响**：无法通过全量 research 套件确认无回归，本次仅以定向用例（4 passed）+ FD 端到端探针佐证。
- **修复方向**：排除本次改动后确认是否既有问题；为慢用例加 marker 或 `--timeout`。

### P3-1　`start.sh` 降级分支的 `ulimit -n` 二次读取可能再次失败

- **文件**：`deploy/start.sh:81`
- **等级**：P3（LOW）
- **事实**：`$(ulimit -n 2>/dev/null || echo unknown)` 已做兜底，但若该子 shell 失败，输出与 `unknown` 混淆。当前实现可接受。

### P3-2　`_RecordingConnection` 在测试内定义了两份

- **文件**：`tests/paper_discovery/test_store_connection_release.py:20-42`、`tests/research/test_task_store_connection_release.py:16-38`
- **等级**：P3（LOW）
- **修复方向**：抽到 `tests/conftest.py` 或共享 helper。

---

## 4. 强制约束清单（沉淀为下次同类改动的门禁）

1. **FD 上限只提升不下调**：任何 `ulimit -n` 赋值前必须先比较现值，禁止无条件覆盖。（对应 P1-1）
2. **SQLite 连接必须确定性 close**：`sqlite3.Connection.__exit__` 只 commit/rollback、**不 close**。任何 `_connect()` 若要被 `with` 使用，**必须**是带 `finally: close()` 的 contextmanager。新增 store 前先 grep 是否有可复用实现。（对应 P1-2、P2-1）
3. **禁止新增裸 `with sqlite3.connect(...) as`**：属已知泄漏模式，建议加静态检查守卫。
4. **RED 验证须用语义等价替身**：验证测试有效性时，替身必须复刻被测对象的协议（含 `__enter__/__exit__`），否则 RED 可能来自 `TypeError` 而非目标断言。（对应 P2-2）
5. **`except BaseException` 适用场景**：需要保证事务回滚的临界区（如 sqlite 事务、锁释放）应捕 `BaseException` 并 `raise` 透传，避免 Ctrl-C 遗留半开事务。
6. **资源 acquire/release 同 `try/finally`**（`regression-guard` 第 10 条）：本次 `close()` 已正确置于 `finally`，作为正例保留。

---

## 5. 残留风险

| 风险 | 等级 | 说明 |
|---|---|---|
| `capability_store.py` 未修复 | P1 | 依赖 CPython 引用计数兜底；换解释器（PyPy）或 GC 延迟即泄漏 |
| `_connect()` 三份复制继续扩散 | P2 | 下一个新 store 极可能再次重犯（已发生 4 次） |
| `RA_FD_SOFT_LIMIT=4096` 对大并发场景是否够用 | P2 | 修复后单连接生命周期极短，4096 应充足；但若后续引入并发下载/PDF 渲染需重新评估 |
| `tests/research` 无法全量验证 | P2 | 本次回归证据仅覆盖定向用例 + paper_discovery 全套 |
| 前端改动未评审 | — | 明确移交 `frontend-reviewer`，本报告不作结论 |

---

## 6. 验证命令与结果

| # | 命令 | 结果 |
|---|---|---|
| 1 | `pytest tests/paper_discovery/test_store_connection_release.py tests/research/test_task_store_connection_release.py -q` | `4 passed in 0.24s` |
| 2 | `pytest tests/paper_discovery -q` | `1006 passed, 12 subtests passed in 60.87s` |
| 3 | 反向验证①：还原旧 `_connect` 后跑上述 4 例 | `4 failed`（成因：`TypeError` 替身缺 `__enter__/__exit__`） |
| 4 | 反向验证②：泄漏替身（支持 with、不 close）跑上述 4 例 | `4 failed`，全部命中 `assert is_closed` |
| 5 | FD 端到端探针：200 次 `list_conferences()` | `state.sqlite3` FD 增量 = **0**（GC 前后均 0） |
| 6 | `ulimit` 三场景降级测试（正常/非法值/超 hard） | 均不中断脚本，退出码 0 |
| 7 | `ulimit` 高值回归测试（本机 1048575） | 被**下调至 4096**（P1-1 证据） |
| 8 | `capability_store` close 计数探针 | 打开 10 次 / close **0 次**（P1-2 证据） |
| 9 | `pytest tests/research -q` | **超时**（见 P2-3） |

---

## 7. 评审边界声明

- 本报告仅评审 `backend/**`、`deploy/start.sh` 与后端测试；`frontend/app.js`、`frontend/index.html`、`tests/frontend/**` 未评审，交 `frontend-reviewer`。
- 只读评审：未修改任何业务代码、测试、spec 或台账；未执行 `git add` / `commit` / `merge` / `push`。
- 反向验证均为**运行时 monkeypatch**，未改动磁盘上的实现文件；临时脚本置于 `/tmp`。

---
---

# 追加：2 个 P1 修复的集中复审（P0/P1 批量修复后复审）

> 评审角色：`backend-reviewer`　评审范围：`deploy/start.sh`、`backend/app/platform/capability_store.py`、`backend/app/research/application/cleanup_snapshot.py`、4 个新增连接释放测试。
> 评审方式：独立 Read/Grep 核对代码事实 + 运行时验证（未采信开发回传说明）。上一轮结论（§1-§7）**完整保留，未改写**。
> 评审时间：2026-11-05　日志：`.codebuddy/agent-logs/spec-015/task-00/backend-reviewer/20261105-190744.md`（spec 编号按当前工作流记为 015）

## R0. 最终结论

| 项 | 状态 |
|---|---|
| **P1-1** `deploy/start.sh` 无条件降级 FD | **已关闭（降级缺陷），但同段代码新引入 P1-NEW-1** |
| **P1-2** `capability_store` / `cleanup_snapshot` 裸连接 | **已关闭（确认关闭）** |
| **本轮新引入 P0/P1** | **1 个新 P1（P1-NEW-1）** |
| **总计** | **打回（Block）** |

**结论：打回（Block）** —— P1-1、P1-2 两个原定 P1 本身都已正确修复关闭；但 P1-1 的新实现在 **bash 3.2（macOS 默认 `/bin/bash`）+ UTF-8 locale** 下会因 `set -u` 直接崩溃退出，导致脚本**完全无法启动服务**，属本轮新引入的 P1 回归。修复成本很低（改为 `${VAR}` 花括号形式即可），建议修完即关闭，无需重开设计评审。

---

## R1. P1-1 逐项结论（`deploy/start.sh:76-108`）

**判定：降级缺陷已修复 ✅ / 新增 locale 崩溃 P1 ❌**

### R1.1 五种 case 分支实测（source 真实片段 + 伪造 `ulimit`，`/bin/bash` 3.2.57）

| # | `current_fd_soft` | `RA_FD_SOFT_LIMIT` | 实测行为 | 期望 | 结论 |
|---|---|---|---|---|---|
| 1 | `unlimited` | 4096 | 打印「已不低于目标，保持不变」，**未调用 `ulimit -n`** | 不降级 | ✅ |
| 2 | 空 | 4096 | 同上（显示 unknown） | 不降级 | ✅ |
| 3 | `1048575` | 4096 | 打印「当前为 1048575，保持不变」，**未下调** | 不降级 | ✅ **P1-1 修复点确认** |
| 4 | `256` | 4096 | `ulimit -n 4096` 抬升 | 抬升 | ✅ |
| 5 | `256` | `abc`（非数字目标） | 不比较、直接尝试设置 `abc`，无 `integer expression expected` | 只尝试不中断 | ✅ |
| 6 | `256` | 空目标 | 不比较、直接尝试设置空值 | 不中断 | ✅ |
| 7 | `256` / `512` / `65536` / `99999999` | 256 / 4096 | 均「保持不变」 | 不降级 | ✅ |

`set -euo pipefail` 下全部 `END-OK`，无中断。

### R1.2 兜底与算术错误处理

- `deploy/start.sh:90`：`*) if { [ "$current_fd_soft" -lt "$RA_FD_SOFT_LIMIT" ]; } 2>/dev/null; then ...` —— 比较包在 `{ ...; } 2>/dev/null` 且处于 `if` 条件位置，`set -e` 下比较失败不中断，**算术错误重定向到位** ✅
- `deploy/start.sh:89`：`""|*[!0-9]*) needs_raise=1` —— 非数字目标不进算术比较，避免 `integer expression expected` ✅
- `deploy/start.sh:93`：`if ulimit -n "$RA_FD_SOFT_LIMIT" 2>/dev/null; then` —— 位于 `if` 条件位置，失败走 L96 只告警，**不中断** ✅
- `deploy/start.sh:100`：`true` 兜底在 `set -e` 下无害（该分支最后一条命令是 `echo`，本就返回 0），属冗余但正确 ✅

### R1.3 未被误改的部分（`git diff` 逐段核对）

本轮 diff 只动两处：L23-26（新增 `RA_FD_SOFT_LIMIT`）、L77-103（FD 块）。以下均**未改动**：

| 位置 | 内容 | 结论 |
|---|---|---|
| `start.sh:37-43` | 端口占用预检 `lsof` | 未改 ✅ |
| `start.sh:45-48` | `RERANKER_ENABLED` 枚举校验 | 未改 ✅ |
| `start.sh:50-75` | Reranker 启动 + runtime env 解析 + 地址白名单 | 未改 ✅ |
| `start.sh:7-9`、`107`、`130` | 单 worker 约束注释与两条 uvicorn 命令（无 `--workers`） | 未改 ✅ |
| `start.sh:105-134` | `-d` 后台分支 / 前台 trap 分支 | 未改，且两条启动路径均在 FD 块（L103 `esac`）**之后** ✅ |

### R1.4 ❗ 新引入 P1-NEW-1：bash 3.2 + UTF-8 locale 下 FD 块崩溃

```
[CRITICAL→按项目纪律 P1] FD 块中「$VAR 紧跟非 ASCII 标点」在 bash 3.2 + UTF-8 locale 下触发 set -u 崩溃
File: deploy/start.sh:84, 94, 96, 99
Issue:
  bash 3.2（macOS 默认 /bin/bash 3.2.57，本项目 which -a bash 仅此一个）在 UTF-8 locale
  下用 (c & 0x80) || isalnum(c) 判定标识符字符，把多字节字符首字节 0xEf 当成变量名合法
  字符，于是 "$RA_FD_SOFT_LIMIT，" 被解析为变量 RA_FD_SOFT_LIMIT\xef；set -u 下报
  "unbound variable"，脚本 exit 1，两条 uvicorn 启动路径都到不了。
  L84/L94/L96/L99 四处都是「$VAR 紧跟 ，或 （」，为本轮新增代码。

实测（真实 /bin/bash 3.2.57 + 真实脚本片段）:
  env -i PATH=... LANG=en_US.UTF-8 /bin/bash -c '. 片段'  → rc=1
      _fd_snippet.sh: line 19: current_fd_soft?: unbound variable
  env -i PATH=... (locale=C)                              → rc=0，FD 块正常
  最小复现: set -u; v=256; echo "当前为 $v，保持"  LC_ALL=C → rc=0 ; LC_ALL=en_US.UTF-8 → rc=1
  对照:     echo "当前为 $v 保持"（空格分隔）→ rc=0；echo "val $v, keep"（ASCII 逗号）→ rc=0
  L84 unlimited 分支同样在 zh_CN.UTF-8 下 rc=1。

影响面:
  本机 launchd 环境 LC_CTYPE=C，故主会话观测到成功；但任何把 LANG/LC_ALL 设为 UTF-8 的
  终端/CI/容器（macOS 开发者常见配置、GitHub Actions 常见默认）跑 ./deploy/start.sh 会
  直接启动失败——比修复前（无条件 ulimit -n 4096，无此风险）更差。

Fix（任选其一，最小改动）:
  1) 加花括号（推荐）："${RA_FD_SOFT_LIMIT}，" / "${current_fd_soft}，" / "${RA_FD_SOFT_LIMIT}（"
  2) 变量与中文之间留 ASCII 空格或改用 ASCII 标点
  3) 用 printf '%s' 分片拼接
  修复后补一条回归测试：在 LC_ALL=en_US.UTF-8 下 `bash deploy/start.sh` 的 FD 块不退出
  （可抽成函数或 `bash -c '. <片段>'` 用例），防止再次退化。
```

**其它同类隐患（P2，非本轮引入）**：`deploy/start.sh:29` `"${VENV}，"` 已用花括号，安全；但全文件共 6 处「`$VAR`+非 ASCII 标点」模式（L29/84/94/96/99×2），建议统一改成花括号形式一次性消除。**当时只扫到 6 处是因为变量后紧跟中文标点，若后续新增中文文案仍会复发**，花括号是唯一稳妥写法。

---

## R2. P1-2 逐项结论

**判定：已关闭 ✅**

### R2.1 `capability_store._connect`（`backend/app/platform/capability_store.py:45-67`）

| 检查项 | 事实 | 结论 |
|---|---|---|
| 装饰器与签名 | L45 `@contextlib.contextmanager`，L46 `-> Iterator[sqlite3.Connection]` | ✅ |
| 连接建立失败时 `finally` 引用未定义变量 | L55 `connection = sqlite3.connect(path)` 在 `try` **之前**；建连抛异常时根本不进入 `try`，`finally` 不会执行 | ✅ 无此风险 |
| 事务语义等价 | L59-63 `try: yield / except BaseException: rollback; raise`；L64-65 `else: commit`；L66-67 `finally: close()` —— 与原 `sqlite3.Connection.__exit__`「成功 commit / 异常 rollback」完全等价，并补上 close | ✅ |
| 保留 `row_factory` / `PRAGMA` | L57 `row_factory = sqlite3.Row`；L58 `PRAGMA busy_timeout=5000` | ✅ |
| 调用点未改 | L86 `with _connect() as connection:`、L114 同上 | ✅ |
| 公开 API 签名不变 | `upsert_capabilities(...)` L74、`get_capabilities(model)` L110、`probed_at_is_fresh(...)` L142 与模块 `__all__` 无变化 | ✅ |
| 与 `paper_discovery_store.py` 同模式 | 后者 L506-528 为 `@contextlib.contextmanager` + `try/(yield, except BaseException rollback, else commit)/finally close`；本文件结构一致（PRAGMA 个数不同，因语义不同） | ✅ 同模式 |

**行号勘误**：上一轮报告写的 `capability_store.py:44/69/97` 是**函数定义行**；本轮复核的实际泄漏点是 `_connect()` 定义（原 L44 附近）与其 2 个调用点（现 L86 / L114），已全部纳入 contextmanager，无遗漏。

### R2.2 `cleanup_snapshot._read_only_connection`（`backend/app/research/application/cleanup_snapshot.py:24-43`）

| 检查项 | 事实 | 结论 |
|---|---|---|
| 装饰器与签名 | L24 `@contextlib.contextmanager`，L25 `-> Iterator[sqlite3.Connection]` | ✅ |
| 保留 `FileNotFoundError` 前置检查 | L34-36 `resolved = Path(path).expanduser().resolve(); if not resolved.is_file(): raise FileNotFoundError` | ✅ |
| 保留只读 URI 与 timeout | L37 `sqlite3.connect(f"file:{resolved}?mode=ro", uri=True, timeout=5.0)` | ✅ |
| 连接建立失败时 `finally` 安全 | 同上，L37 在 `try` 之前 | ✅ |
| 只读不 commit 是否合理 | 合理。只读句柄上 `commit()` 只是结束一个空事务，无数据语义；`mode=ro` 保证不可能写入。用 `try/yield/finally: close()` 更贴合契约，且**避免了对只读连接误发 commit 的潜在 `cannot commit` 类错误** | ✅ |
| 调用点未改 | L47 `with _read_only_connection(path) as connection:`、L64 同上 | ✅ |
| `except BaseException: raise`（L40-41） | 纯 no-op（重抛同一异常），冗余但无害 | P2（可删） |

### R2.3 只读路径的 fail-closed 语义未被削弱

`build_cross_store_snapshot_provider.snapshot()` L125 捕获 `(OSError, RuntimeError, sqlite3.Error, TypeError, ValueError, json.JSONDecodeError)` → 返回 `status="unverified"`；`FileNotFoundError` 是 `OSError` 子类，仍被捕获 → 保持 fail-closed ✅。contextmanager 化**没有**把异常吞掉（`raise` 保留），故调用方语义不变 ✅。

---

## R3. 新增测试的判别力复核

| 文件 | 用例数 | GREEN | RED（临时把实现改回裸连接） | 结论 |
|---|---|---|---|---|
| `tests/platform/test_capability_store_connection_release.py` | 2 | pass | **2 failed** | 有判别力 ✅ |
| `tests/research/test_cleanup_snapshot_connection_release.py` | 1+1 | pass | **2 failed** | 有判别力 ✅ |
| `tests/paper_discovery/test_store_connection_release.py` | 2 | pass | pass（本轮未改该实现） | 上轮已验证 |
| `tests/research/test_task_store_connection_release.py` | 2 | pass | pass（本轮未改该实现） | 上轮已验证 |
| **合计** | **8** | **8 passed** | **4 failed, 4 passed** | ✅ |

- RED 失败原因：`TypeError: '..._RecordingConnection' object does not support the context manager protocol` —— 正是「调用点 `with` 拿到裸连接」的缺陷路径，**不是**替身自身缺陷导致的假 RED（上一轮 §6 第 3 行那条「替身缺 `__enter__` 造成的假 RED」已在本轮被改正：本轮替身透传真实连接的 `__enter__/__exit__`）。
- 反向验证为**临时改写磁盘实现**（非同上一轮的 monkeypatch），备份于 `/tmp`，验证后 `diff` 确认**逐字节复原**（`RESTORE-VERIFIED-IDENTICAL`），复原后复跑 4 passed。未留下任何代码改动。
- 断言强度：L82 `assert len(opened) >= 3`、L83 `assert all(c.is_closed ...)`、L105 `assert opened` —— 均为强断言，不会恒真；`test_..._raises` 用 `ExitStack` 先 `pytest.raises` 再 enter，能真正走到 contextmanager 的异常分支 ✅

### R3.1 `pytest.importorskip("langchain_ollama")` 的风险

- 本机 `.venv` **装有** `langchain_ollama`，两文件实际**执行**（结果 `8 passed` 而非 `8 skipped`），未失去覆盖 ✅
- 写法为 `pytest.importorskip(..., reason=...)`，缺依赖时是 **skip 而非 pass**，属「显式跳过」不属「静默通过」；但 CI/精简环境缺依赖时会**悄悄失去覆盖**，且 skip 不阻塞 CI 绿。→ **P2**：建议改为 `pytest.importorskip` 的失败可见化（如 CI 加 `-W error::pytest.PytestUnraisableExceptionWarning` 不够，更直接的是在该 job 里 `pytest.importorskip` 前加 `assert importlib.util.find_spec("langchain_ollama")`，或在 CI 中禁止 skip：`-p no:cacheprovider --strict-markers` 之外的 `--max-skip=0` 类检查）。

> 附注：这两个测试本身**不依赖** `langchain_ollama`，`importorskip` 只是绕开根 `conftest.py` 的 ollama 隔离 fixture。真正的修法是给 conftest 的 fixture 加 `autouse=False` 或 `skipif`，让这两个纯 sqlite3 测试不被牵连。属 P2。

---

## R4. 全仓残留扫描

### R4.1 `with sqlite3.connect` → **零命中** ✅

```
$ grep -rn "with sqlite3.connect" backend/app
(exit=1, 无输出)
```

### R4.2 8 处 `sqlite3.connect(` 逐一列出 close 路径

| # | 位置 | close 路径 | 结论 |
|---|---|---|---|
| 1 | `backend/app/research/application/cleanup_snapshot.py:37` | `_read_only_connection` L38-43 `finally: connection.close()` | ✅ 本轮 |
| 2 | `backend/app/research/infrastructure/research_store.py:1251` | `_connect` L1256-1259 `try: with connection: yield` / `finally: close()` | ✅ 既有 |
| 3 | `backend/app/memory/repository.py:197` | `connection()` L204-206 `try: yield` / `finally: close()` | ✅ 既有 |
| 4 | `backend/app/platform/capability_store.py:55` | `_connect` L66-67 `finally: close()` | ✅ 本轮 |
| 5 | `backend/app/paper_discovery/infrastructure/paper_discovery_store.py:514` | `_connect` L516-528 `finally: close()` | ✅ 上一轮 |
| 6 | `backend/app/paper_discovery/infrastructure/paper_import_batch_store.py:134` | `_write_transaction` L178-179 `finally: connection.close()` | ✅ 既有 |
| 7 | `backend/app/article_assistant/infrastructure/task_store.py:30` | `_connect` L40-41 `finally: close()` | ✅ 本轮（同根因第五例） |
| 8 | `backend/app/literature_maps/infrastructure/store.py:82` | `_connect`（L80 `@contextmanager`）`finally: close()` | ✅ 既有 |

**8/8 全部处于 `finally: close()` 保护下，无裸 `with conn` 残留。**

### R4.3 「`with self._connect()` 但 `_connect` 返回裸连接」形式残留

- 唯一候选 `paper_import_batch_store.py`：`_connect()` L133-138 确实返回裸连接，但**只在 `_write_transaction()`（L144 `@contextmanager`）内部使用**，由 L178-179 `finally: close()` 兜住；全文件无其它 `with self._connect()` 调用点。**不是残留** ✅
- 其余 7 处 `_connect`/`connection` 均已是 contextmanager。
- **结论：同根因无残留。**

---

## R5. 本轮是否引入新 P0/P1

| 编号 | 级别 | 内容 | 位置 |
|---|---|---|---|
| **P1-NEW-1** | **P1（阻塞）** | bash 3.2 + UTF-8 locale 下 FD 块 `set -u` 崩溃，脚本 exit 1 无法启动 | `deploy/start.sh:84, 94, 96, 99` |
| 其余 | — | 两个 Python 修复**未发现**事务语义、签名、异常处理、分层边界、UTC、SSRF、迁移、并发领用方面的回归 | — |

- 分层边界：`capability_store` 只 import `sqlite3`/`contextlib`/`json`/`threading`/`datetime`/`pathlib` 与 `platform.config`，无 FastAPI/HTTP 客户端 ✅；`cleanup_snapshot` 新增 `contextlib` 与已有依赖，无越界 ✅
- 无新增 SQL 拼接、无 `print` 调试语句、无硬编码凭据、无 `SELECT *` 新增 ✅
- `ruff check` 4 个后端文件 `All checks passed!`（主会话已跑，本轮未复跑，采信但已用 Read 确认无 lint 级问题）

---

## R6. 剩余非阻塞项（P2/建议）

| # | 级别 | 内容 | 位置 |
|---|---|---|---|
| P2-1 | P2 | `except BaseException: raise` 是 no-op，可删；或改为 `except Exception`（若意图是显式声明不吞异常，建议加注释说明） | `cleanup_snapshot.py:40-41` |
| P2-2 | P2 | `importorskip("langchain_ollama")` 会牵连两个不依赖 LLM 的 sqlite3 测试；建议改 conftest fixture 为按需而非全局，或 CI 显式禁 skip 以保覆盖可见 | `tests/platform/test_capability_store_connection_release.py:20`、`tests/research/test_cleanup_snapshot_connection_release.py:17` |
| P2-3 | P2 | `deploy/start.sh` 统一用 `${VAR}` 花括号形式，一次性消除全部「`$VAR`+中文标点」隐患（L29/84/94/96/99×2） | `deploy/start.sh` |
| P2-4 | P2 | `deploy/start.sh` 缺少「FD 块」的自动化回归测试（当前靠人工/主会话运行时验证），建议抽成可 `source` 的函数并加 shell 单测（含 UTF-8 locale 用例） | `deploy/start.sh:77-103` |
| P2-5 | P2（上轮遗留） | `pytest tests/research -q` 超时问题未见本轮处理 | 上轮 §6 第 9 行 |
| P2-6 | 提示 | 主会话回传的「FD 软限制已从 256 抬升到 4096」日志**只能来自 L94**，而 L94 紧跟 `（`（U+FF08），在 UTF-8 locale 下会先崩。请提供 `launchctl print`/plist 的 `EnvironmentVariables` 或启动命令原文，确认实际 locale 为 C，以闭环排除「日志来自旧版本脚本」的可能 | — |

---

## R7. 复审统计

| Severity | Count | Status |
|---|---|---|
| CRITICAL | 0 | pass |
| HIGH（含 P1-NEW-1） | 1 | **block** |
| MEDIUM（P2） | 6 | info |
| LOW | 0 | note |

**Verdict: Block** —— 原 2 个 P1 均已正确关闭；但 P1-1 的新实现引入 1 个 P1 级回归（bash 3.2 + UTF-8 locale 崩溃），须修复后方可合并。

---

## R8. 验证命令与结果（本轮）

| # | 命令 / 操作 | 结果 |
|---|---|---|
| 1 | `grep -rn "with sqlite3.connect" backend/app` | 零命中（exit=1） |
| 2 | `grep -rn "sqlite3\.connect(" backend/app` | 8 处，逐一核对 8/8 有 `finally: close()` |
| 3 | `grep -rn "contextlib.contextmanager" backend/app` | 7 处定义，覆盖全部连接工厂 |
| 4 | `pytest 4 个连接释放测试 -q` | **8 passed** |
| 5 | RED 验证：临时把 `_connect`/`_read_only_connection` 改回裸连接 | **4 failed, 4 passed**，失败原因为 `TypeError: ... does not support the context manager protocol` |
| 6 | 复原校验 `diff 备份 现文件` | `RESTORE-VERIFIED-IDENTICAL`，复原后 4 passed |
| 7 | `bash -n deploy/start.sh` | SYNTAX-OK |
| 8 | FD 块 10 种 case（source 真实片段 + 伪造 ulimit） | 全部符合预期，无降级（见 R1.1） |
| 9 | `env -i PATH=... LANG=en_US.UTF-8 /bin/bash -c '. 片段'` | **rc=1，`current_fd_soft?: unbound variable`**（P1-NEW-1 证据） |
| 10 | `env -i PATH=... /bin/bash -c '. 片段'`（locale=C，launchd 风格） | rc=0，正常 |
| 11 | 最小复现 `set -u; v=256; echo "当前为 $v，保持"` | `LC_ALL=C` rc=0；`LC_ALL=en_US.UTF-8` **rc=1** |
| 12 | `/bin/bash --version`；`which -a bash` | `3.2.57(1)-release`；仅 `/bin/bash`（无 brew bash 5） |

## R9. 复审边界声明

- 仅评审 `backend/**`、`deploy/start.sh`、后端测试；`frontend/**`、`tests/frontend/**` 未评审，交 `frontend-reviewer`。
- 只读评审：**未修改任何业务代码/测试/spec/台账**。第 5 行 RED 验证为临时改写磁盘实现，验证后已 `diff` 确认逐字节复原；备份与临时脚本置于 `/tmp`，未进入仓库。
- 未执行 `git add` / `commit` / `merge` / `reset` / `stash` / `clean` / `push`。
- 本报告仅追加，未改写上一轮 §1-§7 的任何结论。
- 本报告未修改其它任何文件。

---

## R10. P1-NEW-1 关闭确认与最终结论（第三次复核）

> 评审角色：`backend-reviewer`　评审范围：`deploy/start.sh` 单文件增量。
> 评审方式：只读 + 运行时实测（未采信开发回传结论）。
> 评审时间：2026-11-05　日志：`.codebuddy/agent-logs/spec-015/task-00/backend-reviewer/20261105-191308.md`

### R10.0 演进链（明确保留前两轮结论，本节不覆盖任何历史判定）

| 阶段 | 结论 | 依据 |
|---|---|---|
| ① 初审（§1-§7） | P1-1（无条件降级 FD）、P1-2（裸连接）待修 | §3 问题清单 |
| ② 集中复审（§R0-R9） | **打回（Block）** | §R5 P1-NEW-1：`$VAR` 紧跟全角标点 + `set -u` → `unbound variable`，脚本 exit 1 |
| ③ 修复（backend-dev） | 7 处引用改 `${VAR}`（L65/84/94/96/99/107/110），逻辑不变 | 待复核 |
| ④ 关闭确认（本节 R10） | **通过（Approve）** | 见 R10.1-R10.4 |

### R10.1 静态核对

| 检查项 | 命令 | 结果 |
|---|---|---|
| 全角标点紧跟变量 | `grep -nE '\$[A-Za-z_][A-Za-z0-9_]*[，。：；（）「」【】、]' deploy/start.sh` | **零命中（rc=1）** ✅ |
| 扩展非 ASCII 紧跟变量 | `rg '\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7F]'` | **0 命中** ✅ |
| 语法 | `/bin/bash -n deploy/start.sh` | **rc=0** ✅ |
| 7 处引用形式 | `sed -n '65p;84p;94p;96p;99p;107p;110p'` | 7/7 均为 `${VAR}` ✅ |
| 改动面 | `git diff -U0 deploy/start.sh`（剔除注释） | 仅：7 处 `${VAR}` 化 + `RA_FD_SOFT_LIMIT` 定义 + FD case 块；无逻辑改动 ✅ |
| 分支未受影响 | diff 过滤 `worker\|port\|lsof\|--port` | **零命中** → 端口预检 / 单 worker / reranker / `-d` 分支未被触碰 ✅ |

### R10.2 UTF-8 locale 运行时实测（关闭该 P1 的关键客观证据）

环境：`/bin/bash` **3.2.57(1)-release (arm64-apple-darwin24)**（即 macOS 系统 bash，无 brew bash 5）。
方法：`awk 'NR>=77 && NR<=103'` 抽取真实 FD 块（**并注入 L24 的 `RA_FD_SOFT_LIMIT` 定义**），`set -u` 开启，不启动 uvicorn。

| # | `LC_ALL` | 软限制 | rc | 输出 | 判定 |
|---|---|---|---|---|---|
| 1 | `en_US.UTF-8` | 1048575 | **0** | `FD 软限制当前为 1048575，已不低于目标 4096，保持不变。` | 不降级 ✅ |
| 2 | `en_US.UTF-8` | 256 | **0** | 抬升失败警告（被我方沙箱降级限制所阻，见 R10.3） | 不崩溃 ✅ |
| 3 | `C` | 1048575 | **0** | 同 #1 | ✅ |
| 4 | `C` | 256 | **0** | 同 #2 | ✅ |

**四组全部 rc=0，均无 `unbound variable`。**

- **RED 反证（修复前机理复现）**：`LC_ALL=en_US.UTF-8` 下 `set -u; echo "...$RA_FD_SOFT_LIMIT（..."` → **rc=1**，报错为 `RA_FD_SOFT_LIMIT\xef\xbc\x88: unbound variable`（全角括号 U+FF08 的首字节被并入变量名）。证明原 P1-NEW-1 真实存在，且 `${VAR}` 形式彻底消除它。
- **抬升成功路径（launchd 风格干净环境）**：`env -i LC_ALL=en_US.UTF-8` + 子 shell 软限制 256 →
  `FD 软限制已从 256 抬升到 4096（当前 ulimit -n = 4096）。`，**rc=0**，与 `deploy/run.log:1476871` 逐字一致。

### R10.3 评审过程中的两个自查纠正（记录以免误导后续）

1. 首次抽取 L77-105 **漏掉 L24 的 `RA_FD_SOFT_LIMIT` 定义**，4 组 rc=1 报 `RA_FD_SOFT_LIMIT: unbound variable`。这是我抽取脚本的缺陷，**不是目标代码缺陷**；补定义后全部 rc=0。
2. 第二次抽取含 `if [ "${1:-}" = "-d" ]` 但未含 `fi`，rc=2 `unexpected end of file`。同属抽取缺陷，非目标问题。
3. 沙箱内「1048575 → 降为 256 → 再抬 4096」返回 `Operation not permitted`：这是 macOS 内核禁止进程在**主动降低**软限制后回抬，**clean 进程 `ulimit -n 4096` 实测 rc=0**。目标实现「只抬不降」，不会走入该路径，与本次结论无关。

### R10.4 P1-NEW-1 判定

**P1-NEW-1 已关闭（CLOSED）** ✅

- 修复面完整：全文件已无「裸 `$VAR` + 非 ASCII」组合。
- 机理已消除：bash 3.2 把全角标点首字节当变量名字符的根因被 `${VAR}` 花括号界定。
- UTF-8 locale 下实测 rc=0，`set -u` 不再触发。
- 逻辑零改动：FD 块仍为「只抬升、不降级」，其余分支未被触碰。

### R10.5 P2-6 闭环（排除「日志来自旧版本脚本」）

| 证据 | 结果 |
|---|---|
| `launchctl print gui/501/com.researchagent.recovery8000` | `environment = {` 字典内**无任何 `LANG` / `LC_*` 赋值行**（grep 仅命中字典键名本身）→ launchd 默认 **C locale** |
| `deploy/run.log:1476871` | `FD 软限制已从 256 抬升到 4096（当前 ulimit -n = 4096）。` |
| R10.2 抬升成功路径 | `env -i` + UTF-8 下复现**逐字相同**的一行，rc=0 |

**判定：P2-6 闭环。** 无论如何解读：
- 若日志由 C locale 的旧脚本产生 → 旧脚本在该 locale 下本就正常，不构成缺陷；
- 若由新脚本产生 → R10.2 已证明新脚本在 UTF-8 与 C 两种 locale 下均能打出该行且 rc=0。

两条路径都指向「当前代码行为正确」，疑虑消除。

### R10.6 本轮是否引入新 P0 / P1

| 编号 | 级别 | 内容 |
|---|---|---|
| — | — | **无新增 P0** |
| — | — | **无新增 P1** |

逐项确认：无 SQL 拼接、无硬编码凭据、无 `print` 调试、无分层越界（本次仅 shell 脚本）、未引入第二套实现（FD 逻辑仍为单一处）、无本地时间使用（`deploy/start.sh` 不涉及时间戳）、无 `git add/commit/merge/push`。

### R10.7 最终统计

| Severity | Count | Status |
|---|---|---|
| P0 / CRITICAL | 0 | pass |
| P1 / HIGH | 0 | pass |
| P2 / MEDIUM | 4 | info |
| P3 / LOW | 0 | note |

### R10.8 剩余 P2 清单（P2-1 ~ P2-6 去向）

| 编号 | 状态 | 内容 | 位置 |
|---|---|---|---|
| P2-1 | **仍残留** | `cleanup_snapshot.py` 的 `except BaseException: raise` 为 no-op，建议删除或改 `except Exception` + 注释 | `backend/app/research/application/cleanup_snapshot.py:40-41` |
| P2-2 | **仍残留** | `importorskip("langchain_ollama")` 牵连两个不依赖 LLM 的 sqlite3 测试，建议按需 skip 或在 CI 显式禁 skip | `tests/platform/test_capability_store_connection_release.py:20`、`tests/research/test_cleanup_snapshot_connection_release.py:17` |
| P2-3 | **已闭环** ✅ | `deploy/start.sh` 统一 `${VAR}` 形式、消除「`$VAR`+中文标点」隐患 —— 本次修复的 7 处即该项落地，全量复扫零命中 | `deploy/start.sh` |
| P2-4 | **仍残留** | FD 块缺自动化回归测试（当前靠人工运行时验证）。**本次亲自踩到「人工抽取片段容易漏前置定义 / 漏 `fi`」导致假失败**，正是该项必要性的实证：建议抽成可 `source` 的函数并加 shell 单测（必含 `set -u` + `LC_ALL=en_US.UTF-8` + 全角标点用例） | `deploy/start.sh:77-103` |
| P2-5 | **仍残留**（上轮遗留） | `pytest tests/research -q` 整套超时问题未见处理；建议拆分或加 `--timeout` | 上轮 §6 第 9 行 |
| P2-6 | **已闭环** ✅ | 见 R10.5 | — |

### R10.9 最终结论

**通过（Approve）**

- P0 = 0，P1 = 0，不存在阻塞项。
- P1-NEW-1 关闭；P1-1（降级缺陷）、P1-2（裸连接）此前已关闭且本轮复核未见回退。
- 剩余 4 项 P2（P2-1、P2-2、P2-4、P2-5）均为**非阻塞**技术债，建议纳入后续 spec 排期；其中 **P2-4 优先级建议上调**，因本次评审过程本身即证明「FD 块无自动化回归」会持续消耗人工验证成本并产生假失败。

### R10.10 评审边界声明

- 仅评审 `deploy/start.sh`；`frontend/**`、`tests/frontend/**` 未评审（交 `frontend-reviewer`）。
- **只读评审**：未修改任何业务代码、测试、spec、台账；本轮**仅追加本报告**（§R10）。
- 临时脚本全部置于 `/tmp`（`/tmp/fdtest.sh`、`/tmp/fdok.sh`、`/tmp/fdlow.sh`、`/tmp/fdred.sh`、`/tmp/ul.sh`），未进入仓库。
- 未执行 `git add` / `commit` / `merge` / `reset` / `stash` / `clean` / `push`。
- 本报告 §1-§9、§R0-R9 的既有结论与打回记录**逐字保留，未改写**。
