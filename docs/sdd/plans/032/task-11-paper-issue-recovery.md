# Task 11：待处理论文、登录/上传/重试与报告版本衔接

> 关联：[Spec032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task10；当前状态：`已完成（后端定向验证通过；前端留 Task12）`

## 一句话目标

把具体候选的下载、权限、身份、导入和索引失败变成可由用户修复的持久待办，修复后正确接回研究任务。

## 数据与复用

建立按稳定候选去重的 `AcquisitionIssue` 和 `ManualResolution`；保留关联 task、尝试记录、原因码、可行动作和解决时间。整来源抓取失败没有具体论文身份，只留 SourceProgress。复用 `/api/papers/import-items/{item_id}/login|resume|retry`、`paper_browser_manager.py` 和 `/api/kb/documents/upload`；不保存密码/Cookie、不新建 PDF 文件库。

## 实施与文件边界

后端角色改 Research acquisition 与 issue repository/API 接缝、现有 import/KB 上传的必要关联接口及测试；先设计候选→import-item→KB document→research task 的稳定映射，再接登录/继续、上传和任务续跑。登录只在服务所在电脑打开既有 ACM/IEEE headed browser；远程用户可上传。明确上传错论文时禁止绑定，无法判断时才允许人工确认并留痕。浏览器 session 过期可重开；`waiting_login` 不得错误调用仅支持 `failed` 的 retry。

## 定向验收与停止条件

- 同一候选跨两个研究任务只出现一个待办、保留两条关联；解决后历史可查且不会重复导入。
- 需登录→本机登录→resume→索引→ResearchDocumentLink/证据更新；远程上传正确 PDF→复用 KB 索引→续跑；明确错文件→阻断并允许改作为另一论文导入。
- 研究运行中仅续跑受影响步骤；已生成报告保持旧版本，新成果生成新版本。进程重启后问题、动作和批次状态可恢复。
- 只跑 issue、login/resume、KB 上传、Research acquisition 与版本关联定向测试；无法证明原候选身份时不得自动关闭待办。

## 交接与产出

写 `artifacts/task-11/issue-recovery.md`：状态图、接口样例、身份判定与人工确认记录、命令/退出码、改动文件及风险。主 Agent 已复核用户上传仍调用既有 KB 安全导入。执行结果：后端闭环完成；定向测试 `102 passed、12 subtests`，Ruff、compileall、diff-check 通过；真实 headed-browser/远程上传 smoke 留 Task12/最终验收。

## 变更日志

- 2026-09-20：新增用户要求的可人工修复失败论文模块，复用已有登录与知识库上传能力。
- 2026-09-20：完成候选级持久 issue、跨任务去重、login/resume/retry/upload API 与人工身份确认；不新增 PDF 或导入状态机，前端入口留 Task12。
- 2026-09-20：Luna high follow-up 修正 action 投影随最新状态收敛、`resolved_at`/resume 审计持久化和 resolved 重复上传保护；7 项 Task11 测试、相关导入/Research 106 项定向测试通过，真实 headed-browser/远程上传仍由 Task14 复验。
