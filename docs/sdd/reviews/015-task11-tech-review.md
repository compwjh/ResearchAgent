# Spec015 Task11 技术评审（Tech Lead）

- 评审角色：开发主管（Tech Lead）
- 评审模型：自身（本次调度要求：`gpt-5.6-luna/high`）
- 评审时间：2026-09-05（Asia/Shanghai）
- 评审范围：Task11 计划及四份实现报告；USENIX parser、arXiv adapter、USENIX source/search 接线、PaperCandidate/ConferenceSource 字段、SQLite 迁移、API routes/schemas；Task11 定向测试、下载安全/导入旧回归
- 评审约束：只读复核；未修改业务代码、测试或配置，未执行 reset/stash/clean/commit/push
- 进展日志：`.codebuddy/agent-logs/techlead-spec015-task11-review-20260905.md`

## 结论

**阻塞，暂不通过（打回实现修订）。**

基础切片已具备固定 USENIX/arXiv origin、USENIX 显式链接解析、arXiv 标题/作者/年份严格阈值、来源阶段字段和 SQLite 向后兼容迁移；定向回归也通过。但当前实现尚未满足 Task11 的默认年份边界、USENIX 缓存/节流和 PDF 安全探测契约，并存在跨来源合并后错误覆盖 `publication_stage` 的风险，因此不能签字放行。

## 已复核通过的部分

| 维度 | 证据 | 判定 |
|---|---|---|
| USENIX 列表/详情 allowlist | `usenix_paper_parser.py` 只接受 HTTPS `www.usenix.org`，列表只保留显式 `/conference/.../presentation/...`，详情 PDF 不猜路径并保留正式/prepublication 两类链接 | 通过（离线） |
| arXiv 严格匹配 | `arxiv_adapter.py:152-167` 同时校验标题阈值 0.90、作者集合阈值 0.80 和年份相等；abs/PDF 只接受两个 arXiv HTTPS origin | 通过（离线） |
| 来源字段与迁移 | `PaperCandidate` 追加 publication/source/arXiv/source_links；store 对旧表执行幂等 `ALTER TABLE`/重建迁移，旧值默认为 `published`/`dblp` | 通过（离线） |
| API 输入边界 | `PaperAcceptedRequest` 使用受控 year/cycle/q/limit 且 `extra="forbid"`，不接受客户端 listing URL；错误体沿用固定四字段 | 通过（契约局部） |
| 基线回归 | 目标命令实际 `83 passed, 5 warnings, 9 subtests passed`；相关实现 `py_compile` 与 `git diff --check` 通过 | 通过（不等于 Task11 放行） |

## 阻塞项

### T11-B1：accepted API 默认年份违反“最近五个完整年份”（P1）

`backend/app/api/routes.py:452-455` 在未提供 `year` 时使用 `range(current_year - default_years + 1, current_year + 1)`。当前年份为 2026、默认值为 5 时，传给 source 的是 `[2022, 2023, 2024, 2025, 2026]`，把尚未结束的 2026 纳入默认结果；Spec015 明确要求默认完整年份为 2021–2025，不自动包含 2026。搜索 service 自身的 `years is None` 分支使用的是不包含当前年的范围，API accepted 路由与其不一致。

修复要求：accepted endpoint 默认年份改为与 Spec015/search service 一致的 `range(current_year-default_years, current_year)`；显式 `year` 仍可按产品规则单独校验上界，并补 API 回归断言传入年份列表。

### T11-B2：USENIX route 配置的缓存和节流没有实现（P1）

`backend/app/services/usenix_publication_source.py:32-40` 未保存或读取 `ConferenceSource.discovery_routes` 的 `rate_limit_seconds`；`:50-69` 每年重新抓列表和详情，`:108-125` 又直接探测 PDF。source 没有按列表/详情/PDF URL 或查询做缓存，也没有 USENIX 请求间隔控制。重复点击 accepted 查询会重复抓取同一列表、详情和 PDF，违反 Spec015 “accepted 列表与元数据按 URL/查询缓存、禁止高频重复抓取”，并使 `USENIX_DISCOVERY_ROUTES` 中声明的 1 秒限制成为无效配置。

修复要求：实现受控、线程安全的 URL/查询缓存和最小请求间隔，读取服务端 route 配置；缓存命中不得发起网络请求，异常结果按可重试策略处理，并用 fixture/并发测试证明相邻 USENIX 请求满足间隔。

### T11-B3：PDF 可用性探测绕过统一下载安全边界，且会误判无效 PDF（P0/P1）

