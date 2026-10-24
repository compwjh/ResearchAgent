# Task09 最小接口实现合同：摘要队列与图谱交互

## 合同元数据

- 日期：2026-10-24（Asia/Shanghai）
- 角色：architect（独立增量需求/技术评审）
- 模型：Luna max（用户本轮临时指定；不写入长期角色配置）
- 分派：由主会话 `/root` 分派并行评审；本文件不是开发、测试或验收报告
- 未实现事实：本轮只读取现有 Spec、Task 计划、审计、合同和最小相关代码并追加文档；未改业务代码/测试，未运行模型、下载、全量回归或服务，未调用网络，未提交 Git

本合同只固定 Task09 的最小增量接缝，供 `backend-dev` 与 `frontend-dev` 直接实现。它不替换 Task03 的 `schema_version="literature-map-v1"`、Task05 的分析/会话合同，也不创建第二套作业、分析或聊天实现。若实现发现字段与当前冻结合同冲突，以已冻结合同为准，并在评审记录中说明适配。

## 1. 兼容性与不变边界

1. 继续复用 `MapAnalysis`、`MapJob`、`MapEvent`、`MapAnalysisService`、现有执行器、来源版本和结构化错误；分析结果仍按地图/节点分版本保存，旧版本可读。
2. 现有接口保持语义不变：
   - `GET /api/literature-maps/{map_id}/nodes/{node_id}/analyses` 只读分析历史与来源状态；
   - `POST /api/literature-maps/{map_id}/nodes/{node_id}/analyses` 仍是显式分析请求，`evidence_level` 仍为 `abstract|full`，幂等键和服务端来源门禁不变；
   - `GET /api/literature-maps/{map_id}/analyses/{analysis_id}`（若当前路由使用等价路径）只读单项状态；
   - `POST /api/literature-maps/{map_id}/nodes/{node_id}/conversation` 仍只创建/复用既有会话绑定，不创建首条消息；单复数路由沿当前实现，不新增同义聊天接口。
3. 所有读接口（图、节点、分析历史、队列、作业、事件、视图）都不得触发模型、外部元数据检索、导入、索引、下载或重试写入。旧地图打开时的补入队必须由显式幂等 `POST` 完成，不能藏在 `GET`。
4. 全文分析仍只在 `full` 出现在服务端 `available_evidence_levels` 且现有 owner/project/document/generation/manifest/chunker 门禁通过时允许显式调用；Task09 不自动下载、导入、索引或生成全文结果。
5. 所有队列与分析路由均从服务端 `OWNER_ID` 得到 owner，并通过 map/node/job 的 owner-scoped 查询隔离；请求体不得接受 caller-supplied owner、project、document 或 source version。跨 owner 不泄露存在性，按现有 404/结构化错误处理。

## 2. 持久自动摘要队列

### 2.1 队列是既有 MapJob 的聚合控制，不是第二套调度器

地图级摘要队列使用一个持久 `MapJob` 聚合记录（`operation="analysis_queue"`，或同等的已版本化 MapJob 扩展），每篇论文继续使用现有 `MapJob(operation="analysis")` 与 `MapAnalysis` 子记录。聚合记录只保存队列状态、游标、计数、失败子 job/analysis ID 和幂等参数；不得另建一套分析结果表、执行器、聊天框架或下载器。

队列状态至少可持久表达：`active`、`paused`、`completed`、`partial`；`paused` 必须带安全的 `pause_reason`（配置/鉴权/用户暂停等）。计数至少包含 `total`、`completed`、`queued`、`running`、`failed`、`skipped`；失败项含可重试标志和安全错误码，不回传凭据或原始异常。

### 2.2 最小命令与读模型

资源前缀继续为 `/api/literature-maps`。以下是一个增量的地图级队列控制/读模型；若开发选择把它映射到现有 jobs 路由，必须保持相同语义，不能把 `stop` 误当作“暂停队列”。

| 动作 | 最小接口与输入 | 语义 |
|---|---|---|
| 读队列 | `GET /{map_id}/analysis-queue` | 只读返回 `schema_version`、`map_id`、`queue_job_id`、`state`、`pause_reason`、上述计数、当前项和失败项摘要；不创建缺失分析、不提交执行器。 |
| 补入缺失项 | `POST /{map_id}/analysis-queue/ensure`，`{idempotency_key}` | 显式扫描当前未移除节点的已保存摘要；缺项创建/复用现有 abstract `MapAnalysis` 子 job。新节点写入后可调用同一内部 ensure 原语；旧地图打开由前端显式调用一次。请求只接受幂等键和必要的协议字段，不接受论文正文、下载地址或外部身份覆盖。 |
| 暂停 | `POST /{map_id}/analysis-queue/pause`，`{idempotency_key}` | 持久置 `paused`；已运行的一篇允许完成，不停止当前分析、不停止建图/聊天、不清除结果；调度器不再 claim 后续项。重复调用幂等。 |
| 继续 | `POST /{map_id}/analysis-queue/resume`，`{idempotency_key}` | 持久置 `active` 并唤醒同一队列调度；每个地图最多允许一个摘要子 job 进入 running。重复调用幂等。 |
| 重试失败项 | `POST /{map_id}/analysis-queue/retry`，`{idempotency_key, analysis_ids?}` | 默认重试该地图可重试失败项，也可限定现有 analysis ID；调用现有 retry 语义，不创建新版本，不清除可读旧结果；配置/鉴权失败必须先修复后显式重试。 |

