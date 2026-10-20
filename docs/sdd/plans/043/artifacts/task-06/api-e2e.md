# Task06 真实 API E2E 验收记录

结论：**PASS（Task06 backend 分组/导出 HTTP 范围）**

本次只复用既有地图和 GAT 节点，未创建新地图、未调用 provider/model、未发送分析或问答请求，也未直接写生产数据库或知识库。浏览器 PNG 由后续前端验收负责，本报告不替代该门禁。

## 运行元数据

- run_id：`20261021-005937-62f29a4`
- 候选：`codex/spec043-literature-map`，commit `62f29a4`
- 地址：`http://127.0.0.1:8000/`，端口 `8000`
- `/api/ready`：HTTP 200，`ready=true`，warmup 组件均 ready
- 地图：`0baabeae7268429c9f7e4de8098ae1d0`
- GAT 节点：`21041260a5394f42891b020128fa60fa`
- 文档：`55afc3b8f01445429462fe78ed0d4c98`
- 脱敏运行摘要：[`api-e2e.json`](runs/20261021-005937-62f29a4/api-e2e.json)

总计真实 HTTP 请求 27 个：26 个 HTTP 200、1 个预期 HTTP 409；17 个只读 GET、10 个仅作用于该地图的分组写请求。原始导出只存于受控临时目录，未写入仓库；仓库仅保存目标 ID、计数和安全性结论。

## 地图与初始状态

初始 GET 读回地图 revision `9`、status `partial`、`project_id=null`。GAT 节点的 document_id 精确匹配候选文档，`removed=false`、download_status=`indexed`。初始 graph 为 21 nodes、18 edges；目标节点位置为 `(120.0, 80.0)`，无 group。

## 分组创建、命名颜色与归属

1. POST `/groups`，`expected_revision=9`、名称“图注意力网络”、颜色 `#2F80ED`：HTTP 200，revision `10`，返回稳定 group ID。
2. PUT `/nodes/{node_id}/group` 将 GAT 节点归入该组：HTTP 200，revision `11`；节点 document_id 和位置保持不变。
3. PATCH 该组改名/改色为临时验收值：HTTP 200，revision `16`；随后 PATCH 恢复为“图注意力网络”与 `#2F80ED`：HTTP 200，revision `17`。服务端颜色规范化为大写。
4. 使用带首尾空格的同名和小写颜色做 normalized no-op PATCH：HTTP 200，revision 仍为 `17`，没有制造内容变化。

最终只保留合法组“图注意力网络”，GAT 节点归属该组，供后续浏览器验收使用。

## revision 冲突：PASS

在当前 revision `12` 下发送旧 `expected_revision=11` 的创建请求，真实返回 HTTP 409，错误码 `MAP_CONFLICT`。随后 GET groups 仍为 revision `12`、2 个原有测试组，冲突请求没有创建第三组或覆盖已有状态。

## 删除组只解绑：PASS

为避免删除保留组，另建临时组“临时删除验收组”，将 GAT 节点暂时归入后删除：

- 临时组创建：HTTP 200，revision `12`。
- 临时归属：HTTP 200，revision `13`。
- DELETE 临时组：HTTP 200，revision `14`，响应只剩持久组。
- 删除后 GET node：`group_id=null`、`removed=false`，document_id 仍匹配，download_status 仍 `indexed`。
- 删除后 GET KB document：status `indexed`、chunk_count `57`、`project_id=null`。
- 删除前后 graph 均为 21 nodes、18 edges；目标节点位置不变。

随后将 GAT 节点重新归入持久组，最终 revision 为 `17`。没有删除节点、论文原件、文档或边。

## 重开布局与 JSON 导出：PASS

重新 GET map、groups、node、graph 后，最终状态为 revision `17`、status `partial`、持久组 1 个，GAT 节点仍归组且位置为 `(120.0, 80.0)`。全图 positions 的脱敏哈希在初始 graph、删除前、删除后、最终 graph 和 export 中一致，证明分组操作未重写布局。

最终 GET `/api/literature-maps/{map_id}/export`：

- HTTP 200，`Content-Type: application/json`
- `Content-Disposition` 文件名为安全固定名 `literature-map.json`
- schema_version：`literature-map-export-v1`
- revision：`17`
- groups/nodes/edges：`1 / 21 / 18`
- GAT 节点 group_id 与持久组一致
- 所有边均有 source_id/target_id，且两端均为有效节点；方向字段可解析
- 敏感 key 扫描命中 `0`
- 不含 analysis、messages 或 owner_id

导出解析只保留上述目标与计数，没有把全量节点、边、文档列表写入验收产物。

## 证据与边界

- 运行 JSON：[`runs/20261021-005937-62f29a4/api-e2e.json`](runs/20261021-005937-62f29a4/api-e2e.json)
- JSON 仅含目标 map/node/document/group ID、HTTP 状态、revision、数量、布局等价性和导出安全扫描结果。
- 未运行 PNG 导出/浏览器保存打开；未触发 provider/model/KB；未运行全量回归。
- 本次 PASS 仅覆盖 Task06 backend 真实 HTTP 分组与 JSON 导出验收，不宣称 Spec043 总体收口。
