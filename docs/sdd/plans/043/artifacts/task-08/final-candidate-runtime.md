# BLOCKED — Task08 final-candidate runtime smoke (`a328932`)

## 结论

**运行时/API 冒烟通过；Task08 最终验收仍 BLOCKED。** 当前服务为候选 `a328932`、端口 `8000`，`/api/ready=true`，首页和 `styles.css?v=59`、`literature-maps.css?v=10`、`literature-maps.js?v=13` 均真实 HTTP 200。两张既有地图、全文 analysis、目标文档状态，以及真实 application binding 消息路径均已只读/真实 HTTP 核验。

本报告不是 Spec 完成或人工验收签字。当前候选的浏览器复验、全量回归、当前候选新建地图/失败恢复路径和最终验收签字不在本次 runtime-only smoke 范围内，因此不输出 `READY_FOR_USER`。

脱敏、不可覆盖的运行证据：[evidence.json](runs/20261022-092419-a328932-final-runtime/evidence.json)。

## 运行环境与入口

- 候选提交：`a328932`；分支：`codex/spec043-literature-map`。
- 服务：`http://127.0.0.1:8000/`；主会话提供的前台服务 session：`3216`。
- `/api/ready`：HTTP 200，`ready=true`；jieba、Ollama tags、embedding、Qdrant 均 `ready`。
- `/api/health`：HTTP 200，`status=ok`，模型 `qwen3.8:27b`。
- 本次未部署、未改业务代码/数据库、未调用 S2、未下载/重索引、未改变 Ollama LAN。

## 首页与静态资源

首页 `GET /` 返回 HTTP 200，页面实际引用：

- `/assets/styles.css?v=59` — HEAD 200，`text/css`。
- `/assets/literature-maps.css?v=10` — HEAD 200，`text/css`。
- `/assets/literature-maps.js?v=13` — HEAD 200，`text/javascript`。

## 两张既有地图的边界

这两张地图是不同的验收资产，不能把 GAT 节点归错：

1. `35a56c6f2da84fca85fc3c21dfa0055c` 是 Task08 受控恢复/导出地图。`GET /api/literature-maps/{id}` 与 `/graph` 均 200，地图 `partial`、revision `5`、`project_id=null`；图谱为 21 nodes / 17 edges，最新 `preview_apply` job `bc9fc2724e1f4f11a4b309fc644df393` 为 `completed/apply`。本报告不声称目标全文 GAT node 属于这张图。
2. `0baabeae7268429c9f7e4de8098ae1d0` 是单独的全文 ready 地图。`GET` 与 `/graph` 均 200，地图 `partial`、revision `124`、`project_id=null`；图谱为 21 nodes / 18 edges。GAT node `21041260a5394f42891b020128fa60fa` 和 document `55afc3b8f01445429462fe78ed0d4c98` 属于这张图，最新 analysis job `1655a96b6f054c66931260204caaefa4` 为 `completed/finished`。

## 全文 analysis 与文档状态

目标节点 analyses GET HTTP 200，source gate 为：`abstract_available=true`、`fulltext_ready=true`、可用依据为 `abstract/full`；全文 source version 为 `a253fa60f4d0444592fd52f89e23016e8d437f01335f300b176d610eeefa644c`。既有全文 analysis `3bb20a9a794d4104b13fc1fe5f581c66` version 2 为 `completed`，摘要 version 1 `7c63cba835c044859c571dbc87f6a48a` 也保留为 `completed`。

目标文档 `55afc3b8f01445429462fe78ed0d4c98` 的 documents/papers GET 均 HTTP 200：`status=indexed`、`source_hash_state=verified`，source/indexed hash 相等；v1 为 57 chunks、v2 为 92 chunks，均 `indexed`/100%/无错误。没有调用 reindex 或 inspection。

## 真实 application binding smoke

对既有全文会话 `cc9f02f3d8184943bee35b4a23aa9481` 通过真实 HTTP POST 发送短问题，请求 schema 为：

```json
{"content":"请用一句话给出本文标题","model":"qwen3.8:27b","reasoning_effort":"off","mode":"normal"}
```

捕获的 HTTP 200 SSE 摘要：

- `meta` 显示 conversation、模型 `qwen3.8:27b`、`reasoning_effort=off`、`mode=normal`。
- 共 13 个事件，序号严格 `1..13`：`meta=1`、`progress=7`、`token=3`、`sources=1`、`done=1`。
- `done` 为 seq 13、`status=completed`；assistant message ID 为 `5f4bc7db81504e6b96d5f61caad0ae55`。
- sources 仅 1 个文档，document ID 精确为 `55afc3b8f01445429462fe78ed0d4c98`。
- 随后 messages GET HTTP 200，捕获 assistant 状态为 `completed`、last event seq 为 13。

第一次同内容 POST 已持久化为 completed turn，但当时流式摘要器没有输出；为取得可复核 SSE 摘要又执行了一次同内容 POST。两次均完成，证据只保留第二次的事件元数据；没有保存 token、回答正文、隐藏思考、凭据或用户历史。该重复探针不改变产品数据边界，但已在 JSON 中如实记录。

## 准备度与停止条件

| 检查项 | 本次结果 | 说明 |
|---|---|---|
| 服务、首页、ready/health | PASS | 当前候选真实 HTTP 200/ready |
| 既有地图、analysis、文档产物读取 | PASS | 两图身份分离；全文文档状态真实为 indexed/verified |
| application binding 自然语言问题与 SSE | PASS | HTTP 200，done completed，sources 单文档 |
| 当前候选新建地图、失败恢复 | 未执行 | 本轮禁止扩大到新建/重试/外部 provider |
| 前端处理中提示、页面/API 一致性 | 未验证 | 需当前候选浏览器证据 |
| 全量回归与最终人工验收签字 | 未验证 | 不由本运行时冒烟替代 |

按 `spec-acceptance-protocol`，缺少当前候选浏览器/全量/签字等前置证据，当前结论为 **BLOCKED**。需要主会话在这些独立门禁完成后再决定是否进入 `READY_FOR_USER`；本报告不声称 Spec 已完成。

## 可复核路径

- 运行证据：[runs/20261022-092419-a328932-final-runtime/evidence.json](runs/20261022-092419-a328932-final-runtime/evidence.json)
- Task08 地图导出资产：[map JSON](exports/task08-live-map-export.json)、[map PNG](exports/task08-live-map-export.png)
- 全文历史 API 资产：[Task05 full API artifact](../task-05/runs/20261021-172344-82c816f-full/api-e2e.json)
