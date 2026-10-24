# BLOCKED — Spec043 Task09 真实 API E2E 验收

## 结论

**BLOCKED。** 本轮在当前部署上只创建了一张新鲜 Task09 地图，真实完成了 20 篇元数据节点的发现、地图级 abstract 自动摘要队列、暂停/恢复和旧图只读回读；18 篇有非空摘要的节点先各生成了 `version=1` 的非空 abstract 分析，2 篇无摘要节点被安全 `skipped`，没有由本轮发起节点分析 POST。

但同一新鲜地图的真实建图作业在 references/similarity provider 阶段以 `partial/finished` 结束，并持久化 `SEMANTIC_SCHOLAR_RATE_LIMITED`。这是外部元数据 429，按真实 API 验收门禁必须如实阻断。队列完成后的只读回读曾看到首节点出现同一 `source_version` 的 `version=2`；后续 browser 证据确认它是唯一一次主动 manual regeneration（合法 v2），不是 ensure 重复。队列本身已完成 18/20（另 2 项安全 skipped），但 full map 仍是 provider `partial`，不能把本轮结果标记为完整成功或用 Task08 旧样本替代，因此本报告不签署 `READY_FOR_USER`。

本轮没有下载、全文分析、知识库导入/索引，没有重启服务，没有修改业务/测试代码，没有调用 Git，也没有为限流重建第二张地图。

## 运行与边界

- Spec/Task：`043` / `Task09`。
- Run ID：`20261024-153416-task09-graph-attention`。
- 候选服务：`http://127.0.0.1:8000`，实际 `/api/ready` HTTP 200，`ready=true`；jieba、ollama tags、embedding、qdrant 均为 `ready`。
- 资源版本：`literature-maps.js?v=16`、`literature-maps.css?v=12`，同时读取到 `styles.css?v=60`、`app.js?v=60`。
- 工作树事实：沿用协调端交接的“候选工作树有未提交变更”记录；本轮按禁止 Git 的边界未独立运行 `git status`，不将其描述为本轮核验结果。
- 本轮观测到的分析 `model_id` 为 `qwen3.8:27b`；未改模型配置。该字段只用于说明实际运行资源，不替代真实 API 证据。
- 脱敏证据：[evidence.json](task-09-runs/20261024-153416-task09-graph-attention/evidence.json)。证据不包含 owner、Cookie、凭据、完整 abstract、完整模型结果或隐藏推理，只保留公开论文元数据、实体 ID、结果长度/哈希和安全错误码。

## 新鲜地图创建

实际请求为：

```http
POST /api/literature-maps
Content-Type: application/json
```

```json
{
  "topic": "graph attention networks",
  "name": "Task09 live graph attention networks 20261024-153416",
  "limit": 20,
  "idempotency_key": "task09-20261024-153416-map-create"
}
```

响应 HTTP 202，实体如下：

| 实体 | ID | 初始/实际状态 |
|---|---|---|
| fresh map | `858b78f0d9e047efa6d8d1559d83a6de` | 初始 `generating`；最终保留 20 节点、状态 `partial` |
| create job | `f98611b16e23478d94a3035add7e6861` | 初始 `queued/discover`；最终 `partial/finished` |
| abstract queue job | `a73b6881b56a41a78fc8d48abbc30f54` | 自动创建；最终 `completed` |

没有传入 caller owner、项目、论文正文、下载地址或外部身份覆盖字段。

## 真实状态轨迹

所有请求均为当前服务的真实 HTTP 请求；命令退出码均为 0，表内 HTTP 状态为服务实际响应。

