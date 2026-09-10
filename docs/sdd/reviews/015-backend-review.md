# 后端评审：Spec015 USENIX accepted-papers URL slug 修复

- **评审者**：架构师（自身，主会话代执行；本地模型 `backend-reviewer` 子代理因电脑重启中断，两次日志均止于步骤 1）
- **评审对象**：提交 `ff01f3d`（`backend/app/services/usenix_publication_source.py` +55/-11）与 `79dc170`（`tests/test_usenix_publication_source.py` +110）
- **评审时间**：2026-09-06（Asia/Shanghai）
- **评审方式**：只读评审。已核对完整 diff、改动文件全文、调用链（`api/routes.py` → `PaperDiscoverySearchService` → `UsenixAcceptedSource`）与请求模型校验；未修改业务代码、测试、spec 或 git 状态。
- **关联**：[Spec015](../specs/015-security-paper-discovery.md)（状态 `已确认`，Task14 实施中）

## 结论：WARNING（可合并，附强制约束）

修复方向正确且对外契约未变：HTTP 路径、错误码 `USENIX_UNAVAILABLE`、warnings 语义与改动前等价，仅内部 slug 解析与聚合逻辑改善。2022-2024 由固定请求 `cycle1`（404 → 整次 424）改为按年份解析 `summer`/`fall`，并顺带修复了 `cyclecycle1`/`cyclesummer` 拼接与 `_listing_for` 的 URL 嵌套错误。

存在 1 项 HIGH：本提交第二个修复点 `_listing_for` 的新正则路径**没有任何回归测试锁定**。该问题不阻塞本次合入，但须作为下一提交的强制项。

## 代码事实核对

| 事实 | 位置 | 核对结论 |
|---|---|---|
| slug 按年份解析 | `usenix_publication_source.py:277-282` `_cycles_for_year`：≥2025 → `("cycle1",)`，否则 `("summer", "fall")` | 与提交说明一致；`_discovered_pages:349-361` 复用同一函数，搜索路径与 Task14 同步路径的页面集合一致 |
| URL 归一化 | `_listing_url:284-297`：裸数字补 `cycle` 前缀 + 剥离模板字面量 `cycle{cycle}` 前缀 | 默认模板已由 `cycle{cycle}` 改为 `{cycle}`，配合归一化后 `cycle1` 产物与旧行为**逐字一致**；`summer` 不再拼成 `cyclesummer` |
| 按年聚合与失败判定 | `search:120-132` 展开 listing；`search:179-189` 仅当某年全部 slug 失败才计 failed year | `error` 仍为「全部年份失败」，`warnings` 仍为去重后的单个 `USENIX_UNAVAILABLE`，**对外契约无变化** |
| `_listing_for` 修复 | `usenix_publication_source.py:363-376`：由 `(\d{2})/(.+)` 改为精确匹配 `(cycle\d+|summer\|fall)-accepted-papers`，并改走 `_listing_url` | 修复了把 `summer-accepted-papers` 整体塞进 `{cycle}` 的嵌套错误；**无测试覆盖**（见 HIGH） |
| 输入可控性 | `api/schemas.py:63` `cycle` 受 `^cycle[1-9][0-9]*$` 约束；`api/routes.py:459` 再 `removeprefix("cycle")` | API 路径传入的 cycle 只能是纯数字，无法注入路径片段 |
| SSRF 与同源 | `_get_text:200`、`_fetch_listing:384` 均 `validate_url(allowed_hosts={"www.usenix.org"})`；`follow_redirects=False` | 新增 slug 仅来自类常量或受控入参，未放宽白名单 |
| 重复实现 | 搜索路径 `_get_text` 与同步路径 `_fetch_listing` 仍并存 | 属既有设计；本次反而让两者共享 `_cycles_for_year`，**减少**了重复 |

## 问题清单

### [HIGH] `_listing_for` 的新正则路径无回归测试

File: `tests/test_usenix_publication_source.py`（新增测试未覆盖）；代码 `backend/app/services/usenix_publication_source.py:363-376`

Issue: 提交同时修了两处，第一处（按年份解析 slug）有 6 个测试锁定，第二处 `_listing_for` 的正则与 `_listing_url` 委派**一个测试都没有**。该路径只在 Task14 `sync_usenix_units` 中使用，一旦回退成旧的 `(\d{2})/(.+)` 写法，同步会静默生成 `.../cyclesummer-accepted-papers` 之类 URL 并全部 `USENIX_FETCH_FAILED`，且本地全量测试仍会通过。

