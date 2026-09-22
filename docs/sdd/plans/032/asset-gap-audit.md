# Spec032 / 032.1 资产与缺口审计（2026-09-20）

> 本文是修订 [Spec032](../../specs/032-research-source-expansion.md) 的事实输入，不等于已通过的验收。审计只读；其他 Agent 的 Spec031/034 在途修改不纳入本次改动范围。

## 判定口径

- **已有代码**：入口、解析器或测试存在；不等于产品 Worker 可以调用。
- **已接线**：Research Graph / Tool / API / SQLite / UI 能贯通；不能以注册表中的一行配置代替。
- **已验证覆盖**：固定样本及受控真实运行均有证据；代码的 `MIN_YEAR` / `MAX_YEAR` 只表示参数边界。
- **已导入**：正确 PDF 经过既有安全下载、身份核验和知识库索引；发现 PDF URL 或通过 `%PDF-` 检查都不算。

## 可复用代码与 Skill

| 资产 | 现有位置与用途 | 复用前需处理 |
|---|---|---|
| 聚合 Adapter 合同、OpenAlex/Crossref | `backend/app/paper_discovery/infrastructure/aggregate_source_adapters.py`：发现单元、抓取、解析、规范化 | 与会议 Source 的参数/返回类型统一；`health()` 不得发起隐式网络请求；统一 URL 校验、权威级别 |
| IEEE S&P、CCS、NDSS 来源与解析器 | `*_publication_source.py`、`*_paper_parser.py`：Crossref 枚举、OpenAlex 富化、逐年单元 | 加入官网目录优先路径，保留现有聚合路径为兜底；统一 ID、结果和 provenance；接入 Graph/Store |
| USENIX 目录和详情 | `usenix_publication_source.py`、`usenix_paper_parser.py`：年份/cycle、详情摘要、FetchUnit | 统一返回字段；搜索不得调用 PDF 探测；接入同一来源契约 |
| 全局目录、抓取单元、字段来源表 | `paper_discovery_store.py`：SQLite 租约、缓存、来源记录、`field_provenance` | provenance 目前主要接 DBLP，合并论文时需同步处理字段来源；新来源需实际落库 |
| 来源注册表与 API 草案 | `source_registry.py`、`routes_paper.py`：七来源配置、`/api/papers/sources` | 目前无 Adapter 工厂；`POST /sync` 只返回 queued，未真正调度；健康和缓存范围尚非真实投影 |
| 产品 Skill 与 Tool | `.agents/skills/usenix-{catalog,download}-orchestration/SKILL.md`、`backend/app/skills/{registry,tool_dispatch}.py` | 仅 USENIX 有详情 Tool；检索 Tool 枚举仍为 USENIX/DBLP；统一结构化输入/输出及来源专用策略 |
| 旧 USENIX Skill | `.agents/skills/usenix-{accepted-papers,paper-catalog-search}/SKILL.md` | 已标 legacy；保留追溯，但不得作为新 Worker 协议，也不得复制其中研发分派规则 |
| PDF 下载与个人知识库导入 | `conference_pdf_downloader.py`、`paper_download.py`、`paper_import.py`、`paper_import_batch_service.py` | 复用安全和补偿；新增身份存疑阻断，不能新造第二套下载器或文件库 |
| 登录、重试和上传 | `routes_paper.py` 的 import-item `login/resume/retry`、`paper_browser_manager.py`、`routes_kb.py` 的文档上传 | Research Task 未桥接 login/resume，上传不绑定候选，批次重启恢复不完整 |

## 来源、年份与字段的实际证据

