# Task 02 — 列表页字段匹配放宽到任意元素

> 关联：[spec-033](../../specs/033-usenix-parser-real-page-alignment.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01；当前状态：`已完成`

## 1. 状态与一句话目标

**已完成（2026-09-12，经三轮 `backend-dev` 修正并独立复核）。** 让 `parse_accepted_papers` 在真实 USENIX 列表页上抽出**作者与摘要** ——
当前因为只认 `<p>` 上的类名而全部丢失（实测 4 个真实页面 0 作者 0 摘要）。

## 2. 背景与前置条件

- 目标文件：`backend/app/paper_discovery/infrastructure/usenix_paper_parser.py`，类 `_Blocks`（约第 214-293 行）。
- 缺陷代码（约第 255-260 行）：

  ```python
  if tag == "p":
      classes = values.get("class", "").casefold()
      if "field-paper-people-text" in classes:
          self._stack.append({"kind": "people", "data": []})
      elif "field-paper-description-long" in classes:
          self._stack.append({"kind": "desc", "data": []})
  ```

  配套的 `handle_endtag`（约第 284-292 行）也只在 `tag == "p"` 时弹栈。
- 真实页面结构（`/tmp/l_ac42a2e5acc3c28fd58a084ec5d6de23.html` 等）：

  ```html
  <div class="field field-name-field-paper-people-text field-type-text-long field-label-hidden">
    <div class="field-items field-items"><div class="field-item odd">
      <p>Hyeonmin Lee, <em>Seoul National University;</em> …</p>
    </div></div>
  </div>
  <div class="field field-name-field-paper-description-long field-type-text-long field-label-hidden">
    <p>The DNS-based Authentication …</p>
  </div>
  ```

- **前置：先 Read 该文件当前内容**。工作区已有 spec-032.1 的未提交改动，**只允许在其之上追加/修改本任务范围内的小节**，
  禁止整文件重写、禁止 `git checkout` 该文件。

## 3. 数据、配置与接口

不适用（纯解析逻辑，不改签名、不加配置、不加依赖）。

## 4. 实施步骤与文件边界

**允许改动**：`backend/app/paper_discovery/infrastructure/usenix_paper_parser.py`、
`tests/fixtures/usenix/` 下的**列表页** fixture、`tests/test_usenix_paper_parser.py`。

1. 在 `_Blocks.handle_starttag` 中，把「仅 `p` 标签」改为「**任意标签**」：
   - 匹配用完整字段名，避免子串误命中（`field-name-field-paper-people-text` /
     `field-name-field-paper-description-long`），同时**兼容**既有 fixture 的简写形式
     （`field-paper-people-text` / `field-paper-description-long`），二者都要能命中。
   - 用一个 `_stack` 帧记录**起始标签名**与**嵌套深度**（可参考同文件 `_Page` 处理
     `.field-name-field-paper-description` 的 `_description_tag` / `_description_depth` 写法），
     使 `handle_endtag` 能在**真正闭合该字段的元素**时弹栈，而不是只认 `</p>`。
   - 注意 `_current_block()` 依赖 `frame["kind"] == "article"`，新增字段不得破坏该查找。
2. `handle_data` 的取数顺序（`reversed(self._stack)` 取最近一帧）保持不变；
   嵌套时必须以**最内层字段帧**为准，避免把标题文本混入作者。
3. 把 `tests/fixtures/usenix/` 下**列表页** fixture 改成真实结构（字段类名在 `<div>` 上、内层 `<p>` 无 class）：
   `usenixsecurity24-summer-accepted-papers.html`、`usenixsecurity24-fall-accepted-papers.html`、
   `usenixsecurity25-cycle1-accepted-papers.html`、`cycle1-accepted-papers.html`。
   **至少保留一个**用旧 `<p class="…">` 简写形式的用例，证明向后兼容。
4. 在 `tests/test_usenix_paper_parser.py` 补测试：真实 `<div>` 结构下作者与摘要均非空；
   旧 `<p>` 简写形式仍能取到。

**完成后的可观察结果**：对 `/tmp/l_ac42a2e5acc3c28fd58a084ec5d6de23.html`（256 篇）、
`/tmp/l_e19ef3cd65a06856406f58f5f248c1bc.html`（97 篇）、`/tmp/list24.html`（82 篇）、
`/tmp/list25.html`（245 篇）调用 `parse_accepted_papers`，作者非空数量应接近篇数上限（此前为 0）。

## 5. 子代理分派

- 角色：`backend-dev`；模型 `Deepseek-V4.1-Flash`。
- 最小上下文：本 task 文件 + spec-033 + 目标文件 + 上述 4 个真实页面样本路径。
- 单次文件范围：**一次只改 `usenix_paper_parser.py` 一个代码文件**（fixture 与测试随后单独一轮）。
- 回传要求：先回传**代码片段**，再回传说明；主会话读回文件确认后再进入下一任务。

## 6. 边界与明确不做

- 不改 `parse_accepted_papers` / `parse_accepted_listing` / `_Blocks` 的**签名与返回类型**。
- 不改 `_safe_url` 的白名单与 SSRF 防护；不引入新依赖。
- 不改 `_split_authors` 的**切分启发式**本身；但喂给它的文本**必须排除 `<em>` 内的单位名**（见验收第 3、4 条）。
- 不碰详情页路径（`parse_usenix_detail` / `_Page`）——那是任务 03。

## 7. 验收、风险与回滚

**验收**：
1. 4 个真实列表页样本上，作者非空数 > 0 且等于含 people 字段的论文数（此前恒为 0）。
2. 摘要非空数与真实页面 `field-name-field-paper-description-long` 数量一致。
3. 旧 `<p class="field-paper-people-text">` 简写 fixture 仍解析出作者（向后兼容）。
4. **作者列表不含单位名碎片**：排除 `<em>` 内文本后，4 个真实页面中「存在单词作者或含 `@` 作者」的论文数应为 **0**
   （修订前为 19/256、7/97、10/82、32/245，合计 68/680 ≈ 10%）。回归样本：
   `Zhenghang Ren, Mingxuan Fan, Zilong Wang, Junxue Zhang, and Chaoliang Zeng, <em>iSING Lab@The Hong Kong
   University of Science and Technology;</em> Zhicong Huang and Cheng Hong, <em>Ant Group;</em> Kai Chen,
   <em>iSING Lab@… and University of Science and Technology of China</em>`
   → 恰好 8 位作者（`Zhenghang Ren` / `Mingxuan Fan` / `Zilong Wang` / `Junxue Zhang` / `Chaoliang Zeng` /
   `Zhicong Huang` / `Cheng Hong` / `Kai Chen`）。
5. **作者列表不含获奖 / 荣誉标记**：people 字段内只取**首个 `<p>`**。实测 4 个真实页面中「作者里含
   `Award` / `Distinguished` / `Winner`」的论文数为 14/6/4/9 = **33**，修复后应为 **0**。
   回归样本：`Diwen Xue, … Roya Ensafi, <em>University of Michigan</em>` 后紧跟
   `<p style="font-weight: 600; font-style: italic;">Distinguished Paper Award Winner and First Prize
   Winner of the 2022 Internet Defense Prize</p>` → 作者应为 7 位，不含该标记。
6. 标题、presentation 链接、年份行为零回归。
7. `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_usenix_paper_parser.py -q --basetemp=/tmp/pt033a` 全绿。
8. `ruff check` 零新增告警。

**风险**：真实页面里字段可能出现在嵌套更深的层级；若 `_stack` 深度处理不当会把单位名或相邻字段文本混入。
回滚：单文件改动，`git checkout -- <该文件>` 会丢失 spec-032.1 的在途改动，**禁止**；如需回滚请手工删掉本任务新增的分支。

## 8. 产出物、执行结果与变更日志

- **产出物**：修改后的 `backend/app/paper_discovery/infrastructure/usenix_paper_parser.py`（仅 `_Blocks` + 模块级字段类名常量）、
  真实化的 4 个列表页 fixture、`tests/test_usenix_paper_parser.py` 新增用例。
- **执行结果（2026-09-12，三轮修正后由主会话独立复核）**：
  1. 第一轮（`backend-dev`）：`_Blocks` 字段匹配从「仅 `<p>`」放宽到任意元素，新增 `_open_tags` 深度栈与
     `_close_finished_fields()`；4 个 fixture 改为真实 DOM。独立复核：`pytest tests/test_usenix_paper_parser.py
     tests/test_usenix_publication_source.py tests/test_usenix_detail_tool.py -q` → **70 passed**；
     4 个真实页面作者非空 **256/256、97/97、82/82、245/245**（修复前全 0）。
  2. 第二轮（`backend-dev`）：排除 people 字段内 `<em>` 单位名，并把 `,` / `, and ` 归一为 `;`
     （`_split_authors` 本体未动）。独立复核：**74 passed**；「含单词作者或含 `@` 作者」由
     **68/680（10%）降到 1/680**（仅 `list24` 一篇真实单名作者 `Asmita`）。
  3. 第三轮（`backend-dev`）：people 字段**只取首个 `<p>`**，丢弃同一字段内后续 `<p>` 的获奖横幅。
     独立复核：**77 passed**；「作者含 `Award`/`Distinguished`/`Winner`」由 **33 篇降到 0**；
     2022 technical-sessions 作者总数 1275、空作者 0、空摘要 0；
     `OpenVPN is Open to VPN Fingerprinting` → 恰好 7 位、无获奖标记。
  4. `ruff check backend/app/paper_discovery/infrastructure/usenix_paper_parser.py` → `All checks passed!`
- **变更日志**：
  | 时间 | 角色 | 动作 |
  |---|---|---|
  | 2026-09-12 | `backend-dev` ×3 + 架构师(自身)复核 | 实现并独立验证本任务全部验收项；未跑全量回归（按用户要求）；未 commit / 未 push |
