> 关联：[spec-021 论文导入异步化与进度反馈](../../specs/021-paper-import-async-progress.md) ｜ 索引：[README](./README.md)
> 依赖：任务 02、03、04；当前状态：`待执行`

# Task05 评审、部署与复盘

## 状态与一句话目标

`待执行`。完成需求/技术评审与跨端验收、部署重启与运行时验证，并沉淀本轮复盘（尤其"同步执行导致进度 UI 失效"与"多实例共用本地 qdrant"两条）。

## 背景与前置条件

- 依赖：任务 02（后端异步执行器）、03（错误语义与单条重试）、04（前端轮询/取消/软提示）均已 `已完成`。
- 建议：spec-020 / Task06（BUG-04）先闭环，避免状态/I 相位问题在验收时重复出现。
- 运行时验收前置：**本机只能保留一个持有 `data/kb/qdrant` 的实例**，否则导入注定 `KB_STORAGE_LOCKED`。停哪个实例由用户决定（`deploy/stop.sh` 或手动 kill），本任务不自动 kill。

## 数据、配置与接口

- 评审文档：`docs/sdd/reviews/021-requirement-review.md`、`021-tech-review.md`、`021-acceptance-review.md`。
- 部署：`./deploy/start.sh`（前台）或 `-d`（后台）；后端改动必须重启生效。
- 状态台账：`docs/sdd/spec-status-changelog.md` 必须同步 spec-021 的每次状态迁移。

## 实施步骤与边界

1. **需求评审** — `Task(architect)`：目标/范围/边界/明确不做/产品步骤是否可映射到验收点 → 结论通过/打回。
2. **技术评审** — `Task(architect)`：异步执行器单飞与恢复、错误归因窄匹配、轮询与相位判定是否与 spec-019/020 冲突 → 结论通过/打回。
3. **单端回归** — `Task(backend-tester)`（`cd backend && python -m pytest -q`、`ruff check .`）与 `Task(frontend-tester)`（`node --check`、`tests/test_frontend_paper_contract.py`）。
4. **跨端验收** — `Task(tester)` 汇总单端报告并执行 spec-021 的 4 条验收场景，产出 `021-acceptance-review.md`（含通过/不通过结论）。
5. **架构师签字 → 部署**：验收通过后转 `已确认`/`实施中`→`已完成`，重启服务并在最终回复给出可点击地址与实际端口。
6. **复盘（强制，不必询问用户）**：落盘 `docs/sdd/retro/2026-09-10-import-sync-and-qdrant-lock.md`，提炼两条经验：①"UI 承诺的进度必须有异步后端支撑，否则轮询永不触发"；②"本地 Qdrant 单实例限制必须前置为可诊断错误，而不是兜底错误码"。
7. **Git**：在 `fix/spec-021-import-async-progress` 分支上 commit（含实现与验收文档），不 push、不合 main。

## 边界与明确不做

- 不改实现代码（评审/验收只出文档与结论；发现缺陷退回对应 task）。
- 不在评审未通过时转状态；不伪造评审结论。
- 不自动停止用户正在运行的服务实例。

## 验收、风险与回滚

**验收**：三份评审真实结论齐全、验收签字栏已填、`spec-status-changelog.md` 已追加、引用路径真实存在、复盘已落盘（AGENTS.md 收口清单全勾才转 `已完成`）。

**风险**：验收环境仍有两个实例 → 运行时导入必然失败；此时应记录"环境阻塞"而非判定实现缺陷。

**回滚**：任务未能通过时，spec-021 保持 `实施中` 或 `阻塞` 并在 changelog 记录阻塞原因；回滚分支改动不影响 `main`。

## 产出物、执行结果与变更日志

待执行后填写（真实命令、真实输出、评审结论、部署端口与访问地址、日志路径）。
