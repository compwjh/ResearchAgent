# Task 06：评审、全量回归、部署与复盘

> 关联：[spec-026](../../specs/026-reasoning-effort-feedback-fixes.md) ｜ 索引：[README](./README.md)
> 依赖：任务 04、05；当前状态：`已完成`

## 一句话目标

完成三份评审、跑一次全量回归、真实启动服务完成运行时验证，并落复盘。

## 背景与前置条件

- 已确认 spec 026，重点 §验收方式、§评审记录。
- 前置：Task 04、05 均已完成且各自评审通过（评审报告已落盘）。
- 历史教训：024 因范围过大验收 NO-GO（1326 passed / 14 failed）；014/015/022/024 均出现过「服务未运行导致验收 BLOCKED」。本 Task **不得**以 mock 结果声称真实 smoke 通过。

## 数据、配置与接口

不适用（无新增数据模型或接口）。

## 实施步骤与文件边界

1. **需求评审**：`docs/sdd/reviews/026-requirement-review.md` —— 核对 spec 026 与 024 的修订声明一致、边界可测、明确不做无漏洞。
2. **技术评审**：`docs/sdd/reviews/026-tech-review.md` —— 核对 Task 02–05 的实现与 spec 合同一致，重点审 `unknown`/`stale` 不伪造支持集合、乐观建卡不重复建卡、错误文案映射完整。
3. **全量回归**：运行后端 pytest 全量；记录真实命令与结果。
4. **真实 Ollama smoke（必须）**：
   - 拉起 Ollama 与后端（`curl http://127.0.0.1:11434/api/tags`、`curl http://127.0.0.1:8000/api/health` 必须成功）。
   - 验证 ① 发送后 500ms 内 assistant 卡片出现；② 真实 409 路径（使用不支持 xhigh 的模型，或临时构造不支持档位）被呈现为「该模型不支持…」而非「连接失败」。
   - 若端口被占用，换可用端口并在报告中写明。
5. **部署/启动**：由 Agent 直接启动本地服务完成运行时验证，并在最终回复给出可点击地址、实际端口与启动命令（AGENTS.md 强制流程第 7–9 条）。
6. **复盘**：`docs/sdd/retro/2026-09-12-reasoning-effort-feedback-fixes.md` —— 记录三个缺陷的根因、为何 024 评审没发现、遗留项（探测性能改造 → spec 027；PATCH 缺 `_validate_model`）。
7. **状态台账**：追加 `docs/sdd/spec-status-changelog.md`。

## 子代理分派

| 角色 | 模型 | 最小上下文 | 文件范围 | 回读校验 |
|---|---|---|---|---|
| architect | `Deepseek-V4.1-Flash` | spec 026 + Task 02–05 报告 | 评审文档 | 主会话核对结论为真实通过/打回 |
| backend-tester | `Deepseek-V4.1-Flash` | spec 026 §边界 B1-B4/B16 + 后端 diff | 测试报告 | 主会话核对 pytest 真实输出 |
| frontend-tester | `Deepseek-V4.1-Flash` | spec 026 §边界 B5-B15 + 前端 diff | 测试报告 | 主会话核对 DOM 断言与 `node --check` 输出 |
| tester | `Deepseek-V4.1-Flash` | 三份报告 + spec §验收方式 | `reviews/026-acceptance-review.md` | 主会话核对 smoke 是否为真实运行 |

## 边界与明确不做

- 不做：不在本 Task 引入任何新功能或范围外改动。
- 不得：以 mock 结果替代真实 Ollama smoke 的通过结论。
- 不得：服务未启动时声称「已部署/已验证」——必须写明阻塞原因与用户可执行的解决命令。

## 验收、风险与回滚

- 验收：三份评审均为真实结论；全量回归通过；真实 smoke 两条观察点均成立；状态台账已追加；复盘已落盘。
- 风险（高）：本机 Ollama 当前未运行（2026-09-12 实测 `/api/tags` 为空）。若 Task 06 执行时仍不可用 → 状态置 `阻塞`，记录 `ollama serve` 与 `curl` 的真实输出，并在最终回复给出启动命令。
- 回滚：本 Task 不改业务代码，无需回滚；若评审打回，回到对应 Task 而不是修改评审结论。

## 产出物、执行结果与变更日志

待执行后填写：评审文件路径与结论、pytest 全量输出、smoke 的真实 curl/浏览器证据、复盘路径、changelog 行。