这些接口应返回现有结构化错误包和当前队列读模型；同一幂等键不得执行不同参数。若只需要按单项重试，队列读模型必须提供现有 child `job_id`/`analysis_id`，前端可复用既有 `/jobs/{job_id}/retry`，但暂停仍必须是队列级“当前完成、后续等待”。

### 2.3 复用、版本和跳过规则

1. 自动摘要只使用节点已持久化的摘要和既有分析配置。稳定键至少由 `map_id`、规范化论文身份、摘要 `source_version`（现有摘要内容/外部身份哈希）和服务端分析配置指纹组成；前端不能自造 source version。当前 `MapAnalysis` 是地图/节点分区，Task09 不新增跨 owner 的全局结果缓存。
2. 同一地图重新打开、ensure 重复调用或并发 ensure 命中相同稳定键时，返回/复用同一 `analysis_id`、版本和 child job，不重复模型调用。摘要内容或分析配置改变时新建版本，旧版本保持可读；显式“重新生成”沿现有新幂等键创建新版本，失败不得清空旧版本。
3. 节点无非空摘要时记为 `skipped`（含安全原因），不调用模型，不以标题冒充摘要，也不为了补总数检索元数据。节点被移除/地图被删除后，旧 child job 的完成回调不得重新写回或复活节点。
4. 队列只处理 abstract。全文状态和全文分析仍由详情页显式操作；队列 ensure 不检查外部全文，不触发 KB 导入/索引/下载。

### 2.4 并发、暂停、退避与重启门槛

1. 同一地图的摘要子 job 必须串行；不同地图可共享既有受限执行器。持久 claim 必须是 `queued -> running` 的原子转移，并带 worker token/等价租约；已经 `running` 的 job 不能被第二个 worker 当作可执行结果返回。完成/失败写入必须校验 token，旧 worker 的迟到回调 fail-closed。仅靠进程内锁不满足重启要求。
2. `paused` 在持久存储中生效，重启后仍暂停；`active` 重启时只恢复未完成项，孤儿 running job 只可被一次性安全 requeue/恢复。已完成版本不重新生成，队列聚合计数可从持久子状态重建但不得因 GET 重建。
3. transient/429 采用有限退避和 `next_retry_at`/attempt 之类的持久状态，超过上限转安全的可重试失败；配置/鉴权错误暂停队列并给出行动码，不忙等、不泄露密钥。用户暂停与配置暂停都不得把当前 running 子 job 标为用户取消。
4. 同一地图的多个 ensure、resume 或服务恢复不得产生多个聚合 job 或多个 running 子 job；跨 owner 的相同论文不得共享可见结果，除非已有合同明确的 owner-scoped 缓存可安全命中，本 Task 不新造跨 owner 缓存。

## 3. 图形与视图持久化最小增量

1. 保持 `schema_version="literature-map-v1"`、现有 `PATCH /{map_id}/view`、`expected_revision`、原子保存和 owner 隔离。仅向现有 `view_settings` 增加可选 `label_mode: "all"|"neighbors"|"hidden"`；旧图缺失时默认 `all`。不得用新 endpoint 覆盖 positions、group 或既有 filters/layers；PNG 快照复用当前显示状态。
2. 标签确定规则：多作者首位作者加 ` et al.`，缺年份显示“年份未知”，缺作者回退短标题再回退 node ID；视觉截断不改变悬浮/无障碍全标题。`all` 显示全部，`neighbors` 显示选中节点及现有边相邻节点，`hidden` 不显示；不因标签模式修改持久节点位置。
3. 节点半径统一为 `min(28, 8 + 2 * ln(1 + n))`，其中有限非负 `n` 是来源元数据总被引数，不是图内度数；null/非法值使用半径 8 并显示“未知”。选中只改变描边/视觉状态，不改变半径。渲染和 PNG 使用同一 helper。
4. 缩放变换保持指定世界坐标不漂移：滚轮锚点为鼠标对应 SVG 坐标，工具栏加减锚点为当前可视画布中心，双指锚点为触点中点。缩放前先把 client 坐标转换为当前 world 坐标，再按新 scale 计算平移；详情面板/留白/页面滚动不改变该语义。现有双指中点逻辑可复用，不另建坐标系。

## 4. 全文引导与会话草稿

