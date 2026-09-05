# Spec015 真实浏览器会话复核（ACM / IEEE）

> 记录日期：2026-09-05
> 目的：记录用户在 Chrome 中完成的外站访问观察，并与项目 Playwright profile 的证据严格区分。

## 观察结果

### ACM Digital Library

- 用户 Chrome 标签页已打开 `https://dl.acm.org/doi/pdf/10.1145/3453161`，标签页标题为 `dl.acm.org/doi/pdf/10.1145/3453161`，页面进入 PDF 查看器。
- ACM 首页显示机构开放访问提示：`acm open access Provided by Hong Kong Polytechnic University (PolyU)`。
- 首页同时显示 `ACM is now Open Access`，并提供向 Open Access 的过渡说明。

### IEEE Xplore

- 用户 Chrome 会话的 IEEE 页面显示 `Access provided by: Hong Kong Polytechnic University`，并显示 `Sign Out`，说明当前机构会话已认证。
- 该会话已打开 IEEE 全文 PDF 标签页：`https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=10654379`。

## 边界与结论

- 上述证据证明用户 Chrome profile 可以访问 ACM/IEEE 的相应页面；不证明项目 Playwright profile 已继承该登录状态。
- 项目使用独立的受控 profile。对指定 ACM PDF 的项目 Playwright 请求仍返回稳定错误 `LOGIN_REQUIRED`；这与 Chrome 用户会话分离，不应通过复制 Cookie、密码或 profile 数据解决。
- 无 Cookie、Authorization、密码、SSO 内容或浏览器 profile 文件写入日志、API 响应或 Git。
- 直接无会话 HTTP 请求受到站点反爬/挑战限制，不能作为用户浏览器会话的反证。

## 后续验收动作

1. 由用户在项目提供的 headed Playwright 登录窗口中完成 ACM/IEEE 合法认证，或明确将“Chrome 已登录”仅作为人工外站可访问证据。
2. 在项目 profile 内重新执行 `open login → 用户完成认证 → resume → PDF 页数校验 → 知识库导入`。
3. 只有项目 profile 的 resume 与导入闭环成功后，才可解除 Task06 A10/A11 的整体验收阻塞。

## 论文服务不可用复现（2026-09-05）

- `GET /api/health` 返回 HTTP 200，且 `paper_discovery_enabled=true`。
- `GET /api/papers/browser/health` 返回 HTTP 200，Playwright `1.52.0`、`available=true`。
- 在 `ccs`、查询词“agent 安全”、2021–2025 年份下调用论文搜索，等待完整重试后返回 HTTP 424、错误码 `DBLP_UNAVAILABLE`。
- 因搜索没有生成候选快照，前端不会创建 `waiting_login` 条目，也就不会显示“打开登录”按钮；页面的通用文案“论文服务暂时不可用”是该错误的前端降级显示。
- 该现象在重新启动服务并允许外网访问后仍可复现，当前应记录为 DBLP 外部数据源阻塞，而不是 ACM/IEEE 认证失败。

## 记录来源

- Chrome UI 页面标题、URL 与可见无障碍文本；未读取或保存凭证。
- 项目 Playwright 运行日志中的 `LOGIN_REQUIRED` 稳定错误。
