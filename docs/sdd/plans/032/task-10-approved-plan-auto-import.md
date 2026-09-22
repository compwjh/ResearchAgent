# Task 10：批准计划内自动导入、PDF 身份门禁与恢复

> 关联：[Spec032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task08、Task09；当前状态：`已完成（定向验证通过）`

## 一句话目标

让已批准的深度研究计划按既有 `target_paper_count` 预算自动取得、核验并索引选中论文，同时保持普通目录检索不下载。

## 实施与文件边界

后端角色以 `backend/app/research/application/{acquisition,orchestrator,agent_runtime}.py`、现有 `paper_import_batch_service.py`、`conference_pdf_downloader.py`、`paper_import_identity.py` 为输入，只改受影响接缝与定向测试。复用 Spec029 确认句柄、批任务租约/重试、现有 URL/DNS/重定向/SSRF/PDF 文件校验和 KB 索引；不新建下载器或改变报告合成器。

选中候选按“官方公开 PDF → 已核对身份的可信开放版本 → 既有受控登录”执行。PDF 有效≠论文身份正确；明确错链不得入库/引用全文，存疑进入待处理；登录受限、超时、无 PDF 均保留候选并继续其余论文。研究计划外和普通检索不得触发自动下载。进程重启后批次从持久快照恢复或转为可重试终态，不能永久 queued。

## 定向验收

- 已批准计划：自动导入不超过计划预算；未批准/已取消/普通检索：零 PDF 请求。
- 真实 NDSS/USENIX 小样本可走“选中→安全下载→身份核验→知识库索引→ResearchDocumentLink”；ACM/IEEE 限权/错链样本产生稳定问题记录，不拖垮其他来源。
- 幂等重试、租约过期/重启恢复不产生重复 KB 文件或错误成功状态。只跑 Research acquisition、batch/import、安全与身份定向测试。

## 交接与产出

写 `artifacts/task-10/auto-import.md`，列真实和固定样本、PDF 身份核验依据、状态流、命令/退出码与改动文件。主 Agent 已复查普通搜索零 PDF 请求与错误 PDF fail-closed。执行结果：批准计划自动导入按预算、身份门禁、幂等恢复和失败保留路径完成；定向测试 `206 passed`，Ruff、compileall、diff-check 通过。

## 变更日志

- 2026-09-20：新增用户确认的批准计划内自动导入；复用 Spec029 而非另起全文获取链。
- 2026-09-20：实现并验证批准计划触发门禁、候选身份核验、批任务复用、幂等快照与失败恢复；未批准/普通检索保持零 PDF 请求。
