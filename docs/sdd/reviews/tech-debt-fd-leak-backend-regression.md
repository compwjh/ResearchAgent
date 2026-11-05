# 后端回归报告 — FD 泄漏根因修复

- 评审角色：backend-tester（后端回归）
- 日期：2026-11-05
- 工作区：`/Users/wjh/ResearchAgent`，分支 `main` + 未提交改动
- 解释器：`.venv/bin/python`（Python 3.11.16）
- 范围：**仅后端**。前端改动（`frontend/app.js`、`frontend/index.html`、`tests/frontend/**`）不在本报告范围，交由 frontend-tester。
- 进展日志：`.codebuddy/agent-logs/spec-000/task-00/backend-tester/20261105-185206.md`

---

## 0. 被验证的改动（后端侧）

| 文件 | 改动 | 性质 |
|---|---|---|
| `backend/app/paper_discovery/infrastructure/paper_discovery_store.py` | `_connect()` 由「返回裸 `sqlite3.Connection`」改为 `@contextlib.contextmanager`，复刻 `__enter__/__exit__` 语义（成功 commit / 异常 rollback）并在 `finally` 中 `connection.close()` | 根因修复 |
| `backend/app/article_assistant/infrastructure/task_store.py` | 新增同构 `_connect()` contextmanager，3 处 `with sqlite3.connect(...)` 改为 `with self._connect()` | 同类缺陷同批修复 |
| `deploy/start.sh` | 启动 uvicorn 前 `ulimit -n ${RA_FD_SOFT_LIMIT:-4096}`（`if` 保护，失败仅告警） | 缓解措施（提高额度，非根因） |
| `tests/paper_discovery/test_store_connection_release.py`（新增） | 2 个用例：正常退出 / 异常退出均须 close | 回归门禁 |
| `tests/research/test_task_store_connection_release.py`（新增） | 2 个用例：多连接均 close / 异常路径 close | 回归门禁 |

根因说明（与实现注释一致）：`sqlite3.Connection.__exit__` **只做 commit/rollback，不 close**，因此 `with sqlite3.connect(...) as c:` 的连接只能等 CPython 引用计数/GC 回收；长跑服务在 WAL 模式下每条连接额外占 `-wal`/`-shm` FD，累积后触发 `OSError: [Errno 24] Too many open files`。

---

## 1. 命令与结果

| # | 命令 | 退出码 | 真实输出摘要 |
|---|---|---|---|
| 1 | `.venv/bin/python -m pytest tests/paper_discovery/test_store_connection_release.py tests/research/test_task_store_connection_release.py -q` | **0** | `4 passed in 0.25s` |
| 2 | `.venv/bin/python -m pytest tests/paper_discovery -q` | **0** | `1006 passed, 5 warnings, 12 subtests passed in 60.62s` |
| 3 | `.venv/bin/python -m pytest tests/research/test_article_agent.py tests/research/test_candidate_acquisition_integration.py tests/research/test_task_store_connection_release.py -q` | **0** | `9 passed in 8.75s` |
| 4 | `.venv/bin/python -m ruff check backend/app/paper_discovery/infrastructure/paper_discovery_store.py backend/app/article_assistant/infrastructure/task_store.py` | **0** | `All checks passed!` |
| 5 | `bash -n deploy/start.sh` | **0** | （无输出，语法通过） |
| 附加 | `.venv/bin/python -c "import backend.app.main"` | **0** | 导入冒烟通过（FastAPI app 可加载） |

代码行覆盖（就本次修复的两个方法而言）：
- `PaperDiscoveryStore._connect` 的成功/异常/close 三分支：被 `test_store_connection_release.py` 两个用例分别覆盖。
- `TaskStore._connect` 同上：被 `test_task_store_connection_release.py` 两个用例覆盖。
- **未做全局行覆盖率统计**（本任务未要求，避免全仓 `--cov` 拖长耗时）。

---

## 2. 进程级 FD 不增长探针（关键证据）

