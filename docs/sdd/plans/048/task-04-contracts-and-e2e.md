# task-04 版本 / 静态契约同步、浏览器 E2E 与收口

> 关联：[spec-048](../../specs/048-literature-map-create-tab-and-refresh-icon.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03；当前状态：`已完成`
> 产出性质：纯文档任务书，由主会话代行创建（三处留痕：本头部 / spec 变更日志 / 状态台账 2026-11-13 条）。

## 1. 状态与一句话目标

`已完成`。同步静态资源版本与冻结断言，新增 tab / 图标静态契约，完成真实浏览器 E2E、部署验证、评审签字与 spec 收口。

## 2. 背景与前置条件

任务 02 / 03 已落地并读回校验。当前生效版本 `frontend/index.html:11` `literature-maps.css?v=34`、`:903` `literature-maps.js?v=47`；`tests/frontend/` 至少 10 处 `in INDEX` 冻结断言与 fixture 内版本字符串依赖旧值；`test_frontend_map_header_actions_readability.py:31-36,239-240,266-267` 断言两个 header 按钮的 id / 文案 / 事件绑定。

## 3. 数据、配置与接口

不适用。版本契约：`literature-maps.js?v=47 → v=48`、`literature-maps.css?v=34 → v=35`；`app.js?v=77` / `styles.css?v=77` 不动。

## 4. 实施步骤与文件边界

按 Gate 4「每任务 ≤2 个文件」拆子任务，涉及 `frontend/index.html`、`tests/frontend/*.py` 与 fixture：

1. 升两个 live 版本；在 `index.html` **末尾注释区**加两条纯属性 marker（`src="/assets/literature-maps.js?v=47"`、`href="/assets/literature-maps.css?v=34"`），不含 `<script` / `<link` 字面串、不插入 `<head>`，以兼容 `in INDEX` 冻结断言；同步 fixture 与精确 live 版本断言 / `MAP_CSS_VERSION` 常量。
2. 按新契约更新 `test_frontend_map_header_actions_readability.py`：移除 `literature-map-new-button`，刷新按钮改判「无可见文字 + `aria-label` 保留」；三态 / 尺寸 / 对比度约束逐字保留。
3. 新增按能力命名的静态契约测试（禁止含 spec / task 编号）：tab 结构与 `aria-*`、createPanel 默认 hidden 与 tab 切换不重建、刷新图标位置 / 无文字 / CSS 转圈形状、两条 marker 在注释内且无标签字面串、live 版本精确值。
4. 定向验证：`node --check frontend/literature-maps.js`、`pytest -q tests/frontend/`、`scripts/check_test_layout.py`；Spec 收口阶段再跑最终候选全量回归。
5. 真实 Chromium E2E：走 spec「产品使用步骤」1–4（桌面 + ≤760px 窄屏），落盘截图 / 计算样式 / 请求状态；部署验证 `/api/health`、首页与两个新版本资源 200。
6. 评审：`frontend-reviewer` 三项必查、`frontend-tester` 单端静态核对、`tester` 验收签字 + `architect` 合并裁决；状态 `已确认 → 实施中 → 已完成`、台账、复盘、人工验收文档、本地 commit。

## 5. 子代理分派

含 `.py` / `.html` 的实现分派 `frontend-dev`（测试文件改动同样按前端单端处理，由主会话确认归属）；评审 `frontend-reviewer`、单端 `frontend-tester`、验收 `tester`、裁决 `architect`；不派后端角色、不跑后端 pytest 单端回归。每次回传后读回真实文件校验。

## 6. 边界与明确不做

不改松 / 不删 / 不 skip / 不 xfail 既有断言；不重写历史归档报告旧路径；不新增 CI workflow、不设覆盖率阈值；不处理 Langfuse / 404 / 历史 lint 债务；闭环后仅本地 commit，**不 push、不合 main、不 force push**（Spec-047 追加范围五的远端合并另案，用户另行授权）。

## 7. 验收、风险与回滚

- 命令 / 退出码 / 通过数 / 阻塞项全部落盘；`git diff --check` 0、冲突标记 0、引用路径 0 断链。
- 风险：marker 若插入 `<head>` 会污染 `test_frontend_map_header_actions_readability.py` 取首个 `styles.css?v=` 的 `active_version` 语义；旧版本字符串若在 fixture 中遗漏会导致单端回归红灯。回滚：`git revert` 本任务 commit。

## 8. 产出物、执行结果与变更日志

待执行后填写：`docs/sdd/plans/048/runs/task-04/`（E2E JSON / 截图 / `deploy-verification.json` / `full-regression.txt`）、`docs/sdd/reviews/048-*.md`、`docs/sdd/retro/`、状态台账与人工验收文档。