| 顺序 | 请求/动作 | HTTP | 真实结果 |
|---:|---|---:|---|
| 1 | `GET /api/literature-maps/{map}/jobs/{create_job}` | 200 | 作业进入 `running/references`；`provider_count=20`、`accepted_count=20`、`node_count=20` |
| 2 | `GET /api/literature-maps/{map}/analysis-queue` | 200 | 自动队列 `active`；`total=20, completed=2, queued=15, running=1, failed=0, skipped=2` |
| 3 | `POST /api/literature-maps/{map}/analysis-queue/pause`，键 `task09-20261024-153416-queue-pause` | 200 | 同一 queue job 进入 `paused`，`pause_reason=user`；当前运行项未被取消 |
| 4 | 暂停后低频 `GET` | 200 | 当前项完成后为 `completed=3, queued=15, running=0`，没有继续 claim 后继项 |
| 5 | `POST /api/literature-maps/{map}/analysis-queue/resume`，键 `task09-20261024-153416-queue-resume` | 200 | 同一 queue job 回到 `active` |
| 6 | 恢复后低频 `GET` | 200 | 队列继续推进到 `completed=4, queued=13, running=1` |
| 7 | `POST .../analysis-queue/ensure`，同一键连续两次 | 202、202 | 两次都返回同一 `a73b6881b56a41a78fc8d48abbc30f54`；后续 v2 已由 browser 证据归因为独立 manual regen，不是 ensure 新建 |
| 8 | 最终 `GET .../analysis-queue` | 200 | `completed`；`total=20, completed=18, queued=0, running=0, failed=0, skipped=2` |
| 9 | 最终 `GET .../jobs/{create_job}` | 200 | `partial/finished`；`citation_edge_count=6`、`similarity_edge_count=5`，错误码 `SEMANTIC_SCHOLAR_RATE_LIMITED` |
| 10 | browser 侧唯一一次显式 manual regen（交叉证据） | 202 | `analysis_id=42cf...`、`job_id=3264...`，v2 合法；不是本轮 ensure 产生的版本 |

队列完成期间只按约 10–15 秒间隔观察，没有忙等；作业未超时，不需要重复创建。最终 map 回读在队列完成后暴露了一个额外版本；后续 browser 证据确认这是显式 manual regen，本轮没有再发送任何写请求。

## 自动摘要与版本证据

新鲜图 `GET /graph` 返回 HTTP 200、`schema_version=literature-map-v1`、20 节点/11 条边。批量只读分析历史核对结果：

- 队列终态当时为 18 条 `status=completed`、`evidence_level=abstract`、`version=1`；随后最终只读历史核对为 19 条 completed 记录：18 个有非空来源摘要的节点中，首节点多出一条同 `source_version` 的 `version=2`，其余 17 个节点各一条 `version=1`。这只证明版本共存；browser 交叉证据随后确认 v2 是合法手动再生成。
- 结果正文没有写入报告或 artifact；每条只保留分析 ID、子 job ID、source version、序列化长度和 SHA-256。示例：`node_id=3ddd16f157414d3c81b31171107e317b` 的 `analysis_id=b636bd98d5d94608811abda4e4a413dd`、`job_id=dcc6708197f246bda990dd6cf52e1e56`，结果长度 454，哈希见 artifact。
- 2 个无摘要节点为 `3590f82e68cd4d129cb68b00274d86d4`、`8464a2f033624db8857a3669d2d971ca`；各自分析历史 HTTP 200 但 `analysis_count=0`，安全原因 `MAP_ABSTRACT_UNAVAILABLE`。没有标题回退、没有模型调用补齐总数。
- 自动子 job 可由地图事件观察到；本轮没有调用 `POST /nodes/{node_id}/analyses`。因此“无需节点 analysis POST 即自动生成摘要”的证据来自自动队列事件和随后只读分析历史，而不是显式节点请求。
- 迟到版本的事件序列为 65（queued/version 2）→ 66（started）→ 67（completed），`job_id=3264b0f9e3cf4e5f9183c9e4a6faf95c`、`analysis_id=42cf77712d7c430fb4b4311a3d573931`；与 `version=1` 使用同一 `source_version`。在只读阶段无法归因；browser artifact 随后确认它来自唯一一次显式 manual regen，发现后本轮没有继续发写请求。

## 只读归因补充：v1/v2 与本轮请求序列

本节是对终态后发现的 v2 做的只读补充，不覆盖前述 BLOCKED 历史。

