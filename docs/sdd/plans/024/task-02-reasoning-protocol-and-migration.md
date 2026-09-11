# Task 02：冻结推理能力、数据清理与事件协议

> 关联：[Spec 024](../../specs/024-visible-reasoning-controls.md) ｜ 索引：[README](./README.md)
> 依赖：Spec024 用户确认；被依赖：Task03、Task04；当前状态：待执行

## 一句话目标

在不写业务实现的前提下，用真实 qwen3.8:27b 接口和当前数据库结构验证五档推理可行性，并把一次性清理、schema 增量和 SSE 顺序冻结成可测试合同。

## 当前证据

- 2026-09-11 已通过局域网 Ollama 实测确认 qwen3.8:27b-mlx、qwen3.8:27b 与 qwen3.5:9b 存在。
- task1245 日志显示默认 xhigh 推理约产生 800 个不可见 token 后才出现正文。
- backend/app/chat/application/chat_graph.py 当前只读取正文 content。
- backend/app/platform/ollama.py 已有 reasoning 参数接缝，应扩展而非新增客户端。
- Spec022 数据库包含项目、会话、消息、处理步骤、记忆分析和记忆证据；清理旧会话时必须保留项目和长期记忆。

## 前置门禁

- Spec024 状态已转为已确认。
- 记录当前 commit、工作树、数据库 schema 版本及各相关表行数。
- 数据探针只能操作临时数据库；不得在本 Task 删除真实用户会话。

## 思维链（执行阶段、观察点与决策依据）

1. 读取现有模型适配器和会话 schema，列出可复用接缝。
2. 对真实 Ollama 逐档发送最小请求，记录 off、low、medium、high、xhigh 的接受情况和响应字段。
3. 在临时数据库演练旧会话清理，核对保留表行数与引用置空。
4. 用合同测试冻结事件偏序：reasoning_started → reasoning_delta* → reasoning_completed → token* → done。
5. 任一档位无法可靠表达或清理会删除长期数据时，给出 NO-GO，不进入 Task03。

## 子任务与子 Agent

- architect：只读调研、协议冻结、Go/No-Go。
- backend-tester：运行真实能力探针和临时数据库迁移测试。
- 不分派 backend-dev；本 Task 不写业务代码。

## 完整分派 Prompt

~~~text
角色：architect，使用 Spec024 执行配置中的开发主管模型。
目标：验证并冻结 Spec024 的推理能力、数据清理和 SSE 合同，不实现业务代码。
只需读取：
1. docs/sdd/specs/024-visible-reasoning-controls.md
2. docs/sdd/plans/024/task-02-reasoning-protocol-and-migration.md
3. backend/app/platform/ollama.py
4. backend/app/chat/application/chat_graph.py
5. backend/app/chat/application/chat_runner.py
6. backend/app/api/routes_conversations.py
7. 当前会话/记忆 repository 与迁移定义
允许修改：
- docs/sdd/plans/024/artifacts/task-02/protocol-report.md
- tests 中仅限临时合同探针；若无需保留则不修改测试文件
禁止：
- 修改 backend/app 或 frontend 业务代码
- 删除真实数据库数据
- 修改 Ollama 部署、模型或 .env
- reset、stash、clean、push、合并 main
完成后的可观察状态：
- 五档能力矩阵有真实请求证据
- 清理保留矩阵有临时数据库证据
- schema 与事件合同无歧义
- 给出 GO 或 NO-GO
必须验证：
- 对局域网 Ollama 的最小五档探针
- 临时数据库迁移/回滚探针
- git diff --check
结果写入：
docs/sdd/plans/024/artifacts/task-02/protocol-report.md
固定返回字段：
结果状态和摘要；改动文件；测试命令、退出码和结果；产物路径；决策依据；风险与阻塞；主 Agent 后续动作；开始、结束和总耗时；可用时记录模型、token 和工具调用统计。
信息不足时标记阻塞，不得自行扩展设计。
~~~

## 主 Agent 校验

- 读回报告和实际 diff，确认没有业务代码改动。
- 重跑最小模型能力探针，核对真实响应字段而非仅看模型声明。
- 在临时数据库核对项目、记忆、SystemRule、知识库均未被清理。
- 确认事件合同兼容现有 token/done/error，不建立第二条流式链路。

## 实时监控

- 线上子 Agent 正常运行时只等待其主动返回。
- 真实 Ollama 探针可观察服务日志，但不得持续轮询；超时后只读取一次相关时间段。

## 验收标准

- 五档中每档的支持/不支持均有真实证据；不支持时定义 409 且模型未被调用。
- 清理合同明确列出删除、置空和保留表。
- 临时迁移中任一步失败会事务回滚。
- 事件顺序、终态不可逆和关闭推理行为可写成自动测试。

## 风险、停止条件与回滚

- 五档不被当前模型模板接受：NO-GO，修订 Spec 后再确认。
- 现有外键无法在保留 MemoryRecord 的同时删除会话：NO-GO，先调整清理设计。
- 本 Task 仅新增文档/合同测试，回滚为撤销本 Task 文件，不触碰用户数据。

## 产出物

- artifacts/task-02/protocol-report.md

## 执行结果

待执行后填写。

## 变更日志

- 2026-09-11：根据共同理解创建 Go/No-Go 协议任务。
