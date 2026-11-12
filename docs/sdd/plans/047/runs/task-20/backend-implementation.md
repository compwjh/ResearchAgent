# spec-047 追加范围五 · Task 21（C：测试布局合规）backend-dev 自测

- 日期：2026-11-12
- 执行角色：`backend-dev`（本次只做一件事：C 测试布局合规；不含 E1 覆盖率）
- 范围：仅 `tests/**` 的文件名 / 位置与仓库根 `conftest.py`；**未改任何测试断言内容、未删测试、未改 `backend/**` / `frontend/**` / spec / 台账 / 评审 / 历史归档报告 / `scripts/check_test_layout.py`**；未 commit / push / 合 main。
- 日志：`.codebuddy/agent-logs/spec-047/task-20/backend-dev/20261112-214806.md`（spec §6 规定 task-21 产出落在 `runs/task-20/`，日志路径按分派要求同为 task-20）。

## 1. 迁移前 RED 基线（真实输出）

| 命令 | 退出码 | 输出 |
|---|---|---|
| `.venv/bin/python scripts/check_test_layout.py` | **1** | stderr 5 项：`tests root contains test source: tests/conftest.py`；4 条 `test filename contains delivery id: tests/evaluation/test_task03_reproducibility.py`、`test_task04_idempotency.py`、`tests/observability/test_task05_decoupling.py`、`tests/platform/test_task06_identity_redaction.py` |
| `.venv/bin/python -m pytest -q`（4 个旧名文件） | 0 | `39 passed in 1.41s` |
| `.venv/bin/python -m pytest -q tests/system/test_startup_warmup.py tests/kb/test_kb_routes.py` | 0 | `37 passed in 4.97s` |

基线两组均绿，故迁移后任何红灯均可归因于本次改名 / conftest 迁移。Langfuse `127.0.0.1:3000` 连接拒绝的 span 导出告警在迁移前后均出现（spec §2 明确不处理）。

## 2. 改动清单（git mv 与等价迁移）

| # | 操作 | 源 → 目标 | 内容变化 |
|---|---|---|---|
| 1 | `git mv` | `tests/evaluation/test_task03_reproducibility.py` → `tests/evaluation/test_fallback_reproducibility.py` | 0 行 |
| 2 | `git mv` | `tests/evaluation/test_task04_idempotency.py` → `tests/evaluation/test_score_idempotency.py` | 0 行 |
| 3 | `git mv` | `tests/observability/test_task05_decoupling.py` → `tests/observability/test_observability_decoupling.py` | 0 行 |
| 4 | `git mv` | `tests/platform/test_task06_identity_redaction.py` → `tests/platform/test_trace_identity_redaction.py` | 0 行 |
| 5 | 等价迁移（见下） | `tests/conftest.py` → 仓库根 `conftest.py` | 根文件 +35 行；源文件移除 |

`git diff --cached --summary` 对 4 个改名显示 **R100（100% 纯改名）**，`--stat` 为 `0 insertions(+), 0 deletions(-)`；4 个文件内部代码（含 docstring 中的历史 task 编号）逐字未动。

### 2.1 关键发现：仓库根 `conftest.py` 已存在，字面 `git mv` 不可行

分派要求 `git mv tests/conftest.py conftest.py`，但勘察确认**仓库根 `conftest.py` 已存在且被 git 跟踪**（4092B，spec-038 P3 起，含 5 个 `autouse=True` fixture：`_stop_cached_conversation_workers`、`_isolate_default_memory_dir`、`_isolate_capability_db`、`_isolate_ollama_model_cache`、`_pin_default_route_to_langchain_in_tests`）。实测字面命令报 `fatal: destination exists, source=tests/conftest.py, destination=conftest.py`；若强制 `-f` 覆盖会删除这 5 个既有 fixture，违反「不删测试 / 最小改动」。

**采用的最小等价迁移**（终态与要求一致：全局 fixture 在仓库根 `conftest.py`，`tests/` 根不再有 `.py` 源文件）：