- 本轮向 `POST /api/literature-maps/{map_id}/nodes/{node_id}/analyses` 发起次数为 **0**。本轮唯一写请求序列是：一次 `POST /api/literature-maps`（map-create 键，HTTP 202）→ 一次 queue `pause`（pause 键，HTTP 200）→ 一次 queue `resume`（resume 键，HTTP 200）→ 一次 queue `ensure`（`task09-20261024-153416-queue-ensure`，HTTP 202）→ 同一 ensure 键立即重放一次（HTTP 202）。其余针对节点、分析、job、event、map、graph、queue 的请求均为 GET；发现 v2 后也没有再 POST。
- v1 自动摘要 job：`job_id=dcc6708197f246bda990dd6cf52e1e56`，创建 `2026-10-24T07:34:48.163507Z`，完成 `2026-10-24T07:36:13.985012Z`；cursor 含 `queue_job_id=a73b6881b56a41a78fc8d48abbc30f54`，`analysis_version=1`。
- v2 job：`job_id=3264b0f9e3cf4e5f9183c9e4a6faf95c`，创建 `2026-10-24T07:41:17.745335Z`，完成 `2026-10-24T07:41:35.500212Z`；cursor 只有 `analysis_id/node_id/evidence_level`，**没有 `queue_job_id`**，`analysis_version=2`。事件 65→66→67 与该 job 对应，表面上更接近独立手动 regen；browser artifact 已确认其来源。
- v1/v2 的公开分析字段相同：`evidence_level=abstract`、相同 `source_version=c518a10f...d1e42c`、相同 `model_id=qwen3.8:27b`，均 completed/non-empty。GET 分析响应不暴露服务端分析配置指纹、稳定 key 或请求幂等键，因此本轮**不能证明 config fingerprint 相同，也不能仅凭 source_version 相同判定重复**。
- 当前处理：保留只读阶段的 `LATE_VERSION_UNATTRIBUTED` 历史记录，但以 browser artifact 的 `manual_regeneration` 事实纠正归因；v2 不计为自动 ensure bug。artifact 已追加上述 job cursor、时间、请求序列和“本轮 node analysis POST=0”。
- 最终 fresh map GET 仍为 HTTP 200、`status=partial`、`revision=6`；`latest_job_id=3264b0f9e3cf4e5f9183c9e4a6faf95c`、`latest_job.status=completed`、`analysis_version=2`。最终阻断原因是 provider partial，而不是把合法 manual v2 误判为 ensure 重复。

### browser 交叉归因纠正

协调端提供的 [task-09-browser-e2e.md](task-09-runs/20261024-153416-task09-live-graph/task-09-browser-e2e.md) 及其 [api-e2e.json](task-09-runs/20261024-153416-task09-live-graph/api-e2e.json) 记录：

- `2026-10-24T15:41:17+08:00`，浏览器在 fresh 节点已有 v1 后，唯一一次主动点击“重新生成摘要”；真实 `POST /nodes/3ddd16f.../analyses` HTTP 202，body 仅为 `evidence_level=abstract`，返回 v2 `analysis_id=42cf...`、`job_id=3264...`。
- 点击时 v1 仍可读，v2 为 `queued/pending`；browser artifact 明确记录此为“唯一一次手动再生成”，之后未重复触发。该 POST 不是本代理 API 序列的一部分，因此本代理 node-analysis POST 计数仍为 0。
- 因此 v1/v2 同 `source_version` 是合法手动 regen 的预期版本化行为；ensure 幂等检查恢复为通过。真正阻断仍是 provider references/similarity 的 `SEMANTIC_SCHOLAR_RATE_LIMITED`，不能把 queue `completed` 误写成 full map completed。

## 本轮真实论文元数据

以下均来自 fresh map 的 provider 返回；为避免泄露正文，只记录标题、年份、公开外部身份、摘要是否非空、摘要长度/引用数和自动分析 ID。`analysis_id=—` 表示合同要求的安全跳过，不代表旧样本结果。

