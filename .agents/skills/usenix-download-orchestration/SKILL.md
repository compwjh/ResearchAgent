---
name: usenix-download-orchestration
description: USENIX Security 论文 PDF 下载与个人知识库导入的编排协议。当用户已从检索结果中选定具体论文、需要下载并导入时使用本技能。本技能负责编排决策——决定下载优先级（官方正式 PDF → prepublication PDF → arXiv 兜底）、arXiv 匹配不确定时如何处理、以及导入失败后的重试与恢复；实际下载、安全校验与导入由 download_and_import_paper 工具执行，本技能不接触 PDF 字节。
tools: [download_and_import_paper]
---

# USENIX 论文下载与导入编排

## 定位：编排层，不是执行层

本技能是**编排协议**：决定「按什么顺序尝试、失败后怎么退、什么时候该停」。
**下载、URL 白名单校验、PDF 内容校验、导入全部由工具（执行层）完成，编排层不接触 PDF 字节。**

| 层 | 负责 | 对应物 |
|---|---|---|
| 编排层（本技能） | 决策：下载顺序、兜底条件、重试与恢复 | 本文件 |
| 执行层（工具） | 执行：下载、安全校验、导入、去重 | `download_and_import_paper` |

## 适用范围

- 用户已从检索结果中选定论文，要求下载 / 验证 / 导入。
- 官方 PDF 不可用时，决定是否可以退到 prepublication 版本或 arXiv。

**不适用**：发现年度页面、按研究方向检索、目录缓存、RAG 召回——
这些属于 `usenix-catalog-orchestration`。

## 输入契约

只接受服务端生成的 `search_id + catalog_paper_id` 或既有导入任务 `item_id`。
**不接受客户端提交的任意列表 URL、PDF URL、Cookie、密码或 Authorization。**

从服务端候选读取已验证的来源证据和 `publication_stage`，
**不得把 `accepted` / `prepublication` 改成 `published`。**

## 编排决策点

1. **固定下载顺序**（不得颠倒，不得跳过校验）：
   1. USENIX 详情页显式给出的**正式 PDF**；
   2. 页面显式给出的 **prepublication PDF**；
   3. 两者均失败后，才考虑 **arXiv 严格匹配**。
2. **arXiv 兜底判定**：仅当标题、作者集合与年份均达到匹配阈值时才接受；
   否则判定为 `ARXIV_MATCH_UNCERTAIN`，**不导入**，并向用户说明匹配不确定。
   arXiv 只使用 `arxiv.org` / `export.arxiv.org` 的 HTTPS API。
3. **调用工具执行**：调用 `download_and_import_paper`，由工具完成
   URL 白名单、逐跳重定向、DNS/peer IP、大小、魔数、页数与临时文件的安全校验，
   以及导入后的去重、补偿与重试。**不得新建旁路下载器。**
4. **失败与恢复**：
   - 下载失败 → **不创建有效的知识库记录**；
   - 重复下载在下载前与写入前均需去重；
   - 批量任务逐项隔离，单项失败不影响其余项；
   - 登录等待、超时、中断与租约过期可恢复。
5. **状态一致性**：`accepted` / `prepublication` 状态在文件、元数据与导入任务中保持一致。

## 硬边界

- 不读取或保存用户浏览器 Cookie、密码、profile、Token 或完整认证 URL。
- 不绕过验证码、付费墙、登录权限或 robots / 使用条款；
  合法登录只通过现有 Playwright 等待项完成。
- 不猜测 PDF 文件名，不遍历站点目录，不访问其它会议网站。
- 不接受任意 URL 入参；URL 必须由工具按白名单校验。
- 日志只记录阶段、稳定错误码、耗时与脱敏来源，**不含凭证或敏感 URL 参数**。

## 停止条件

出现以下任一情况立即停止并向用户说明：

- 出现非白名单 URL，或 PDF 无效 / 超限；
- arXiv 匹配不确定；
- 出现认证信息泄露风险；
- 既有导入模块无法安全复用；
- 缺少定位论文所需的输入（`catalog_paper_id` 或 `item_id`）。

停止时**如实报告失败**，不得伪造成功状态、时间或 token。
