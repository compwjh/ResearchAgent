# Task05-D2b 前端双向交互契约报告

## 结论

`PASS`：原文 block、PDF locator overlay 与切片 item 均支持点击及 Enter/Space 键盘激活；v1 重叠关系和 v2 跨页关系保留全量关联，窄屏栏切换保存两侧 scrollTop。交互路径不监听 scroll、不发起额外请求、不触发 POST/reindex/embedding。

## 交互契约

- 原文 block 使用 `data-block-id`；切片使用 `data-chunk-id` 与空格分隔的完整 `data-block-ids`。
- 点击/Enter/Space 原文：激活对应原文及全部已渲染关联切片，切到切片栏并滚动/聚焦首项。
- 点击/Enter/Space 原文：若关联切片超出首批 100 条，先按本地 `chunkRows` 关系追加批次，再激活全部关联切片。
- 点击/Enter/Space 切片：激活切片及全部关联原文块；若 PDF 目标页尚未被 IntersectionObserver 渲染，先按 `block_id→page` 映射主动渲染并等待目标页，再切到原文栏并滚动/聚焦首项；v2 跨页 overlay 不截断。
- 高亮只通过 `data-active="true|false"` 与 `aria-current="true|false"` 表达；不依赖 `CSS.escape`，不把不可信文本写入 HTML。
- 每个 chunk row 保留完整 `anchorRelations`（`block_id`、`coverage`、`is_primary`、`unmapped_reason`）；按 primary 优先、coverage 降序选择首个滚动目标。`partial`/unmapped 状态及每项稳定原因通过 textContent 显示。
- 程序化滚动仅位于激活处理器；没有 scroll listener，因此不会形成滚动联动循环。
- 窄屏 pane 切换复用既有 tab/ARIA 状态并在每次切换前保存 source/chunks 两侧 scrollTop。

## 分段列表

切片关系先完整聚合，默认每批 100 条，加载更多按钮只追加本地已聚合数据。加载更多不调用 fetch；新增 item 继续绑定同一联动处理器，且切片 `data-block-ids` 关系不丢失。

## 版本与安全

`frontend/index.html` 中 `styles.css`、`app.js`、`kb-inspection.js` 均同步到 `?v=18`。Markdown 仍通过唯一 Marked→DOMPurify→block renderer；元数据和 hostile 输入均使用 DOM API/textContent。PDF.js 仍固定本地 4.10.38、同源 worker 与 D2a display-only API。

Inspection 请求维护 document/version 本地 ETag cache：304 有缓存时直接渲染缓存，无缓存显示 `INSPECTION_CACHE_MISS_304`；PDF observer root 绑定实际滚动容器 `#kb-source-content`。模块版本、manifest hash 以及可注入 worker version/hash mismatch 均映射稳定错误码。

真实浏览器 hostile fixture 入口为 `docs/sdd/fixtures/spec-018/frontend/hostile-fixture.html`，步骤和零外联允许清单见同目录 `README.md`；页面移除 Google Fonts 远程 @import，仅保留本地字体回退。

## 验证结果

| 检查 | exit code |
| --- | ---: |
| `node --check frontend/kb-inspection.js` | 0 |
| `node --check tests/test_frontend_kb_inspection_interaction.js` | 0 |
| renderer/runtime/PDF 契约测试 | 0 |
| interaction 契约测试 | 0 |
| `git diff --check` | 0 |

交互测试覆盖 v1 overlap、v2 跨页 overlay、懒加载页按需 materialize、首批外 chunk 按需追加、anchor coverage/primary/unmapped、click/Enter/Space、窄屏 scrollTop 保存、100 条分段加载、零额外网络和零 POST；runtime 测试额外覆盖 inspection ETag 304 cache/hit/miss。
