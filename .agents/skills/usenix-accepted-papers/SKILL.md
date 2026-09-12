---
name: usenix-accepted-papers
description: ResearchAgent 项目级 USENIX Security accepted/prepublication 论文下载、PDF 安全验证、导入与失败恢复协议；不负责目录检索。
tools: [download_and_import_paper]
status: legacy
---

# USENIX accepted papers — 下载与导入版

> ⚠️ **遗留版本（待迁移）**：本文件保留以确保既有引用不失效。
> 新的编排协议请使用 `usenix-download-orchestration`（只含编排决策，不含研发流程与调度规则）。
> 论文检索模块迁移到新技能后，本文件将被废弃。

## 适用范围

本 Skill 只在用户已经从冻结搜索结果选择论文、要求下载/验证/导入时使用。它不负责发现年度页面、按研究方向检索、目录缓存、RAG 召回或来源进度卡片；这些工作使用 `usenix-paper-catalog-search` Skill。

先读取：

- `docs/sdd/specs/015-security-paper-discovery.md`
- `docs/sdd/plans/015/task-05-secure-download-and-kb-import.md`
- `docs/sdd/plans/015/task-06-batch-import-and-login-resume.md`
- `docs/sdd/plans/015/task-11-usenix-accepted-and-arxiv-fallback.md`
- `docs/sdd/plans/015/task-12-usenix-paper-skill.md`

若 Spec 未确认、候选不来自服务端冻结结果、目标 Task 不存在或信息不足，停止并记录阻塞，不自行补设计。

## 输入与固定下载链

1. 只接受服务端生成的 `search_id + catalog_paper_id` 或既有导入任务 `item_id`；客户端不得提交任意列表 URL、PDF URL、Cookie、密码或 Authorization。
2. 从服务端候选读取已验证的来源证据和 `publication_stage`，不允许把 `accepted`/`prepublication` 改成 `published`。
3. 下载顺序固定为：USENIX 详情页显式正式 PDF → 页面显式 prepublication PDF → 两者失败后调用 arXiv 严格匹配。
4. arXiv 只允许 `arxiv.org`/`export.arxiv.org` HTTPS API；标题、作者集合和年份达固定阈值才接受，否则返回 `ARXIV_MATCH_UNCERTAIN`，不自动导入。
5. 每次 URL、DNS、重定向和 PDF 内容校验必须调用既有 `paper_download_security.py` 与 `paper_download.py`；不得新建旁路下载器。
6. 通过校验后复用 `paper_import.py`、`paper_import_identity.py`、批量状态机和个人知识库索引；导入失败执行既有补偿/重试/恢复。

## 严格边界

- 不在本 Skill 中请求 accepted 列表或 presentation 页面来建立目录；不按用户 query 直接抓取论文。
- 不在下载流程中创建或写入论文发现目录的向量 collection；PDF 导入仍进入个人知识库既有 collection。
- 不读取或保存用户浏览器 Cookie、密码、profile、Token 或完整认证 URL。
- 不绕过验证码、付费墙、登录权限或 robots/使用条款；合法登录只通过现有 Playwright 等待项完成。
- 不猜测 PDF 文件名，不遍历站点目录，不访问其他会议网站。

## 子 Agent 执行协议

开发/修复前读取目标 Task，并确认目标 `junior-dev` 存在；弱调度器只能原样执行 Task Prompt。使用本地 Ollama 时遵守每次最多 2 个代码文件、约 150 行；线上模型不受该数量限制但仍需拆分验证。子 Agent 必须回传：结果状态和摘要、改动文件、测试命令/退出码/结果、产物路径、复用依据、风险与阻塞、主 Agent 后续动作、开始/结束/总耗时，以及可用时模型/token/工具统计。

## 必须验证

- URL allowlist、逐跳重定向、DNS/peer IP、大小、魔数、页数和临时文件安全测试通过。
- 下载失败不创建有效知识库记录；重复下载在下载前和写入前均去重。
- accepted/prepublication 状态在文件、元数据和导入任务中保持一致。
- 批量任务逐项隔离；登录等待、超时、中断和租约过期可恢复。
- 日志只记录阶段、稳定错误码、耗时和脱敏来源，不含凭证或敏感 URL 参数。

## 停止条件与回填

出现非 allowlist URL、无效/超限 PDF、arXiv 匹配不确定、认证信息泄露、旧导入模块无法安全复用或 Task 约束不完整时立即停止。成功/失败都要回填对应 Task、导入任务和（若启用）`.sdd/runtime/task-ledger.sqlite3`，不得伪造时间、token 或完成状态。禁止 `git reset`、`stash`、`clean`、自动 push 或合并 `main`。