1. 根 `conftest.py` 顶层补 `import time`（:19），为迁入的 `_drain_and_reset()` 提供依赖；原有 5 个 autouse fixture **逐字保留、0 行删除**。
2. 追加来源注释（:98-100）与 `tests/conftest.py` 第 31 行起的 fixture 定义块（:103-128：`_WARMUP_TERMINAL_STATUSES`、`_WARMUP_DRAIN_TIMEOUT_SECONDS`、`_drain_and_reset()`、`clean_warmup_registry()`），**逐字复制**：`diff -u`（源块 vs 迁入块）**EXIT=0**；`.venv/bin/python -m py_compile conftest.py` **EXIT=0**；`.venv/bin/python -m ruff check conftest.py` **EXIT=0 / `All checks passed!`**。
3. `git rm tests/conftest.py`（删除的是 conftest 配置源文件，fixture 定义已完整迁入，无任何测试或断言被删）。
4. 未改 `tests/system/conftest.py` / `tests/kb/conftest.py`：二者均以**形参名** `clean_warmup_registry` 引用（`:13`，目录级 `autouse=True`），不是 import；其 docstring 中「根 `tests/conftest.py`」属历史叙述，按 `AGENTS.md`「历史归档报告中的旧路径不随改名重写」保留。


## 3. 验证命令与真实输出（全部真实执行）

| # | 命令 | 退出码 | 真实输出 |
|---|---|---|---|
| 1 | `.venv/bin/python scripts/check_test_layout.py` | **0** | `test layout: ok` |
| 2 | `.venv/bin/python -m pytest -q tests/evaluation/test_fallback_reproducibility.py tests/evaluation/test_score_idempotency.py tests/observability/test_observability_decoupling.py tests/platform/test_trace_identity_redaction.py` | **0** | `....................................... [100%]` / `39 passed in 2.18s` |
| 3 | `.venv/bin/python -m pytest -q tests/system/test_startup_warmup.py tests/kb/test_kb_routes.py` | **0** | `..................................... [100%]` / `37 passed in 4.88s` |
| 4 | `git diff --check` | **0** | 无输出 |
| 附加 | `git diff HEAD --check`（覆盖 staged 改名 / 删除） | **0** | 无输出 |
| 附加 | `.venv/bin/python -m pytest --fixtures tests/system/test_startup_warmup.py` | **0** | `rootdir: /Users/wjh/ResearchAgent`；`clean_warmup_registry -- conftest.py:124` |
| 附加 | `.venv/bin/python -m ruff check conftest.py` | **0** | `All checks passed!` |

命令 2/3 的 stderr 仍有 Langfuse `127.0.0.1:3000` span 导出 transient 告警（`Failed to export span batch ... Connection refused`），与迁移前基线完全一致，spec §2 列为不处理项，退出码与通过数不受影响。

附加全仓 lint：`.venv/bin/python -m ruff check .` **EXIT=1 / `Found 185 errors.`**（`[*] 97 fixable`），全部为仓库既有问题（分布在 `.codebuddy/skills/**`、`backend/**`、`docs/**`、`scripts/**`、`tests/**` 等；含 4 个改名文件原本就有的 F401/C408/I001 等）。本次唯一有内容改动的文件 `conftest.py` 单独 `ruff check` 为 **EXIT=0 / All checks passed!**，4 个改名文件内容 0 行变化，故**未新增任何 lint 错误**；未越界修这些既有问题。

迁移前后对比：4 文件 `39 passed` → `39 passed`；system+kb `37 passed` → `37 passed`；布局门禁 `EXIT=1` → `EXIT=0`。

## 4. conftest 引用核查结论

