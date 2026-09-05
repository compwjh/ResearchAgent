# Spec015 Task14 — USENIX 固定样本与纯解析器（结果文档）

## 范围
- 仅改 `backend/app/services/usenix_paper_parser.py`、`tests/test_usenix_paper_parser.py`，新增 `tests/fixtures/usenix/` 下精简 fixture。
- 临时取消 150 行限制；代码文件仍限 2 个。

## 四组 fixture 结构
均置于 `tests/fixtures/usenix/`，每文件仅保留 1-2 个
`<article class="node node-paper view-mode-schedule">` 块，已删除 style/script/导航。
块内层级与真实页面一致：

- `cycle1-accepted-papers.html`：`/conference/usenixsecurity26/...` 前缀，2 篇。
- `usenixsecurity25-cycle1-accepted-papers.html`：`.../usenixsecurity25/...`，2 篇（年份 2025）。
- `usenixsecurity24-summer-accepted-papers.html`：`.../usenixsecurity24/summer-...`，1 篇（年份 2024）。
- `usenixsecurity24-fall-accepted-papers.html`：`.../usenixsecurity24/fall-...`，2 篇（年份 2024）。

每块字段：
- 标题：`<h2><a href="/conference/<code>/presentation/<slug>">标题</a>`
- 作者：`<p class="field-paper-people-text">Name, <em>affil;</em> Name, <em>affil</em>`
- 摘要：`<p class="field-paper-description-long">正文</p>`

## 提取字段
- `UsenixAcceptedPaper` 新增 `abstract: str`（默认 `""`）、`keywords: tuple[str, ...]`（默认 `()`），
  两个默认字段置于 dataclass 末尾，不破坏既有 positional 构造。
- 新增 `parse_accepted_papers(markup, *, page_url) -> tuple[UsenixAcceptedPaper, ...]`，
  支持 cycle / summer / fall 三种结构（仅前缀不同，块结构一致）。
- 对象入口 `UsenixAcceptedParser.parse_papers` 同步暴露；`__all__` 已更新。
- 既有 `parse_accepted_listing`、`parse_usenix_detail` 行为未改动。

## 缺字段行为（强制）
- 4 页均无显式 PDF href → `official_pdf_url`/`prepublication_pdf_url` 恒为 `None`，
  `pdf_url` 为 `None`、`pdf_access` 为 `"unknown"`。
- 无任何官方关键词字段 → `keywords` 恒为空 tuple，**禁止推断或生成**。
- 年份从 `page_url` 的 conference code 数字段推导（如 `usenixsecurity26`→2026），
  正文年份作兜底；无法确定则抛 `UsenixPaperParseError`。
- 跨年 presentation 链接（conference code 与 listing 不一致）一律跳过。
- 作者切分：`\s*;\s*|\s+and\s+` 分组，组内取首个 `,` 前为姓名，剥离 `<em>` 单位。

## 验证结果
- `py_compile backend/app/services/usenix_paper_parser.py`：OK
- `pytest -q tests/test_usenix_paper_parser.py`：12 passed（既有 5 + 新增 7）
- `git diff --check`：exit 0，无空白错误

## 风险与遗留
- 作者切分为启发式：末段可能夹带单位名，本任务允许缺字段稳定，不强求完美切分。
- 仅覆盖 listing 页字段；detail 页仍走既有 `parse_usenix_detail`（含显式 PDF / citation meta）。