| node_id | 论文标题 | 年 | 外部身份（部分） | 摘要 | analysis_id |
|---|---|---:|---|---|---|
| `3ddd16f157414d3c81b31171107e317b` | Graph Attention Networks | 2017 | arXiv `1710.10903`; DOI `10.17863/cam.48429` | 非空，1044 字符；被引 29148 | v1 `b636bd98d5d94608811abda4e4a413dd`；迟到 v2 `42cf77712d7c430fb4b4311a3d573931` |
| `55447f8311d24d38b99b0a56a3e704b4` | How Attentive are Graph Attention Networks? | 2021 | arXiv `2105.14491` | 非空，1293；被引 2183 | `7ae79d4c701f45cda2712e7bfed39e8f` |
| `fade0df075b7459096a6dc174688c64a` | AASIST: Audio Anti-Spoofing Using Integrated Spectro-Temporal Graph Attention Networks | 2021 | arXiv `2110.01200`; DOI `10.1109/icassp43922.2022.9747766` | 非空，882；被引 681 | `48552827d7324a88985ef0fb7dc7ee11` |
| `8ccc5fd89ecc4fd0adbdf8f91a329b4b` | Advanced intrusion detection in internet of things using graph attention networks | 2025 | DOI `10.1038/s41598-025-94624-8` | 非空，1291；被引 77 | `0c88d80a6b324b1382e9fe3d65411383` |
| `34be4d08d0ec49979ba57e25f130b37f` | Social-BiGAT: Multimodal Trajectory Forecasting using Bicycle-GAN and Graph Attention Networks | 2019 | arXiv `1907.03395` | 非空，1350；被引 761 | `b024fe3fc1c04a658bfc087bce7e94d4` |
| `2c730b77c230484c8f0d961a7a1b9760` | Graph Attention Networks: A Comprehensive Review of Methods and Applications | 2024 | DOI `10.3390/fi16090318` | 非空，943；被引 281 | `da7a61bcd7224ffca506853dbe91e248` |
| `3a12132c95914d1ba8f989d7e9ba23d1` | Dynamic Job-Shop Scheduling via Graph Attention Networks and Deep Reinforcement Learning | 2024 | DOI `10.1109/tii.2024.3371489` | 非空，1239；被引 71 | `4783b2865b374f888fcff2b144037950` |
| `8908dfc77ef345fc94cd3966aa4067ec` | MOGAT: A Multi-Omics Integration Framework Using Graph Attention Networks for Cancer Subtype Prediction | 2024 | DOI `10.3390/ijms25052788` | 非空，2168；被引 75 | `4e367cafc97f4f68b31f0321a457d9d9` |
| `58d55f34502748a596f793720b6a3e89` | End-to-End Spectro-Temporal Graph Attention Networks for Speaker Verification Anti-Spoofing and Speech Deepfake Detection | 2021 | arXiv `2107.12710`; DOI `10.21437/asvspoof.2021-1` | 非空，1144；被引 265 | `f93f22c48f164e888508a3b08579d889` |
| `e184b94677a74db386413539942aa5aa` | Multivariate Time-Series Anomaly Detection based on Enhancing Graph Attention Networks with Topological Analysis | 2024 | arXiv `2408.13082`; DOI `10.1145/3627673.3679614` | 非空，1436；被引 65 | `e72c4b1136a640cca22df5ffe9d88501` |
| `4155ba1e2b874a3dbc29d0858ebbb4bd` | RadioGAT: A Joint Model-Based and Data-Driven Framework for Multi-Band Radiomap Reconstruction via Graph Attention Networks | 2024 | arXiv `2403.16397`; DOI `10.1109/twc.2024.3457157` | 非空，1697；被引 66 | `98f42bdd15cc4586aae60d0db641e917` |
| `c9a69657552f466abad904dd28ff59a0` | Contextual Recommendations: Dynamic Graph Attention Networks With Edge Adaptation | 2024 | DOI `10.1109/access.2024.3477956` | 非空，1111；被引 38 | `5c7a7abd597845bab423a90fdaa93cae` |
| `3590f82e68cd4d129cb68b00274d86d4` | Social recommendation system based on heterogeneous graph attention networks | 2024 | DOI `10.1007/s41060-024-00698-4` | 空，0 | —（安全跳过） |
| `b3e157a1a3ba4f87a6c787dd23177e87` | When Spatio-Temporal Meet Wavelets: Disentangled Traffic Forecasting via Efficient Spectral Graph Attention Networks | 2023 | DOI `10.1109/icde55515.2023.00046` | 非空，1574；被引 171 | `1863b31ad8024293b3d9274e271d3ec2` |
| `b90f727be35744afbfdfadcc349463e5` | DualGATs: Dual Graph Attention Networks for Emotion Recognition in Conversations | 2023 | DOI `10.18653/v1/2023.acl-long.408` | 非空，1166；被引 101 | `98a7e339705244388411cad3b26d8554` |
| `6bb52d0ac6c440a299139acd14e54eb8` | Fault location method for distribution networks based on multi-head graph attention networks | 2024 | DOI `10.3389/fenrg.2024.1395737` | 非空，1223；被引 28 | `ab120cbdca3044e282ca2293181526f9` |
| `8464a2f033624db8857a3669d2d971ca` | Multi-head multi-order graph attention networks | 2024 | DOI `10.1007/s10489-024-05601-z` | 空，0 | —（安全跳过） |
| `4806b409083d4290a6856a494259181d` | HGAT: Heterogeneous Graph Attention Networks for Semi-supervised Short Text Classification | 2021 | DOI `10.1145/3450352` | 非空，1476；被引 203 | `e0e84faa6d1e4a04a6d502ccd69e55a9` |
| `a901bd059fe8400cafd59abb83ecc522` | Meta Learning With Graph Attention Networks for Low-Data Drug Discovery | 2023 | DOI `10.1109/tnnls.2023.3250324` | 非空，1602；被引 105 | `f88a3c7def8248bb852447facfbda347` |
| `9bf83093ce284a8788a77a9760e5d24d` | ResGAT: Residual Graph Attention Networks for molecular property prediction | 2024 | DOI `10.1007/s12293-024-00423-5` | 非空，1446；被引 15 | `1be6db21fcb94bc5a3d93cf4ad6430f7` |

