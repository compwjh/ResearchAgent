# Spec-043 Task-05 浏览器真实 Smoke（frontend-tester）

## 结论

**PASS（前端浏览器 smoke）**。候选 `b94717c` 在 `http://127.0.0.1:8000/` 的文献地图、真实节点详情、摘要分析展示、历史项点击以及“关于本篇提问”导航均通过。本轮没有重复触发摘要/全文模型 POST；唯一允许的写操作是点击“关于本篇提问”创建/复用 conversation，未发送问题。

全文分析没有被判定为成功：真实接口产物明确返回 `409 MAP_FULLTEXT_UNAVAILABLE`，页面保持“基于全文分析”禁用，符合 `fulltext_ready=false` 的合同。

## 实体与运行环境

- 浏览器：真实 Chrome，会话 tab `325738149`（CUA）。
- 候选：`b94717c`；服务 `127.0.0.1:8000`。
- 复用地图：`0baabeae7268429c9f7e4de8098ae1d0`，页面标题 `API E2E graph attention networks r2`。
- 目标节点：`21041260a5394f42891b020128fa60fa`，`Graph Attention Networks`。
- 页面入口版本：`app.js?v=59`、`literature-maps.js?v=8`、`literature-maps.css?v=6`；通用站点样式实际为 `styles.css?v=57`。
- 版本请求只读检查：`GET /`、`GET /assets/literature-maps.js?v=8`、`GET /assets/literature-maps.css?v=6` 均 HTTP 200。

## 浏览器步骤与观察

1. 打开文献地图。真实列表显示 `2/2`；选中地图后中心显示 `21 个节点 · 18 条关系 · 已完成 · 阶段：地图可用`。
2. 点击 GAT 节点。详情显示真实作者、年份 `2017`、会议、摘要、引用数 `29014`、`indexed`，以及知识库文档 `55afc3b8f01445429462fe78ed0d4c98`。
3. 只读检查 AI 分析面板：显示 `可用依据：摘要级`；摘要 source version 为 `c518a10f28b2656ae30f53790a67ef835c8ebe219168460969b763f481d1e42c`；全文索引片段依据显示“未提供”；摘要按钮可用，全文按钮 disabled。
4. 读取真实后端产物 `runs/20261021-002317-b94717c/abstract-poll-03.json`。v1 摘要分析为 `completed`，摘要非空，`source_refs` 明确为摘要来源；`full-submit.json`/headers 为 `409 MAP_FULLTEXT_UNAVAILABLE`，`source_status.fulltext_ready=false`、`source_versions.full=null`。页面与接口状态一致。
5. 点击历史列表中唯一的 `v1 · 摘要级 · 已完成`。页面仍显示同一摘要、同一 source version 和“依据：摘要级”，全文依据仍为“未提供”；没有第二版本，未伪造跨版本对比。
6. 点击“关于本篇提问”。真实 URL 为 `/c/3eb7139887ec46a6a4f6973bd973d669`；侧栏选中“关于论文：Graph Attention Networks”，新会话输入框为空、没有用户消息/模型消息。未发送问题。

## 范围与证据边界

- 本轮没有点击分析按钮，没有重复摘要/全文生成，没有启动新服务，没有改代码，没有跑后端 pytest 或全量回归。
- 摘要/full 的 API 文件是同一候选的真实 HTTP 证据，仅作只读核对；不把 fixture 或历史结果冒充本轮浏览器生成。
- CUA 提供了实时地图详情和会话跳转截图，但未产生可引用的本地截图文件路径；因此本报告不虚构截图路径。
- 进度日志：`.codebuddy/agent-logs/spec-043/task-05/frontend-tester/20261021-002418.md`。

## 缺陷结论

- P0：无。
- P1：无。
- 本轮未发现前端 DOM、source/evidence 串线、全文禁用条件或会话导航缺陷。
