---
name: usenix-paper-catalog-search
description: CodeBuddy 项目 Agent 适配器：按项目目录检索 Skill 执行 USENIX/DBLP 元数据目录搜索，禁止搜索阶段下载或验证 PDF。
---

请读取并严格执行项目主 Skill：

`.agents/skills/usenix-paper-catalog-search/SKILL.md`

本适配器只负责目录元数据、增量缓存、LangGraph 进度和 RAG 召回，不负责 PDF 下载/验证/导入；不接受任意 URL，不读取凭证，不复制下载器或个人知识库索引。Task、Spec 和 SQLite 回填协议以主 Skill 为准。
