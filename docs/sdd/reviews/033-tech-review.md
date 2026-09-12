# 033 技术评审 — USENIX 解析器与真实页面结构对齐

- 评审对象：`backend/app/paper_discovery/infrastructure/usenix_paper_parser.py`（spec-033 task-02 / task-03 的改动）
- 评审方式：只读（Read/Grep + 定向 pytest/ruff + stdin 探针脚本，未改动任何仓库文件）
- 结论：**通过（附强制意见，见文末约束清单）**
- 说明：同一文件内 spec-032.1 的在途改动（`_PAPER_DESCRIPTION_RE` / `_Page.abstract` 摘要抽取）按要求**不属本次评审范围、不作判定**；`usenix_publication_source.py` 的 491 行改动属 spec-032.1（`docs/sdd/plans/032.1/task-03/04`），亦不在本次范围。

## 佐证命令与结果

| 命令 | 结果 |
|---|---|
| `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_usenix_paper_parser.py -q --basetemp=/tmp/rv033` | **42 passed** |
| 追加 `tests/test_usenix_publication_source.py` | **84 passed** |
| `env -u PYTHONPATH .venv/bin/python -m ruff check backend` | `All checks passed!` |

## 逐条评审点

### 1. 单一实现（详情页作者复用列表页 `_Blocks`）— 通过

- 证据：`usenix_paper_parser.py:261-263` 详情页回退调用 `_blocks(markup, article_classes=_DETAIL_ARTICLE_CLASSES)` 后仅取 `["authors"]`，再用既有 `_split_authors()` 切分。
- `<em>` 单位排除（L470）、只取首个 `<p>`（L348-370）、`,`→`;` 归一（L418）、帧栈深度（L405/L454）全部只在 `_Blocks` 内实现一次；Grep 全 `backend/**` 无第二处 `people-text` / `_split_authors` / 归一化正则。
- 无第二套 people 解析，符合 task-03 §4「必须复用」与项目「禁止重复实现」约束。

### 2. fail-closed 保持 — 通过

- 证据：`usenix_paper_parser.py:268-270`：`year` 走完三级回退后仍 `if not title or not authors or year is None: raise UsenixPaperParseError()`；作者回退得空 tuple 时同样命中该判定。
- 反例测试 `tests/test_usenix_paper_parser.py:523-536`（无 meta 且无 people 字段）断言仍抛 `USENIX_PARSE_FAILED`；实测「未闭合 field `<div>` 导致作者为空」时同样抛错而非返回半成品。

### 3. 安全边界未放宽 — 通过

- `_safe_url`（L180-195：scheme/hostname/port/username/password/query/fragment/反斜杠/`presentation` 路径白名单）在 `git diff` 中**零改动**。
- PDF 判定 L271-280 未改：仍为 `_safe_url` + `safe.casefold().endswith(".pdf")`，label 仅用于区分 official / prepublication；L158-161「不得由链接文本推断 PDF 路径」的注释与逻辑保留。标题/正文均未参与 PDF 推断。

### 4. 摘要来源未分叉 — 通过

- 证据：`usenix_paper_parser.py:281` `abstract = " ".join("".join(page.abstract).split())`，仍取 spec-032.1 的 `_Page.abstract`；详情页的 `_blocks` 调用（L261-263）**未读** `["abstract"]`，desc 字段不参与详情页摘要。

### 5. 站点级 `.description` 未误判 — 通过

- 证据：L17 `_PAPER_DESCRIPTION_RE` 要求完整 class token `field-name-field-paper-description`（前后为空白/边界），站点级 `class="description"` 不匹配。
- 测试：`tests/test_usenix_paper_parser.py:458-464`、`514-520` 断言 `"Open Access"` / `"USENIX is committed"` 不进入 `abstract`。

### 6. 标题清洗不过度 — 通过

