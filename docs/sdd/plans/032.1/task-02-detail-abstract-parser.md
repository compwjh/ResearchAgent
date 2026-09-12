# Task 02：`parse_usenix_detail` 补齐 abstract 解析

> 关联：[spec-032.1](../../specs/032.1-usenix-skill-decoupling.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`待执行`

## 一句话目标

让 `parse_usenix_detail()` 能从 USENIX presentation 详情页提取摘要，并填充
`UsenixAcceptedPaper.abstract`，为后续「详情页抓取单元」（任务 03）提供解析能力。

## 背景与前置条件

- 现状：`backend/app/paper_discovery/infrastructure/usenix_paper_parser.py` 的
  `parse_usenix_detail()`（约 139–163 行）只取 title / authors / year / official_pdf /
  prepublication_pdf，**未取 abstract**；`UsenixAcceptedPaper` dataclass **已具备 `abstract` 字段**
  （默认 `""`），本任务只需正确填充，不需改数据类结构。
- 列表页路径 `parse_accepted_papers()`（约 308–330 行）从 `.field-paper-description-long` 取摘要，
  但列表页实际无摘要（`catalog_search_graph.py` 注释自认 "USENIX listing pages carry no abstract"），
  故详情页是唯一可靠的官方摘要来源。
- 既有 fixture 位于 `tests/fixtures/usenix/`，均为**精简手工片段**（343–713 字节），
  新建 fixture 必须沿用该风格，不要提交整页 HTML。

## 已核实的真实结构

样本：`https://www.usenix.org/conference/usenixsecurity24/presentation/zhang-qingzhao`（HTTP 200）。

摘要位于 Drupal 标准字段：

```html
<div class="field field-name-field-paper-description field-type-text-long field-label-hidden">
  <div class="field-items field-items"><div class="field-item odd">
    <p>Collaborative perception, which greatly enhances ...</p>
  </div></div>
</div>
```

> **⚠️ 陷阱（必须规避）**：同一页面另有一个 `<div class="description">`，内容是
> "USENIX is committed to Open Access..." 的**站点说明**，不是论文摘要。
> **禁止**用 `description` 作为摘要选择器，否则会把站点说明误当论文摘要写进目录。

## 实施步骤与文件边界

1. 新建 fixture `tests/fixtures/usenix/presentation-detail.html`（精简片段），至少包含：
   - `citation_title` / `citation_author` meta；
   - 上述 `field-name-field-paper-description` 摘要块；
   - **一个 `.description` 陷阱块**（用于断言不会被误取）。
2. 新建无摘要变体 `tests/fixtures/usenix/presentation-detail-no-abstract.html`（含其它字段、无摘要块）。
3. 在 `usenix_paper_parser.py` 中实现摘要提取：
   - 取 `.field-name-field-paper-description` 内 `.field-item` 的文本；
   - 取不到时 abstract 保持 `""`，**不得抛异常、不得用站点说明兜底、不得从 PDF 链接反推**；
   - 文本做空白归一化（连续空白折叠为单空格、去首尾），与文件既有文本处理风格一致；
   - 复用既有 `_page(markup)` 封装，不新增解析器。
4. `parse_usenix_detail()` 构造 `UsenixAcceptedPaper` 时传入 `abstract=...`。

**只允许改动**：`usenix_paper_parser.py`、新增 fixture、新增/更新测试。
**不要改** `usenix_publication_source.py` 与 `catalog_search_graph.py`——抓取单元与图接入属于任务 03。

## 子代理分派

角色 `backend-dev`（模型 `qwen3.8:27b-mlx`）。本地模型约束：单次**最多 2 个代码文件、约 150 行**。
回传：改动文件清单、测试命令/退出码/结果、fixture 路径、风险与阻塞。

## 边界与明确不做

- 本任务**只做解析，不做网络抓取**（抓取单元属任务 03）。
- 不新增第二套 HTML 解析器或新依赖。
- 不改 `parse_accepted_papers`（列表页）既有逻辑。
- 不改 `UsenixAcceptedPaper` 的字段定义。
- 禁止用 `.description` 取摘要。

## 验收（每条都要有测试）

1. 从 `presentation-detail.html` 解析出的摘要与 fixture 中摘要文本一致。
2. 无摘要 fixture → `abstract == ""`，不抛异常。
3. `.description` 陷阱块不会被当作摘要（断言结果不含 "Open Access" 等站点说明字样）。
4. 既有 `tests/test_usenix_paper_parser.py`、`tests/test_usenix_publication_source.py` 全绿（回归保护）。
5. `.venv/bin/ruff check backend/app/paper_discovery/infrastructure/usenix_paper_parser.py` 干净。

## 产出物、执行结果与变更日志

> 待执行后填写：真实命令、退出码、测试结果、改动文件清单。
