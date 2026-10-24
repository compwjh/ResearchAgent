# Task09 indexed/full 阶段真实浏览器结果（暂不作最终 manual-ready）

运行：`20261024-205007-task09-import-full`
服务：`http://127.0.0.1:8000/`
资源：`literature-maps.js?v=18`、`literature-maps.css?v=12`、`app.js?v=60`
浏览器：Chromium `136.0.7103.25`

## 已确认的真实 indexed 状态

目标地图：`9b1e4739443e40c98400cfb69aec1e45`
目标节点：`2e35b888d3cb414090e2d8e55e5bae1a`
目标 document：`ae3a1c3f7ee746bba031b06306ff3230`

- 节点 GET HTTP 200，`document_id` 已绑定，`download_status=indexed`。
- `/api/kb/documents?limit=100` 中同一 document 为 `status=indexed`、PDF `2018-Conference-Exploring-Visual-Relationship-for-Image-Captioning.pdf`、`chunk_count=66`；v1 `indexed / 66 / progress 100`，v2 `indexed / 51 / progress 100`，`error=null`。
- HEAD `/api/kb/documents/ae3a1c3f7ee746bba031b06306ff3230/source` 返回 HTTP 200、`content-type=application/pdf`、`content-length=3088287`（约 3.09 MB），未下载正文。
- 真实页面详情显示：`已加入知识库 · 文档 ID：ae3a1c3f7ee746bba031b06306ff3230`、`在知识库中查看`、`入库状态：indexed`。

截图：[indexed 节点面板](screenshots/01-indexed-full-entry.png)

## Full gate 当前事实（阻塞，未伪装 ready）

节点 analyses/source-status 的有限轮询结果：

- 初始无分析；后台唯一分析随后为 `analysis_id=6979b54169044b5ab5339215495782d5`、`job_id=94dad8d2789146fbabd429169a8f48cd`，状态 `pending → running → completed`。
- 该分析的 `evidence_level=abstract`，source version `de788f55ac4bf0fa28bb823fbc2adf27f1be389b6ea329e742ac5eca970b30aa`；不是 full analysis，且不是本代理触发。
- 轮询结束时 `source_status.fulltext_ready=false`、`available_evidence_levels=[abstract]`、`source_versions.full=null`。
- 真实 Full 页签可切换，但页面仍显示：“全文索引尚未就绪；请先主动入库并等待索引完成。”并显示“打开知识库处理全文”；全文分析入口不可作为已 ready 成功。

这形成一个需主会话/合法恢复流程处理的引导缺口：KB 列表已显示 indexed，但 map analysis source gate 仍未形成 v1 full manifest；本阶段不调用 inspect/reindex，不发 full/import/regen，不把 indexed 文档冒充 full-ready。

## 提问草稿只读验证

在真实页面预先填入测试草稿 `用户已有草稿：请不要覆盖（Task09 indexed/full runtime）`，点击“关于本篇提问”一次：

- 真实 conversation：`bedb0cdcb5194095abf35a1e464c493f`。
- 页面打开会话后 `#question` 完整保留原草稿，`draft_preserved=true`。
- 没有 `/messages` POST、SSE 或发送动作；本代理没有点击发送。
- 该会话 POST 是本次人工案例所需的会话桥接，不是 fullanalysis/import/regen。

## 请求与边界

- 页面仅产生既有地图允许的 `analysis-queue/ensure` 与上述 conversation POST。
- 本代理发出的禁止写请求：full analysis 0、import 0、regen 0、download 0、reindex/inspect 0。
- 目标地图当前真实队列仍为 partial/active（读取时 `20 total, 3 completed, 15 queued, 1 running, 0 failed, 1 skipped`）；fresh 主例 `858b78f0d9e047efa6d8d1559d83a6de` 的已验证 evidence 仍在先前 run（18 completed、2 skipped）。

## 阶段结论

`BLOCKED_FULL_GATE_INDEX_MANIFEST`：已确认真实 import/indexed、文档入口和草稿不发送；full gate 尚未合法恢复。保留本阶段截图和实体 ID，待主会话完成允许的恢复后，再补写最终 [`task-09-manual-acceptance.md`](../task-09-manual-acceptance.md)，不把本阶段结果当作最终用户 READY。