`backend/app/services/usenix_publication_source.py:108-113` 的 `_get_pdf()` 直接对页面显式 URL 执行 `client.get()`，将整个响应放入 `response.content`，只判断 `200–299` 和 `startswith(b"%PDF")`。这条探测链没有复用 `paper_download.download_candidate()`/`paper_download_security.validate_url()` 的 allowlist、DNS 公共地址/peer 复核、重定向逐跳校验、响应头 64 KiB、64 MiB 总大小和 120 秒总超时；注入或配置了自动跟随重定向的 client 时还可能扩大实际请求目标。并且 `%PDFx...` 会被当作可用，而统一下载器要求 `%PDF-`，因此正式链接返回伪魔数时不会回退到 prepublication/arXiv，最终在导入阶段才失败。

修复要求：不要在 source 内另起不受限的 PDF 下载器；使用统一下载安全组件做受限 probe/下载（或实现同等逐跳、大小、魔数和 peer 校验），严格使用 `%PDF-`，任何不合法或超限响应都必须继续 prepublication → arXiv 路线。补充伪 PDF、超限、重定向、DNS/peer 和自动跟随开关测试。

### T11-B4：跨来源去重身份和出版阶段优先级不满足契约（P1）

`backend/app/services/paper_discovery_search.py:255-260` 及 `:350-380` 的 fallback identity 仅为规范化标题+年份+会议，不包含作者集合；同标题同年同会但作者不同的论文会被错误合并。更重要的是 `_merge_candidate()` 仅按 abstract/pdf/doi 丰富度替换候选，未把 `published` 阶段、DBLP/USENIX/arXiv 来源优先级纳入决策；在 `publication_scope=all` 下，拥有更丰富 PDF 的 accepted/prepublication 记录可能替换已发表记录，导致同一论文最终候选被标成 `accepted`/`prepublication`，而不是保留已发表优先并合并全部来源链接。

修复要求：fallback identity 按规范化标题+作者集合+年份（并保持 DOI/DBLP key 优先）；合并时显式定义并测试 publication stage/source priority，至少已发表记录不能被 accepted/prepublication 覆盖，且多个受控来源链接仍完整保留。

## API 与错误降级复核

- `POST /api/papers/search` 已把 `publication_scope` 透传至 search service；`published` 默认兼容旧路径，`accepted/all` 的 USENIX 异常以 warning/稳定错误码降级，方向正确。
- `GET /api/papers/conferences/{conference_id}/accepted` 使用服务端 source route，不接收任意 URL，保存 opaque `search_id/candidate_id` 快照；但目前通过 `service._candidate_from_record` 私有 helper 接线，后续 service 重构容易破坏 API，建议抽成公开 application 用例。
- accepted 路由 schema 的 `year` 只设下界，没有拒绝未来年份；如果产品不允许抓取未来 USENIX cycle，应补与 search service 一致的当前年份上界和稳定错误码。
- Task11 当前实际测试文件中没有覆盖上述 accepted API 默认年份、route cache/rate limit 或完整来源探测安全边界；已有 83 项通过应视为离线基础回归，不应作为 Task11 端到端放行证据。

## 其他遗留风险（不改变本次打回）

- `arxiv_adapter.py:169-176` 在节流等待期间持有锁；网络 I/O 不在该锁内，但并发调用会在锁内 sleep，可能造成不必要的调用者串行等待。应采用锁外计算/条件唤醒或明确单 flight 设计，并测试并发缓存命中。
- parser 用整页文本的第一个 `20xx` 年份作为 fallback，若页面头部/导航先出现其他年份，可能记录错误论文年份；建议优先结构化 publication date 并限定会议年份路径。
- `source_links` 和来源字段在 store 中按 JSON 持久化，当前上层依赖 adapter 保证 URL 安全；应在快照边界再次校验受控 origin，避免未来注入式 source 或重构绕过 allowlist。

## 必须补齐后再评审

1. 修复默认完整年份，并新增 API 传参回归。
2. 为 USENIX 列表/详情/PDF 实现配置驱动的缓存与节流，补重复查询和并发证据。
3. 将正式 PDF → prepublication → arXiv 的探测纳入统一 PDF/SSRF 安全边界，补 `%PDF-`、大小、重定向与 peer/DNS 测试。
4. 按作者集合和出版阶段优先级修复跨来源去重，补 `publication_scope=all` 的已发表/accepted 冲突 fixture。
5. 完成上述修复后重跑 Task11 全链路、下载安全、批量导入、旧 KB/API 回归，再申请 tech-lead 复评。

## 签字

- 开发主管（Tech Lead）：**当前协作 Agent，签字：阻塞，暂不通过**
- 签字时间：2026-09-05（Asia/Shanghai）