Fix: 补两条纯单元测试（MockTransport 或注入 route 即可，无需外网）：
1. `_listing_for("/conference/usenixsecurity24/summer-accepted-papers", ROUTED_SOURCE_TEMPLATE)` 返回 `https://www.usenix.org/conference/usenixsecurity24/summer-accepted-papers`，断言不含 `-accepted-papers-accepted-papers` 与 `cyclesummer`；
2. `_listing_for` 对无模板 route 返回原 page，对非 accepted 路径同样原样返回。

### [MEDIUM] 显式 `cycle=cycle1` 与不传 cycle 行为相同，且该分支无测试

File: `backend/app/services/usenix_publication_source.py:126-127`；`backend/app/api/routes.py:459`

Issue: `explicit_cycle` 把 `"1"` 视为默认值而置为 `None`，因此对 2022-2024 显式传 `cycle1` 也会改抓 `summer`+`fall`。这是修复的必然取舍（这些年份本无 cycle1 页面），但意味着 `cycle` 参数对 2022-2024 实际不具备过滤语义，且该分支（含 `cycle=cycle2` 的 legacy 单 listing 行为）没有任何测试锁定。

Fix: 用测试固定当前语义（显式 `cycle2` → 仅请求 `cycle2`；显式 `cycle1` → 与缺省等价），并在 accepted 接口文档/错误提示中说明 cycle 的生效范围。

### [MEDIUM] `_cycles_for_year` 缺少适用年份下界

File: `backend/app/services/usenix_publication_source.py:274-282`

Issue: 规则为「≥2025 → cycle1，其余 → summer+fall」。当前默认检索窗口是 `[current_year-5, current_year)`，即包含 2021；2021 及更早年份的 listing 形态未纳入规则，大概率 404，导致默认窗口内常驻一个失败年、`warnings` 恒含 `USENIX_UNAVAILABLE`（`error_code` 仍为 None，不 424，故不影响主流程）。

Fix: 明确受控年份下界（例如 2022 起），对界外年份直接跳过或归入显式降级说明，避免常驻噪声告警掩盖真实故障。

### [LOW] `_listing_for` 允许集与 `_accepted_path_ok` 不一致

File: `backend/app/services/usenix_publication_source.py:342-345` vs `372`

Issue: `_accepted_path_ok` 允许 `cycle\d+|summer|fall|accepted`，`_listing_for` 正则只有 `cycle\d+|summer|fall`。`accepted` slug 页面会走「返回原 page」分支（仍可抓取），当前 `_discovered_pages` 不会生成该 slug，故不可达；但两处集合不一致，后续任一方改动易产生静默不一致。

Fix: 抽公共 slug 集合常量，或为 `accepted` 分支写明「故意不套模板」的注释与测试。

### [LOW] 达到 limit 后仍抓取剩余 listing（既有行为，非本次引入）

File: `backend/app/services/usenix_publication_source.py:133-142`

Issue: 内层 detail 循环 `break` 只跳出当前 listing，外层仍会为剩余 slug 各发一次 listing 请求（受 rate limit 约束）。2024 年两个 slug 的代价可接受，但年份一多会放大。

Fix: 外层加 `if len(records) >= limit: break`。属优化项，可择机处理。

### [LOW] 部分年份失败时整体不写缓存（与改动前一致，未退化）

File: `backend/app/services/usenix_publication_source.py:191-193`

Issue: `warnings` 非空即不缓存，故只要有一个年份失败，相同查询每次都会全量重抓所有年份。改动前同样如此，非本次引入；仅在「常年失败年份 + 默认 5 年窗口」组合下会放大请求量。

Fix: 可考虑仅缓存成功年份的结果并保留 warning，或为失败年份单独设置较短 TTL。

### [LOW] 测试 fixture 年份与场景不一致

File: `tests/test_usenix_publication_source.py:250-267`

Issue: `test_partial_slug_failure_keeps_year_available` 用 2024 场景，但 `DETAIL` 常量是 `usenixsecurity25/presentation/demo`、`DETAIL_HTML` 的 `citation_publication_date` 为 2025。handler 按路径后缀匹配故能通过，不影响被测行为（slug 解析），但读起来会误导。

