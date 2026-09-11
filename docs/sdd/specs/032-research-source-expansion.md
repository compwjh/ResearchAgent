# Spec 032 — Research Task 数据源与安全会议扩展

## 状态

**当前状态：待确认**

## 一句话目标

在不改变 Research Task 主流程和既有下载安全语义的前提下，以统一 Source Adapter 接入 OpenAlex、Crossref 及 IEEE S&P、ACM CCS、NDSS 官方论文目录，并保留来源权威级别、增量缓存和字段级 provenance。

## 背景与依赖

- Spec027 首版只使用 USENIX Security 与 DBLP，无法覆盖更广泛科研主题。
- README 中已有 Crossref/OpenAlex 能力，但与 Spec015 全局论文目录和异步增量流程并非同一来源契约。
- 本 Spec 依赖 Spec027 的 Research Task、Spec015 的目录模型；不重新设计 Planner、报告或全文导入。

## Source Adapter 合同

| 字段/方法 | 约束 |
|---|---|
| source_id / source_kind | 稳定、全局唯一 |
| authority_rank | 官方会议 > 官方 DOI 元数据 > 聚合书目来源 |
| discover_units(scope) | 返回年份/cycle/track 等持久化抓取单元 |
| fetch_unit(unit, conditional_headers) | 支持 ETag/Last-Modified/内容 hash 与超时 |
| parse_catalog(response) | 标题、摘要、关键词、作者、年份、DOI、页面/PDF 地址及 provenance |
| normalize_identity(record) | 复用现有 DOI/标题规范化和去重 |
| health() | 安全、脱敏、无下载副作用 |

## 数据模型增量

| 实体 | 关键字段 | 约束 |
|---|---|---|
| SourceDefinition | source_id、kind、authority_rank、enabled、allowed_hosts | 服务端受控配置 |
| SourceFetchUnit | source_id、scope_key、etag、last_modified、content_hash、status | 复用/扩展 Spec015，不建平行缓存 |
| FieldProvenance | paper_id、field_name、source_id、source_record_id、observed_at | 高权威字段不能被低权威覆盖 |
| SourceCoverage | task_id、source_id、requested_units、cached/fetched/failed | 提供 Research Task 进度卡片 |

## 来源范围

- 学术聚合：OpenAlex、Crossref；DBLP 继续作为辅助书目信息来源。
- 安全会议官方目录：USENIX Security（既有）、IEEE Symposium on Security and Privacy、ACM CCS、NDSS。
- 官方页面字段优先；聚合来源只补缺失 DOI、作者或书目信息，不能覆盖更高权威的标题、摘要、关键词和官方链接。
- 搜索阶段只保存目录元数据，不探测或下载 PDF；下载仍走 Spec029/既有安全链。

## 接口

| 动作 | 输入 | 成功返回 | 失败 |
|---|---|---|---|
| GET /api/papers/sources | filter | 来源、能力、健康和缓存范围 | 503 store |
| PATCH /api/papers/sources/{id} | enabled | 更新受控启停 | 404；409 内置约束 |
| POST /api/papers/sources/{id}/sync | scope | 202 既有目录同步任务 | 400；409；503 |
| Research Task Planner source 参数 | source_ids/scope | 只接受启用且允许的来源 | 422 未知来源 |

## 边界与失败场景

- 页面结构变化、周期页拆分、摘要/关键词缺失、限流、ETag 异常、重复 DOI、同名论文和来源冲突。
- 单源失败不得清空旧缓存；页面内容未变化不重复向量化。
- URL、DNS、重定向与 SSRF 规则继续复用既有平台能力；Planner 不能传任意根 URL。
- 新来源必须具备固定 HTML/JSON 样本和 provenance 测试后才能启用。

## 明确不做

- 不让用户添加任意网站或自定义爬虫。
- 不在搜索阶段下载/验证 PDF，不绕过登录或反爬。
- 不改 Research Task 停止规则、模型路由、报告语义和个人知识库 Collection。

## 验收方式

- 每个来源使用固定样本验证列表发现、详情解析、缺失字段、分页/年度单元和字段 provenance。
- 重复范围只抓取新增/变化/失败/过期单元；服务重启和目录索引重建后缓存仍成立。
- 来源冲突按 authority_rank 合并，低权威来源不能覆盖官方字段。
- 单源失败时 Research Task 显示对应状态并使用其他来源；最终 Task 一次全量回归和部署。

## 产品使用步骤（由产品经理在 Spec 确认后填写）

- 待确认后补充来源选择、同步进度、缓存提示和降级旅程。

## 执行配置

| 角色 | 选用模型 | 上下文上限 | 分派方式 | 职责 |
|---|---|---|---|---|
| 架构师 | 自身 | 200k | 主会话 | 来源权威和复用边界 |
| 产品经理 | `qwen3.5:9b` | 32k | `Task(doc-updater)` | 来源选择与进度旅程 |
| 开发主管 | `qwen3.8:27b-mlx` | 32k | `Task(architect)` | Adapter、安全和去重评审 |
| 初级开发 | `qwen3.8:27b-mlx` | 32k | 分端开发 Agent | 来源适配器和界面实现 |
| 测试 | `qwen3.5:9b` | 32k | 分端 tester + `Task(tester)` | 固定样本和集成验收 |

## 任务计划

| 编号 | 任务 | 文档 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 Spec032 | 本文件 | — | 完成 |
| 02 | 冻结 Adapter、provenance 与增量协议 | [`task-02-source-adapter-contract.md`](../plans/032/task-02-source-adapter-contract.md) | Spec027/015、确认、双评审 | 待执行 |
| 03 | 接入 OpenAlex 与 Crossref | [`task-03-openalex-crossref-adapters.md`](../plans/032/task-03-openalex-crossref-adapters.md) | 02 | 待执行 |
| 04 | 接入 IEEE S&P、ACM CCS 与 NDSS | [`task-04-security-conference-adapters.md`](../plans/032/task-04-security-conference-adapters.md) | 02 | 待执行 |
| 05 | 接通来源合并、任务进度与界面 | [`task-05-source-merge-progress-ui.md`](../plans/032/task-05-source-merge-progress-ui.md) | 03、04 | 待执行 |
| 06 | 最终评审、回归、部署与复盘 | [`task-06-review-regression-deploy.md`](../plans/032/task-06-review-regression-deploy.md) | 02–05 | 待执行 |

## 评审记录

- 需求评审：`docs/sdd/reviews/032-requirement-review.md`（待评审（未执行））
- 技术评审：`docs/sdd/reviews/032-tech-review.md`（待评审（未执行））
- 验收评审：`docs/sdd/reviews/032-acceptance-review.md`（待评审（未执行））

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-12 | 架构师（自身） | 创建聚合来源和四大安全会议扩展 Spec |
