# 真实登录恢复验证

日期：2026-10-26；部署目录 /Users/wjh/ResearchAgent，端口8000。

POST /api/papers/import-items/9eed783f-ff98-4021-99dd-1ab2787688cb/login
Content-Type: application/json
Body: {}

实际 HTTP 200，curl退出码0。响应见 login-response.json。原批次1a76e369-c638-4f2c-a430-42552a1e7012的搜索TTL已过，但持久快照有效；本次不重新检索，不提交凭据，不宣称下载成功。临时浏览器会话仍有资源有效期，过期后可重新打开登录，不取消持久等待任务。
