# Task 13：Spec032.1 余项移交——IDE 助手与会话 Skill 粘性

> 关联：[Spec032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task09、Spec032.1 自身 Task07 评审；当前状态：`部分完成（Task08 真实检索→导入通过；Task10 真实连续会话待补证）`

## 一句话目标

不丢失 032.1 尚未完成的跨环境事项，同时不把 IDE 研发 Skill 误作产品运行时 Skill。

## 移交清单与边界

1. [032.1 Task08](../032.1/task-08-local-session-usenix-skill.md)：本地 IDE 会话的 USENIX 助手 Skill 只调用运行中的产品 API，不重新实现抓取/下载。按新版多来源合同检查该脚本输入/输出；若产品 API 尚未稳定，明确阻塞而不写假样例。
2. [032.1 Task10](../032.1/task-10-session-skill-stickiness.md)：产品会话点名一次 Skill 后，后续“就下载第一篇”能继续使用当前 Skill/Tool；允许显式切换或退出，禁用/删除 Skill 时自动清除。对 Research Worker 的来源选择不能产生跨任务串台。
3. 032.1 Task07 的技术/验收评审仍在 032.1 自身完成后方可收口；本 Task 不代签其评审、不回填虚构成功。

## 分派与验证

两个子项可分别分派 IDE Skill 和后端会话角色，各自只读原 Task、Spec032 新合同和对应 API；改 `.codebuddy/skills/**` 与会话 Skill 状态/测试时不得触碰其他模块。验证 IDE 脚本真实调用与服务不可达错误；会话连续两轮的 Skill/Tool 保留、切换、退出、禁用和任务隔离。只跑相关定向测试；如旧 Task10 已被其他工作真实完成，先核对代码/报告并只补缺，不重复开发。

## 交接与产出

写 `artifacts/task-13/carryover.md`，逐项说明原任务、实际状态、改动文件、命令/退出码、真实运行证据与 032.1 状态台账链接。主 Agent 已验证产品 Skill 与 IDE Skill 目录分工。执行结果：4 passed 的 Task13 合同、73 passed 的会话/仓储/Skill 相关测试、脚本 Ruff/py_compile/不可达服务探针通过；Task08 真实检索→导入 smoke 已通过，Task10 真实连续会话仍留待补证。

### 2026-09-20 复核执行结果

- `search_papers.py --base-url http://127.0.0.1:18080 --query agent --years 2024 --limit 3`：退出码 `0`；返回 `partial` 和 3 个真实候选，候选含 USENIX 详情页和摘要状态。
- 明确不可达探针 `--base-url http://127.0.0.1:9`：退出码 `2`；中文错误、无 traceback。
- `pytest tests/test_skill_carryover.py -q`：退出码 `0`，`4 passed`；两份 IDE 脚本 Ruff 与 `py_compile` 均退出码 `0`。
- 本轮修复 `.codebuddy/skills/usenix-paper-assistant/scripts/search_papers.py`、`download_paper.py` 的不可达提示，使其显示实际 base URL；更新 Task13 测试断言。随后第三个真实候选导入返回 `indexed`，Task13 保持“Task08 真实 smoke PASS、Task10 真实连续会话待补证”。

### Task10 真实会话 smoke（2026-09-20）

- 沙箱外健康探针 `GET http://127.0.0.1:18080/api/health`：退出码 `0`，HTTP `200`，服务可访问。
- 第一轮 `POST /api/conversations/messages`，内容“使用 usenix-catalog-orchestration 搜索 agent 论文”：SSE 返回 `skill_intent` completed 与 `intent`，`skill=usenix-catalog-orchestration`、`source=rule`；未调用下载接口。随后 `GET /api/conversations/7e957237e2c44a25a752242efc301ee1/messages` 为 HTTP `200`，但助手仍 `streaming`、`last_event_seq=7`，Ollama 生成约 60 秒未收口。
- 第二轮“就下载第一篇吧”未执行：该请求可能触发真实论文下载/外部网络/知识库写入，平台安全门禁拒绝；在“不下载论文”约束下不绕过。故只记录首轮真实 Skill 命中，不能将 Task10 标记为真实连续两轮 PASS。
- 当前结论：Task10 离线合同/定向链路 PASS；真实 sticky tool smoke BLOCKED（模型未收口，且第二轮下载语义需要无副作用测试 seam）。

### Task10 无副作用第二轮补证（2026-09-20）

- 第二轮改用“继续搜索第一篇吧”，SSE 返回 `intent`，其中 `skill=usenix-catalog-orchestration`、`source=sticky`、`confidence=1.0`；真实 API 已观察到 Skill 粘性沿用，且未执行下载。
- 模型生成阶段随后保持 `streaming`，精确文本“就下载第一篇吧”对应的真实工具调用仍待无副作用 seam 或用户明确授权的受控环境；不将其伪造为完成。

## 变更日志

- 2026-09-20：按用户确认把 032.1 未完成事项纳入 032，保留源 Task 链接和完成门禁。
- 2026-09-20：审计并补齐 IDE Skill `source_page_url` 回退；修复错误提示固定端口问题；当前服务真实检索返回 3 个 USENIX 候选，第三篇通过既有安全导入链 `indexed`，重复/失败候选分别返回 409/424；Task10 仍需真实连续两轮会话证据。
