# 真实索引发布一致性复验

日期：2026-10-26。已独立复审和定向测试的主目录候选启动于127.0.0.1:8000。

POST /api/kb/documents/d4dfd2a620384ad5bece27320661f8f0/reindex
Content-Type: application/json
Body: {"chunker":"v2"}

HTTP202，curl退出码0；task_id=f69932bca4e34352ac4ebf7d45722af5。仅一次补修复后的v2重建，不全库重建、不修改v1、不放宽来源精确定位。原始首次重建证据保留于../20261026-reindex-entry。

读取状态使用现有GET /api/kb/papers并只保存目标document_id。曾探测不存在的 /api/kb/documents/{id}/status 返回404，不作为产品任务失败或成功证据。
