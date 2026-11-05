# 技术债四项修复 — 当前部署版本运行时验证（2026-11-05）

> **主会话纯文档代行留痕**：本文件只记录运行时证据与清理动作，不含业务代码改动，
> 也不是独立评审。实现由 `backend-dev` / `frontend-dev` 分端承担；独立复审与单端回归
> 分别见 `tech-debt-fd-leak-backend-review.md`、`tech-debt-fd-leak-backend-regression.md`、
> `tech-debt-hash-deeplink-frontend-review.md`、`tech-debt-hash-deeplink-frontend-regression.md`。

- 服务：`http://127.0.0.1:8000/`（launchd job `gui/501/com.researchagent.recovery8000`，keepalive）
- 启动命令：`cd /Users/wjh/ResearchAgent && exec env HOST=127.0.0.1 PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh`
- 重启验证命令：`launchctl kickstart -k "gui/$(id -u)/com.researchagent.recovery8000"`

## 1. 用户要求的四项

| # | 项目 | 修复 | 运行时证据 |
|---|---|---|---|
| 1 | FD 泄漏根因 + launchctl FD 软限制 256 | 4 处 SQLite 裸连接改 `@contextlib.contextmanager` + `finally: close()`；`deploy/start.sh` 只抬升不降级 | 软限制 `256 → 4096`；重启后 sqlite FD `50 → 3`；两次压测无累积 |
| 2 | 刷新后 `#literature-maps-view` 不自动切视图 | `frontend/app.js` 新增 `HASH_VIEW_MAP` / `syncViewFromLocationHash()` + `hashchange`；`?v=68` | 真实浏览器直达加载后唯一可见主区 = `literature-maps-view`，地图列表 7 张；未知 hash 回落 `chat` |
| 3 | vm 用例「失败路径不收起」没跑 `applyNodeColor()` 的 catch | 用例 6 改写为 `extract('applyNodeColor')` 真实 async 函数进 `node:vm`，覆盖 4 条失败路径 + 1 条对照组 | 定向测试通过；`frontend-tester` 变异验证（409 分支误置位）被捕获且已还原 |
| 4 | 清理 `map-usability` 冗余改动 | 备份后丢弃第三轮已被 `main` 覆盖的 13 个改动文件 + 1 个 untracked 测试 | `git -C <worktree> status --short` 为空；分支 `codex/spec030-report-quality` 保留、HEAD 仍 `6307d0db` |

## 2. FD 泄漏根因（主会话实测定位）

- 旧进程 PID 14317：`155 FD`，其中 `50` 个 sqlite 相关；更早的旧进程曾累积 `235` 个 `.sqlite3` FD，
  在 `launchctl limit maxfiles` = `256 / unlimited` 下触发 `OSError: [Errno 24] Too many open files`
  （页面裸 HTML、CSS/JS 0 字节、SQLite `unable to open database file`）。
- `lsof -p 14317` 显示 `data/paper_search/state.sqlite3` 被打开 **26 次**，另有 18 个 `-wal`、2 个 `-shm`。
- 根因：`paper_discovery_store.py::_connect()` 返回裸 `sqlite3.Connection`，36 处
  `with self._connect() as connection:` 走 `Connection.__exit__`——**只 commit/rollback，不 close**。
- 修复文件（4 处）：
  - `backend/app/paper_discovery/infrastructure/paper_discovery_store.py`
  - `backend/app/article_assistant/infrastructure/task_store.py`
  - `backend/app/platform/capability_store.py`（复审 P1-2 补修）
  - `backend/app/research/application/cleanup_snapshot.py`（复审 P1-2 补修）
- `grep -rn "with sqlite3.connect" backend/app` → **零命中**；8 处 `sqlite3.connect(` 全部有 `finally: close()` 路径。

## 3. 运行时数字（真实服务，非 mock）

### 3.1 重启与软限制

| 项 | 值 |
|---|---|
| 重启前 | PID 14317，155 FD / **50 sqlite FD** |
| 重启后（第一次） | PID 7383，96 FD / **3 sqlite FD** |
| `deploy/run.log` | `FD 软限制已从 256 抬升到 4096（当前 ulimit -n = 4096）。` |
| `/api/health` | 200 |
| launchd locale | `launchctl print` 的 environment 中**无** `LANG` / `LC_*`，默认 C locale（P2-6 闭环） |

### 3.2 FD 压测（真实 API，非内部函数）

- 第一次（PID 7383，50 × 5 = **250 次** `/api/papers/conferences`、`/api/papers/sources`、`/api/kb/documents`、`/api/literature-maps`、`/api/tools`）：
  total FD `115 → 97`（**−18**），sqlite FD `23 → 4`（**−19**）。
- 最终重启后（PID 19766，40 × 5 = **200 次**同类调用）：
  total FD `129 → 122`（**−7**），sqlite FD `34 → 27`（**−7**）。
