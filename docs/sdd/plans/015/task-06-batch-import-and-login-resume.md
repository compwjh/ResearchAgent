# 任务 06 — 实现批量任务与登录续传

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 05；当前状态：`待执行`

## 一句话目标

建立持久化、幂等、逐项隔离的批量导入任务，并通过项目内 Playwright 支持 ACM Digital Library、IEEE Xplore 的用户登录后续传。

## 背景与前置条件

- 复用任务 05 单篇导入服务；批量层不复制下载和知识库逻辑。
- 使用任务 02 已验证的 Playwright 版本、站点解析规则和 profile 策略。
- 浏览器操作必须可见且由用户亲自完成认证，应用永不接收密码。

## 数据、配置与接口

- 持久化 `PaperImportBatch` 与 `PaperImportItem`，单批最多 20 项。
- 实现创建批次、查询状态、重试失败项、打开登录、登录后续传接口。
- 建立任务幂等键：搜索会话、候选、目标知识库身份和有效任务状态组合。
- 浏览器健康只返回 `available/version/supported_sites/reason`，不返回 Cookie、profile 路径内容或认证状态明细。

## 实施步骤与文件边界

1. 建立批次/条目 schema、仓储和状态迁移规则，所有计数从条目真实状态聚合。
2. 创建接口校验搜索会话与候选；去重输入并限制 20 项；已有论文直接返回对应 `paper_id`。
3. 使用受控并发执行单篇导入；公开论文继续运行，`LOGIN_REQUIRED` 只暂停当前项。
4. 服务重启时把遗留 `downloading/validating/indexing` 转为可重试失败，不自动重复写入。
5. 建立 Playwright browser manager：显式 profile、单站点会话锁、超时、关闭和崩溃恢复。
6. 分别实现 ACM、IEEE 页面解析器，只提取经允许的 PDF 下载请求；站点规则彼此隔离。
7. 登录接口打开目标站点；用户完成后 resume 重新检查授权并把受控 Cookie/请求上下文仅用于该下载。
8. 凭证只保存在浏览器 profile；日志、异常、trace 和 API 响应统一脱敏。
9. retry 只处理 `failed/waiting_login`；成功项不可重跑；并发 resume 只能一个生效。
10. 添加任务级 spec-013 观测，记录批次/条目标识、状态、耗时、站点域名和错误码。

## 子代理分派

- 分派 A（`junior-dev`）：批次/条目仓储与状态机，最多 2 文件。
- 分派 B（`junior-dev`）：任务服务和幂等/恢复，最多 2 文件。
- 分派 C（`junior-dev`）：Playwright browser manager，最多 2 文件。
- 分派 D（`junior-dev`）：ACM 解析器与测试，最多 2 文件。
- 分派 E（`junior-dev`）：IEEE 解析器与测试，最多 2 文件。
- 分派 F（`junior-dev`）：导入/登录/resume 路由，最多 2 文件。
- `tester` 负责真实账户验收，`tech-lead` 复核凭证边界；任何日志泄密立即停止门禁。

## 实时监控

```bash
tail -f deploy/run.log
ps aux | grep '[P]laywright'
lsof -nP -iTCP -sTCP:LISTEN
```

## 边界与明确不做

- 浏览器不可用时公开 PDF 导入仍正常；登录项返回明确可恢复错误。
- 一个等待登录项不得占用整个批次 worker；同站点同时登录需串行化。
- 不读取密码输入，不输出 Cookie，不把 profile 纳入 Git、备份包或诊断附件。
- 不绕过验证码、机构 SSO、付费墙和下载限额；无授权明确失败。
- 不支持四大顶会以外站点的专用登录解析器，新增站点另行评审。

## 验收标准

- 批量导入逐项更新，总数与状态聚合准确，失败和等待不阻塞公开项。
- 重复创建、重复 retry、并发 resume 均幂等。
- 服务重启后无永久 running 条目，失败项可以安全重试。
- ACM、IEEE 各用一个合法权限样本完成真实浏览器登录续传并进入知识库。
- 无权限、登录取消、浏览器崩溃、页面结构变化均返回可理解错误。
- 全部日志和观测扫描不到密码、Cookie、Authorization 或带令牌 URL。

## 风险、回滚与产出

- 风险：站点 DOM/跳转变化；解析器按域隔离并以稳定网络响应优先，失败不影响公开下载。
- 回滚：禁用浏览器登录能力，保留公开导入；未完成任务转为可重试失败。
- 产出：批量状态机、任务恢复、Playwright 桥接、ACM/IEEE 适配和测试。
- 执行结果：待执行后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-03 | 架构师(自身) | 创建任务计划，状态为待执行 |
