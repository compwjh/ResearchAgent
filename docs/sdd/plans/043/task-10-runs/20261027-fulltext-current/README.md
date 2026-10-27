# 当前候选真实全文分析

部署498b6ded，JS31/CSS19；2026-10-27T13:50:03Z由真实浏览器点击“基于全文分析”。

地图0baabeae7268429c9f7e4de8098ae1d0，节点21041260a5394f42891b020128fa60fa（Graph Attention Networks），已有全文索引就绪。未下载PDF或改写知识库。

- 新analysis：74c6245585dd4f6ab81ffc3ca6bd58ba，v5，evidence_level=full。
- 新job：9283fdd06bec4faf8828897813a2d670。
- 点击后真实UI：全文分析正在生成；等待提示及操作禁用可见。
- GET /api/literature-maps/{map_id}/analyses/{analysis_id} HTTP200，analysis/job均completed。
- 新结果summary601字符，5条citations和1项source_refs；原始响应附在本目录，未用历史v4冒充。
- 浏览器自动更新为“全文分析已完成”，结果及历史版本可查看。

截图：task10-fulltext-running.png、task10-fulltext-completed.png。响应：task10-fulltext-new-result.json；启动后的running实体快照：task10-fulltext-new-analyses.json。

人工复现：文献地图→API E2E graph attention networks r2→Graph Attention Networks节点→全文分析→基于全文分析。应立即显示生成中并等待，后台完成后自动显示完成和新版本结果；若来源不是fulltext_ready，先按卡片指引处理，不重复点击。耗时随模型负载波动，本次约两分钟内完成。
