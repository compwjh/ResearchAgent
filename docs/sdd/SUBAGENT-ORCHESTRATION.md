# 子代理编排与执行（Subagent Orchestration）

> 本文件是 `AGENTS.md` 的外链文档，**只在需要分派子代理 / 配置子代理 / 排查子代理异常时按需加载**。
> `AGENTS.md` 只保留三条致命约束的摘要与本文链接，不复述细节。
> 模型档位不在此处，单点维护于 `MODEL_REGISTRY.md`。

## 范式一：Agent 模式（首选，带 tools / skill / 独立上下文 / 可编排）

本项目已接入 CodeBuddy 的 agent 框架，把角色固化为**子代理**，而非临时拼 prompt：

- **本地模型注册**：`.codebuddy/models.json`（Ollama 走 `http://localhost:11434/v1/chat/completions`，`apiKey: ollama`，`supportsToolCall` 按实测填）。
- **角色子代理**：`.codebuddy/agents/<role>.md`，YAML front matter 支持：
  - `tools`（function call 白名单，如 `Read, Grep, Glob, Bash`）
  - `skills`（启动时自动加载的技能，如 `verification-loop`）
  - `model`（可为每个角色绑定不同模型，含本地模型 ID）
  - `permissionMode` / `maxTurns` / `memory` / `mcpServers` 等
- **技能库**：`.codebuddy/skills/<name>/SKILL.md`，沉淀角色 checklist、模板与行为边界，供 agent 自动加载。
- **编排**：支持显式调用（"使用 tester 子代理验收"）、自动委派（description 写 `Use PROACTIVELY`）、Agent Teams 并行、后台任务、按 `agentId` 恢复。

### 编排方式（多角色协同）

- **编排顾问 agent**：`.codebuddy/agents/planner.md`，按 SDD 门禁顺序产出「分派计划」（每角色的任务、最小上下文、产出路径、行为边界）。
- **⚠️ 子代理拿不到 `Agent`/`Task` 分派工具**：即使 front matter 写 `tools: ..., Agent` 也不生效（planner 实际只拿到 Read/Grep/Glob）。因此**嵌套分派不可行，编排由主会话执行**：planner 出计划 → 主会话用 Task 逐个分派 → 汇总。
- 已铺开的角色 agent：`doc-updater`、`architect`、`planner`、`backend-dev`/`frontend-dev`、`backend-reviewer`/`frontend-reviewer`、`backend-tester`/`frontend-tester`、`tester`；配套技能 `tdd-workflow`、`coding-standards`、`verification-loop`、`security-review`、`regression-guard`、`strategic-compact`、`backend-patterns`、`frontend-patterns`。
- 调用方式：`Task` 工具的 `subagent_name` 指定角色名（如 `backend-tester`）；也可自然语言显式调用（"使用 architect 子代理评审"）或靠 `description` 里的 `Use PROACTIVELY` 触发自动委派。
- 也可用 **Agent Teams** 做并行编排（`team_create` + 具名成员 + `send_message` 通信）。

## 实测约束（高频踩坑，配置子代理前必读）

- **⚠️ 子代理工具集不含 `Write`（2026-09-12 实测：`Tool Write not found in agent`）**：即使 front matter 的 `tools` 写了 `Write` 也不生效。因此**新建文件只能用 `Bash` heredoc**，且定界符必须加单引号（`'PYEOF'`），文件较大时分多次 `cat >>` 追加，创建后必须 `Read` 读回校验。
  - 已写入 `backend-dev.md` 的正文；新增/修改角色 agent 时应同步该说明，避免子代理反复尝试 `Write` 而浪费轮次。
- **⚠️ `tools` 必须包含 `Bash`**，否则子代理无法落盘报告与进展日志（只读子代理需由架构师代落盘）。
  - 创建/修改 agent 定义时必须复核：所有角色 agent 都被要求写 `.codebuddy/agent-logs/spec-<NNN>/task-<TT>/<role>/` 日志。曾漏配 `doc-updater.md`（只有 Read/Grep/Glob/Edit），实战中无法写日志。
- **`Task` 工具调用内置 `code-explorer` 时是只读的**（无 Bash/写文件），无法落盘报告；调用自定义 agent（如 `tester`）时其 `tools` 才生效，可用 Bash 真实执行命令与写文件。
- **新建的 agent 文件即时生效**，无需重启。
- **⚠️ 子代理分派可能撞账号级频率限制（429）**：报 `usage exceeds frequency limit` 并给出重置时间时，可**改用其它模型档位继续**（分派时覆盖 `model` 参数），不必等待重置。
  - **这是临时绕过手段，不是规范**：一旦因 429 临时改档，**不得**回头把该档位写进 `AGENTS.md` 或提交信息里当作正式配置（2026-09-12 曾因此把临时档位 `hy3` 固化成"全部角色统一"，属事故，已还原）。临时改档只改 `.codebuddy/agents/<role>.md` 的 `model` 字段，并在任务结束后还原。
