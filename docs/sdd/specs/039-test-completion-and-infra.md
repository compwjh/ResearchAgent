# Spec 039 — 测试补全与测试基建整理

## 状态

**当前状态：已确认**（2026-09-19 用户授权「直接进行文件的改名和相关 skill 的沉淀，不需要评审」）

## 一句话目标

补齐缺失的测试**类型**与具体用例，并将散落平铺、含 `spec`/`task` 数字的测试文件按功能分类重命名，把命名规则固化进 skill。

## 发现的问题（2026-09-19 核查）

### 一、测试「类型」缺口（按类型而非具体用例）

| 测试类型 | 现状 |
|---|---|
| 单元测试（函数/类） | ✅ 充足 |
| 集成测试（mock 网络，如 Crossref/OpenAlex `httpx.MockTransport`） | ✅ 充足 |
| API 端点测试（FastAPI `TestClient` in-process） | ✅ 充足 |
| 后端端到端（真实服务 + 真实调用） | ⚠️ 仅手动产物（`artifacts/spec029-030-031-api-sample.md`），无 pytest 用例 |
| 前端 DOM 契约（静态核对 / `?v=N` / XSS） | ✅ 充足 |
| **前端 / 网站端到端（真实浏览器操作，不调 API）** | ✅ 已补（`tests/e2e/`，Playwright 真实浏览器，覆盖 spec028–031 核心生命周期） |

### 二、具体用例缺口（实现层）

**A 类：功能未实现 → 无测试**
- `Planner` 的 `source_ids/scope` 422 校验（spec032 接口表要求「只接受启用且允许的来源，422 未知来源」；backend 无此逻辑，测试也无）
- `SourceCoverage` 任务进度表（spec032 数据模型要求 `task_id × source_id` 进度；backend 搜 `SourceCoverage` 0 命中）

**B 类：已实现但漏测**
- 增量缓存语义（etag 未变不重复向量化、单源失败不丢旧缓存、重复范围只抓新增/变化单元）
- 跨来源同 paper 字段合并集成测试（usenix 官方 × openalex 聚合，官方优先）
- `SourceRegistry.list_enabled` 小方法
- 并发 / 重复写入（重复 DOI、同名论文、并发领用写 provenance）

### 三、命名违规（git 核实）

- **42 个含 `spec` 数字、17 个含 `task` 数字的测试文件，全部由 `compwjh` 创建**。
- 根因：该规则此前**只在对话里口头要求，从未沉淀到 AGENTS.md / skill**（AGENTS.md 搜「test 文件 / 命名规范 / spec 数字」0 命中），导致无人遵守。

### 四、目录混乱

- `tests/` 平铺 150+ 个 `test_*.py`，无功能分类；仅 `fixtures/`、`runtime/` 两个既有子目录。

## 解决方案

### 1. 分类目录树（`tests/` 下）

```
tests/
├── paper_discovery/   来源适配器、解析器、paper_discovery_store、search、import、download、
│                      spec032 sources/authority/provenance/aggregate
├── research/          research session/task、routing、orchestrator、planner、evaluator、critic、
│                      agent、article、capability、online_model、reasoning、skill、tool、ollama、
│                      intent、token_budget、spec027/029/030/031/034 系列
├── kb/               所有 kb_*
├── memory/            memory_*、spec038、seed_test_memory
├── conversation/      conversation_*、chat_route、frontend_conversation_*
├── frontend/          所有 frontend_*（.py 契约 + .js）
├── system/            system_rule、api_module_boundaries、api_routes_coverage、spa_fallback、
│                      startup_warmup、observability*、bench_routes、session_search、import_compensation
├── fixtures/          保留（共享样本，不被分类移动）
└── runtime/           保留（运行时契约）
```

### 2. 命名规则（已沉淀 skill：`test-naming`）

- 禁 `spec\d+` / `task\d+`，按**被测功能**命名。详见 `.codebuddy/skills/test-naming/SKILL.md`。
- 反例→正例：`test_spec032_ccs_source.py` → `test_ccs_source_adapter.py`；`test_spec034_task07_contract.py` → 按该测试验证的功能命名（如 `test_approval_guidance_contract.py`）。

### 3. `__init__.py` 规范

- 每个子目录加 `__init__.py`，首行 docstring 说明该测试集功能（满足「每个 __init__.py 上说明这个 test 集的功能」）。

### 4. 移动时的路径修正（关键，否则会坏）

