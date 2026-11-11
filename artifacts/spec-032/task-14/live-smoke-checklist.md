# Spec032 Task14 真实服务 Smoke 清单

状态：`部分执行（健康检查与受控目录同步通过；导入/完整覆盖仍阻塞）`

- `PORT=18080 RERANKER_ENABLED=false ./deploy/start.sh`：退出码 0，Uvicorn 启动并监听 18080，Reranker disabled。
- 真实浏览器已加载 `http://127.0.0.1:18080/` 和 `#papers-view`；页面通知流请求返回 200。
- 沙箱外 `curl` 已验证 `/api/health`、`/api/ready` 均 HTTP 200；模型、embedding、Qdrant ready。
- USENIX 2024 sync：`completed`，`paper_count=227`；NDSS 2024 official sync：`completed`，`paper_count=142`；服务重启后两个 sync 句柄仍可读取 completed。
- IEEE S&P 2024 本轮外站同步返回 `SOURCE_FAILED`/degraded；未把失败伪装为成功，CCS 仍按 bounded NO-GO 处理。
- 真实样本必须限制在已验证的 IEEE S&P 2024 与既有 USENIX 小样本；CCS/NDSS 未验证年份只记录 blocked/NO-GO。
- 真实导入需使用既有安全下载、身份校验、KB 上传和批任务恢复链；不得在 smoke 中直接访问任意 PDF URL。
- 必须覆盖批准计划门禁、候选身份 mismatch/uncertain、waiting_login login/resume、failed retry、人工上传、旧报告不可变和服务重启。

本轮离线相关回归：`765 passed, 5 warnings, 15 subtests`；该数字不能替代真实登录/上传、完整四会年度覆盖和批次恢复 smoke。

## 2026-09-22 重启与 Semantic Scholar API smoke

- 旧的 18080 进程无部署 PID 文件，已确认工作目录为本项目后终止并以前台方式重启：
  `PORT=18080 RERANKER_ENABLED=false ./deploy/start.sh`。
- `GET /api/health`：HTTP 200，`paper_discovery_enabled=true`，模型配置已加载。
- `GET /api/papers/semantic-scholar/autocomplete?query=privacy&limit=3`：HTTP 200，返回 3 个候选。
- 同一候选的 `citations` 请求曾返回 HTTP 200；`references` 请求在不同调用中出现 provider 限流（429）和空/异常响应（代码侧已兼容空页与 `citedPaper=null`，定向测试覆盖）。
- 当前进程保持运行在 `http://127.0.0.1:18080`；真实 API 仍受 provider 限流影响，不能把单次 references 失败记为代码回归通过或失败。
- 2026-09-22 代码补强：429/5xx/网络失败统一使用有界指数退避，合法 `Retry-After` 优先且最大 30 秒；相关定向回归 72 passed，真实 provider 限流仍需部署环境复验。

## ACM/IEEE 登录恢复入口

- 只有当某个导入项进入 `waiting_login` 并在论文待处理列表显示“登录”时，才从 ResearchAgent 卡片点击该按钮；该动作会打开与具体论文绑定的受控登录页面，并保留批次/候选句柄。
- 登录页面出现后由用户完成账号登录；Agent 不读取、代填或保存账号、密码、Cookie、验证码或 OTP。遇到 Cloudflare/验证码时只由用户自行完成，不绕过安全验证。
- 登录完成后回到 ResearchAgent，点击同一论文的“继续/恢复”；预期状态为 `downloading → validating → indexing → completed`，或显示明确的 `BROWSER_SESSION_*`/下载错误并保留重试入口。
- 直接打开 ACM/IEEE 通用登录页只能完成浏览器登录准备，不能替代从待处理论文卡片触发的绑定恢复流程；当前没有 open issue 时不应伪造一个登录任务。
