> 关联：[spec-021 论文导入异步化与进度反馈](../../specs/021-paper-import-async-progress.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03；当前状态：`待执行`

# Task04 前端：真实轮询进度、取消与软超时提示

## 状态与一句话目标

`待执行`。在后端已"入队即返回 + 后台执行"的前提下，让导入进度面板**逐条实时可见**，补齐单条目重试入口、取消入口与"仍在导入"的软提示；任何路径不自动跳转视图。

## 背景与前置条件

- 依赖任务 02/03：`POST /api/papers/imports` 返回时批次为 `queued`，`GET /api/papers/imports/{id}` 能反映逐条迁移；新增 `POST /api/papers/import-items/{item_id}/retry` 与 `KB_STORAGE_LOCKED`。
- spec-020 / Task05（BUG-03）已确立：面板逐条可见（含未完成）、完成不清空、禁止自动跳转、direct 论文不伪造 `batch_id`。
- spec-020 / Task06（BUG-04）已确立：`submitting` 相位以 `paperState.submitInflight > 0` 为唯一依据。
- 现状：`frontend/app.js:1077-1105`（轮询）、`1107-1167`（`renderPaperBatch`）、`1169-1203`（`renderDirectImports`）。

## 数据、配置与接口

- 条目状态文案补齐：`queued` 排队中 / `downloading` 下载中 / `validating` 校验中 / `indexing` 建索引中 / `completed` 已完成 / `failed` 失败 / `waiting_login` 等待登录 / `cancelled` 已取消。
- `PAPER_ERROR_TEXT` 追加：`KB_STORAGE_LOCKED: '知识库存储被另一个实例占用，请关闭其他服务实例后重试'`。
- 新增状态：`paperState.slowSince`（批次非终态但长时间未推进的时间戳）。
- 接口消费：`GET /api/papers/imports/{id}`（既有）、`POST /api/papers/import-items/{id}/retry`（新增）、`POST /api/papers/import-batches/{id}/cancel`（既有，仅 `queued`/`waiting_login`/`failed` 可取消）。

## 实施步骤与文件边界

**文件边界**：只改 `frontend/app.js`、`frontend/index.html`（`?v=N` 递增）、`frontend/styles.css`（若需样式，作用域限定 `#papers-view`）与前端契约测试 `tests/test_frontend_paper_contract.py`。**不得改 `backend/**`**。

1. **先补契约测试**：新状态文案、`KB_STORAGE_LOCKED` 文案、单条目重试按钮、取消按钮的存在性断言。
2. `PAPER_STATUS_TEXT` / `PAPER_ERROR_TEXT` 补齐上述枚举与文案。
3. `renderPaperBatch`：每条按 `status` 渲染对应文案；`failed` 条目在整批"重试失败项"之外**追加单条"重试"按钮**（调用新端点，点击后立即禁用 + 加入 `retryingBatchIds` 语义的重试中集合，返回后刷新卡片与汇总）。
4. 批次级"取消"按钮：仅当批次非终态或处于可取消态时显示；取消成功后刷新。
5. 软提示：轮询时若批次非终态且 `updated_at` 超过建议阈值（3 分钟）未变化，状态栏追加"（仍在导入，可离开此页）"，**不得**谎报失败。
6. 轮询健壮性：请求失败计入 `lastImportError`，达到连续失败阈值时给出可见错误但**不静默停止**，由用户取消或重试。

## 子代理分派

- 角色：`frontend-dev`（`hy3`，32k）。
- 最小上下文：本文件 + spec-021 §边界最后三条 + `frontend/app.js` 的 `906-990`、`1042-1071`、`1077-1203` 三段行号范围。
- 单次范围：≤2 个代码文件、≤150 行；多轮分派。
- 回传：先回传代码/用例与验证输出，再回传说明；日志路径必给。

## 边界与明确不做

- 不改后端；不改 spec-020 已确立的 DOM 契约（不新增/更名元素 id，可新增 class）。
- 不引入框架/构建；CSS 作用域限定 `#papers-view`。
- 任何路径不得自动切换视图；跳转只由"在知识库中查看"按钮触发。
- 不得为 direct（无批次）导入伪造 `batch_id`；direct 论文继续保留"已完成/已在知识库"展示。
- 软提示不得改变 `importPhase` 判定（不得把"慢"算成失败）。

## 验收、风险与回滚

**验收**：
1. `node --check frontend/app.js` 通过。
2. `python -m pytest tests/test_frontend_paper_contract.py -q` 通过。
3. 运行时：提交 3 篇 → 面板立即出现"排队中"，随后逐条可见"下载中/建索引中/已完成"。
4. 运行时：制造 1 篇失败 → 单条"重试"只重跑该条，其余条目不受影响。
5. 运行时：`KB_STORAGE_LOCKED` 场景显示可行动文案（不是"论文导入失败"）。
6. 运行时：取消按钮仅对可取消批次显示，取消后 UI 即时刷新。

**风险**：轮询与前一轮原有 `is-progressing` 动画冲突 → 需确认终态移除动画；状态文案与后端 `ITEM_*` 常量逐字对齐，避免 Unknown 文案漏出。

**回滚**：回退 `frontend/**` 改动；纯前端无数据影响。

## 产出物、执行结果与变更日志

待执行后填写（真实命令、真实输出、改动文件与行数、日志路径）。
