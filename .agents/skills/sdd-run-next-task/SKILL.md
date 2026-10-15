---
name: sdd-run-next-task
description: 按仓库 SDD 协议通过 CLI 领取并执行一个符合条件的 Task。用户要求执行下一个待办 Task、继续 SDD 工作或运行下一项任务时使用。
---

# SDD Run Next Task

一次只领取并执行一个 Task。让 CLI 管理领取、生命周期和最终结果；从 canonical Prompt 获取任务指令。

## 执行流程

1. 在项目仓库中依次运行以下命令：

   ```sh
   python3 -m scripts.sdd_tasks doctor
   python3 -m scripts.sdd_tasks rebuild
   python3 -m scripts.sdd_tasks status --json
   ```

   检查每个 JSON envelope 的 `ok` 与 `code`。任一步失败就停止并报告返回的机器码和诊断，不手工修复账本或 Task 镜像。

2. 确认当前 IDE ID、稳定 executor ID 和仍存活的持久执行器 PID。缺少任一值或无法核验 PID 时停止，不领取 Task。用这些真实值只调用一次：

   ```sh
   python3 -m scripts.sdd_tasks next --claim --ide <ide-id> --executor <executor-id> --owner-pid <persistent-executor-pid>
   ```

   `code` 为 `NO_TASK` 时报告当前没有可领取任务并结束。其他失败码也立即停止。成功时保存 `data.run_id`、`data.task_id` 和 `data.prompt_path`。

3. 从主工作树根解析 `prompt_path`，读取完整 `prompt.md`。按其中经过协议校验的 `Role:` 标签选择当前 IDE 实际可用的角色 Agent；把整个 Prompt 原样交给它，不改写、删节或另造任务上下文。若没有可调用该角色的能力，返回 `executor_unavailable` 并停止，不由调度器代做。

4. 只接受 Prompt 指定的 `result.json`。若子 Agent 未生成文件、文件不可读、不是合法 JSON 或缺少有效的 `outcome`，报告结构化阻塞并停止；不要用文字摘要替代或猜测结果。`outcome` 为 `succeeded` 时运行：

   ```sh
   python3 -m scripts.sdd_tasks complete --run-id <run-id> --executor <executor-id> --owner-pid <persistent-executor-pid> --result <result-path>
   ```

   `outcome` 为 `failed` 或 `blocked` 时运行：

   ```sh
   python3 -m scripts.sdd_tasks fail --run-id <run-id> --executor <executor-id> --owner-pid <persistent-executor-pid> --result <result-path>
   ```

   `result-path` 使用 Prompt 给出的仓库相对路径。生命周期命令若返回失败，原样报告其 `code` 并停止；不要修补结果或手动回填状态。

5. 仅在 `complete` 或 `fail` 返回成功后读取 CLI 的终态结果：

   ```sh
   python3 -m scripts.sdd_tasks result --json --run-id <run-id>
   ```

   把此命令返回的完整 JSON 作为最终结果依据。报告 Task、Run、outcome、摘要和阻塞项，然后结束本次调用；不要自动领取第二个 Task。

## 停止条件

CLI 错误、无可领取 Task、缺少执行身份、角色执行器不可用、用户决策未完成、Prompt 缺失或结果文件无效时停止并报告机器码或明确原因。遵循 `AGENTS.md` 的通用纪律与 `docs/sdd/TASK-PROTOCOL.md` 的 Task/Prompt/result 协议。
