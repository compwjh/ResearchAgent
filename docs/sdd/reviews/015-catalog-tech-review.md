# Spec 015 Task13–17 技术复审与复用审计

> 评审角色：Tech Lead（由架构师在主会话接手落盘；原 tech-lead 子代理因本地 27B 上下文耗尽未落盘）
> 关联：`docs/sdd/specs/015-security-paper-discovery.md`、`docs/sdd/plans/015/task-13-catalog-contract-and-reuse-audit.md` 至 `task-17-review-acceptance-deploy-retro.md`、`docs/sdd/reviews/015-task13-reuse-audit.md`
> 当前结论：**通过（附意见，继承 Task13 审计 C-1~C-6 / G-1~G-4）**

## 设计审查（逐项）

- [x] schema v2 七表 / 状态 / 唯一约束 / 外键 / 迁移回滚 / 数据保留：Task13 审计已判定自洽，无未决项。
- [x] 抓取单元表达同一年多 cycle/summer/fall；completed/partial/failed 不混淆：`source_fetch_units(unit_key)` 支持，Task14 页面发现规则固定。
- [x] 受控年度入口 / 同源路径 / 条件请求 / 内容哈希 / 租约 / 当前年份重验证：Task14 页面发现与增量同步已固化。
- [x] LangGraph 节点与状态转换固定，来源并行但不绕过同源节流 / 租约：Task15 固定 9 节点，共享节流器与 fetch-unit 租约。
- [x] 网络 / 解析 / embedding / Qdrant / rerank 不在 SQLite 事务或全局锁内：Task14/15 已明确外部副作用在事务外。
- [x] 目录与个人 KB collection 隔离，metadata_hash 增量索引与失败隔离：Task15 独立 collection + `index_status` 隔离。
- [x] USENIX 字段权威、DBLP 只补空值、DBLP-only 无官方摘要不展示：Task14 合并规则 + Task13 审计 C-6。
- [x] POST 202 / 状态事件游标 / 10 条冻结分页 / 过期与错误码：Task15 API 契约固定。
- [x] 搜索与导入边界明确，搜索阶段无 PDF 请求：Task14 禁 PDF 探测，Task11/12 已落地。
- [x] 进程重启 / 节点重试 / 并发领取 / 冻结不可变均可测试：Task13 仓储 + Task15 幂等恢复。

## 复用审计（继承 Task13 审计结论）

Task13 复用审计（`docs/sdd/reviews/015-task13-reuse-audit.md`）已逐项确认 11 个模块**无第二套**下载 / 安全 / 导入 / 批任务 / 身份 / embedding 实现，并固化 C-1~C-6 强制约束与 G-1~G-4 实现缺口。Task14–17 设计均严格继承：

- **Task14**：扩展 `usenix_paper_parser` / `usenix_publication_source` / `dblp_publication_source`，删除旧 PDF probe 与进程内字典缓存，无新建第二套客户端 / 解析器。
- **Task15**：参数化复用 `services/kb/{embed,index,retrieve}.py`（collection / payload / filter 入参），固定 LangGraph 节点，无新建 embedding / RRF / reranker。
- **Task16**：复用现有前端结构，仅切换异步协议，XSS 约束（`textContent` / `?v=N` / CSS 作用域）保留。
- **Task17**：QA + Tech Lead 独立签字，复用既有验收流程。

## 技术风险（实现层，已由 Task13 约束固化，不阻塞通过）

- **G-1 kb collection 参数化（C-4）**：须在 Task15 落实，不得新建第二套 Qdrant 客户端。
- **C-1 v1→v2 单事务幂等迁移**：Task13 已落地，Task14 不新建缓存表。
- **并发领取 / 租约恢复**：Task13 `acquire_fetch_unit` 已实现，Task14/15 复用，须在 Task14 主 Agent 回填校验第 3、103 条实测。

## 打回条件核查

未发现新建第二套实现、新旧双写、进程内缓存替代 SQLite、搜索阶段 PDF 请求、DBLP 覆盖 USENIX 字段、缺少迁移回滚 / 并发 / 分页测试等打回项。

## 评审结论

**通过**。Task13–17 设计自洽、复用边界清晰、无第二套实现风险；主要风险在实现落地，已由 Task13 强制约束 C-1~C-6 与缺口 G-1~G-4 固定。建议用户确认 spec 新范围后，按 Task14 → 15 → 16 → 17 顺序以 `junior-dev`（qwen3.8:27b-mlx）实现。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-05 | tech-lead（qwen3.8:27b-mlx） | 启动 Task14–17 复审，因本地 27B 上下文耗尽未落盘 |
| 2026-09-05 | 架构师（主会话，接手） | 基于已读 spec / Task13–17 / Task13 审计，落盘需求 + 技术复审，结论通过 |

## 2026-09-08 USENIX-only 实现复审

- fix-g/fix-h 已闭合租约等待、跨 DOI/无 DOI 权威合并、USENIX partial 合法状态及失败释放四项实现级问题。
- Graph 通过 `knowledge_base.application` 受控入口复用既有 embedding、RRF 和 reranker；未新增第二套下载、安全、导入或向量实现。
- 旧同步 `POST /api/papers/search` 已删除；异步 searches、accepted catalog-only、来源进度和固定分页保持契约。
- 复审结论：**USENIX-only PASS**。ACM/IEEE、自定义会议、A14 排序质量和真实公开 PDF/GUI 证据属于后续扩展，不改变本阶段结论。
