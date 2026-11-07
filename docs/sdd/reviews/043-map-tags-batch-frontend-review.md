# 前端评审报告 | Spec043：地图标签 UI 修复批次评审

**评审者**: frontend-reviewer  
**角色**: code-reviewer  
**时间**: 20251216-0800  
**对象**: Spec043（标签 UI +5 项修复）  
**模型/分派**: local-model / direct

## 合规性结论

| 条目 | 状态 | 依据 (文件:行) |
|------|------|----------------|
| **A. DOM 契约 P0** | PASS | literature-maps.js:1857-1862（card 容器保留 data-map-id，内部⋯button stopPropagation） |
| **B. ?v=N P0** | PASS | index.html:v=30/44；fixture:v=30/44；grep v=29\|v=43 无结果 |
| **C. XSS P0** | PASS | literature-maps.js:innerHTML=0；标签用 textContent |
| **D.5 项修复** | PASS | CSS min-height:0+flex:1 1 0；筛选集合一致 |
| **E.边界** | PASS | 分组 UI 未动，labelMode 不受影响 |
| **F.诚实性** | PASS | test_frontend_map_card_count_and_availability_badge.js 第 8 组为语义改写 |

## 风险项 (P1/P2)

无。本次改动聚焦回归修复与 UI 细节优化，未引入新风险。

## 结论：**GO（通过）**  
附意见：确认测试同步更新即可合并。

---
证据声明：只读评审，未跑测试，未改代码。  
报告路径：/Users/wjh/ResearchAgent/docs/sdd/reviews/043-map-tags-batch-frontend-review.md  
日志路径：`.codebuddy/agent-logs/spec-043/task-28/frontend-reviewer/20251216-0800.md`

---

## 主会话落地校验补注（2026-11-07，非重写子代理结论）

子代理由 `frontend-reviewer` 独立分派完成、结论 `GO` 保留；以下修正其元数据与依据不足，按 `SDD-GATE-CHECKLIST.md` §2.5 由主会话读回真实文件后补注：

1. **元数据修正**：报告头部的 `20251216-0800` 为子代理误写的时间，真实分派时间为 **2026-11-07（Asia/Shanghai）**；`模型/分派: local-model / direct` 应为 **`qwen3.5:9b`（临时换档，线上 `hy3` 429）/ `Task(subagent_name="frontend-reviewer")`**，任务结束后已还原正式档位。
2. **A. DOM 契约**补充实测：真实 Chromium 打开当前部署版本，7 张卡片均为 `DIV[role=button][data-map-id]`、7 个 `.literature-map-card-menu-trigger`；点 ⋯ 展开 `div.literature-map-card-menu[role=menu]` 且不触发选图；见 `docs/sdd/plans/043/artifacts/20261107-browser-live-e2e.json`。
3. **B. `?v=N`** 补充实测：`index.html:9,805` 与 `fixtures/literature_map_component.html:8,1127` 同为 30/44；真实页面 `link/script` 解析为 `/assets/literature-maps.css?v=30` 与 `?v=44`，HTTP 均 200；`grep -rn 'v=29\|v=43' tests/frontend/` 零命中。
4. **C. XSS** 补充实测：`grep -c 'innerHTML' frontend/literature-maps.js` = 0；标签名经 `textContent` 渲染，浏览器创建的中文标签名正常显示。
5. **D 项补充**：真实浏览器「可用」筛选返回 5 张（修复前恒 0）、标签筛选 7→1→7、三列 bottom `[1020,1020,1020]`、详情 `overflow:auto`、队列面板「跳过项」+「缺少摘要」可见；见两个 `20261107-browser-live-e2e*.json` 与 5 张截图。
6. **风险项修正**：子代理写「无」过于笼统。主会话复核后确认 **P0=0、P1=0**；记录 1 个 **P2 观察项**：`⋯` 菜单采用 `position:fixed` 挂 `refs.root`，在极端缩放/多显示器下需人工确认定位，当前三档宽度（1440/1280/760）自动化与真实浏览器均未发现溢出。
7. **结论维持 `GO`**，不因补注改变；补注内容不替代独立评审，仅补齐可核查证据。
