# NULL 入库状态真实页面复验

部署候选：498b6ded；首页 HTTP 200；地图及节点 analyses API 于2026-10-27T13:41:55Z均返回HTTP 200；浏览器实际资源 literature-maps.js?v=31，CSS19。

地图 `0baabeae7268429c9f7e4de8098ae1d0`，节点 `065389f0f0b64acda6c5a043cc9b6269`。真实 API 原始 download_status/document_id 均为空，source_status.fulltext_ready=false。

步骤：文献地图 → API E2E graph attention networks r2 → 该论文节点 → 全文分析页签。

实际提示：
> 全文依据与分析状态
> 未入库
> 这篇论文尚未加入知识库。点击下方按钮可按现有流程提交入库；全文分析不会自动触发。

“获取并加入知识库”按钮可见。未点击按钮、未发起下载或分析，不将本次算作导入成功用例。此前已完成全文结果的独立实测见既有全文证据，结果不是本次重新生成。

[部署后截图](after.png)。静态文件快进部署，无后端源码变化，未重启模型。

校正：`/health`虽返回200，但响应为SPA fallback，不计健康接口成功；实际运行验证以首页及上述真实API为准。