- 两次均**无累积**；health 200。
- 后端回归的独立探针（`gc.disable()`）：修复后 800 次 store 调用 = `connect 800 / close 800 / 存活 0`，
  FD `27 → 27`；复刻修复前的对照组 200 次 → FD `27 → 429`（**+402**），证明探针能观测泄漏。

### 3.3 hash 直达（Playwright Chromium，真实页面）

```
加载 http://127.0.0.1:8000/?fdcheck=2#literature-maps-view
→ appScript: ["/assets/app.js?v=68"]
→ hash: "#literature-maps-view"
→ visibleMainAreas: ["literature-maps-view"]      # 无需手动点左侧导航
→ mapRows: 7
加载 ...#no-such-view
→ visibleMainAreas: ["chat"]                       # 未知 hash 回落
```

### 3.4 定向测试

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest` 四个连接释放测试 | `8 passed` |
| `pytest tests/paper_discovery -q` | `1006 passed` |
| `ruff check` 四个后端文件 | `All checks passed!` |
| `bash -n deploy/start.sh` | `SYNTAX_OK` |
| `node --check frontend/app.js` | 0 |
| `for f in tests/frontend/*.js; do node "$f" \|\| exit 1; done` | `16/16` |
| `.venv/bin/python -m pytest tests/frontend/ -q` | `396 passed / 0 failed` |
| 变异验证（hash 映射改错、409 分支误置位） | 两者均被测试捕获并完整还原 |

## 4. 评审演进（如实记录，不掩盖）

1. 首轮复审：`backend-reviewer` 通过但列 2 个 P1 ——
   **P1-1** `deploy/start.sh` 无条件 `ulimit -n 4096` 会把 1048575 **下调**到 4096；
   **P1-2** `capability_store.py` / `cleanup_snapshot.py` 同根因裸连接未修。
2. `backend-dev` 修复两 P1 后，集中复审给出**打回（Block）**，新发现
   **P1-NEW-1**：`$VAR` 紧跟全角标点在 macOS `/bin/bash` 3.2.57 + `LC_ALL=en_US.UTF-8` 下
   触发 `unbound variable`，脚本 exit 1（本机 launchd 为 C locale 故未触发，但 UTF-8 终端/CI 会启动失败）。
3. 修复 7 处为 `${VAR}` 后，最终复审 **通过**：P0=0 / P1=0；
   UTF-8 与 C × 软限制 1048575/256 共 4 组 rc 全 0，RED 反证修复前 UTF-8 下 rc=1。
4. 用修复后的 `start.sh` 再次 `launchctl kickstart -k` 真实重启：`health=200`，日志再次出现抬升记录。

**剩余 P2（非阻塞，记录不处理）**：`cleanup_snapshot` 的 `except BaseException: raise` no-op；
两个纯 sqlite3 测试被 `importorskip("langchain_ollama")` 牵连；FD 块缺 shell 自动化回归测试（建议后续补）；
`pytest tests/research` 整套超时遗留；前端「新建对话只改 pathname 不清 hash」的固有取舍；
vm 用例 6 的 async IIFE 断言失败时 stdout 仍先打印 `ok`（退出码为 1，门禁以退出码判定）。

## 5. worktree 清理

- 对象：`/Users/wjh/.codex/worktrees/map-usability/ResearchAgent`（分支 `codex/spec030-report-quality` @ `6307d0db`，是 `main` 的祖先）。
- 冗余判定：13 个文件与当前 `main` 全部 `DIFFERS`，内容均为**第三轮（`v=39`）旧版本**，
  已被 `main` 的 `546072e5`（第四轮 `v=40`）及后续提交覆盖；untracked 的
  `test_frontend_node_style_panel_collapse_on_apply.js` 也已在 `main`。
- 清理前备份：`/tmp/map-usability-redundant-20261105.patch`（757 行）、`/tmp/map-usability-untracked-test.js`。
- 清理后：`git status --short` 为空；worktree 目录与分支保留未删（如需彻底删除 worktree 需另行确认）。

## 6. 产物路径

| 内容 | 路径 |
|---|---|
| 本运行时验证 | `docs/sdd/reviews/tech-debt-fd-leak-hash-runtime-verification.md` |
| 后端复审（含打回→最终通过演进） | `docs/sdd/reviews/tech-debt-fd-leak-backend-review.md` |
| 后端单端回归 | `docs/sdd/reviews/tech-debt-fd-leak-backend-regression.md` |
| 前端复审 / 回归 | `docs/sdd/reviews/tech-debt-hash-deeplink-frontend-review.md`、`tech-debt-hash-deeplink-frontend-regression.md` |
| 新增后端测试 | `tests/paper_discovery/`、`tests/platform/`、`tests/research/` 下 `test_*_connection_release.py` |
| 新增前端测试 | `tests/frontend/test_frontend_view_hash_deeplink.js` |
| 状态台账 | `docs/sdd/spec-status-changelog.md` |
| 角色日志 | `.codebuddy/agent-logs/` |

本地 `main` 提交，未 push 远端。
