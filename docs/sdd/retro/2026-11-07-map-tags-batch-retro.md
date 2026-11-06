# 复盘：Spec043 七项合并批次（含地图级标签分类系统）

日期：2026-11-07（Asia/Shanghai）｜分支：`feature/spec-043-map-tags-and-ux-batch`

## 1. 做了什么

用户一次性确认七项：①次级按钮视觉可用性 ②新建地图级标签分类系统（沿用 `:651-700` 设计、挂 Spec043、不建 045）③详情面板三列同底 ④「可用」筛选为空 Bug ⑤「跳过 2」无原因 Bug ⑥「主题相似」无感 ⑦单篇全文 RAG 被误判为深度研究 Bug（默认 A+B）。用户明确「全部修了，不用拆分」，故合并为一个跨端批次、一次版本号、一次回归、一次部署、一次提交。

## 2. 关键决策与边界

- **不做「分组」→「标签」改名**：用户两次强调节点分组功能必须保留、且刚验收收口。冻结为「节点级仍叫分组、地图级叫标签」两套术语并存，撤销历史提案里的 23 处文案改名验证项。
- **C（删分组）永久排除**：从待决策阶段起写入冻结边界，实现全程未触碰 `literature_map_groups` / `/groups` / `group_id`。
- **revision 不得递增**：标签绑定若递增 `literature_maps.revision` 会与 `PATCH /view` 的 409 乐观锁踩踏。作为 Gate 2 P0 约束下发，`store.py` 纯新增 239 行、零删除，双用例覆盖。
- **版本号双点同步**：`index.html` 与 `fixtures/literature_map_component.html` 必须同时升，且 6 个既有测试文件硬编码断言同步；Gate 2 把它列为 P0，实际执行中未漏。

## 3. 分派通道：本批次最大的非技术成本

| 阶段 | 档位 | 现象 | 处置 |
|---|---|---|---|
| Gate 2 评审 | `Deepseek-V4.1-Flash` | 连续 4 次 429 | 按失败处置换档 |
| Gate 2 评审 | `qwen3.8:27b-mlx` | 一次 `No result found`（无日志、非 OOM，内存空闲 85%） | 还原线上档重试 |
| Gate 2 评审 | `qwen3.5:9b` | 成功（14 次工具调用 / 156s），但产出混入上一批次无关段落、模型字段空泛 | 主会话按 §2.5 读回核实代码事实后修订，三处留痕（非代写结论） |
| Gate 4 实现 | `Deepseek-V4.1-Flash` | 429 | 换档 |
| Gate 4 实现 | `qwen3.8:27b-mlx` ×2 | 19 次/270s、17 次/292s 均上下文超限，`git diff -- backend/ tests/` 为空 | 记录阻塞、还原档位、停下告知用户 |
| Gate 4 实现 | `hy3`（用户授权临时 0.00 倍率） | **7 次分派全部成功** | 用户授权后解除阻塞 |
| 评审 / 验收 | `hy3` / `qwen3.5:9b` | 评审阶段额度耗尽 429；9b 三次零落盘 | 纯文档产出由主模型代行并注明 |

**经验**：
1. 本地 27B 不适合本项目 `store.py`（5005 行）这类大文件任务——4 份自动加载的 SKILL.md 叠加文件片段即超 32k 上下文，即使主会话把结构事实喂进 prompt 也仍会爆。不是 OOM，也不是配置错误。
2. `qwen3.5:9b` 能稳定完成**短、只读、结构化**的评审章节，但会拼贴历史内容；不能用于含并发/事务的后端实现，也不适合长 diff 代码评审。
3. 线上档位 429 是账号级频率限制，重试无意义；按文档换档或请用户授权临时档位是有效路径。临时档位必须**只改 agent 的 `model` 字段、任务结束还原、不写进任何流程纪律文档或提交信息**（2026-09-12 曾把 `hy3` 误固化为规范，本批次遵守了这条教训）。
4. 主模型代行只能用于**纯文档**（评审报告、验收报告、台账、复盘、spec 同步）；含 `.py/.js/.html/.css` 的实现一律分派，本批次无一次例外。

## 4. 真实回归与修复

FE-1b 为修「右下角空白」直接删除详情面板 `max-height`，导致 `test_frontend_map_layout_viewport.py` 1440/1280 两例失败：画布高度 541.9 → 1034.16。根因不是「max-height 该不该删」，而是 **grid item 默认 `min-height:auto` + 内层 `flex:1 1 auto` 让长内容顶高整行**。

FE-1c 的正确解：列表面板保留 `min-height: min(700px, calc(100vh-160px))` 决定行高，详情面板改 `min-height:0`、详情内层 `flex:1 1 0`（flex-basis 归零解除 max-content 增长上限）、保留 `overflow:auto`。修复后三列 bottom `[1020,1020,1020]`、画布高度前后不变、427 passed。

**教训**：「删掉钳制」与「跟随行高」不是同一件事；涉及 grid 高度必须同时处理最小尺寸与增长上限，并用真实浏览器量三列 bottom，不能只看静态 CSS。

## 5. 验证数据（真实执行，非计划）

- 后端 `pytest tests/literature_maps tests/research/test_single_paper_rag_intent_routing.py tests/research/test_research_intake_intent_routing.py -q` → exit 0 / **306 passed**。
- 前端 `pytest tests/frontend -q` → exit 0 / **427 passed**（修复前 425 passed / 2 failed）。
- `node --check` / `py_compile` → exit 0；`grep -c 'innerHTML' frontend/literature-maps.js` = 0。
- 真实 API E2E `20261107-map-tags-live-e2e.json`：8 项全绿（201/409/200/tags/旧字段/422/200/清空），队列 `skipped_items` 2 条带原因。
- 真实浏览器 E2E：标签创建→徽标→筛选 7→1→取消 7、「可用」筛选 **5 张**（修复前恒 0）、三列同底、详情内部滚动、「跳过项」+「缺少摘要」可见；5 张截图落盘。
- 部署：8000 重启后新 PID 29829，`health/home/css?v=30/js?v=44` 均 200，新端点 `/api/literature-maps/tags` 200 证明新后端代码已加载。

## 6. 未做到 / 不冒充

- 第 7 项未执行需 LLM 全链路的真实会话消息 API E2E；由 14 个跨边界用例 + 12 个硬门槛用例 + 真实 binding 落盘覆盖，**验收报告明确标注不等价于真实 API E2E**。
- 第 1 / 6 项未做像素级对比度与浏览器勾选前后边数计数，仅静态契约 + 自动化覆盖。
- 后端代码评审与验收评审由主模型代行（分派通道失败），已在报告头部、spec 评审记录/变更日志、台账三处留痕并注明「代行，非独立评审」。
- `tests/research` 全量在子代理环境超时（网络/LLM 用例），主会话对全部触碰被改代码路径的相关文件逐一运行全绿；未把「全量 research 通过」写入任何材料。

## 7. 后续建议（不扩入本批次）

1. 第 7 项补一次真实会话消息 API E2E（发完整草稿、检查 SSE 不含 `research_intake` / `deep-research-orchestration`、含 `rag_retrieval`），并按 spec `:1586-1591` 走人工验收 6 步。
2. 人工验收时按 P2 观察项点一次：像素级对比度、主题相似勾选前后边数、binding 读取失败提示。
3. 为本地 27B 分派精简 `skills` 白名单或改用「主会话喂最小片段 + 子代理回传片段」模式，避免大文件任务上下文超限。
4. `_assert_tag_owned()` 全量 `list_tags` 可在标签量增长后优化为按 `tag_id` 单点查询。
