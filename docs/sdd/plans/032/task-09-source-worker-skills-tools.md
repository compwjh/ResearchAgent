# Task 09：多来源 Worker Skill 与统一 Python Tool

> 关联：[Spec032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task06–08；当前状态：`已完成（worker-tool-v1；Graph/Planner 全量接线仍由 Task08 后续承接）`

## 一句话目标

让各会议 Worker 依据来源专用的产品 Skill 编排，但只调用注册、受控的共用 Python Tool，并返回同一 `SourceResult` / `ImportResult` 合同。

## 复用与划界

复用 `.agents/skills/usenix-catalog-orchestration/`、`usenix-download-orchestration/` 和 `backend/app/skills/{scanner,registry,tool_dispatch,tool_executor}.py`。IEEE S&P、CCS、NDSS 分别有来源策略 Skill（可按目录/下载职责拆两份）；OpenAlex/Crossref/DBLP 是补缺工具而非独立会议下载 Skill。Skill 只写适用条件、调用顺序、受控回退与停止条件；HTML/PDF、缓存、登录和安全由确定性 Tool 执行。

## 实施与文件边界

后端角色修改产品 Skill 与 `backend/app/skills/**` 的注册/分派薄层、必要的 `paper_discovery` Tool facade 和测试。先冻结 Tool JSON schema 与机器可读返回样本，再接七来源查询和四会议详情/导入操作；每次 Tool 都携带 source_id、稳定候选 ID、实际 provenance、错误码/重试性/耗时。来源专用扩展不得改变公共必填字段；未知 Tool/来源和未授权 URL 拒绝。

## 定向验收

两个不同来源 Skill 的 Worker 完成“目录→详情→选中候选→导入请求”，Tool 输出通过同一个 schema 验证器；无可用目标子 Agent/Skill 时明确阻塞，不由弱调度器猜测参数。不得复制 PDF 下载器、写抓取脚本到 SKILL.md、将研发 Task/Git 规则混进产品 Skill。只跑 Skill/Tool 合同与受影响来源测试。

## 交接与产出

写 `artifacts/task-09/worker-tool-contract.md` 和逐来源执行样例，回传改动文件、测试命令/退出码、Tool schema 版本、风险/阻塞。主 Agent 验证注册入口可实际执行，而非只出现在 Tool 列表。执行结果：已完成；统一 `paper_discovery` Tool 已真实注册和分派，两个来源通过同一验证器，未验证来源保持 blocked。

## 变更日志

- 2026-09-20：以 Spec032.1 USENIX Skill/Tool 为基线，加入多会议 Worker 合同。
- 2026-09-20：Luna high 子 Agent 完成 `worker-tool-v1` facade、三份来源 Skill 和注册/分派接线；主 Agent 复跑 132 个相关测试与 21 个 subtests，ruff、compileall、git diff-check 通过。IEEE 仅使用 2024 已验证样本，CCS/NDSS 未验证状态保留。
