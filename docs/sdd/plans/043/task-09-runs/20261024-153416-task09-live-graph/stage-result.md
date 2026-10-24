# Task09 真实浏览器阶段结果（中间交接）

运行：`20261024-153416-task09-live-graph`
候选地图：`858b78f0d9e047efa6d8d1559d83a6de`
实际资源：`literature-maps.js?v=16`、`literature-maps.css?v=12`、`app.js?v=60`

## 已确认

- 真实页面渲染 20 个节点、11 条关系；标签模式实测 `all=20`、`neighbors=7`、`hidden=0`，切换不改变节点位置，隐藏标签时节点仍可访问/可选。
- 20 个真实节点的引用半径均满足 `min(28, 8 + 2*ln(1+n))`（误差 ≤0.01）；选中前后半径不变。
- 非中心留白点滚轮缩放锚点误差约 `(-0.090,-0.139)` viewBox 单位；工具栏中心缩放误差约 `(-0.00002,-0.00001)`；打开详情并滚动页面后再次滚轮仍通过，页面滚动未被改写。
- 队列真实文案依次观察到“状态：已暂停 / 完成 3/20 · 排队 15 · 运行 0 · 失败 0 · 跳过 2 / 用户已暂停。”、“状态：已完成 / 完成 18/20 · 排队 0 · 运行 0 · 失败 0 · 跳过 2”；完成态保留“重试失败单元”。
- 当前 fresh 节点详情实际显示“摘要级”、`全文索引尚未就绪；请先主动入库并等待索引完成。`；切换全文未产生导入、下载或分析 POST，全文分析按钮为禁用。
- “关于本篇提问”真实会话创建后，已有 `#question` 草稿保持原文且未发送；空草稿预填包含标题、作者、年份、研究问题、方法、主要结论、局限、证据等级，未产生消息 POST/SSE。

## 产物

- [地图总览截图](screenshots/01-task09-map-overview.png)
- [节点详情与标签截图](screenshots/02-task09-node-detail-and-labels.png)
- 全部 20 个实际作者/年份标签：[label-audit.json](label-audit.json)
- 完整报告：[task-09-browser-e2e.md](task-09-browser-e2e.md)

## 当前限制/风险

- 多作者短标签实际出现 `Petar Velickovic et al. et al., 2017` 等重复 `et al.`，记录为前端缺陷，不在验收中修复。
- fresh map 仅有摘要级来源；用户指定的历史全文 ready map 通过真实键盘焦点+Enter 激活指定重叠节点，并在真实页面验证了全文 ready 提示、source version 与可用的手动全文分析按钮；历史回放仍不计入 Task09 fresh 实体门禁。
- 本轮对 fresh map 只触发一次手动摘要再生成：`analysis_id=42cf77712d7c430fb4b4311a3d573931`、`job_id=3264b0f9e3cf4e5f9183c9e4a6faf95c`（202 accepted/queued at click time）；旧 v1 结果当时仍显示。之后未重复触发。