- 证据：`_without_site_suffix`（L211-218）先做正则匹配、再要求 `"usenix" in match.group("site").casefold()` 才截断；正则（L40-42）要求分隔符**两侧有空白**、末段最多两词、并以 `$` 锚定。
- 实测：`"Pipes | Something"` → 原样；`"Foo | USENIX"` / `"Foo - USENIX"` / `"Foo | USENIX Association"` → `Foo`。
- 作用域：仅 `page.meta.get("title")`（文档 `<title>`）兜底分支（L246-253）调用清洗；`citation_title` / `og:title` / `h1` 三条优先来源不经过清洗。
- 残余（非误删，仅欠清洗）：`"… | USENIX Security Symposium"` 不匹配而不截断；真实站点后缀为 `"| USENIX"`，无影响。

### 7. HTML 容错 — 通过（附 1 条观察）

- 实测（探针）：未闭合 `<p>`、多层 `field-item` 嵌套、字段后游离 `</div>` 三种情况作者/摘要均正确；`_pop_open_tag`（L381-391）对无匹配的游离闭合标签不做误删。
- 未闭合的 field `<div>`（缺 `</div>`）会丢字段：`_close_finished_fields` 未触发，而 `</article>` 分支（L485-490）直接弹栈且 `return`。旧实现同样丢（旧代码仅认 `</p>`），**非回归**；详情页表现为 fail-closed 抛错，不产生半成品。

### 8. 默认行为零回归 — 通过

- 证据：`_Blocks.__init__`（L322）与 `_blocks`（L502）默认均为 `("node-paper", "view-mode-schedule")`；L433 `all(token in classes for token in self._article_classes)` 与旧 `"node-paper" in classes and "view-mode-schedule" in classes` 在子串语义上等价；`view-mode-full` 仅由详情路径显式传入。
- 测试 `tests/test_usenix_paper_parser.py:575-591` 断言列表页仍忽略 `view-mode-full`；`parse_accepted_papers`（L545-581）返回结构与筛选逻辑未改；2025 fixture 实解 2 篇、无重复。

### 9. 代码质量 — 通过

- ruff（含 `backend` 全量）零告警；无 `print`、无未引用常量（`_VOID_ELEMENTS` / `_UNTAGGED_ELEMENTS` 均被使用）、无注释掉的死代码。
- 注释均为「为什么」（如 L28-32 解释两种 view-mode 为何必须分开、L413-417 解释为何在 `_Blocks` 内做 `,`→`;` 归一），符合项目注释规范。

## 问题清单

| 级别 | 位置 | 问题 | 建议 |
|---|---|---|---|
| MEDIUM | `usenix_paper_parser.py:411` | 摘要跨多个 `<p>` 时**段落粘连**：`text = " ".join("".join(frame["data"]).split())` 在相邻文本节点间无分隔。实测 `<p>A.</p><p>B.</p>` → `'A.B.'`。这是 task-02 把 desc 字段从「单个 `<p>`」放宽到「整个字段 div」后新暴露的行为（旧实现在真实页面取不到摘要，无对照），现有测试 `tests/test_usenix_paper_parser.py:377-378` 只用 `in` 断言，未覆盖 | 在块级元素（`p` / `div` / `li` / `<br/>`）的开始或结束边界补一个空格（可参照 `_Page.handle_starttag:90-93` 对 `_VOID_ELEMENTS` 的处理），或改为按节点以 `" "` 拼接后再 collapse |
| MEDIUM | `usenix_paper_parser.py:263` | 详情页作者回退固定取 `detail_blocks[0]`，未校验 block 身份。实测「侧栏/相关论文的 `node-paper view-mode-full` 在前」时静默取到侧栏作者（`('Sidebar Person',)`），不触发 fail-closed。task-03 §4 仅验证过 4 个真实页「恰好 1 个 block」 | 优先选 `block["presentation"] == article` 的 block，其次选 `title` 与已解析 `title` 一致的 block，最后才回落 `[0]`；并补一条「首个 block 非本页论文」的测试 |
| LOW | `usenix_paper_parser.py:268` → `_year_from_page_url:530-532` | markup 兜底用 `\b(19\|20)\d{2}\b` 扫全文，实测页脚 `© 1997 USENIX` 会产出 1997。仅在 URL 会议代号无 2 位数字时可达（真实 presentation URL 恒有），风险低 | 详情页只依赖 URL 会议代号，不再把整页 markup 作为年份来源 |
| LOW | `usenix_paper_parser.py:485-490` | 字段元素未闭合时（`</div>` 缺失）作者/摘要静默丢失；详情页由 fail-closed 兜住，列表页则该篇作者为空 | 在 `article` 分支弹栈前先调用一次 `_close_finished_fields()` 语义的收尾，避免无闭合标签时丢字段 |