- **本地模型驱动子代理较慢**：实测单次分派 3–8 分钟（27B 量化模型），属正常成本，不要误判为卡死；追求速度可改用 `qwen3.5:9b`（需先在用户级 `models.json` 注册）。
- **子代理失败时先查历史日志**：`.codebuddy/agent-logs/spec-<NNN>/task-<TT>/<role>/`。若以前有详细日志而本次连第一条都没写，说明是执行慢/超时，而非配置错误（配置错误会直接报 `model not found`）——可避免重复排查已解决的配置问题。

### 模型字段的三条硬约束

1. **`model` 只接受已注册的模型名**，填自定义 ID 会报 `Subagent model config is invalid! Model ... not found`。
   - 框架读取**用户级 `~/.codebuddy/models.json`**；项目级 `.codebuddy/models.json` 的自定义 ID 未被识别。
   - 为不同角色分配不同本地模型，需先在用户级 `models.json` 注册（属用户全局配置，改动前须经用户同意）。
2. **`model` 名不能含 `/` 的命名空间 ID**：实测 `oamazonasgabriel/qwen3.8-27b:q4-km-32gbGPU` 虽已注册仍报 `not found`；改用不含 `/` 的即正常。
   - 补充：`model` 名带 `-q4` 这类后缀是可以的。此前"只有无后缀名能调度"是误判，真实根因是注册名与 agent 里写的字符串不一致。细节见 `docs/sdd/retro/2026-09-01-subagent-model-naming.md`。
3. **模型档位的唯一真源是 `.codebuddy/agents/<role>.md` 的 `model` 字段本身**，`AGENTS.md` 不再复述型号——任何"两处必须逐字一致"的要求都会导致临时改动被误固化为规范。

## 子代理"思考不可见"的解决方案

子代理的推理过程默认不对外可见（尤其本地模型会先长篇 thinking 再输出）。解决办法：

- **进展日志落盘（已落地，推荐）**：各角色 agent 的 system prompt 要求**每完成一步就追加写日志**到 `.codebuddy/agent-logs/spec-<NNN>/task-<TT>/<role>/<时间戳>.md`，格式为 `[时间] 步骤 N / 观察 / 判断 / 下一步`。外部可用 `tail -f <日志路径>` **实时观察思考轨迹**。
- 日志属运行产物，已在 `.gitignore` 忽略；回传摘要必须给出日志路径。
- **线上子代理禁止常态轮询日志（长期规则）**：线上模型子代理正常运行时，主 Agent 不得为了查看进度而反复读取其进展日志、轮询工作树文件或检查文件时间；应使用 Agent 等待机制，等待子代理主动返回最终结果。只有出现明确超时、报错、长时间无返回、需要定位阻塞，或用户明确要求查看过程时，才按需读取一次相关日志进行诊断。该限制不取消子代理自身的日志落盘义务；本地模型任务仍可依据其较慢且不稳定的运行特征自适应检查。
- 备选：Ollama 的 `/v1` 接口思考内容在 `reasoning_content` 字段，需框架透传才可见；纯 `ollama run` 场景可用 `--hidethinking` 反向关闭思考输出。
- 若需更强的实时交互，可试用 Agent Teams（具名成员 + `send_message` 主动汇报进度）。

## 范式二：`ollama run` 裸调用（无 tool-call 场景的降级手段）

纯文本产出、不需要工具调用时可用此方式：

- **调用方式**：优先 `ollama run <model> < /path/to/prompt.md`（文件喂入 + 前台流式），可实时观察思考；后台落盘用 `curl -s http://localhost:11434/api/generate -d '{"model":..,"prompt":..,"stream":false}'`（注意用独立 python 脚本写 body，避免 shell 吞掉花括号导致 `missing request body`）。
- **上下文压缩原则**：只给子模型完成本角色所需的**最小信息**，不要塞整项目。
- **针对中小本地模型的 prompt 写法（关键，踩坑总结）**：
  - ❌ 只给"节选 + 注释" → 子模型被迫凭空造，产出占位骨架（如 `...勿动其内部...`），不可用。
  - ❌ 给"完整大文件原文" → 输入 token 暴涨，量化 27B 在超时内无输出（280s timed out）。
  - ✅ **增量片段式 prompt**：只描述改动点 + 关键上下文行，要求输出**最小代码 diff/片段**（而非完整文件），由架构师 apply 并校验。
- **架构师必须落地校验**：子模型产出代码片段后，由架构师读取真实文件做最小增量修改、跑 lint/语法校验，不直接套用占位或覆盖现有逻辑。
- **查看思考**：前台 `ollama run` 流式输出混有终端转义符，但能看清推理过程与质量；需干净产出落盘时用非流式 curl。

## 相关文档

- 模型清单与角色档位：`MODEL_REGISTRY.md`（唯一真源）
- 工具调用实测对比：`TOOLCALL_BENCHMARK.md`
- 角色上手与最小上下文：`ROLE-ONBOARDING.md`
- 历史复盘：`retro/2026-09-01-subagent-model-naming.md`、`retro/2026-09-02-subagent-timeout-mlx.md`
