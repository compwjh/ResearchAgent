# Task 07：官网目录优先、聚合兜底与逐年字段覆盖

> 关联：[Spec032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md) ｜ 审计：[资产与缺口](./asset-gap-audit.md)
> 依赖：Task06 合同通过；当前状态：`部分完成（IEEE S&P 2024、NDSS 2024 固定样本；CCS 2021–2025 bounded NO-GO）`

## 一句话目标

把 IEEE S&P、ACM CCS、NDSS 从“以 Crossref 枚举的会议来源”补成官网目录优先、聚合元数据兜底，并对四会议约定年份逐年给出可核查的字段/下载覆盖证据。

## 必须复用的资产

- 三会议 `*_publication_source.py`、`*_paper_parser.py`、Crossref/OpenAlex 富化和 `ConferencePdfDownloader`；USENIX `usenix_publication_source.py`、详情摘要 FetchUnit；现有固定样本与 Task04 真实验收报告。
- 会议官网发现与 Crossref fallback 要保留各自原始来源记录和字段 provenance；官方页面不提供的关键词/摘要不能填“官方”。

## 实施与文件边界

后端按会议拆分互不覆盖的子分派；仅改对应来源/parser、受控抓取单元与 fixtures/测试。先建立官网列表/详情真实固定样本和允许主机，再实现年份/cycle/track/page 单元与内容 hash；若官网字段缺失或页面失败，以现有聚合 Adapter 补缺并标注降级。USENIX 只修合同差异和目录阶段误探测 PDF，不重写已验证的详情链。

## 验证门禁

- USENIX 2022–2026；其余三会 2021–2025：每个来源×年份记录官方页/样本、发现总数、摘要/关键词缺失、PDF 候选、正确下载和入库比例。未验证年份标“未验证”，不靠 `MIN_YEAR` 推断成功。
- 单页失败保留旧缓存，结构变化有稳定错误；目录阶段不 GET/HEAD/Range PDF。实时外站只做受控小样本，不批量施压。
- 分别运行该来源固定样本/边界测试和静态检查；无官网可靠入口或身份错链无法隔离时，该来源年度 NO-GO，不伪造完成。

## 交接与产出

每源单独写 `artifacts/task-07/<source>-coverage.md`，附页面、字段统计、真实/模拟区分、命令/退出码、改动文件及未通过年份。主 Agent 汇总成 `coverage-matrix.md` 后决定 Task08 可启用范围。执行结果：首轮部分完成；IEEE S&P 2024、NDSS 2024 官方目录固定样本通过；CCS 2021–2025 已完成 bounded NO-GO 审计，未验证年份不得宣称覆盖。

## 变更日志

- 2026-09-20：承接原 Task04 已有会议代码，补足其未实现的官网优先和覆盖证明。
- 2026-09-20：Luna high 子 Agent 完成 IEEE S&P 2024 官方 HTML 路由、固定样本、字段缺失告警和 PDF 响应拒绝；主 Agent 复跑 76 个定向测试，ruff、compileall、git diff --check 通过。Task08 仅可启用已验证的 IEEE 2024，其余来源继续按 NO-GO 处理。
- 2026-09-20：Luna high 子 Agent 补齐 NDSS 2024 官方 accepted-papers HTML 路由、固定样本、字段缺失告警和 PDF 响应拒绝；仅验证 2024 固定样本子集，2021–2023、2025 仍未验证。CCS 官方节目页仍因 JavaScript/入口身份无法在受控样本中可靠隔离，保持 NO-GO。
- 2026-09-20：Luna high 子 Agent 完成 CCS 2021–2025 官方入口审计：2021/2022/2024 可读但缺统一 DOI/详情身份键，2023 程序页显示动态数据库失败，2025 accepted 页要求 JavaScript 且列表为空；未新增 parser/source/fixture，更新 `artifacts/task-07/ccs-coverage.md` 为 bounded NO-GO，并保留 Crossref/OpenAlex fallback。