| 来源 | 当前发现方式 | 有证据的年份 | 摘要 / 关键词 | 下载和导入证据 |
|---|---|---|---|---|
| USENIX | 官方 accepted/technical/presentation 页面 | 固定 HTML：2024 summer/fall、2025 cycle1；代码处理 2022+，首轮仍需逐年复核 2022–2026 | 官方详情可取摘要；关键词仅官方确实给出时保存 | 已有官方/prepublication/arXiv 路径；本轮尚无完整逐年导入证明 |
| IEEE S&P | 当前主要靠 Crossref 枚举，OpenAlex 富化；非官网目录主链 | 固定/真实资料主要 2021–2025 | OpenAlex 可补摘要/关键词，不能归为 IEEE 官方字段 | 2024 记录为 11/270 成功下载；登录层未完成真实闭环 |
| ACM CCS | 当前主要靠 Crossref 枚举，OpenAlex 富化；非官网目录主链 | 固定样本 2023–2025，历史报告实扫 2019–2025；首轮验收 2021–2025 | OpenAlex 可补摘要/关键词；缺失允许但须标记 | 2024 记录 50/418 成功下载，Cloudflare/权限仍有缺口 |
| NDSS | 当前主要靠 Crossref 枚举，OpenAlex 富化；非官网目录主链 | 固定/真实资料主要 2021–2025 | OpenAlex 可补摘要/关键词；当前 `article_url` 常是 DOI resolver | 报告记录 2024 140/140、2025 211/211 下载，5/5 真实入库 |
| OpenAlex / Crossref | 聚合 API | Adapter 接受范围输入，不代表任意年份已验收 | OpenAlex 可有摘要/关键词；Crossref 关键词未映射，摘要不保证 | 仅候选 PDF 链接；不独立导入 |
| DBLP | 辅助书目检索 | 无真实稳定跨年成功样本 | 不提供可靠摘要/关键词 | 不独立下载；当前 Graph 对 bot challenge 有降级 |

真实统计取自 [Task04 跨会议报告](./artifacts/task-04/cross-conference-oa-acceptance.md)；它们是当时样本，不是持续可用性承诺。官方官网发现和 2021–2025 全链路仍须重新验收。

## 当前必须纠正的接线/数据问题

1. Research Graph、`search_paper_catalog` Tool、前端来源卡片目前主要枚举 USENIX/DBLP；新 Adapter 未统一转成 `CatalogPaper` / `CatalogSourceRecord` 落库，也未进入 Worker 选源。
2. Registry 的 `ccs` / `ieee_sp` 与 Source 实际 `acm-ccs` / `ieee-sp` 不一致；Crossref 与三会议的 authority 在 Registry 和 Adapter 中也有冲突。权威级别必须由**实际字段来源**决定，不由会议标签冒充官网。
3. `field_provenance` 表已有，但非 DBLP 路径未完整写入；论文合并后的 provenance 迁移和对外查询缺失。
4. `POST /api/papers/sources/{id}/sync` 目前会伪装 queued 而无真实调度；`openalex/crossref/dblp` 则返回无入口。必须接到可查询终态，或诚实返回不可用。
5. USENIX 某旧 `search()` 路径仍探测 PDF，需与目录搜索阶段禁止碰 PDF 的合同对齐。
6. 当前 Spec032 定向回归审计为 `279 passed, 3 failed`；三个失败是 IEEE/CCS/NDSS 测试仍断言旧 authority 方向（`tests/test_spec032_{ieee_sp,ccs,ndss}_source.py`），不能把 Task05 记为验收通过。
7. Research acquisition 的 `waiting_login` 仅展示文字，未桥接已有 `login/resume`；错误状态统一 retry 对 `waiting_login` 无效。进程重启后导入批次的 durable snapshot 未被统一恢复。
8. 普通知识库上传与研究候选没有身份关联；目前不存在按候选聚合的“待处理论文”队列、人工上传绑定、身份存疑门禁和修复后证据/报告版本衔接。
9. Spec032、032.1 的 Task 状态表与 README 不一致；032.1 Task08（IDE 助手）和 Task10（会话 Skill 粘性）待办，Task09 文档缺失。移交和收口必须如实处理，不得补造完成证据。

## 复用裁决

优先抽取/参数化现有解析、身份、缓存、下载、安全、登录和索引能力；允许为统一合同修改现有代码。禁止复制第二套 HTTP 下载器、PDF 安全规则、个人文件库或 Research Task 状态机。新的会议 Skill 只作来源策略和 Tool 调用编排，HTML/PDF 字节、缓存和 provenance 由确定性 Tool 处理。
