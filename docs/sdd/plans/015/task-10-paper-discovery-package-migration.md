# 任务 10 — 论文发现限界上下文目录重构

> 关联：[spec-015](../../specs/015-security-paper-discovery.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03、05、06、07、08；当前状态：`待确认`

## 一句话目标

把 Spec015 的领域模型、仓储、应用用例、数据源、浏览器、解析器、安全和命名逻辑统一收纳到 `backend/app/paper_discovery/`，让目录直接表达一个可独立阅读和迁移的论文发现限界上下文。

## 当前证据

- 领域模型当前位于 `backend/app/domain/paper_discovery.py`、`paper_import_batch.py`。
- Spec015 实现当前分散在 `backend/app/services/` 的 discovery、download、import、batch、browser、parser、source、security 和 identity 文件。
- API 路由位于 `backend/app/api/routes.py`，知识库和旧文章流程与新论文发现代码共享顶层 services 目录。

## 前置门禁

- 用户确认 Spec015 的架构变更；确认前不得移动、重命名或修改业务代码。
- 先建立完整 import/测试/脚本清单，确认 Spec013/014、KB 和旧文章流程的文件边界。
- 记录迁移前分支、commit、工作树和全量测试结果；不执行 reset、stash、clean 或覆盖用户修改。

## 思维链（可观察设计依据）

1. 先按 import 关系而不是文件名分类，避免把通用 KB PaperRecord 或旧文章下载误迁入。
2. 先移动纯 domain，再移动 repository/application，再移动 sources/browser/parsers/security，逐层修复 import，减少循环依赖。
3. API 保持薄适配层；每一层迁移后立即运行对应测试，确认行为不变。
4. 最后删除旧 Spec015 文件并扫描旧路径引用；发现外部依赖时保留显式兼容转发或暂停迁移。

## 允许范围与禁止操作

- 允许：新建/移动 `backend/app/paper_discovery/` 内的 Spec015 文件，更新对应 import 和测试路径，补充 `__init__.py` 与架构契约测试。
- 禁止：修改 API 契约、SQLite schema、错误码、安全策略、KB 数据格式、Spec013/014 模块；禁止顺手重构旧 `article_download.py` 或 `download_paper_skill.py`。
- 禁止：reset、stash、clean、force checkout、覆盖其他 Spec 的未提交修改、commit/push。

## 子任务拆分

1. **import 盘点与包骨架**：列出迁移白名单/黑名单，创建包目录和依赖方向契约测试。
2. **domain/repositories/application 迁移**：按层移动模型、SQLite 仓储和批量/单篇用例，保持行为不变。
3. **sources/browser/parsers/security 迁移**：移动 DBLP/OpenAlex、ACM/IEEE、Playwright 和安全模块，修复 import。
4. **API/测试收口**：更新 API 依赖、测试 import、文档路径，删除旧 Spec015 实现文件并执行全量验证。

每个含代码文件的子任务必须先分派 `junior-dev`；使用本地模型时遵守每次最多 2 个代码文件、约 150 行限制，使用线上模型时仍按风险拆分。每次分派必须把完整 Prompt、允许文件、验证命令、日志路径和固定返回字段落盘。

## 测试与验收标准

- 新包 import 无循环依赖；domain 不导入 FastAPI/httpx/Playwright/Qdrant/环境配置。
- 论文发现、单篇导入、批量状态机、登录续传、安全下载、旧 KB 兼容和 API 测试全量通过。
- `rg` 不再发现生产代码引用旧 Spec015 路径；兼容转发（若保留）必须有明确注释和测试。
- `git diff --check`、全仓冲突标记扫描、敏感信息扫描通过；服务健康与论文 API smoke 结果不变。
- 迁移前后公开接口、数据库 schema、错误码、日志字段和运行时行为一致。

## 风险、停止条件与回滚

- 发现循环依赖、外部旧 import、测试行为变化或边界归属不清时停止迁移，保留已完成的小步移动并记录原因。
- 回滚只允许按迁移清单反向移动或恢复 import；不使用破坏性 Git 命令，不覆盖用户修改。
- 若无法证明迁移后行为等价，Task10 保持阻塞，Spec015 不得标记完成。

## 产出物

- `backend/app/paper_discovery/` 包及架构契约测试。
- 迁移清单、路径引用扫描、分层验证报告和更新后的 API/任务文档。

## 执行结果

待用户确认架构变更后填写。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-05 | 架构师(自身) | 根据用户反馈创建目录重构任务，状态为待确认；未移动或修改业务代码 |