探针为临时脚本（`/tmp`，**已删除**），要点：
- 使用**真实** `PaperDiscoveryStore` / `TaskStore`，指向 `tempfile.mkdtemp()` 的临时 SQLite，**未触碰** `data/paper_search/state.sqlite3`。
- `sqlite3.connect` 用 `CountingConnection(sqlite3.Connection)` 子类接管（`Connection.close` 是只读属性，不能直接给实例打补丁），统计 opened / closed / 仍存活。
- 进程 FD 数用 `lsof -p <pid> | wc -l`（macOS 无 `/proc/self/fd`）。
- 循环期间 `gc.disable()`，以保证 FD 不下降**不是靠 GC 回收**。

### 2.1 读路径（修复后）

循环 200 轮 × 4 次 store 调用（`list_conferences` / `list_search_ids` / `list_catalog_papers` / `TaskStore.get`）= **800 次** store 调用：

```
[FIXED] iterations=200  store_calls=800
[FIXED] sqlite3.connect 次数        = 800
[FIXED] connection.close() 次数     = 800
[FIXED] 结束时仍打开连接数           = 0
[FIXED] 进程 FD 数 before/after      = 27 / 27  (delta=0)
[FIXED] gc 状态                       = gc.disable() 已生效（循环期间未发生 GC 回收）
```

### 2.2 对照组（复刻修复前模式，同进程）

把 `with sqlite3.connect(...)` 的旧写法还原（建连后不 close、持有引用防 GC），同样 200 次：

```
[CONTROL 修复前模式] N=200 -> 进程 FD before/after = 27 / 429  (delta=402)
[CONTROL] 关闭后 FD = 27
```

即修复前约 **+2 FD / 连接**（`state.sqlite3` + `-wal`），200 次泄漏 402 个 FD；修复后 **delta=0**。这与线上 `Too many open files`、以及 macOS `maxfiles=256` 下很快耗尽的现象一致。

### 2.3 写路径 + 异常路径（修复后）

200 轮 `save_conference`（写）+ 强制在 `_connect()` 块内 `raise`（异常回滚路径），两个 store 各 200 次：

```
[WRITE+EXCEPTION] 200 轮写路径+异常路径  FD before/after = 27 / 27 (delta=0)
```

结论：**正常退出、写提交、异常回滚三条路径都确定性释放连接**，不依赖 GC。

### 2.4 探针可信度自检（防止「恒真」）
- 对照组的 delta=402 证明 FD 计数方法**确实能观测到泄漏**，不是永远返回 0 的假探针。
- 修复后 opened==closed==800 且 live==0，证明 close 被真实调用而非计数错觉。

---

## 3. 静态核对

| 核对项 | 命令 | 结果 | 判定 |
|---|---|---|---|
| 调用点未变 | `grep -c "with self._connect()" backend/app/paper_discovery/infrastructure/paper_discovery_store.py` | **36** | PASS（符合预期 36，说明修复集中在 `_connect`，未逐个改 36 处调用） |
| `_connect` 内唯一真建连 | `grep -n "sqlite3.connect" ...paper_discovery_store.py` | 仅 `514: connection = sqlite3.connect(self.database_path)`（在 `_connect` 内） | PASS |
| `finally` + `close` | `grep -n "finally:\|connection.close()"`（两文件） | `paper_discovery_store.py:527 finally:` / `:528 connection.close()`；`task_store.py:39 finally:` / `:40 connection.close()` | PASS |
| 裸连接模式残留 | `grep -rn "with sqlite3.connect" backend/app` | **无匹配**（exit 1） | PASS |
| 全仓 `sqlite3.connect(` 调用点清查 | `grep -rn "sqlite3\.connect(" backend/app` | 8 处（见下） | 见下判定 |

`backend/app` 内 8 处 `sqlite3.connect(` 的处置判断：

