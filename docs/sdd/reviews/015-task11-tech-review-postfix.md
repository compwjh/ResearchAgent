# Spec015 Task11 技术复评（修订后，Tech Lead）

- 评审角色：开发主管（Tech Lead）
- 评审模型：自身（本次调度要求：`gpt-5.6-luna/high`）
- 评审时间：2026-09-05（Asia/Shanghai）
- 适用 Skill：`.agents/skills/usenix-accepted-papers/SKILL.md`
- 评审范围：前次 Task11 技术评审四项修订；USENIX parser/source、arXiv adapter、search 去重与阶段合并、API 默认年份、来源字段/SQLite、定向安全与旧回归
- 评审约束：只读复核；未修改业务代码、测试或配置，未执行 reset/stash/clean/commit/push
- 进展日志：`.codebuddy/agent-logs/techlead-spec015-task11-postfix-20260905.md`

## 结论

**阻塞，暂不通过（仅剩一个 P1 修复项）。**

前次提出的四项阻塞均已实际修订并有回归证据：API 默认年份、USENIX cache/节流、统一安全 PDF probe、作者集合与出版阶段去重均通过复核。当前唯一剩余问题是 probe 将“带 `%PDF-` 前缀但不可读取的截断/损坏文件”当作可用，从而阻断规定的 prepublication → 严格 arXiv 回退。Spec015 及 Task11 计划仍标记 `待确认/待确认`，本报告是实现复评，不改变该流程状态。

## 修订项复核

| 前次项 | 实际证据 | 结论 |
|---|---|---|
| T11-B1 默认完整年份 | `backend/app/api/routes.py:452-456` 默认传入 `range(current_year-default_years, current_year)`；显式未来年份返回 `INVALID_ACCEPTED_YEAR` | 已修复 |
| T11-B2 USENIX cache/节流 | `usenix_publication_source.py:57-76,138-180,216-231` 使用线程安全 TTL cache、按 route `rate_limit_seconds` 预约；重复查询不再访问列表/详情/PDF | 已修复 |
| T11-B3 SSRF/下载探测 | `usenix_publication_source.py:150-180` 复用 `download_candidate()`，固定 `www.usenix.org`，不跟随外域重定向，使用统一大小/响应头/严格 `%PDF-` 约束 | 基本已修复；见 P1 |
| T11-B4 去重与阶段 | `paper_discovery_search.py:264-269,364-430` 加入规范化作者集合；阶段优先级 `published > accepted > prepublication`，合并保留来源链接 | 已修复 |

## 剩余阻塞

### T11-P1：PDF probe 未验证页面可读性，无法可靠触发回退

`backend/app/services/usenix_publication_source.py:157-166` 调用统一下载器时传入 `validate_pdf_pages=False`。统一下载器在该模式下只做 URL/重定向/大小/响应头和 `%PDF-` 魔数检查，不调用页数/可读取性校验。因此，响应体为截断或损坏内容但恰好以 `%PDF-` 开头时，`_get_pdf()` 会返回 `True`；`_preferred_pdf()` 随后选择正式 URL，不会尝试页面提供的 prepublication PDF，更不会进入 arXiv 兜底。这与 Task11 “正式 PDF 缺失或无效时回退”不一致。

最小修复：probe 必须启用统一页可读性校验（或注入等价的轻量 PDF page validator），任何 `INVALID_PDF` 都视为 probe 失败并继续 prepublication → arXiv。新增冻结 fixture：正式响应 `%PDF-` 但不可读取、prepublication 为可读取 PDF，断言选择 prepublication；并保留现有伪 `%PDFx`、超限、外域重定向测试。修复后重新运行 Task11 全链路与下载安全回归。

## 已通过的验证与边界

- 实际定向回归：`92 passed, 5 warnings, 9 subtests passed`，退出码 0。
- 相关 8 个 Python 实现文件 `py_compile` 通过；`git diff --check` 通过。
- USENIX allowlist、列表显式 presentation 链接、正式→prepublication→arXiv 顺序、arXiv 标题/作者/年份严格阈值、固定 arXiv origin、有限重试/3 秒节流、来源字段和 SQLite 迁移均有离线证据。
- API 不接受客户端 listing/PDF URL；accepted 查询默认年份已排除当前未完成年份；跨来源同 DOI/标题+作者+年份合并不会以低阶段覆盖 published。
- 这些是 fixture/注入 resolver/MockTransport 证据，不替代真实 USENIX 外网、DNS rebinding、peer 绑定和运行时服务验收；这些仍属于 QA/集成门禁。

## 非阻塞遗留风险

- `UsenixAcceptedSource._route()` 在没有 `discovery_routes` 时保留 1 秒默认路线；公共 API 另有服务端 route 配置检查，但建议未来让 application 层统一拒绝未配置 accepted route，避免直接 service 调用绕过配置语义。
- `_get_text()` 对 HTML 页做 allowlist/DNS 校验但没有显式 peer resolver；生产默认 HTTP client 通常提供连接扩展，真实环境仍需 QA 记录 peer/DNS 证据。
- 运行环境的真实 USENIX 页面 DOM、公开 PDF、arXiv 限流和实际网络重定向尚未做外网验收；不应由本离线技术复评升级为完整 acceptance。

## 必须补齐后再复评

1. 修复并测试可读取页面校验，确保损坏 `%PDF-` 正式文件触发 prepublication/arXiv 回退。
2. 复跑 Task11 source/parser/arXiv/search、下载安全、批量导入、旧 KB 和 API 回归，并保留真实退出码。
3. 在 Spec015/Task11 流程门禁确认后，再由 QA 完成真实来源与运行时验收。

## 签字

- 开发主管（Tech Lead）：**当前协作 Agent，签字：阻塞，暂不通过**
- 签字时间：2026-09-05（Asia/Shanghai）
