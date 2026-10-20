# Task06 增量合同：分组与导出

2026-10-21 架构师纯文档准备。依据已确认 Spec043/Task06，不表示本 Task 已实现或通过；Task05 真实验证仍在进行，暂不分派本 Task 编码。

## 分组

- 复用既有 map revision、node.group_id、布局和所有者校验，不重定义节点身份或图谱作业。分组持久化在地图专属存储；不写知识库或共享目录。
- 分组投影 `{group_id,name,color}`：服务端稳定 ID，名称去空白后 1–80 字，颜色仅 `#RRGGBB`；不允许任意 CSS。最多 200 组，满足地图节点规模上限，不做自动聚类。
- API 前缀 `/api/literature-maps/{map_id}`：GET `/groups` 返回 `{schema_version,map_id,revision,groups}`；POST `/groups` 接受 `{expected_revision,name,color}`；PATCH `/groups/{group_id}` 接受 `{expected_revision,name?,color?}`；DELETE `/groups/{group_id}` 接受 `{expected_revision}`。写操作返回 `{schema_version,map_id,revision,groups}`。
- PUT `/nodes/{node_id}/group` 接受 `{expected_revision,group_id:string|null}`，返回 `{schema_version,map_id,revision,node}`。节点/分组必须属于该 owner 的同一张有效地图，墓碑节点不可分组；未知分组404、无效输入400/422、revision冲突409且不写入。
- 新建/修改/删除组和节点归属修改均在单事务校验 revision 后递增一次；删除组清空所有关联节点 group_id，不删除节点/边/论文原件。无改动请求不制造内容变化；冲突后前端重新读取，不覆盖用户操作。
- 刷新元数据继续保护 position/group_id，重新打开保留布局/分组。颜色只表达人工分组，不暗示支持/反对关系。

## JSON 导出

- GET `/export` 返回授权地图的 `application/json`，安全文件名通过 Content-Disposition 指明；只读，不触发 provider、模型、下载或索引。
- 顶层 `{schema_version:"literature-map-export-v1",exported_at,map,groups,nodes,edges}`。map 含 map_id/name/topic/project_id/filters/requested_count/revision/view_settings，省略 owner_id；nodes 只导出未移除节点，edges 仅两端均有效的边。
- 节点包括稳定节点 ID、外部身份、标题/作者/年份/venue/摘要/关键词/引用数、目录与文档关联 ID、下载状态、布局和组。边包括引用方向、相似分数/依据/模型版本/content hash及真实来源。
- 元数据 provenance 和关系 provenance 必须按生产实际键建立受控白名单，保留来源标识/公开链接/依据/采集时间，禁止原样导出任意内部 dict。未知字段默认不导出；不含 credentials、内部路径、诊断原异常、prompt、隐藏推理或全文索引片段。
- JSON 导出不包含 analysis/问答消息，不做 JSON 导入；导出失败应返回固定错误，不生成空文件冒充成功。

## PNG 与前端

- 使用当前 SVG 图谱生成 PNG，白/浅色背景、地图标题、引用/相似图例及分组图例；不包含详情面板/工具条。不得引入后台图片服务或新前端框架。
- 在画布快照内使用确定的本地样式和字体后转换为图像；校验非零尺寸和非空 PNG，失败明确提示，可建议先适应画布。保留用户布局，不为导出改写服务端位置。
- 左侧分组管理，详情节点选择分组，中央工具栏导出 PNG/JSON；安全文本渲染，作用域样式和缓存版本同步。

## 验证

受影响领域验证 owner/同图限制、revision并发、删组不删节点/原件、刷新布局保护；JSON 真实解析且无敏感字段、方向/数量正确；浏览器实际保存并打开 PNG。Task05 通过后才分派实现，不提前标完成；全量回归仍仅 Task08。