## 旧图只读回读

为验证兼容读取而使用 Task08 历史 ID `35a56c6f2da84fca85fc3c21dfa0055c`，只发 GET，不把其内容计入本轮新鲜结果：

- `GET /api/literature-maps/{old_map_id}`：HTTP 200，历史 map `status=partial`、`revision=11`。
- `GET /api/literature-maps/{old_map_id}/graph`：HTTP 200，21 节点/17 条边。
- `GET /api/literature-maps/{old_map_id}/analysis-queue`：HTTP 200，`state=completed`、`queue_job_id=null`、`total=0`；GET 没有隐式创建队列或分析。

旧图没有被 `ensure`、暂停、恢复或重试；旧结果不能冒充本轮新摘要。

## 验收矩阵

| 检查项 | 结果 | 证据/限制 |
|---|---|---|
| 当前候选 ready、资源版本可记录 | PASS | `/api/ready` 200；JS v16/CSS v12 |
| fresh map 使用真实主题、`limit=20`、Task09 名称 | PASS | 本报告 fresh map 请求与 202 响应 |
| 真实 provider 元数据落图 | PASS（部分层） | 20/20 节点持久化，论文元数据见上表 |
| 不发 node analysis POST 即自动建立摘要队列 | PASS | 自动事件 + 聚合 queue job；本轮未调用节点 POST |
| abstract 分析非空、只处理有摘要节点 | PASS | 18/18 完成且非空；2 个 `MAP_ABSTRACT_UNAVAILABLE` 跳过 |
| 队列单地图串行推进 | PASS | 自动队列最终 18 completed、0 running、0 queued |
| pause 保留当前、阻止后继 claim | PASS | paused 后当前完成，`queued=15/running=0` |
| resume 使用同一队列继续推进 | PASS | 恢复后 `completed=4, queued=13, running=1`，最终完成 |
| ensure 重放不新建版本/队列 | PASS | 本代理同键两次 202、同一 queue job；v2 已由 browser 证实为独立合法 manual regen |
| 显式 manual regen 版本化且保留旧结果 | PASS（交叉证据） | browser 点击时 v1 保留、v2 queued/pending；不计作自动 ensure 重复 |
| 旧图读回不隐式入队 | PASS | old map/graph/queue 均 200，旧 queue `total=0` |
| 外部元数据层完整成功 | **BLOCKED** | `SEMANTIC_SCHOLAR_RATE_LIMITED`；不得降低门槛或用旧样本替代 |

**最终裁决：BLOCKED。** API 核心摘要队列（18 completed、2 skipped）、暂停/恢复、ensure 幂等和 manual regen 版本化均有证据；但外部 provider 429 使完整地图保持 `partial`，不能把 queue `completed` 误写成 full map 完成。后续应在 provider 限流解除后用新鲜候选重新执行真实门禁；不能把本轮 `partial` 结果、旧 Task08 结果或 fixture 结果写成完整 Spec 验收通过。
