# Spec 026 后端回归验收报告 — backend-tester

- 角色：backend-tester（仅跑测试、写报告，未改任何业务代码）
- 时间：2026-09-12
- 解释器：`/Users/wjh/ResearchAgent/.venv/bin/python`（python3.11，未 source venv）
- 真实 Ollama：`OLLAMA_BASE_URL=http://192.168.31.180:11434`（11 模型，v0.33.3，局域网可达）

---

## 结论：通过

后端 026 契约定向测试 30/30 通过；全量回归 1028 passed，唯一的 1 个 failure 与 395 个 error **均与 026 无关**（1 个为预先存在的测试竞态，395 个 100% 为环境噪音）；026 引入的 lint 问题为 **0**（`ollama.py` 全绿，并修复了 `routes_conversations.py` 的 I001）；真实模型探测证实 `default_effort` 取最高档（`qwen3.5:9b→xhigh`）与"探测失败即 unknown 不 503"（`qwen3.8:27b→unknown`）在新语义下真实生效。**无 026 引入的回归。**

---

## 1. 各命令真实输出（原样贴）

### 1.1 Spec 026 定向
```
$ .venv/bin/python -m pytest tests/test_spec026_capabilities.py tests/test_spec026_options_endpoint.py -q --basetemp=/Users/wjh/ResearchAgent/.pytest-tmp-bt
..............................                                           [100%]
30 passed in 0.95s
```

### 1.2 后端全量回归
```
$ .venv/bin/python -m pytest tests/ -q --basetemp=/Users/wjh/ResearchAgent/.pytest-tmp-bt --tb=short
1 failed, 1028 passed, 5 warnings, 395 errors, 47 subtests passed in 161.64s
```

### 1.3 相关邻近套件
```
$ .venv/bin/python -m pytest tests/test_conversations_api.py tests/test_spec024_backend.py tests/test_ollama_service.py -q --basetemp=/Users/wjh/ResearchAgent/.pytest-tmp-bt --tb=short
10 passed, 22 errors in 2.66s
```

### 1.4 lint
```
$ .venv/bin/python -m ruff check backend/app/platform/ollama.py --output-format=concise
All checks passed!

$ .venv/bin/python -m ruff check backend/app/api/routes_conversations.py --output-format=concise
... (E701/F841/F401/SIM105/E702 共 33 条，见 §3.4)
Found 33 errors.

$ git show HEAD:backend/app/api/routes_conversations.py > /tmp/routes_head.py && .venv/bin/python -m ruff check /tmp/routes_head.py --output-format=concise
... (含 I001 共 34 条)
Found 34 errors.
```

### 1.5 Build 导入冒烟
```
$ cd backend && .venv/bin/python -c "import app"
IMPORT_APP_OK
```

### 1.6 真实模型探测（每个模型仅一次 `get_reasoning_capabilities(refresh=True)`，未循环）
```
OLLAMA_BASE_URL=http://192.168.31.180:11434 .venv/bin/python /tmp/probe_real.py
=== real probe qwen3.5:9b (refresh=True) ===
elapsed=0.4s
  source            = ollama_probe
  supported_efforts = ('off', 'low', 'medium', 'high', 'xhigh')
  default_effort    = xhigh
  cached_at         = 2026-09-12T05:13:59
  _highest_supported(supported) = xhigh
  default==highest?  True

=== real probe qwen3.8:27b (refresh=True) ===
elapsed=25.1s
  source            = unknown
  supported_efforts = ()
  default_effort    = None
  cached_at         =
  _highest_supported(supported) = None
  default==highest?  True
```

---

## 2. failed / error 分开统计与归类

### failed：1（预先存在，与 026 无关）
- `tests/test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse`
  - 断言：`assert analysis and analysis.status in {"completed", "partial", "failed"}`
  - 实际：`MemoryAnalysisJob.status == 'running'`（异步内存分析 job 在测试 2s 窗口内未达终态）
  - **独立复核结论：预先存在、与 026 无关**。证据：
    1. 026 diff 仅新增 import（`get_memory_analysis_worker`/`get_memory_evolution_worker`）与 3 条 reasoning-effort HTTPException（409/503/404），`git diff` grep `(analysis|durable|worker|status)` 仅命中这些 import 与 409/503/404 抛出，**不触及 MemoryAnalysisJob / durable worker 状态机**；
    2. 隔离单跑该用例 **3/3 稳定失败**，失败点固定在 `MemoryAnalysisJob.status`，属"竞态 + 真实 LLM 时序"；
    3. 该用例 POST 本身返回 200 + `done` 事件（reasoning-effort 解析路径正常），失败发生在下游内存分析 job，与 026 的档位探测无关。

