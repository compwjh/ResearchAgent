# 复盘：知识库论文卡片布局缺陷（2026-09-02）

> 关联：`docs/sdd/specs/012-kb-recall-quality.md`（交付后缺陷修复，同功能范围，未新建编号）
> 性质：纯前端布局缺陷，无后端接口/数据问题，无 spec 范围变化。

## 一、缺陷与现象

用户反馈：知识库中论文卡片**内容展示不完全**——「重建索引 / 删除」按钮看不到、标题也展示不完全。

## 二、根因（两条，均在 CSS 布局，不在 JS 逻辑）

| # | 现象 | 根因 | 触发条件 |
|---|---|---|---|
| 1 | 标题被截成「…」 | `.kb-item-name` 是 `white-space: nowrap` + `overflow: hidden` + `text-overflow: ellipsis`，并与页数 meta 在同一 flex 行争抢宽度 | 侧栏仅 320px，任何长文件名必被截断 |
| 2 | 操作按钮看不到 | `.kb-item` 是 3 行 grid（head / versions / actions），双版本徽章 + 进度条把单卡撑到约 110px；而 `.kb-side` 高度固定（`height: calc(100vh - 130px)`）、`.kb-list` 是 `flex:1 + overflow-y:auto`，可视区仅约 300px | 论文 ≥3 篇时，按钮落在滚动区之外 |

关键点：**按钮在 DOM 里是存在的**（`renderKbPapers` 正确创建了 `kb-item-actions`），只是被容器可视区裁切——这类缺陷不会让任何接口测试或 `node --check` 失败。

## 三、修复

1. 标题独占一行、完整换行显示：`display:block` + `word-break:break-word` + `overflow-wrap:anywhere`，去掉 nowrap/ellipsis；meta 独立成行；侧栏 320px → 360px。
2. `actions` 移入版本徽章行并右对齐（`margin-left:auto`），进度条改为独占一行、去掉 `flex:1 1 90px` 的横向挤占；单卡高度约 110px → 约 80px。
3. 按钮补 `border: 1px solid var(--line)` 与 `white-space: nowrap`，提升可辨识度（此前是无边框灰底，视觉上像一段文字而非按钮）。
4. 静态资源 `?v=12` → `?v=13`。

验证：`node --check` 通过；服务冒烟 `/` 200、新 CSS/JS 已发布；全量回归 `253 passed`。

## 四、为什么验收没抓到（流程教训）

spec-012 的验收评审（`012-acceptance-review.md`）覆盖很扎实——跑了真实 PDF、校验了接口、核对了 DOM 契约（JS 里的 class 是否在 CSS 中存在）。但**没有一项验证「元素在真实视口里是否可见」**：

- 静态代码核对能证明 `kb-item-actions` 被创建、CSS 里有定义，**证明不了它没被滚动区裁掉**；
- 本次新增的双版本徽章 + 进度条是我自己在 spec-012 期间加的，它把卡片高度抬高了约 30px，**属于「新增内容撑破了既有固定高度容器」**——改动方正是我自己，但当时只关注功能，没回头核算容器容量。

可复用规则（建议后续沿用）：

1. **在固定高度容器内新增内容时，必须回头核算容量**：容器高度 / 单卡高度 = 可见条数。低于 3 条就要么压缩单卡，要么调整容器。
2. **「DOM 契约校验」要升级为「可见性校验」**：除了 class 是否在 CSS 中定义，还要确认元素是否在可视区内、有没有被 `nowrap`/`ellipsis`/`overflow:hidden` 吃掉内容。能用 headless 浏览器量一次 `getBoundingClientRect` 最稳（本项目有 `playwright-cli`/`agent-browser` skill 可用）。
3. **验收清单补一条**：涉及 UI 的 spec，验收点需包含「在目标视口下的渲染确认」，不能只靠静态核对 + 接口实测。

## 五、未决

- 列表仍是滚动区：论文很多时（>4 篇）下方的卡片仍需滚动才能看到按钮。这是侧栏固定高度的固有约束，当前认为可接受；若后续论文数量增长导致体验恶化，再考虑侧栏独立滚动分页或卡片折叠。
- v2 切分质量仍未经真实论文端到端确认（spec-012 遗留的非阻塞建议，此处重申）。