| 文件 | 是否 `with <裸连接>` | 是否本范围 | 说明 |
|---|---|---|---|
| `paper_discovery/infrastructure/paper_discovery_store.py` | 否（`_connect` 已 close） | ✅ 已修 | 本次根因 |
| `article_assistant/infrastructure/task_store.py` | 否（`_connect` 已 close） | ✅ 已修 | 本次同类修复 |
| `paper_discovery/infrastructure/paper_import_batch_store.py` | 否（文件内有 `.close()`） | 否 | 已是安全模式，不在本次范围 |
| `research/infrastructure/research_store.py` | 否（有 `.close()`） | 否 | 已是安全模式 |
| `memory/repository.py` | 否（有 `.close()`） | 否 | 长驻连接，有显式 close |
| `literature_maps/infrastructure/store.py` | 否（有 `.close()`） | 否 | 安全模式 |
| `research/application/cleanup_snapshot.py` | **是**（`with _read_only_connection(path)`，仅 commit 不 close） | 否（**列为后续技术债**） | 只读清理快照路径，调用频次低，未在本次 FD 事故链主路径；建议后续同样包 contextmanager |
| `platform/capability_store.py` | **是**（`with _connect()`，`_connect` 返回裸连接） | 否（**列为后续技术债**） | 同类「裸连接 + with」模式，发生频次低但同源缺陷 |

> 判定：本次范围内两个文件**已彻底修复**，无「with 裸连接」残留；剩下 2 处同源但**不属于本次 FD 根因修复范围**（不同的 store、低频调用），作为技术债登记，不构成阻塞。

---

## 4. 安全 / 契约侧检查

- 事务语义**未被削弱**：`_connect` 成功路径仍 `commit()`，异常路径仍 `rollback()` 后重抛；与 Python 官方 `Connection.__exit__` 语义一致，因此原有「写失败不留半成品」的保证保留。
- `paper_discovery_store.py` 的 `__init__` 内 `BEGIN` + 显式 `connection.commit()` 与新的 contextmanager 叠加：内层已 commit，退出时再 commit 为空操作，**不会重复提交业务数据**；迁移失败仍 rollback。
- 无新增硬编码密钥 / SQL 字符串拼接；改动仅涉及连接生命周期。
- `deploy/start.sh` 的 `ulimit -n` 在 `set -e` 下用 `if` 包裹，失败不中断启动——已通过 `bash -n` 语法校验。

---

## 5. VERIFICATION REPORT

```
VERIFICATION REPORT
===================

Build:     PASS   (import 冒烟 `import backend.app.main` exit 0；bash -n deploy/start.sh exit 0)
Types:     N/A    (纯 Python 项目，未配置 pyright/mypy；以 ruff 作为静态门禁)
Lint:      PASS   (ruff check 2 文件: All checks passed!, 0 warning)
Tests:     PASS   (命令1 4 passed; 命令2 1006 passed + 12 subtests; 命令3 9 passed; 合计 1019 passed / 0 failed)
Security:  PASS   (0 新增密钥/注入面；事务 commit/rollback 语义保持)
Diff:      3 files changed (backend 2 + deploy 1), +58/-11；新增 2 个测试文件

FD 探针:    PASS   (800 connect / 800 close / live=0, FD 27→27 delta=0；对照组 delta=+402)
静态核对:   PASS   (with self._connect() = 36；两文件 finally+close 就位；无 "with sqlite3.connect" 残留)

Overall:   READY（后端侧，不阻塞）
```

### 阻塞项
- **无**。后端两个 store 的 FD 根因已修复，回归测试与进程级探针均证明连接被确定性释放。

### 非阻塞跟进（技术债，建议另立 task）
1. `backend/app/platform/capability_store.py`：`_connect()` 返回裸连接 + `with _connect()`，与本次相同的 commit-only 模式。
2. `backend/app/research/application/cleanup_snapshot.py`：`with _read_only_connection(path)` 同样只 commit 不 close。
   - 建议：抽一个公共 `sqlite_connection()` contextmanager 到 `backend/app/platform/`，统一替换上述两处，避免第三次复现。
3. `deploy/start.sh` 的 `ulimit -n 4096` 只是提高上限（缓解），根因已由 close 修复；建议在长跑环境的 systemd/launchd 层同样固化 maxfiles。

### 备注
- 前端改动与前端测试**未在本报告中验证**，需 frontend-tester 单独出具结论。
- 探针脚本运行后被完全清理（`/tmp/fd_probe*.py` 与 `/tmp/fdprobe-*` 临时库均已删除），未污染仓库与 `data/`。
- 未执行任何 git add / commit / merge / push，未重启服务。