Fix: 新增 2024 专用 detail 常量，或加注释说明「此处只校验 slug 解析，不校验年份」。

## 安全与契约核对（通过）

- **SSRF**：外发 URL 仍由 `validate_url(allowed_hosts={"www.usenix.org"})` 把关，新增 slug 值来自类常量或受 `^cycle[1-9][0-9]*$` 约束的入参；无新增用户可控 host/路径输入。
- **重定向**：`_get_text` 与 `_fetch_listing` 保持 `follow_redirects=False`。
- **对外契约**：`error_code` 判定（`failed_years == len(selected_years)`）与 warnings 去重语义与改动前等价；API 层 `routes.py:489` 的 424 触发条件不变。
- **分层与时间**：未向 `domain/` 引入 FastAPI/HTTP 依赖；本次改动不含时间戳逻辑，UTC 约定不受影响。
- **禁止重复实现**：未新增第二套下载/安全/导入实现，且跨路径复用了 `_cycles_for_year`。

## 回归证据

```bash
/Users/wjh/ResearchAgent/.venv/bin/python -m pytest tests/ -q
# 619 passed, 38 subtests passed, 5 warnings in 130.78s
```

与提交 `79dc170` 记录的 619 passed 一致，无回归。

## 强制约束清单（下一提交必须满足）

1. 补齐 `_listing_for` 的两条单元测试（HIGH 项）。
2. 为显式 `cycle` 分支补测试，固定「cycle1 = 缺省、cycle2 = 仅 cycle2」语义。
3. 明确受控年份下界并在代码或文档中写明，消除默认窗口内的常驻告警。
4. 保持 `validate_url` 白名单与 `follow_redirects=False`；任何新增 slug 必须来自常量或受控入参。

## Review Summary

| Severity | Count | Status |
|---|---|---|
| CRITICAL | 0 | pass |
| HIGH | 1 | warn |
| MEDIUM | 2 | warn |
| LOW | 4 | info |

Verdict: WARNING — 1 个 HIGH（新代码路径无测试）应在下一个提交补齐；无阻断缺陷，本次可合入。

## 整改闭环（2026-09-06，提交 `8a26e29`）

| 评审项 | 处置 | 证据 |
|---|---|---|
| HIGH：`_listing_for` 无测试 | 已补 `test_listing_for_applies_template_to_summer_slug`、`test_listing_for_returns_original_page_without_template` | `tests/test_usenix_publication_source.py:306-319` |
| MEDIUM：显式 cycle 分支无测试 | 已补 `test_explicit_cycle_requests_only_that_cycle`、`test_explicit_cycle1_matches_default_behavior`，固定「cycle1 = 缺省、cycle2 = 仅 cycle2」 | 同上 `:322-355` |
| MEDIUM：受控年份下界 | 已实现 `USENIX_MIN_YEAR = 2022`，界外年份不产生 listing 也不计失败；years 非空且全部界外时置 `error_code = "USENIX_UNAVAILABLE"` | `backend/app/services/usenix_publication_source.py:277` 起 |
| LOW：fixture 年份串味 | 新增 2024 专用 `SEC24_DETAIL` / `SEC24_DETAIL_HTML`，不再复用 2025 常量 | 测试文件 `:297-303` |

**落地校验发现并修正的子代理问题**（回传未提及）：新增分支误用 2 空格缩进（与全文件 4 空格递增不一致，后续插入代码极易 `IndentationError`）、一段已过期的旧注释与新逻辑并存。

**回归**：`.venv/bin/python -m pytest tests/ -q` → **626 passed / 38 subtests passed / 0 failed**（基线 619 + 新增 7）。

> 注：`backend-tester` 子代理曾回报「全量 pytest 因 `langchain_ollama` 缺失无法运行」并判 A1 FAIL；主会话用 venv 复核为伪失败（该依赖在 venv 中存在）。详见 `docs/sdd/retro/2026-09-06-backend-review-handover.md`。

**结论更新**：WARNING 的三项（1 HIGH + 2 MEDIUM）已全部闭环，本批次改动可进入验收；LOW 项中的优化建议（limit 提前 break、部分失败缓存策略）未处理，属可选改进。
