# 任务 14 — 实现 USENIX 增量目录同步

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)
> 依赖：任务 13；被依赖：任务 15、17；当前状态：`待执行`
> 主 Skill：`.agents/skills/usenix-paper-catalog-search/SKILL.md`（本任务禁止 PDF 下载/验证）

## 一句话目标

把 USENIX Security 官方 accepted 页面转换为可恢复、可缓存、按年份/页面增量更新的全局论文目录，并让 DBLP 并行补齐书目信息而不覆盖官网字段。

## 当前证据

- 当前解析器只从列表提取 presentation URL，详情模型缺少摘要和关键词。
- 当前 USENIX source 按用户查询字符串过滤标题，并在搜索阶段逐篇下载/探测 PDF；这两种行为必须删除。
- 当前 source 使用进程内字典缓存和单个 cycle 模板，无法覆盖 2024 summer/fall 与服务重启后的增量缓存。
- 四个权威固定样本 URL 已写入 Spec015；实现 fixture 必须保存最小必要 DOM，不把完整网页或第三方内容无选择复制进仓库。
- Task13 提供抓取单元和全局目录仓储；本任务不得另建缓存表。

## 前置门禁

1. Task13 已完成并通过 Tech Lead 复用审计；schema v2、领取、租约、目录 upsert 可用。
2. USENIX Skill、Spec015 的来源白名单和安全边界保持有效。
3. 真实网络只用于受控验收；单元测试必须使用 fixture/MockTransport，不依赖外网。
4. 使用本地 Ollama junior-dev 时每次最多 2 个代码文件、约150行；线上模型无该数量限制。

## 数据、配置与接口增量

- `UsenixAcceptedPaper` 增加 `abstract: str`、`keywords: tuple[str,...]`；关键词缺失为空 tuple，不推断。
- 新增年度页面发现结果：年份、规范入口、accepted 页面 URL 列表、发现状态和安全错误。
- USENIX 抓取单元以 accepted 页面规范路径作为 `unit_key`；详情页失败写 `partial` 事件，不丢弃同页面成功论文。
- DBLP 抓取单元按 `stream + year + page offset` 标识，严格过滤主会；只补目录空字段。
- 本任务提供同步用例接口供 LangGraph 调用，例如 `sync_usenix_units(search_id, conference_id, years)` 与 `sync_dblp_units(...)`；不得在本任务直接启动后台线程或新增 HTTP 路由。

## 页面发现与解析规则

1. 请求年份入口由服务端根据 `usenixsecurityYY` 受控规则构造；只允许 `https://www.usenix.org/conference/usenixsecurityYY`。
2. 只接受同源、无查询/fragment/userinfo、路径会议前缀一致，且末段匹配 `cycle[0-9]+-accepted-papers`、`summer-accepted-papers`、`fall-accepted-papers` 或 `accepted-papers` 的链接。
3. 已配置的四个首批页面作为确定性种子；入口发现可补充同年份的其他合法 accepted 页面，但不能接受跨年份或任意 URL。
4. accepted 页面解析标题、作者、摘要、官网关键词和 presentation/PDF 显式链接；未提供字段保持空，不猜测。
5. 目录同步不调用 `download_candidate`、`_get_pdf`、HEAD 或 Range 请求；URL 可保存但内容只在导入时验证。

## 思维链（可观察执行阶段）

1. 从四个官方页面提取最小、去敏的真实 DOM fixture，并记录页面结构差异。
2. 扩展纯解析器，使 cycle/summer/fall fixture 输出统一模型；先通过测试再接网络 source。
3. 将 source 拆成“发现页面、抓文本、解析详情、写抓取单元”步骤，复用安全校验和来源节流。
4. 连接 Task13 仓储，实现缓存命中、条件请求、内容哈希、partial、失败重试和租约恢复。
5. 让 DBLP 作为并行辅助同步器写来源记录；执行确定性字段合并。
6. 证明搜索阶段没有 PDF 请求，重复年份不重复抓取，重启新 service 后仍命中 SQLite 缓存。

## 子任务拆分与子 Agent 分派

### A：固定样本与纯解析器

```text
你是 junior-dev，使用 qwen3.8:27b-mlx。实现 Spec015 Task14 的 USENIX 固定样本与纯解析器切片。
只读取：已确认 Spec015 的 USENIX流程/复用章节、Task14、现有 usenix_paper_parser.py、tests/test_usenix_paper_parser.py，以及四个已指定官方 URL 的受控响应。
允许修改：使用本地 Ollama时最多2个代码文件、约150行，优先 backend/app/services/usenix_paper_parser.py 与 tests/test_usenix_paper_parser.py；HTML fixture 作为测试数据不计代码文件但必须最小化。线上模型不受文件数限制。
禁止：修改 source/store/API/UI/下载器；推断关键词；猜测 PDF 路径；接受非同源/跨年份链接；复制整站；git add/commit/reset/stash/clean。
完成状态：2024 summer/fall、2025 cycle1、2026 cycle1 fixture 均能提取标题、作者、摘要、可选官网关键词、presentation和显式PDF链接；缺字段有稳定行为。
必须验证：.venv/bin/python -m pytest -q tests/test_usenix_paper_parser.py；.venv/bin/python -m py_compile backend/app/services/usenix_paper_parser.py；git diff --check。
结果文档：docs/sdd/reviews/015-task14-usenix-parser.md；日志：.codebuddy/agent-logs/junior-dev-spec015-task14-parser-<timestamp>.md。
固定返回字段：结果状态和摘要；改动文件；测试命令、退出码和结果；fixture/产物路径；决策依据；风险与阻塞；主 Agent 后续动作；开始、结束、总耗时；可用时模型/token/工具统计。
先回传代码和测试结果；信息不足则阻塞。
```