- 移入一层子目录后，`Path(__file__).resolve().parents[1]`（仓库根）→ `parents[2]`。
- `__file__.parent / "fixtures"` → `ROOT / "tests" / "fixtures"`，其中 `ROOT = Path(__file__).resolve().parents[2]`。
- 已知 52 个文件用 `parents[1]`、5 个 spec032 文件用 `__file__.parent / "fixtures"`，移动时必须同步修正。
- 验证：移动前后 `pytest --collect-only -q` 收集到的用例数一致、无 `ERROR collecting`。

## 任务计划

| 编号 | 任务 | 依赖 | 状态 |
|---|---|---|---|
| T1 | 创建分类目录 + 各 `__init__.py` 功能说明 | — | ✅ 完成 |
| T2 | 违规文件改名 + 分类（42 个含 spec/task 数字）+ 路径修正 | T1 | ✅ 完成 |
| T3 | 其余测试文件按功能分类放置（保留原名） | T1 | ✅ 完成 |
| T4 | 补具体用例缺口（见「二」） | — | ⏸ 待做（A 类需先实现后端，建议并入 spec032 收口） |
| T5 | `pytest --collect-only` 验证收集数不变 | T2/T3 | ✅ 完成（2613 → 2613，无 ERROR） |

## 执行记录（2026-09-19）

- 新建 7 个功能子目录（`paper_discovery` / `research` / `kb` / `memory` / `conversation` / `frontend` / `system`），各含 `__init__.py` 功能说明；`fixtures/` `runtime/` 保留。
- 全量 `tests/*.py` 按功能移入子目录：**42 个违规文件已改名**（去 `specNNN`/`taskNN`，按功能命名）+ 其余按功能归类（保留原名）。
- 移动时同步修正路径引用：仓库根定位 `parents[1]` → `parents[2]`；fixtures 定位 `__file__.parent / "fixtures"` → `parents[2] / "tests" / "fixtures"`；唯一一处跨文件兄弟 import（`test_deep_research_task10_backend.py`）改为包路径 `from tests.research.test_xxx import`。
- **陷阱记录**：子目录加 `__init__.py` 后 pytest 改用 package 导入，扁平的 `from test_x import` 兄弟引用会失效；今后跨文件引用须用 `from tests.<sub>.test_x import`。
- 命名规则已沉淀至 `.codebuddy/skills/test-naming/SKILL.md`。
- 验证：`pytest tests --collect-only` 重组前后均为 **2613 collected**，无导入错误。

## 补充：前端 / 网站端到端（2026-09-19）

- 新建 `tests/e2e/`（`__init__.py` 含功能说明、`conftest.py` 管理 Playwright 浏览器、`test_research_lifecycle_e2e.py` 用例、`README.md` 运行文档）。
- 覆盖 spec028–031 共同支撑的「研究会话全生命周期」：创建 → 计划/模型路由(spec031) → 运行与持久化调度/恢复(spec028) → 全文获取与证据(spec029) → 证据矩阵与只读报告(spec030)。测试只通过浏览器操作页面，**不显式调用后端 API**。
- 常规 `pytest` 用 `RUN_E2E` 环境变量整集跳过（避免污染单元/集成套件、且不因缺少浏览器/服务报错）；运行需先 `./deploy/start.sh -d` 起服务（:8000）+ `python -m playwright install chromium`。
- 验证（本环境已跑）：创建段 **PASSED**（创建研究会话 → 自动打开 → 详情状态进入 planning，2.5s）；重型跟随段因依赖后端 LLM 完整运行，在无 LLM 环境按设计 **skip**（reason: 任务未在窗口内进入运行/完成阶段）。

> T4 中 A 类（Planner 422、SourceCoverage）需先实现后端逻辑，建议并入 spec032 收口或单独功能任务；B 类直接补测试。

## 验收方式

- `tests/` 按功能分子目录，无平铺；每目录 `__init__.py` 有功能说明。
- 全仓无 `test_*spec\d+*` / `test_*task\d+*` 文件。
- `pytest --collect-only -q` 收集数与整理前一致，无导入错误。
- T4 补齐的用例通过。

## 执行配置

| 角色 | 模型 | 上下文上限 | 职责 |
|---|---|---|---|
| 架构师 | 自身 | 200k | 分类方案与命名裁决 |
| 测试 | `qwen3.5:9b` | 32k | 改名脚本、路径修正、收集验证、补用例 |

> 本 spec 经用户授权直接执行，跳过「待确认 → 评审」门禁。
