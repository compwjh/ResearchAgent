# Spec015 Task17 USENIX-only 验收复核

- 角色：tester
- 时间：2026-09-08
- 范围：USENIX 官方目录优先、DBLP 辅助；不含 ACM/IEEE 登录、自定义会议、A14 排序质量和真实 PDF/GUI 扩展。
- 原始日志：`.codebuddy/agent-logs/tester-spec015-task17-final2-20260908-163933.md`

## 结论

**USENIX-only 通过；Spec015 总状态保持实施中。**

## 证据

- fix-g 定向套件：105 passed。
- 并发租约单赢家、过期租约恢复、跨 DOI/无 DOI 合并、DBLP partial、USENIX partial：7 passed。
- 前端契约：4 passed；`node --check frontend/app.js` 通过。
- 全量后端回归：650 passed、1 skipped、5 warnings、38 subtests；`py_compile`、`git diff --check`、冲突扫描和前端旧路由扫描通过。
- 空 SQLite 首次 USENIX 同步：2 个抓取单元、3 篇 fixture 论文，搜索阶段未触发 PDF 探测。

## Deferred

ACM/IEEE 合法登录、自定义会议/DBLP Venue Search、A14 排序质量标注集、真实公开 PDF 导入和 GUI/窄屏运行时证据留待后续扩展；本轮不伪造为已完成。