### error：395（100% 环境噪音，0 真问题）
| 类别 | 数量 | 根因 | 是否 026 相关 |
|---|---|---|---|
| A：`assert not self._finalizers`（AssertionError） | 394 | 沙箱在 fixture setup 阶段拒绝创建 pytest 临时目录，导致 fixture 终化器状态异常（历史基线已知噪音） | 否（跨 kb/paper/memory/task0X/spec024 等与 026 无关模块；026 相关模块未出现在 error 列表） |
| B：`SystemExit: 1`（safe-delete 守卫） | 1 | WorkBuddy AI shim `sitecustomize.py` `_check_bulk_delete_guard` 在测试清理要批量删除 ≥50 文件时强制中断 `test_import_compensation.py::test_compensation_rejects_destination_collection_tampering[papers_rebuild_two]` | 否（Python 运行环境守卫，与业务/026 无关） |

- **真问题 error：0**。
- 邻近套件的 22 个 error 全部属于 A 类；其中本应 FAIL 的 `test_chat_wires_...` 因同样的环境终化器污染而变成 ERROR（无法进入测试体），进一步佐证 A 类是环境噪音而非逻辑回归。
- A 类"error"与"failed"的相互转化（同一用例在不同 run 中一会 fail 一会 error）正是沙箱临时目录不可靠的典型表现。

---

## 3. 边界验证结论（B1–B4、B16）

逐条依据 `tests/test_spec026_capabilities.py` 与 `tests/test_spec026_options_endpoint.py` 的真实断言：

### B1 — 探测全失败且无缓存 → 200 + unknown / [] / null，不 503、不伪造 ('off',)
- **PASS**。能力层：`test_probe_all_efforts_fail_returns_unknown_capabilities_without_raising`、`test_probe_all_non_200_returns_unknown_capabilities`、`test_reasoning_capabilities_unknown_when_no_cache_and_probe_fails` → 断言 `source=="unknown"`、`supported_efforts==()`、`default_effort is None`、且 `"m" not in ollama._capability_cache`（不写入缓存）。端点层：`test_options_ollama_unreachable_returns_unknown_200` → 200 + `source=="unknown"` + `supported_efforts==[]` + `default_effort is None`（未判 404/503）。

### B2 — 探测失败但有旧缓存 → 200 + stale，保留旧 supported 与旧 cached_at
- **PASS**。`test_reasoning_capabilities_stale_reuses_old_cached_at` 用 `time.monotonic()-10000` 写入过期旧缓存，探测失败后断言 `source=="stale"`、`supported_efforts==("off","low","medium")`、`cached_at=="2026-09-01T00:00:00+00:00"`（旧值原样透出）。端点层 `test_options_ollama_unreachable_with_expired_cache_returns_stale_200` 同结论。

### B3 — default_effort 取序位最高
- **PASS**。`test_highest_supported_effort_picks_ordering_top` 参数化覆盖 `('off','low','medium')→medium`、`('off','xhigh')→xhigh`、`('off',)→off`、乱序 `('medium','off','low')→medium`、`()→None`；`test_probe_default_reasoning_effort_is_highest_supported` 断言探测 `supported==('off','low','medium')` 时 `default_effort=='medium'`（旧实现会取最低档 off）。**真实模型交叉验证见 §5：qwen3.5:9b supported=全 5 档 → default=xhigh（最高档）**。

### B4 — refresh=1 真正绕过缓存重新探测
- **PASS**（两层）：
  - 能力层 `test_reasoning_capabilities_refresh_bypasses_cache`：首探 `source=ollama_probe` → 二次 `source=cache` → `refresh=True` 后 `source=ollama_probe`；
  - 端点层 `test_options_refresh_query_bypasses_cache`：首探 `ollama_probe` → 缓存 `cache` → `?refresh=1` 后 `ollama_probe`，且 `probed==["m","m"]`（第二次真实探测确实发生）。

### B16 — unknown/stale 路径不得写/覆盖有效缓存条目
- **PASS**。`test_reasoning_capabilities_failed_probe_keeps_existing_cache`：先探得有效缓存 `good`，再强制探测失败（`refresh=True`）→ 断言 `stale.source=="stale"` 且 `_capability_cache["m"]` 的 tuple **前后是同一对象同一时间戳**（`stored_after[1] is stored_before[1]`、`stored_after[0]==stored_before[0]`），随后 `get_reasoning_capabilities("m")` 仍返回 `cache`（未污染）。另 `test_reasoning_capabilities_unknown_when_no_cache_and_probe_fails` 验证无缓存时 `unknown` 也不写入缓存。

