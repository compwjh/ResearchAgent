# Task04 增量合同：扩展、刷新与恢复

日期：2026-10-19。架构师纯文档落盘；依据已确认Spec043/Task04，延续Task03 `literature-map-v1`，不另建地图应用、身份、下载或限流系统。实现前后端均以此合同交接；与实际旧接口冲突先回报，不私自改旧行为。

## 固定约束

- Task03已有接口、节点ID、owner、revision、缓存和job/events合同保持。新能力仅版本化增量；数据库增量迁移，保留既有地图/布局/分组/文档关联。
- 预览读取和计算不改变节点集。地图读取不联网；只有用户主动预览/刷新/确认触发外部工作。来源/年份限制继承地图；引用方向仍引用者→被引用者。
- 所有写入校验owner；同key不同参数409；确认时CAS核对revision，冲突409并重新预览，不覆盖用户操作。新加入每批最多20、总数200，服务器事务内复核，不只靠前端按钮。
- 作业共享现有1RPS、缓存、有限退避及每job60逻辑外呼预算。重试复用同job和剩余预算，不重做成功单元；不可重试失败不自动重试，缺引用不能当零引用。
- 预览保存候选元数据和确定外部身份，不使用客户端传入的PDF/元数据快照作为可信输入。失败、限流及数量不足明确标记，不硬凑候选。

## 增量资源

统一沿用已有schema_version/error envelope。资源前缀 `/api/literature-maps/{map_id}`。

1. `POST /previews`：`{kind: "topic"|"references"|"citations"|"refresh", node_id?, query?, idempotency_key}`。references/citations必须有属于当前地图的node_id；topic query默认地图主题，来源/年份门禁不变。返回202 `{preview_id, map_id, job_id, status, base_revision}`；后台作业进度沿用jobs/events。
2. `GET /previews/{preview_id}`：`{preview, job}`。preview包含 `preview_id/kind/status/base_revision/candidates/diff/warnings`。candidate至少 `candidate_id/title/authors/year/external_ids/already_present/removed`；其他元数据复用节点字段。候选的ID是预览内稳定句柄，不是客户端任意paper_id。
3. `POST /previews/{preview_id}/apply`：`{expected_revision, selected_candidate_ids: [], idempotency_key}`。只接受本预览中已验证的新候选，重复选择按输入错误拒绝；节点上限/数量/owner/预览归属/revision事务内检查。返回202 `{map, job, preview_id, added_node_ids}`；加入节点后补当前图内真实关系及相似层，不递归扩张。幂等重放返回原句柄，不能重复加点。
4. refresh预览只包含现有节点元数据/关系差异，不能把provider缺失数据解释为删除。apply对明确允许的元数据/边更新，位置、viewport、人工分组、下载/文档状态不被覆盖；未选择新增论文不自动加入。刷新没有差异也给明确空结果。
5. `POST /nodes/{node_id}/remove`：`{expected_revision, idempotency_key}`，返回 `{map, removed_node_id}`。移除节点及关联边，保存移除墓碑；成功单元重试、普通扩展/刷新不得静默加回。共享目录/缓存/PDF不删除。
6. `POST /nodes/{node_id}/restore`：`{expected_revision, idempotency_key}`，只能恢复当前地图的已移除节点，重新检查200上限；显式恢复才清墓碑。返回202 `{map, job, restored_node_id}` 并有界补关系。

预览、job和apply结果必须持久化可重开。预览完成后地图revision变化时apply拒绝，不将候选旧快照强写新地图。若实现采用预览过期，必须持久截止时间且稳定410 `MAP_PREVIEW_EXPIRED`；不得无文档新增任意短时过期。

### 刷新差异的实际字段合同

真实API已验证 `preview.diff` 为数组，不是显示字符串：

```json
{"diff":[{"node_id":"21041260a5394f42891b020128fa60fa","changes":{"citation_count":{"from":29000,"to":29014}}}]}
```

每项以服务端node_id标识论文，changes键为元数据字段名；字段差异使用from/to，关系差异使用relations下added/removed数组。前端按当前图或候选的节点身份显示标题/ID、字段名称及前后值，区分null、空字符串、空数组与缺失键；不得将整个对象显示为“未提供”。动态内容一律作为纯文本渲染。无差异明确提示无需更新。这是对生产者实际结构的补记，不改接口shape。

## 任务状态与恢复

- stop保留已完成图和预览结果；晚到回调不能复活stopped/deleted地图、写入节点或覆盖终态。
- 服务重启恢复未终结作业，已持久单元不重复外呼；重复worker以现有claim/CAS互斥。
- retry仅补可重试失败和未完成单元；provider歧义响应保留固定错误，不无限重试。相似层不可用时可补算，不抹掉引用图。
- GET job/events只读取已保存进度；前端使用事件游标、分阶段提示、已完成/等待/有限退避/失败数量，不伪造百分比。

## 前端交接

- 原地图工具栏提供“继续搜索”“刷新预览”；节点详情提供“参考文献”“引用它的论文”，不跳到新的研究或论文检索工作流。
- 候选面板可勾选，展示已有/已移除/新增及剩余容量；确认前不改变图。已有节点禁选，墓碑需明确恢复操作，不混为普通新增。
- refresh展示实际字段/关系差异，确认后应用；409提示重新读取与预览，不能自动重放覆盖。
- 停止/重试入口随job状态显示，空结果、限流、部分失败给具体范围与下一步。新增节点不重排已有人工位置；未明确分组的数据保持原组。

## 实现与验证边界

- 后端仅 `backend/app/literature_maps/**`、地图路由及精准领域测试；共享client必要接缝先回报，不另造provider client。
- 前端仅地图组件/既有壳必要资源版本及精准前端测试。代码/测试名按能力命名，不含spec/task编号。
- 真实阶段案例复用已存图，预览引用候选→确认少量加入→保存重开；验证200/20、重复命令、409、墓碑、stop/重启、有限重试与刷新布局保护。mock不代替真实API；全量仍仅Task08。
- Task03的provider partial及KB异步v2问题保留在旧证据；本Task不重写KB索引或恢复Spec032全部工作。
