# Spec043 三项 UX 缺陷修订复盘（2026-11-06）

## 一、范围与结果

用户在人工验收阶段连续反馈三项缺陷：① 地图列表卡片显示建图目标数 `20 篇` 而非当前 32 篇；② 「在知识库中查看」只切页面不定位论文；③ 整理／移动地图后切走再回来丢失位置与视口。按 Bug 规则挂在已完成的 `Spec043` 下，不新建编号；用户逐条确认后追加「用户确认与冻结范围」并额外纳入 `partial` 徽标修正，冻结 4 项实现范围与 8 条「明确不做」。

最终：卡片「可用 32 篇」；目标文档跳转后高亮、focus、滚动到视口内；zoom-out 后**小于 500ms 防抖窗口**立即切走，`revision 287 → 288`、`viewport.scale 2.3333`、`view_initialized=true`，切回后视口保持不回初始。真实服务 `/api/health 200`，验收准备度 10/10，P0/P1=0。

## 二、验证数据

| 项 | 结果 |
|---|---|
| 后端定向回归 | `240 passed` |
| 前端契约回归 | `396 passed / 0 failed`（分 5 批） |
| node vm | `24 PASS / 0 FAIL` |
| ruff | 4 条告警，与 HEAD 基线逐条相同（既有债） |
| 分端复审 | 后端「通过」、前端「通过（无保留）」，P0/P1=0 |
| 验收 | `043-ux-defects-acceptance-review.md` PASS；架构师 `043-ux-defects-merge-decision.md` 同意收口 |
| 真实 E2E | `043-ux-defects-live-e2e.md`（含修复前→修复后逐项对照） |

## 三、两轮 P1 与两个 E2E 独有发现

**第 1 轮评审 P1**：`keepLocalView` 机制建好但无调用方传参（不可达）；`view_initialized` 后端从不写入（前端显式分支空转）；`service.py` 越表未登记。修复后集中复审闭合。

**第 2 轮评审／回归 P1**：`keepLocalView` 读路径未吸收服务端 revision（409 风险）；`loadMapGraph` 未校验 `positions` 地图归属（跨图结构性缺口）；`resolveInitialFitPending` 删掉极小缩放 fit 启发式，破坏既有提交 `61096ed6 fix(maps): fit unreadable opening views`（`test_first_open_fits_a_tiny_saved_view_to_the_real_canvas` 稳定失败）；`literature-maps.css` 改了内容却未升 `?v=`。修复方式是把 fit 判定改为「有显式保存证据 → 绝不 fit；无任何证据 → 恢复旧启发式」，两条契约并存。

**真实 Chromium E2E 抓到两个单测完全没覆盖的时序缺陷**：

1. **跳转假阳性**：状态栏写「已定位到知识库中的该文档」，但目标 `li` 无高亮、无 focus、`rectTop=10505`（视口高 720）。根因是 `showView('kb')` 内部与 `jumpToKnowledgeBase` 自身共两次 `loadKbPapers()` 重建列表，把旧 DOM 上的 class/focus/scroll 全部冲掉。修法：删除「对跳转前旧 DOM 立即定位」分支，`pendingKbPaperId` 保留为当前跳转目标，由每次 `renderKbPapers()` 末尾在新 DOM 上重新定位，并加 `item.isConnected` 拒绝旧节点写状态。
2. **flush 从未发出**：`app.js` 的 `showView()` 先 `hideAllMainAreas()` 再 `setActive(false)`，flush 时 SVG 实测 `0×0`，`saveView()` 的 `if (!viewport.valid) return false` 早退，PATCH 从未发出 —— 这正是用户抱怨「移了位置之后下次查看又是原来的位置」的**最终根因**，前两轮代码修复都绕过了它。修法：`if (!viewport.valid && !allowInactive) return false`，仅放行离开时 flush；PATCH body 只用 `state.view`，测量值不进 payload，普通 active 路径守卫完好。

**教训**：node vm 单测与 `TestClient` 都覆盖不了「视图隐藏顺序」与「异步重渲染时序」。本轮若只按单端回归 READY 就收口，会带着两个用户可见缺陷上线。真实浏览器 E2E + 修复前／修复后对照是必要门禁，不是可选项。

## 四、流程偏差（如实记录，不追认）

- **Gate 1/2 增量需求／技术评审**由 `architect` 与实现**并行补做**，属收口阶段增量评审，**不追认实现前拦截**；记为流程改进项 R-1。历史 `043-requirement-review.md` / `043-tech-review.md` 仍为原 spec 的有效评审。
- **验收签字**由 `architect` 与 `tester` 并行产出；`merge-decision.md` 已注明「以 tester 报告最终结论为准」及签字生效条件。
- **两处越表文件**：FE-4（`literature-maps.css` / `styles.css`）经 T-7 裁决、BE-3（`backend/app/literature_maps/application/service.py`）经后端复审裁决，均为冻结项的**必要配套、非范围扩张**，已在 spec 任务表补登记（`:457-460`），并确立「任务表外文件须先裁决／同提交补登记」约束。
- **版本号**：同批次多次改动最终定为 `app.js?v=70` / `literature-maps.js?v=42` / `literature-maps.css?v=27` / `styles.css?v=68`；早前评审文档中的 69/41 为过期快照，以工作区实况为准。

## 五、残余 P2（7 条，非阻塞，转后续 spec）

1. flush 409 失败后 `positionsDirty` 残留，`active=false` 时不重排，需 `setActive(true)` 显式补偿。
2. KB indexing 窗口内轮询会重复滚动到跳转目标。
3. `jumpToKnowledgeBase` 返回 promise 在两处调用点未消费（已兜底，可读性）。
4. `allowInactive 放行 + 测量值不进 payload` 缺单测断言。
5. 导出 JSON 新增 `view_initialized` 键属接口面纯新增，需在使用文档中说明。
6. `active_node_counts` docstring 未标注 ids≤100 边界；`view_initialized` 单向单调未写明。
7. 两处 `re.findall(...)[-1]` 版本断言依赖「最后一处版本号即生效值」的隐含假设，建议改精确匹配 `src=`。

## 六、后续建议

- 把「真实浏览器 E2E：跳转定位 + 跨视图保存」固化为 Spec043 人工验收回归脚本，避免后续改动再次绕过时序路径。
- 统一 SQLite 连接工厂、FD block shell 自动化回归等上一轮遗留 P2 可与本轮 P2 合并为一个技术债 spec。
- `architecture-boundary-guards` / Spec044 仍待用户决策，本轮未触碰。