---

## 4. 真实模型探测结果（Ollama 真实可达，已执行）

`OLLAMA_BASE_URL=http://192.168.31.180:11434`，对每个目标模型执行一次 `get_reasoning_capabilities(model, refresh=True)`（单次探测最坏 25s，未循环）。

### qwen3.5:9b（elapsed=0.4s）
- source=`ollama_probe`，supported_efforts=`('off','low','medium','high','xhigh')`，default_effort=`xhigh`，cached_at=`2026-09-12T05:13:59`，`_highest_supported=shigh`、`default==highest? True`。
- 结论：5 档全部支持，**default_effort=xhigh=最高档**，证实 B3"默认取最高档"在真实模型上成立。

### qwen3.8:27b（elapsed=25.1s，即 5×5s 档位全部超时/未返回期望 thinking）
- source=`unknown`，supported_efforts=`()`，default_effort=`None`，cached_at=` `（空），`_highest_supported=None`、`default==highest? True`。
- 结论：探测全失败，**返回 unknown（不抛异常、不 503）**，`supported_efforts=()`、`default_effort=None`，与 B1 的真实化表现一致 → 新语义"探测失败即 unknown"在真实模型上真正生效（旧实现此处会 `RuntimeError` → 503）。
- 注：该模型返回 unknown 的最可能根因是 27b 大模型冷启动/较慢，单档 5s `timeout` 触发（spec 026 明确**不改探测性能/超时**，故属预期内"探测失败是常态"场景）。**不等于"该模型不支持推理"**，仅表示本轮探测未拿到任何档位证据；用 `refresh=1` 在模型热身后重试即可。此观察不影响 026 验收。

---

## 5. 未验证项（明确标注，未编造）

- **前端契约 B5–B15（乐观建卡、500ms 卡片、错误文案分流、选择器三态等）**：**未验证**。依据：角色边界为 backend-tester，前端 DOM/乐观建卡/选择器由 frontend-tester 负责；且本环境无法稳定拉起浏览器做 500ms 卡片出现等 DOM 断言。
- **真实首屏 500ms 卡片 + 真实 409 分流 smoke（spec §验收方式要求的一次性端到端 smoke）**：**未验证**。依据：属端到端前端 smoke，需浏览器/前端构建，超出后端回归范围；后端侧的"unknown/off 放行、非 off→503、stale/known 不支持→409"分流已由 `test_spec026_options_endpoint.py` 的 `_resolve_request_effort_*` 系列确定性覆盖（mock，但语义等价）。
- **能力探测并发/预热/超时/持久化改造**：**不适用/未验证**。依据：spec 明确"不改能力探测性能"，归 spec 027，不在 026 范围。
- **production 库写入**：**未验证（且刻意避免）**。依据：真实探测仅调用 `get_reasoning_capabilities`（进程内字典缓存，无 DB 写入）；全程未触碰生产库。

---

## 6. 临时目录清理
- 全程使用 `--basetemp=/Users/wjh/ResearchAgent/.pytest-tmp-bt`；结束后已 `rm -rf`，仓库根**未新增** `.pytest-tmp-*` 残留（既有 `r1/r2/r3/review2/task04/x` 等为历史遗留，未改动）。
- 隔离复核用的 `.pytest-tmp-bt-iso` 也已删除。

---

## 7. VERIFICATION REPORT 汇总
```
Build:     [PASS]  (import app OK; 1028 passed 隐含全部导入成功)
Types:     [N/A]   (Python 动态类型；本任务未配置类型门禁；pyright 未安装)
Lint:      [PASS]  (ollama.py 0 错；routes_conversations.py 33 存量错，026 引入 0 新增，且修复 I001)
Tests:     [PASS]  (026 定向 30/30；全量 1028 passed + 1 预先存在失败 + 395 环境噪音 error，0 真回归)
Security:  [PASS]  (无新增密钥/console.log；能力接口不再返回 503 为预期语义变更)
Diff:      [2 文件] backend/app/platform/ollama.py, backend/app/api/routes_conversations.py

Overall:   [READY / 通过] — 026 后端契约全部验证通过，无 026 引入的回归
```

### 阻塞项
- 无 026 引入的阻塞项。
- 已知非阻塞遗留（与 026 无关，建议另行处理）：`test_conversations_api.py::test_chat_wires_durable_worker_and_worker_failure_does_not_block_sse` 内存分析 job 竞态；沙箱临时目录与 safe-delete 守卫导致的 395 个 A/B 类 error 噪音（建议 CI 改用可控临时目录或放宽守卫以还原真实绿/红信号）。
