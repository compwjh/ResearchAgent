# Task02 入口覆盖与可行性

关联：[Spec050](../../specs/050-agent-safety-and-factuality.md) · [任务索引](README.md)

依赖：Task01。当前状态：待执行。

## 目标、数据与接口

盘点工具分发、下载/导入、研究异步及重试入口；落盘授权与事件契约、M3 Max 加载冒烟、可用数据及许可；为第一交付和第二交付分别给出阻塞项。

## 分派与边界

角色：architect / backend-dev / tester。模型与预算引用 Spec 执行配置和当次用户指派。只读取本任务契约、相关路径及直接依赖产物。涉及前后端分别分派。改动及交接结果需读回核对。

## 验收与回滚

覆盖矩阵逐入口可追溯；第一交付独立 Go/No-Go；训练或公开数据阻塞只影响第二交付。

发现缺陷先定向修复。发现超范围需求退回 Spec 评审。候选验证失败时维持既有可用版本与硬安全约束，记录具体阻塞。

## 产物、结果与变更

待执行后填写实际文件、验证命令、退出码、测试结果与回滚证据。

## 可先分派：本机复训证据核对

接手条件：检出 `codex/spec050-piguard-integration`，并可读取训练 Mac 上的 `/Users/wjh/piguard-repro`。GitHub 分支仅包含方案和任务文档，模型权重及原始实验记录保存在训练 Mac。若本机目录不可读，记录缺失路径，由负责人提供受控只读副本。

1. 查看 `/Users/wjh/piguard-repro/logs/formal-v1.exit-code` 和 `/Users/wjh/piguard-repro/runs/formal-v1/events.jsonl`。核对退出码 0、最终 `finished` 事件、3 个 epoch 和 7,194 步。
2. 查看 `/Users/wjh/piguard-repro/runs/formal-v1/config.json`、`/Users/wjh/piguard-repro/logs/model-revision.txt` 和 `/Users/wjh/piguard-repro/runs/official-clean/preparation-audit.json`。核对基础模型版本、训练 76,729 条、验证 144 条，以及六条排除记录。
3. 查看 `/Users/wjh/piguard-repro/runs/formal-v1/best_scores.json`，核对最佳验证准确率 111/144。运行 `shasum -a 256 /Users/wjh/piguard-repro/runs/formal-v1/best_model.pth`，与 Spec050 的候选权重哈希比较。此步骤只需读文件，无需加载模型。
4. 在本任务目录新增 `piguard-training-evidence.md`。逐项记录预期值、实测值、证据路径和结论（符合、差异、缺失）。有差异时保留实测值，交负责人裁决。交付仅覆盖证据核对，Task02 的其余契约和可行性验收仍待执行。

这项核对可在 Spec 确认前进行。执行范围限于读取实验文件和撰写核对记录，模型转换、公开评测和运行时接入由后续任务处理。