### B：USENIX 页面发现与增量同步

```text
你是 junior-dev，使用 qwen3.8:27b-mlx。实现 Spec015 Task14 的 USENIX 页面发现、缓存与目录同步切片。
只读取：已确认 Spec015、Task13/14、Task13复用审计与store实现、A后的parser/source及其测试、paper_download_security.py。
允许修改：使用本地 Ollama时最多2个代码文件、约150行，优先 backend/app/services/usenix_publication_source.py 与 tests/test_usenix_publication_source.py；需要store接口变化时先阻塞并报告，不自行扩表。线上模型可按任务范围扩展文件。
禁止：调用/复制PDF下载器；搜索阶段HEAD/GET PDF；进程内字典作为权威缓存；按用户query过滤入库；任意URL；绕过来源节流；git reset/stash/clean。
完成状态：受控入口发现合法 accepted 页面；按fetch unit租约抓取；completed/304/hash不变命中缓存；partial/failed有事件；重启新source实例仍从SQLite识别缓存。
必须验证：.venv/bin/python -m pytest -q tests/test_usenix_publication_source.py tests/test_paper_discovery_store.py；添加断言确保零PDF请求；git diff --check。
结果文档：docs/sdd/reviews/015-task14-usenix-sync.md；日志：.codebuddy/agent-logs/junior-dev-spec015-task14-sync-<timestamp>.md。
固定返回字段同Task要求；必须逐项报告复用的安全/store符号和删除的旧PDF probe调用。
```

### C：DBLP 辅助同步与权威字段合并

```text
你是 junior-dev，使用 qwen3.8:27b-mlx。实现 Spec015 Task14 的DBLP辅助同步和字段合并切片。
只读取：已确认 Spec015、Task13/14、复用审计、现有 dblp_publication_source.py、paper_discovery_normalization.py、paper_discovery_store.py 及对应测试。
允许修改：使用本地 Ollama时最多2个代码文件、约150行，优先 dblp_publication_source.py 与 tests/test_dblp_publication_source.py；若合并器位于其他既有文件，先返回最小改动方案，由主Agent拆分下一分派。线上模型不受数量限制。
禁止：让DBLP覆盖USENIX标题/作者/摘要/关键词；放宽Workshop等过滤；显示无官方摘要的DBLP-only记录；新建规范化实现；git reset/stash/clean。
完成状态：按stream/year分页形成fetch unit；重试/错误稳定；DOI/DBLP key只填空值；跨来源合并保留source record与官方字段。
必须验证：.venv/bin/python -m pytest -q tests/test_dblp_publication_source.py tests/test_paper_discovery_search.py tests/test_paper_discovery_store.py；git diff --check。
结果文档：docs/sdd/reviews/015-task14-dblp-merge.md；日志：.codebuddy/agent-logs/junior-dev-spec015-task14-dblp-<timestamp>.md。
固定返回字段同Task要求；信息不足必须阻塞。
```

## 子 Agent 必须返回的字段

结果状态和摘要、改动文件、测试命令/退出码/计数、fixture与报告路径、复用符号、删除或替换的旧调用、决策依据、风险与阻塞、主 Agent 后续动作、起止时间与总耗时；可用时模型/token/工具统计。

## 主 Agent 回填校验

1. 读回四组 fixture 与解析结果，确认摘要来自官网、关键词缺失时为空。
2. 检查所有发现 URL 与年份/会议前缀；拒绝外站、query、fragment、跨年份和路径混淆。
3. 使用记录请求的 MockTransport 搜索两次，第二次必须零重复正文请求；构造当前年份过期后只发条件请求。
4. 新建 source/service 实例复用同一临时 SQLite，确认缓存跨进程语义成立。
5. 搜索 2022 后再搜索 2022–2024，断言只领取 2023/2024 缺失单元。
6. 扫描生产调用图确认目录同步不调用 PDF 下载/探测；运行现有下载安全和导入回归。

## 实时监控命令

```bash
tail -f .codebuddy/agent-logs/junior-dev-spec015-task14-*.md
.venv/bin/python -m pytest -q tests/test_usenix_paper_parser.py tests/test_usenix_publication_source.py tests/test_dblp_publication_source.py
```

## 测试与验收标准

- 四个官方结构固定样本全部通过，标题/摘要必有，关键词按页面真实情况为空或原值。
- 多页面年份不被错误标成单页面完成；同一单元并发只抓一次。
- 缓存跨 service 实例有效；历史年份不重复抓取，当前年份按条件请求重验证。
- USENIX 失败、DBLP成功以及反向失败均形成独立进度与可用目录结果。
- USENIX字段不可被DBLP覆盖；无官方摘要的DBLP-only记录不进入可见目录。
- 搜索阶段网络记录中没有PDF、HEAD或Range探测。

## 风险、停止条件与回滚

- 页面结构无法从固定fixture确定：标记 `USENIX_PARSE_FAILED` 并停止，不放宽到任意链接。
- 官网没有稳定年度入口：保留用户给定种子并记录发现阻塞，不遍历站点或猜测论文URL。
- DBLP分页/上限无法证明年度完整：该单元保持partial，不伪装completed。
- 回滚删除本任务新增适配层并恢复检查点版本；不得删除已存在目录/导入数据。

## 产出物

- 四组最小USENIX页面fixture与解析测试。
- USENIX页面发现、增量同步与持久缓存。
- DBLP辅助同步和权威字段合并。
- 三份实现报告与执行日志。

## 执行结果

待执行后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-05 | 架构师（自身） | 创建Task14，固定官方样本、自动发现、增量缓存、DBLP辅助和禁止PDF探测；未执行代码 |