1. `available_evidence_levels` 含 `full` 时才启用“全文分析”；否则按钮不得发起分析 POST，详情页显示将机器码映射为可行动的安全文案，并桥接既有“加入知识库/登录/上传/等待索引/重试”入口。任何入口都等待用户点击，不自动下载、导入、索引或重试。
2. 现有会话 POST 请求体保持 `{evidence_level, idempotency_key}`。地图端只在返回既有 conversation ID 后调用现有导航，并以可选 UI 参数传入预填建议；不创建 `/messages` 请求、不自动发送、不覆盖已有草稿。已有草稿非空时显示“插入建议问题”或保留原稿。
3. 建议 Prompt 至少包含论文标题、作者、年份、研究问题、方法、结论、局限和证据等级；它是可编辑草稿，不是分析结果。全文后来 ready 时由用户显式开启全文会话，不能静默升级旧摘要会话的 source/context。

## 5. 开发前的可执行验收断言

- 同一地图重复打开/ensure/并发 ensure：稳定 source/config 只有一个分析版本和一次模型调用；摘要改变产生新版本，旧版本可读。
- 新节点、旧地图补入、无摘要 skip、移除/删除和 owner 越权均有持久结果；迟到回调不能复活节点。
- pause 期间当前项可完成、后续不 claim；resume、进程重启、429/有限退避、配置错误暂停和失败重试均可从 GET 读到一致状态；GET 本身不产生 job 或外部调用。
- 队列调度与现有建图/聊天执行器不互相 stop；同一地图不存在两个 running 摘要子 job，worker 迟到回调不能覆盖新状态。
- 标签、半径、三档模式、非中心滚轮/画布中心工具栏/双指中点和保存重开符合上述数学及视图合同；图形实现可与后端队列并行。
- full 不可用时只显示实际引导；full ready 后仍由用户显式分析。会话预填可编辑、不自动发送、不覆盖已有草稿；无新增下载或聊天系统。

## 评审签字

- 评审人：architect（独立增量需求/技术评审）
- 结论：GO；本合同列出的并发 claim/worker token、持久 pause/recovery、GET 无副作用和现有路由兼容是实现门槛，不是用户范围扩张。

## 6. 实现字段固定（backend-dev，2026-10-24）

本节只把上文“最小接口与输入/读模型”落成字段名，未改变语义；前端接入以此为准。

### 6.1 队列读模型

`GET /{map_id}/analysis-queue` 及四个队列控制 POST 均在现有 `schema_version` envelope 中返回以下顶层字段：

```json
{
  "schema_version": "literature-map-v1",
  "map_id": "…",
  "queue_job_id": "…",
  "state": "active|paused|completed|partial",
  "pause_reason": null,
  "counts": {
    "total": 0,
    "completed": 0,
    "queued": 0,
    "running": 0,
    "failed": 0,
    "skipped": 0
  },
  "current": null,
  "failed_items": []
}
```

`queue_job_id` 在尚未显式 `ensure` 时为 `null`；GET 不创建聚合或子 job。`current` 为当前摘要子项的安全摘要（含 `node_id`、`analysis_id`、`job_id`、`status`），`failed_items` 含 `node_id`、`analysis_id`、`job_id`、安全 `error_code`、`retryable`、可选 `next_retry_at`。worker token、原始异常和凭据永不进入读模型。

### 6.2 队列控制请求

- `ensure`、`pause`、`resume` 请求体均为 `{ "idempotency_key": "…" }`；
- `retry` 请求体为 `{ "idempotency_key": "…", "analysis_ids": ["…"]? }`，省略 `analysis_ids` 表示该地图全部可重试失败项；
- 四类请求均拒绝额外字段；相同幂等键绑定不同参数返回既有结构化冲突错误。

### 6.3 分析 claim/finish 与 view 增量

摘要子 job 的持久 worker token 仅存在于服务端 job 元数据，原子 `queued -> running` claim 返回的内部对象可携带 token，`finish` 必须匹配 token；重复 claim、过期/迟到 token 或已移除节点均 fail-closed。队列恢复只重排 active 队列的孤儿 running，paused 队列保持 paused。

`PATCH /{map_id}/view` 在既有请求体中增加可选 `label_mode: "all"|"neighbors"|"hidden"`；省略时保持已有值，旧图缺失时读模型默认 `all`，不覆盖 `positions`、`viewport`、`filters`、`layers` 或 revision 语义。

### 6.4 后端调度实现备注（不新增外部字段）

自动队列继续使用独立单槽 queue executor；显式 abstract/full 分析使用现有通用受限 executor，避免长摘要阻塞另一张地图的显式请求。服务端 claim 的内部 lease deadline 由存活 service 的一次性 timer 唤醒原子 recovery；300 秒 lease 是本阶段的有界执行限制，过期 worker 的 finish 仍以 token+lease CAS fail-closed，达到 attempts 上限的孤儿 child 终止为安全失败。runtime reset 会取消旧 service 的 retry/lease timers 并阻止其后续持久写，队列读模型和控制接口字段保持 6.1/6.2 不变。