- 全仓 Grep（`clean_warmup_registry|from conftest import|import conftest|from tests\.conftest`）命中仅 4 处：`tests/system/conftest.py:13`、`tests/kb/conftest.py:13`（形参引用 + 目录级 autouse 包装）、`conftest.py:124`（迁入后的定义）、`docs/sdd/reviews/20261110-lingering-fixes-backend-recheck.md:51`（历史评审旧路径，按 `AGENTS.md` 不重写）。**无任何 import 形式依赖**，故源文件改名 / 删除不会造成符号断链。
- `pytest --fixtures` 显示 `clean_warmup_registry -- conftest.py:124`，证明仓库根 `conftest.py` 被 pytest 收集（rootdir 为仓库根）。输出中未列出 `_` 开头的 5 个根 autouse fixture 与 `_reset_warmup_registry_in_system` 包装 fixture，系 pytest `--fixtures` 默认隐藏私有名，不代表未加载；两组定向 pytest 全绿且目录级 wrapper 以形参请求该 fixture，若根文件未收集会直接报 `fixture 'clean_warmup_registry' not found`，因此**隔离仍生效**。
- `tests/` 根目录已无 `.py` 源文件；4 个旧路径与 `tests/conftest.py` 均已不存在；未改 `scripts/check_test_layout.py` 本身。

## 5. 风险、偏差与阻塞

1. **唯一实现偏差（已就地解决）**：字面 `git mv tests/conftest.py conftest.py` 因根 `conftest.py` 已存在而失败；采用「保留根文件原文 + 逐字追加 fixture 块 + `git rm tests/conftest.py`」的等价迁移。git 状态为 `M conftest.py` + `D tests/conftest.py`（不是 rename），因为最终根文件内容仅约 26 行来自源文件、相似度不足；终态满足 `AGENTS.md` 与 spec §4 C2。**未删任何测试 / fixture / 断言**，根文件原有 5 个 autouse fixture 逐字保留。若主会话要求严格 rename 记录，需另行确认（但会牺牲根文件原文零改动的前提）。
2. **历史路径未重写**：`docs/sdd/reviews/**`、`docs/sdd/plans/047/runs/**` 等历史归档报告及 `tests/system/conftest.py` / `tests/kb/conftest.py` docstring 中仍写旧路径 `tests/conftest.py` 与旧文件名；按 `AGENTS.md`「历史归档报告中的旧路径不随改名重写」与分派要求保留，不影响 pytest 运行。
3. **并发改动**：最终 `git diff HEAD --name-status` 还显示 `docs/sdd/spec-status-changelog.md`、`docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md`、6 个 `tests/frontend/*.py` 有其它角色的并发改动；**本任务未触碰这些文件**，`git diff --check` / `git diff HEAD --check` 已覆盖且均 EXIT=0。
4. **未跑全量回归**：spec §5 的候选全量 `.venv/bin/python -m pytest -q` 属任务 22 主会话 / tester 收口阶段；本任务按分派只做 C 范围的定向验证，未越界执行。
5. **fixture 不可用 / 测试失败：均未发生**，因此无需最小修复方案；未使用 skip / xfail / 放宽断言凑绿。
6. 环境依赖：Langfuse `:3000` 未启动导致 span 导出 transient stderr，spec §2 明确不处理。
7. 全仓 `ruff check .` 既有 EXIT=1（185 errors，见 §3）；本任务只保证改动文件零新增，未顺手优化既有 lint 债务。

## 6. 复用与边界自查

- 复用既有 `clean_warmup_registry` / `_drain_and_reset` 实现（逐字迁移，未重写、未新增第二套隔离 fixture）；复用既有 `scripts/check_test_layout.py` 门禁与其既有命名正则，未改脚本。
- 未改 `backend/**`、`frontend/**`、spec / 台账 / 评审 / 历史归档报告；未改 4 个测试文件内部任何一行代码；未改 `tests/system/conftest.py` / `tests/kb/conftest.py`。
- 未执行 git commit / push / 合 main / force push；`git mv` / `git rm` 产生的 index 变更保持 staged，供主会话收口。

## 7. 进展日志

`.codebuddy/agent-logs/spec-047/task-20/backend-dev/20261112-214806.md`
