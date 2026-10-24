# Spec018 PDF safety repair：Task05 runtime evidence

## 运行范围

本记录引用 Task05 的真实 HTTP 运行 `20261021-015442-dd616d5-v1-reindex`，用于确认修复候选 `dd616d5` 上既有 GAT 文档的来源安全状态。只对 document `55afc3b8f01445429462fe78ed0d4c98` 执行一次 `chunker=v1` scoped reindex；没有启动/停止服务、直接写生产 DB、改 manifest、调用 provider 或执行全库重建。

证据主文件：[`Task05 api-e2e run`](../../../043/artifacts/task-05/runs/20261021-015442-dd616d5-v1-reindex/api-e2e.json)。运行时服务地址为 `http://127.0.0.1:8000/`，当次`/api/ready` HTTP 200 且 `ready=true`；不代表续跑时服务仍在线。

## 修复后真实 HTTP 结果

- `POST /api/kb/documents/{document_id}/reindex`，body `{"chunker":"v1"}`：HTTP 202，task `46266f04e0e445b6ab0dfbb2998f842b`，queued。
- 一次只读状态轮询：HTTP 200；目标文档和 v1 均 `indexed`，progress `100`，error null；没有第二次 reindex。
- `/api/kb/papers`：目标 canonical `source_hash_state=verified`，source/index hash 相等，v1 状态 `indexed/100`。
- 只读 v1 manifest：`status=ready`、progress `100`、`source_hash_state=verified`、mapped `57`、unmapped `0`、index fingerprint 存在。
- generation requirement：通过；节点 `document_id` 与目标精确匹配。

上述结果证明 scoped reindex 已将该文档发布到 verified/ready 状态，但不等于 map 全文门禁已经可用。

## Task05 map gate 结果

对 map `0baabeae7268429c9f7e4de8098ae1d0` / node `21041260a5394f42891b020128fa60fa` 的只读 analyses GET 返回 HTTP 200，但 `fulltext_ready=false`、`available_evidence_levels=["abstract"]`、`source_versions.full=null`。map 与 document 的 project ID 均为 null，owner-scoped association 集合中没有该 document 条目，因此部署候选无法计算 full `source_version`。

依据合同，本轮没有提交全文分析、幂等回放、全文会话、QA 或 SSE，也没有将既有摘要结果宣称为全文结果。Task05 的既有摘要成功、原始全文 409 和前一轮 reindex 失败证据保持不变。

## 图谱保护核验

scoped reindex 前后 graph 均为 revision `17`、status `partial`、`21` nodes、`18` edges；GAT 节点位置 `(120.0, 80.0)` 和 group ID `8c8f20f7a4c04e0e92f9cdd78fc01ce7` 保持不变。groups GET 为 HTTP 200，保留 `1` 个组。脱敏布局/分组哈希前后相同：`e88b7d51b1753bb9114c2b90f927fd140d66d726499fe32408119610d58bb3e1`。

## 结论

**BLOCKED（来源解析/association 尚未满足 Task05 全文门禁）。** Spec018 repair 的 scoped v1 reindex 真实完成并达到 verified/ready；但这次运行没有合法地把未绑定地图的 shared-pool document association 补入，也没有绕过 API 门禁。下一次全文验收应在后端修复 shared-pool association/来源版本解析并部署新候选后进行。

## 继续验收记录

继续核验时没有重复 reindex，也没有为通过验收直接写 association。已部署服务当前无监听：目标文档状态 GET 与 map source-status GET 均为连接被拒、无 HTTP 状态码；没有重启服务，没有提交全文分析/会话或调用 provider。脱敏记录见 Task05 continuation run `20261021-171101-dd616d5-continued`。

## 后续解除阻塞：82c816f真实全文运行

原失败和服务不可达记录保留。后续确认剩余原因是共享池列表过滤矛盾，并非必须给当前用户伪造association；候选`82c816f`修复无关联canonical共享记录的读取，继续排除任何已有项目/owner关联的文档。未直接写生产权限，未再次reindex。

独立backend-tester在当前8000部署跑通run `20261021-172344-82c816f-full`：ready=true；canonical verified、v1 indexed/100；全文source gate可用。全文analysis `3bb20a9a794d4104b13fc1fe5f581c66`版本2完成，summary 627字符；幂等重放同ID。会话`cc9f02f3d8184943bee35b4a23aa9481`问答完成，718个连续事件，5条引用仅来自目标文档。地图21节点/18边、分组和布局未被分析改写。

当前结论：**真实单文档修复与全文集成PASS**；不等于Spec最终全量/验收签字完成。真实证据见[后续API run](../../../043/artifacts/task-05/runs/20261021-172344-82c816f-full/api-e2e.json)及Task05的追加报告。