## 未被 spec 覆盖的行为变化（需知悉，均不构成回归）

1. 详情页标题来源链由 `citation_title → og:title → <title>` 变为 `citation_title → og:title → h1 → <title>`（spec L101 明确要求，属已覆盖）。
2. `_Page` 的 `meta["title"]` 被拆出独立 `meta["h1"]` 键；`meta["title"]` 的消费者经 Grep 确认只有 `parse_usenix_detail` 一处，无旁路影响。
3. `_Blocks` 的 people / desc 字段匹配由「子串包含」改为「class token 集合交集」（`_field_kind:372-379`）：形如 `my-field-paper-people-text` 或 `field-paper-people-text-extra` 的类名**不再命中**。属收紧且符合 task-02 §4.1「避免子串误命中」，但 spec 边界条目未逐字列出；真实页面与全部 fixture 均使用完整 token，无实际影响。
4. 列表页 desc 字段的收集范围由「首个 `<p>`」扩到「整个字段元素」（即 MEDIUM-1 的行为面）。

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | warn |
| MEDIUM | 2 | info |
| LOW | 2 | note |

Verdict: **通过** — 无 CRITICAL / HIGH；9 项评审点全部通过，2 条 MEDIUM 建议在 task-04 验收前修掉。

## 强制约束清单（后续改动必须遵守）

1. 详情页作者抽取**只能**复用 `_Blocks` + `_split_authors`，不得出现第二套 people 解析；`_safe_url` 白名单、`.pdf` 显式判定、`_Page.abstract` 摘要来源三者不得放宽或分叉。
2. `_blocks()` / `_Blocks()` 的 `article_classes` 默认值必须保持 `("node-paper", "view-mode-schedule")`，`view-mode-full` 仅限详情路径显式传入。
3. 文本跨元素拼接必须保证块级边界有分隔符（修复 MEDIUM-1 后补一条多段摘要的精确断言，替换现有 `in` 断言）。
4. 详情页作者回退必须绑定到「本页论文」的 block（修复 MEDIUM-2），并补对应负例测试。
5. `parse_usenix_detail` 的 fail-closed 判定（`title` / `authors` / `year` 缺任一即抛 `UsenixPaperParseError`）不得放松。
6. 时间与错误码不得改动：`UsenixPaperParseError.code == USENIX_PARSE_FAILED`、`retryable = True` 保持不变。

## 整改复核（2026-09-12 追加，非本次评审时点）

> 本节为事后追加，记录两条 MEDIUM 的闭环状态；上方「问题清单」为评审时点的原始记录，**不回溯修改**。

| 编号 | 状态 | 复核证据 |
|---|---|---|
| MEDIUM-1 摘要段落粘连（`:411`） | **已整改** | 实测 `<p>A.</p><p>B.</p>` 由 `'A.B.'` 变为 `'A. B.'`；新增 `test_listing_abstract_separates_every_block_level_boundary`、`test_listing_abstract_does_not_split_inline_emphasis_text`；原 `in` 弱断言已替换为 `==` 精确断言（强制约束 #3 已满足） |
| MEDIUM-2 作者块无身份校验（`:263`） | **已整改** | `_detail_authors_block()` 按 `presentation URL → title → [0]` 选块；新增 `test_detail_author_fallback_ignores_a_sidebar_block_ahead_of_the_paper` 等 3 条测试，负例在修复前会取到 `Sidebar Person`（强制约束 #4 已满足） |

- 复核人：架构师(自身) + `tester`（验收报告「两条 MEDIUM 整改的独立复核」表）+ `architect`（签字前 Grep 核对测试名真实存在）。
- 强约束 #1/#2/#5/#6 经 `tester` 逐条边界核验（12 条）均保持，无违反。
- 残余：评审时点的 2 条 LOW 经确认**有意保留**（非回归），详见 `033-acceptance-review.md`。
