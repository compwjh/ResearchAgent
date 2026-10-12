# Spec 016 — 冻结实现协议（预实现合同）

版本：protocol/v1。协议评审者：protocol_review；角色：architect；模型：gpt-6-luna xhigh；分派方式：collaboration.spawn_agent。来源为 main 上 Spec016、Task02–06 与本次架构评审。此文件是 Task03–06 实现者的唯一机器接口合同。协议变化须先修改本文与相关 Prompt，再提升协议版本；禁止在代码中临时加字段。

## 0. 不变量与执行门禁

- Git 跟踪的 Task Markdown 是定义与持久状态唯一事实源。SQLite 是同机共享、可重建的运行缓存；账本和原始日志放在主工作树根下的 .sdd/runtime，保证所有 linked worktree 使用同一个数据库。主工作树根由 git worktree list --porcelain 第一项确定；common-dir 仍用于仓库身份与锁文件。
- Task02 云端 preflight 报告 7/7。tester 后续确认 Python 3.9 CLI、pytest、ruff 环境可用。Task02 的 CodeBuddy 真实协议验收尚未执行，保持 deferred；不得声称通过。
- 用户授权先完成云端 CLI 与测试，CodeBuddy 验收留本地。该授权足以继续 Task03/04；Task02 与 Spec016 的完整验收状态仍未完成。计划需为 Task03 写明云端阶段授权和 preflight 证据 gate，不得用“Task02 完成”伪装依赖已满足。
- 不执行 push、merge、reset、stash、clean，不自动删除或回滚用户文件。成功实现提交用新的临时 Git index 和精确路径白名单构造 candidate；真实 index 仅在第 6 节规定的成功提交后，对 committed_paths 做限定协调。
- Python 3.9+ 标准库实现；产品业务数据库和 backend/app/services/task_store.py 不在范围。隐藏推理不记录。

## 1. Task Markdown 机器块与 schema v1

一个可运行 Task 文档必须各含且仅含一个 metadata 块和一个完整 prompts 块，标记独占一行；metadata 块内容必须是 UTF-8 JSON，禁止 YAML/TOML、重复 key、注释、尾逗号和未知字段。

~~~text
<!-- sdd-task-meta:v1:begin -->
{ ... JSON object ... }
<!-- sdd-task-meta:v1:end -->

<!-- sdd-task-prompt:v1:begin -->
... 一个或多个可原样分派的完整子 Agent Prompt ...
<!-- sdd-task-prompt:v1:end -->
~~~

schema v1 的必填字段、类型与约束如下。metadata additionalProperties=false；唯一扩展键见 migration_state。

| 字段 | 类型 | 约束 |
|---|---|---|
| schema_version | integer | JSON 数值必须是整数 1；拒绝 true、1.0、字符串 "1"、缺失和任何其他版本号 |
| task_id | string | 全仓唯一，格式 spec-NNN-task-NN |
| spec_id | string | 恰为三位数字 |
| title | string | 去首尾空白后非空 |
| status | string | pending、blocked、completed、cancelled |
| priority | integer | 默认 100；值越大优先级越高 |
| created_at | string | 带 Z 或 UTC offset 的 ISO 8601 时间，用于稳定排序 |
| depends_on | array[string] | 无重复 Task ID；不得成环 |
| required_gates | array[string] | 稳定 spec-qualified gate ID，格式 `spec-NNN.<lowercase-kebab-case-name>`；领取方必须逐项从 Task 的 canonical view 验证满足 |
| agent_role | string | 逻辑角色名；不得硬编码 IDE API 或当前模型 |
| required_capabilities | array[string] | read/edit/shell/subagent 等能力名 |
| allowed_paths | array[string] | 仓库相对 POSIX 路径；精确路径或目录前缀；拒绝 glob、绝对路径、空段、..、反斜线和越界 symlink |
| worktree | object | 必须有 path、branch、mode、base_rule；v1 mode=per_spec、base_rule=explicit_commit，path 为 .worktrees/spec-NNN |
| max_attempts | integer | 默认 3，必须 >=1 |
| prompt_version | integer | 必须 >=1；Prompt 变化时递增 |
| return_schema | string | v1 固定 sdd-run-result/v1 |
| expected_artifacts | array[string] | 仓库相对路径；每个路径还须在 allowed_paths 内 |
| validation_commands | array[string] | 每项 POSIX shlex 参数字符串；用 shlex.split(posix=True) 拆 argv，以 shell=false 执行；不支持 shell 表达式、管道、重定向或展开 |
| migration_state | string | 可选；仅 legacy 对账使用，unverified 或 verified；缺省仅用于新 Task。unverified 永不可领取 |

worktree 对象精确为 {"path": ".worktrees/spec-NNN", "branch": "feature/spec-NNN-<slug>", "mode": "per_spec", "base_rule": "explicit_commit"}。Task 中无其他字段可隐式扩大路径、命令或角色范围。所有路径读写前做 repo/common-dir 根 containment 检查；每个 symlink resolve 后仍须位于授权根内，否则失败关闭。

最小 metadata 样例：

~~~json
{
  "schema_version": 1,
  "task_id": "spec-016-task-04",
  "spec_id": "016",
  "title": "实现 SQLite Task 账本",
  "status": "pending",
  "priority": 100,
  "created_at": "2026-10-11T00:00:00Z",
  "depends_on": ["spec-016-task-03"],
  "required_gates": ["spec-016.cloud-stage-authorized"],
  "agent_role": "backend-dev",
  "required_capabilities": ["read", "edit", "shell"],
  "allowed_paths": ["scripts/sdd_tasks", "tests/sdd_tasks"],
  "worktree": {
    "path": ".worktrees/spec-016",
    "branch": "feature/spec-016-portable-task-ledger",
    "mode": "per_spec",
    "base_rule": "explicit_commit"
  },
  "max_attempts": 3,
  "prompt_version": 1,
  "return_schema": "sdd-run-result/v1",
  "expected_artifacts": [],
  "validation_commands": ["python3 -m unittest tests.sdd_tasks.test_store"]
}
~~~

schema_version 验证使用严格类型检查：解码后要求 type(value) is int 且 value == 1；Python bool 虽是 int 子类仍必须拒绝，1.0 和 "1" 也拒绝。缺失、错误类型、值不是 1 均以稳定的 unsupported_schema_version 错误失败关闭，不降级解析。

TaskDefinition 是 frozen dataclass，精确字段为：
~~~python
metadata: Dict[str, Any]
prompt: str
path: pathlib.Path
task_hash: str
prompt_hash: str
~~~
metadata 保留通过验证的 JSON object；task_id/status 等从 metadata 读取，避免复制后不一致。prompt_hash = SHA-256(marked prompt body 的精确 UTF-8 字节)。task_hash = SHA-256(UTF-8 canonical JSON(metadata 去除 status 与 migration_state，sort_keys=true、ensure_ascii=false、separators=(',', ':')) + LF + prompt_hash 的 ASCII hex)。此算法让 completion 改 status 不产生漂移；Prompt、allowed paths、依赖等定义字段变化会漂移。所有 hash 为 64 个小写十六进制字符。

Task Markdown 人读章节顺序固定：目标、当前证据、前置门禁、执行阶段/决策依据、分派 Prompt、子代理返回后处理、监控、验收、风险/回滚、产出、执行结果、变更日志。模型私有思维链不属于协议字段。

## 2. Prompt 变量

Prompt 块可含多个分派段；整块作为不可拆分的 canonical template。唯一替换项为 {{RUN_ID}}, {{WORKTREE}}, {{BASE_COMMIT}}, {{RESULT_PATH}}, {{EVENT_PATH}}。渲染器拒绝未知变量、缺少值、未渲染残留；只替换以上字面 token，不运行模板语言或读取环境变量。Prompt hash 是模板 hash；RenderedPrompt.rendered_hash 是替换后 bytes 的 hash。path 变量必须是相对路径或 worktree path，不得将绝对个人路径、credential、环境变量值写入 Prompt。

### 可解析的分派 Prompt 标签

Prompt marker 内容可用两种完整表示：其一，整个 marker body 是一个 plain-text 分派 Prompt；其二，body 仅由一个或多个独立 fenced `text` 或 `prompt` 代码块组成，每块是一个完整分派 Prompt。fenced 模式的块外只允许空白；禁止混合未包围文本和代码块。对每个完整 Prompt 按以下顺序各解析且仅解析一行标签，标签大小写、空格和冒号固定，冒号后同一行必须有非空值。标签值之后可有多行补充，续行归属到下一个固定标签前一节：

1. Role:
2. Read:
3. Allowed paths:
4. Forbidden:
5. Validation:
6. Result:
7. Return schema:

每节的首行值和本节续行拼接后都必须非空白；因此一整句或单字段 Prompt 不合法。缺标签、重复标签、乱序、空值、半截围栏或不完整 fenced 块均拒绝 parse_task；弱调度器不得补写或猜测。

- Role 的首行去首尾空白后必须精确等于 metadata.agent_role。角色不同的分派需拆成独立 Task，避免绕过单一逻辑角色定义。
- Read 的值必须列出实际读取文件/目录，或者精确写 none 表示无读取依赖；不得写“自行判断”“相关文件”之类开放范围。
- Allowed paths 的首行值必须是 JSON 字符串数组，解析后与 metadata.allowed_paths 顺序和值完全相同。后续说明不能扩大范围；metadata 是唯一授权来源。
- 机器校验要求 Forbidden 内容非空，且去首尾空白后不能精确为 `none`、`无` 或 `空`（`none` 忽略大小写）；不尝试从自由文本推断动作语义。需求/技术评审须确认其写出了至少一项明确禁止动作。
- Validation 的首行值必须是 JSON 字符串数组，解析后与 metadata.validation_commands 完全相同；当 metadata.validation_commands 为空数组时，首行必须精确写 none。不得在续行新增未登记验证命令。
- Result 必须包含字面占位符 {{RESULT_PATH}}，并说明写入完整结果 JSON。
- Return schema 首行必须精确等于 sdd-run-result/v1，metadata.return_schema 也必须是该值。

最小有效 Prompt（metadata.agent_role 为 backend-dev；metadata.allowed_paths 为 ["scripts/sdd_tasks"]；metadata.validation_commands 为 ["python3 -m unittest tests.sdd_tasks.test_documents"]）：

~~~text
Role: backend-dev
只执行该 Task 指定的实现切片。
Read: ["docs/sdd/TASK-PROTOCOL.md", "scripts/sdd_tasks/__init__.py"]
Allowed paths: ["scripts/sdd_tasks"]
不得改业务代码、tracked Task、Git 历史或 allowed paths 之外的内容。
Forbidden: 不得 push、merge、reset、stash、clean，不得伪造测试结果。
Validation: ["python3 -m unittest tests.sdd_tasks.test_documents"]
运行后记录实际命令、退出码与测试数量。
Result: 将完整 sdd-run-result/v1 JSON 写入 {{RESULT_PATH}}；未运行的测试写 not_run，不得声称通过。
Return schema: sdd-run-result/v1
只返回简短交接摘要和结果路径。
~~~

示例中的描述性续行可多行，但不得与 metadata 已冻结的角色、路径、验证命令和结果路径产生冲突。

## 3. sdd-run-result/v1 JSON

result.json 与 run 摘要内的 JSON marker 必须有且只有以下根字段，拒绝未知字段；所有路径为 repo-relative POSIX path。数组可为空，不允许缺字段。

~~~json
{
  "schema": "sdd-run-result/v1",
  "run_id": "UUID",
  "task_id": "spec-016-task-04",
  "task_hash": "64 lowercase hex",
  "prompt_hash": "64 lowercase hex",
  "outcome": "succeeded",
  "summary": "实际完成内容的一句话摘要",
  "changed_files": [
    {"path": "scripts/sdd_tasks/store.py", "change": "modified", "additions": 3, "deletions": 1, "sha256": "64 lowercase hex"}
  ],
  "artifacts": [
    {"path": "docs/sdd/runs/016/task-04/UUID.md", "kind": "run-summary", "sha256": "64 lowercase hex", "included_in_commit": true}
  ],
  "commands": [
    {"argv": ["python3", "-m", "unittest", "tests.sdd_tasks.test_store"], "status": "executed", "exit_code": 0, "duration_ms": 40, "summary": "1 test passed"}
  ],
  "tests": [
    {"name": "tests.sdd_tasks.test_store", "outcome": "passed", "exit_code": 0, "summary": "1 test passed"}
  ],
  "decisions": [{"decision": "使用显式事务", "evidence": "双进程 fixture 只有一个领取成功"}],
  "risks": [],
  "blockers": [],
  "main_agent_actions": [],
  "started_at": "2026-10-11T00:00:00Z",
  "ended_at": "2026-10-11T00:01:00Z",
  "duration_ms": 60000,
  "model": null,
  "token_usage": {"input": null, "output": null, "total": null, "source": null},
  "tool_call_count": null,
  "log_paths": [".sdd/runtime/runs/UUID/events.jsonl"]
}
~~~

字段规则：outcome 仅 succeeded/failed/blocked；change 仅 added/modified/deleted/renamed；数组子对象也拒绝未知字段。changed_files.additions/deletions 为非负整数或 null，sha256 可空（deleted path）；artifacts.included_in_commit 为 boolean 或 null；commands.status 为 executed/skipped，executed 时 exit_code 必须是真实 int，skipped 时 exit_code=null 且 summary 写原因；tests.outcome 仅 passed/failed/skipped/not_run，未运行绝不可写 passed。duration_ms 为非负整数；model、token_usage 的各数值、tool_call_count 可以 null 且不得估算；时间须带时区且 ended_at >= started_at。log_paths/changed_files/artifacts 的路径不得绝对化。成功结果还必须通过 task_id/run_id/hash 对照、验证命令、产物存在、工作区 allowed-path diff 和 commit 检查；JSON 或文本中的“success”不能替代这些证据。

结果和摘要递归拒绝敏感 key/value：password、cookie、Authorization、Bearer、API/access/client secret 等；token_usage 是允许字段但只存数值/null。拒绝 Unix home、macOS /Users、Windows drive 下的个人绝对路径、绝对工作目录、完整原始 stdout/stderr。命令仅存实际执行 argv 的安全版本、真实退出码和经脱敏短摘要；未执行命令明确 status=skipped。发现敏感内容时不得写 Git 摘要或成功提交，只留下本地阻塞证据。隐藏推理、凭证和绝对路径不得进入 Git。

Run summary 的敏感内容检查覆盖完整 Markdown 文件，包括两个 JSON marker 块以外的人读说明；marker 外文本不是绕过检查的通道。执行 Task 的解析器必须递归检查 metadata JSON 与完整 Prompt body，拒绝其中的敏感字段和值、个人绝对路径及环境变量值。Task08 对账须保留既存 legacy Task 的人读历史正文，不自动改写或仅因历史正文出现旧路径而阻止迁移；Task06 的 journal/提交前检查必须扫描本次新增的文档 diff，禁止新加入的敏感内容或绝对个人路径，覆盖新建文档及旧文档新增正文。

## 4. 镜像、rebuild 与 SQLite

Task metadata.status 是唯一权威持久状态；人类显示映射固定为 pending=待执行、blocked=阻塞、completed=完成、cancelled=取消。Task 正文顶部人读状态行、对应 spec 表和 plans/NNN/README 表均是镜像。镜像通过 metadata.task_id 唯一定位。跨 worktree 同一 Task ID 的定义 hash（不含 status）若不同，rebuild/doctor/claim 一律失败；不能按时间或路径新旧猜测定义。相同 hash 的副本由 metadata.worktree.path 指定 canonical worktree：将该路径相对主工作树根解析，并必须在 git worktree list 注册表中精确找到。该注册 worktree 存在且包含该 Task 时，它是 status 与三处镜像的唯一权威副本；其状态/镜像须恰命中且一致，否则 doctor/claim/complete 失败。其他同 hash 副本可保留旧状态或旧镜像，只输出 stale/non-authoritative 诊断，不阻断领取、不自动修复，也不参与状态写入。若 canonical worktree 不存在或缺该 Task，但同 hash 副本的 status 不同，必须失败并要求人工处理，不能猜测最近版本；若各副本 status 相同，可按同 hash 去重用于只读 rebuild/status，但 claim 必须先按 explicit base 创建/验证 canonical worktree 并校验副本后再执行。metadata.worktree.path 的规范路径不存在时，不能把另一个副本升格为权威。状态更改只写 canonical worktree 的 Task、spec、README 镜像；journal 持久化后才写。Task08 对账后才为 legacy Task 写 migration_state=verified 并转换；migration_state=unverified 永不 claim。migration_unverified 是迁移标记，不是 Task.status。

canonical Task/spec/README 定义文档及其镜像路径的每个路径组件均拒绝 symlink，即使 resolve 后仍在仓库内也拒绝；不得通过 symlink 读取或写入权威文档。该严格规则不扩大到普通 allowed artifact：普通产物继续按 safe-in-root 规则允许解析后仍位于授权根内的 symlink。

### Gate evidence

每个 Task 的门禁只从它自己的 canonical authority worktree view 读取，固定路径为 `docs/sdd/gate-evidence.json`；不得退回主工作树或其他副本。canonical view 用 metadata.worktree.path 相对主工作树根解析，并须在 `git worktree list` 注册表中精确匹配。尚不存在时，先按明确 base 创建并验证该 canonical worktree，再读门禁；不能用 stale/main 副本的门禁满足它。registry 文件本身及其路径组件拒绝 symlink；evidence.path 相对该 canonical view 根解析并须保持 safe-in-root。

registry 根 schema 精确为 `{"schema":"sdd-gates/v1","gates":[...]}`，拒绝未知字段、重复 JSON key、重复 gate_id、坏类型和无效路径/hash。每个 gate entry 精确含 `gate_id`、`status`、`evidence`；gate_id 格式为 `spec-NNN.<lowercase-kebab-case-name>` 且必须以本 canonical view 的 spec_id 开头；status 只允许 `passed`、`pending`、`failed`。evidence 精确含 `path` 和 `sha256`；path 为非空 repo-relative POSIX 路径，sha256 为 64 位小写十六进制并对该 view 下证据文件的原始字节核验。缺失 registry/entry/文件、hash 不匹配或 status 不是 passed 均为未满足；结构无效时返回稳定 gate_evidence_invalid 诊断并失败关闭。只有 ID 前缀与对应 Task.metadata.spec_id 完全相同的 gate 才可匹配；同一全局 satisfied set 可汇总多个 view 的已核验 ID，但调用方必须先对每个候选 Task 的 canonical view 单独验证，不能把另一 view 的事实用于该 Task。

cloud-stage 示例：`spec-016.cloud-stage-authorized` 为 `passed`，证据指向 `docs/sdd/plans/016/artifacts/recovery-context.md`，SHA-256 为 `a5eb23aa8907ba0fcb6fc0c2b66615a47bf7100405381598a9798b5bff24b725`。该证据只证明用户授权云端继续；它不满足/暗示 `spec-016.task-02-codebuddy-validated`，CodeBuddy A6 仍须单独证据。

### Spec 状态领取门禁（Task05）

除 Task 状态、依赖、legacy 对账及 required_gates 外，pending Task 只有在其 canonical worktree 的当前 Spec 状态为 `已确认` 或 `实施中` 时才能领取。Task 的 `metadata.spec_id` 决定 Spec；在该 Task canonical worktree 的 `docs/sdd/specs/` 下必须唯一找到以该 spec ID 开头的权威 Spec 文档。不得从主工作树或其他 worktree 读取替代副本。权威 Spec 使用 `## 状态` 下唯一一行 `**当前状态：<state>**`；state 是 `待确认`、`已确认`、`实施中`、`已完成`、`阻塞` 之一，可用一对 Markdown 反引号包裹，并可在 token 后附一个括号内的人读说明，例如 `**当前状态：\`实施中\`（2026-09-08；说明）**`。section 标题必须唯一，当前状态行必须恰有一行；其他历史说明/变更记录允许存在，不参与解析。缺少、重复、格式错误或未知状态均以稳定 Spec 文档错误失败关闭，不猜测状态。

共享 helper `read_spec_status(spec_path: pathlib.Path) -> str` 只解析上述当前状态行；文档缺失/歧义或语法错误抛 `SpecStatusError(ValueError)`，其 `code` 为稳定 `SPEC_STATUS_INVALID`，`path` 指向相对仓库路径。`catalog_status.status(conn)` 对每个 pending Task 在其 canonical Spec 上调用同一 helper；合法但不可领取的状态加入 waiting 原因 `spec_not_claimable:<state>`。`已确认` 与 `实施中` 不增加状态阻塞原因；`待确认`、`已完成`、`阻塞` 均不可领取。

`claim_next` 在公共 claim/workspace 锁内解析每个候选的 canonical Spec，并在 `BEGIN IMMEDIATE` 插入 run 与 lease 前重新读取、解析及核验其状态仍为 `已确认` 或 `实施中`；不得只信任先前 `status` 结果、SQLite 副本或已缓存状态。状态在选择后变成其他合法状态时跳过候选并记录 `spec_not_claimable:<state>`；状态缺失、歧义、语法无效或 canonical Spec 不可读取则失败关闭，不创建 run/lease。此门禁复用现有 A5，不增加用户审批步骤或 metadata 字段。

~~~json
{"schema":"sdd-gates/v1","gates":[
  {"gate_id":"spec-016.cloud-stage-authorized","status":"passed","evidence":{"path":"docs/sdd/plans/016/artifacts/recovery-context.md","sha256":"a5eb23aa8907ba0fcb6fc0c2b66615a47bf7100405381598a9798b5bff24b725"}},
  {"gate_id":"spec-016.task-02-codebuddy-validated","status":"pending","evidence":{"path":"docs/sdd/plans/016/artifacts/recovery-context.md","sha256":"a5eb23aa8907ba0fcb6fc0c2b66615a47bf7100405381598a9798b5bff24b725"}}
]}
~~~

Run summary 路径精确为 `docs/sdd/runs/<spec_id>/task-<task-number>/<run_id>.md`，其中 task-number 是 task_id 的两位序号，路径由 Task ID 与 run ID 推导，不接受摘要正文或调用方另给路径。summary 必须恰有一对 result marker 与一对 metadata marker：

~~~text
<!-- sdd-run-result:v1:begin -->
{ ... sdd-run-result/v1 JSON object ... }
<!-- sdd-run-result:v1:end -->

<!-- sdd-run-meta:v1:begin -->
{ ... sdd-run-meta/v1 JSON object ... }
<!-- sdd-run-meta:v1:end -->
~~~

每个 begin/end marker 必须独占一行且恰出现一次；两块必须闭合、不嵌套、不重叠，每块只含一个 JSON object（JSON 前后可有空白），块外可有摘要说明文本。两块顺序可互换。result 块严格遵守 sdd-run-result/v1。metadata 块必须精确使用以下 schema，拒绝缺失、未知字段、重复 key、错误类型及格式：

~~~json
{
  "schema": "sdd-run-meta/v1",
  "run_id": "UUID",
  "task_id": "spec-NNN-task-NN",
  "task_hash": "64 lowercase hex",
  "prompt_hash": "64 lowercase hex",
  "attempt": 1,
  "ide": "nonempty string",
  "executor_id": "nonempty string",
  "agent_role": "nonempty string",
  "model": null,
  "worktree": ".worktrees/spec-NNN",
  "branch": "feature/spec-NNN-slug",
  "base_commit": "40 or 64 lowercase hex",
  "claimed_at": "timezone-aware ISO 8601 timestamp"
}
~~~

run_id 必须是规范 UUID；attempt 必须是严格整数且 >=1；model 为非空字符串或 null；worktree 是仓库相对 POSIX 路径。两个 marker 的 run_id/task_id/task_hash/prompt_hash 必须逐项一致并绑定当前 claim/Task；attempt、ide、executor_id、base_commit、claimed_at 复制自当前 claim；agent_role、worktree、branch 复制自对应 Task metadata；metadata.model 必须等于 result.model。claimed_at 必须不晚于 result.started_at。导入层另行核验 base_commit 与 Git 历史，不以摘要自证。不得记录 owner、PID、host 或 token，rebuild 的 owner_json 固定为 `{}`。只有 succeeded/failed/blocked 终态结果可由摘要导入；TaskRun.state、started_at、ended_at、duration_ms 分别取 result.outcome、result.started_at、result.ended_at、result.duration_ms；result_doc 取实际 summary 相对路径。error_code 与 error_summary 置 null，不合成诊断；失败原因通过 result.summary 查询。缺少任一 marker、绑定不符或旧格式无 metadata marker 时拒绝导入，不猜测/补造字段。

rebuild 对同 ID 定义 hash 冲突、缺 canonical authority 且状态分歧、缺依赖、环、坏 JSON、canonical 镜像冲突、summary 坏 schema 一律报告并失败；同 hash 同状态正常去重，同 hash 状态分歧按前述 canonical 规则处理。run_id 重复但内容不同也冲突。TaskEvent 原始事件和 lease 只能从仍存在 SQLite 恢复，DB 损坏或删除时不得伪造/重建。

SQLite schema 固定表：schema_migrations(version PK, applied_at)、tasks(task_id PK, source_path, status, priority, created_at, task_hash, prompt_hash, definition_json)、dependencies(task_id, depends_on，联合唯一并均为 FK)、runs(run_id PK, task_id FK, attempt, state, ide, executor_id, owner_json, agent_role, model, worktree, branch, base_commit, task_hash, prompt_hash, claimed_at, started_at, ended_at, duration_ms, result_doc, error_code, error_summary)、events(run_id, sequence，联合 PK，timestamp, event_type, payload_json)、artifacts(run_id, path，联合 PK，kind, sha256, git_status, included_in_commit)、leases(task_id PK/FK, run_id UNIQUE/FK, owner_token, claimed_at, refreshed_at, expires_at)。每 task 最多一个活动 lease；claim 用 BEGIN IMMEDIATE 再检查状态/hash/gates/dependencies/lease，partial unique index 再防竞争。启用 WAL、foreign_keys、busy_timeout。import 不建目录/DB。Schema version 不匹配时停止。

数据库物理路径固定为主工作树根/.sdd/runtime/task-ledger.sqlite3；.sdd/runtime/ 必须被 Git 忽略。rebuild 必须先在临时 DB 完整 parse/validate 所有文档与摘要。目标 DB 已存在时绝不 os.replace/unlink 活动 DB/WAL；持公共维护锁并在现有库用 BEGIN IMMEDIATE 合并 tasks/dependencies/可重建 runs 的单事务，保留 events/artifacts/所有 leases；活动 lease 存在时拒绝 rebuild、不改现有库。运行中 task hash 漂移时拒绝同步该 task/整个 rebuild 并保留原状态。只有目标 DB 确实不存在时，才 fsync staging DB 并 atomic replace 到目标；不自动清理。公共 lock 位于 git common-dir/sdd 下，claim/rebuild/completion 互斥；业务 runtime 内容留在主工作树根/.sdd/runtime。

## 5. 精确 Python API（Python 3.9 类型注解）

错误统一从 API 抛 ValueError 子类；错误消息包含稳定 code 和相对路径/字段；CLI 把 code 放 JSON，不把 traceback 放 stdout。

### documents.py
- TaskDocumentError(ValueError)：属性 code: str, path: pathlib.Path, field: Optional[str]。
- frozen TaskDefinition 字段见上节。
- parse_task(path: pathlib.Path) -> TaskDefinition；读取 UTF-8 并校验 marker、严格 schema_version=1、JSON、Prompt 七标签完整性及与 metadata 的 Role/Allowed paths/Validation/Return schema 一致性、path 与 hash；失败 TaskDocumentError。
- parse_task_text(text: str, path: pathlib.Path) -> TaskDefinition；与文件入口同校验，用于 fixture。

### store.py
- connect(db_path: pathlib.Path) -> sqlite3.Connection；只在显式调用时创建 DB，启用 WAL/FK/busy_timeout/row_factory。
- initialize(conn: sqlite3.Connection) -> None；只建当前版本 schema，拒绝未知版本。
- transaction(conn: sqlite3.Connection, *, immediate: bool = False)；context manager，异常 rollback，成功 commit；claim 必须 immediate=True。
- frozen TaskRun 精确字段：run_id:str, task_id:str, attempt:int, state:str, ide:str, executor_id:str, owner:Dict[str, Any], agent_role:str, model:Optional[str], worktree:str, branch:str, base_commit:str, task_hash:str, prompt_hash:str, claimed_at:str, started_at:Optional[str], ended_at:Optional[str], duration_ms:Optional[int], result_doc:Optional[str], error_code:Optional[str], error_summary:Optional[str]。

### catalog.py
- discover_worktrees(repo_root: pathlib.Path) -> Tuple[pathlib.Path, ...]；使用 git worktree list --porcelain 与 git common-dir，不由 cwd 猜根。
- frozen RebuildReport 字段 tasks:int, runs:int, deduplicated:int, database:pathlib.Path。
- rebuild(db_path: pathlib.Path, repo_root: pathlib.Path) -> RebuildReport；任何冲突抛 CatalogError，原 DB 不变。
- status(conn: sqlite3.Connection) -> Dict[str, Any]；keys 为 eligible, waiting, running, blocked, completed, diagnostics；未 rebuild 时给稳定错误。
- load_satisfied_gates(task:TaskDefinition, repo_root:pathlib.Path) -> Set[str]；解析该 Task 的 canonical worktree 中固定 `docs/sdd/gate-evidence.json`，只返回证据存在且 hash 匹配的 passed ID；canonical view 未注册时失败，调用方须先创建/验证它。汇入 claim_next 的集合只含从各候选自身 view 核验的 spec-qualified IDs。

### selection.py / leases.py
Run state 只存在账本：claimed -> running -> succeeded/failed/blocked/abandoned；succeeded 仅 journal complete 后写入，abandoned 仅 owner 已死且 lease 过期后可写。失败 run 终态，重试创建新的 run/attempt；Task 持久状态不会写 running/claimed。Task.status 只允许 pending -> completed/blocked/cancelled、blocked -> pending/cancelled；completed/cancelled 除经人工评审更正文档外为终态。
- frozen OwnerIdentity 字段：executor_id:str, host_id:str, pid:int, process_started_at:str, token:str。token 只在 common-dir 本地库，不进 Task Markdown/Git/result。
- `next --claim` 必须显式提供 `--owner-pid <positive-int>`，其值是持久执行器进程 PID；不得使用即将退出的 CLI 子进程 PID。CLI 只在能读取该 PID 的 host 与 process-start identity 并确认进程存活时领取；恢复时同样按 host/PID/start-time 核验，无法确认即 fail-closed。
- frozen Claim 字段：task:TaskDefinition, run_id:str, attempt:int, ide:str, owner:OwnerIdentity, claimed_at:str, expires_at:str, worktree_path:pathlib.Path, branch:str, base_commit:str, task_hash:str, prompt_hash:str, state:str, recovery_of:Optional[str]。claim 不含 rendered Prompt；Task06 生成其路径/hash。fresh claim 的 recovery_of=null；Task05 过期 owner 恢复指向 abandoned run，Task06 failed partial 恢复指向符合本节规则的 failed run。
- claim_next(conn, candidates: Sequence[TaskDefinition], satisfied_gates: Set[str], *, workspace_snapshots: Mapping[str, WorkspaceSnapshot], ide:str, owner:OwnerIdentity, now:str, lease_minutes:int=120) -> Optional[Claim]；调用方在 common claim/workspace lock 内逐候选解析 canonical worktree view，校验 registry/gates 并为 fresh Task 准备 clean snapshot；partial recovery 则加载其原 before snapshot 并验证当前 dirty 仍符合恢复范围，`workspace_snapshots[task_id]` 必须提供该原 before snapshot（不得提供新的 dirty 快照充当基线）。BEGIN IMMEDIATE 内按恢复优先、priority desc、created_at asc、task_id asc 重验 catalog hash/status/dependency/gates/lease，原子插入 run+lease 和 `workspace_snapshot` 事件（恢复时还插入 `recovery_claim` 事件），之后才可返回 Claim；快照未持久化不得返回 claim。无任务返回 None，不改 Task。CLI 再调用 status(conn) 生成不可领取原因矩阵。
- refresh_lease(conn, run_id:str, owner_token:str, *, now:str, lease_minutes:int=120) -> str；仅 owner 匹配且未过期时刷新，返回 expires_at；否则 LeaseError。
- frozen RecoveryDecision 字段见 workspace.py。
- frozen RecoveryReport 字段：run_id:str（原 run UUID）, state:str（成功返回固定 `abandoned`）, action:str（`requeued` 或 `preserved_for_recovery`）。
- recover_expired(conn, run_id:str, observed_owner_alive:bool, decision:RecoveryDecision, *, now:str) -> RecoveryReport；租约未过期、owner alive、worktree/base/hash 不匹配或 decision=conflict 时拒绝接管；成功时将原 run 标记 abandoned。unchanged 返回 action=`requeued`；partial 返回 `preserved_for_recovery`，保留原 worktree 与基线供后续恢复 claim；此函数不创建新 claim（没有新 owner/IDE 参数），下一次 claim_next 创建 run 并将 recovery_of 指向该原 run。绝不删除/回滚文件。

事件 `workspace_snapshot` 的 payload 精确为 `{"schema":"sdd-workspace-snapshot/v1","source_run_id":null|<UUID>,"snapshot":<WorkspaceSnapshot JSON>}`；snapshot 恰含 WorkspaceSnapshot 全部字段，pathlib.Path 用 `os.fspath` 序列化，allowed_hashes 按路径 key 排序。此事件只存在于本地 runtime SQLite/JSONL，不得复制到 Git/result/summary。事件 `recovery_claim` 的 payload 精确为 `{"schema":"sdd-recovery-claim/v1","recovery_of":<eligible abandoned or failed source run UUID>}`。两事件都在创建新 run/lease 的同一 SQLite 事务中写入；source_run_id fresh 时为 null，恢复时指向原 before snapshot 所属 run。新恢复 run 的 `workspace_snapshot` 保存从该 source 复制的原 before baseline，而非捕获为“新 clean”基线；不得因此添加表或列。

`recover_expired` 在同一 SQLite 事务中将原 run 标记 abandoned、关闭 lease 并追加 `recovery_decision` 事件；其 payload 精确为 `{"schema":"sdd-run-recovery/v1","action":"requeued"|"preserved_for_recovery","decision":"unchanged"|"partial"}`，只允许 `requeued/unchanged` 与 `preserved_for_recovery/partial` 两种配对。事件仅在本地账本，禁止 owner/token 等秘密，不进入 Git。Task05 partial 后的新 claim 的 `recovery_of` 与 `workspace_snapshot.source_run_id` 均指向紧邻的前一条 abandoned run；snapshot 完整复制该 run 持有的原始 before baseline。loader 沿 source_run_id 链追到 fresh snapshot（null），并逐段核验快照完全相同及 Task/run/hash/worktree 绑定；不得以链中间快照重置基线。被任一 `recovery_claim` 引用的 abandoned 或 eligible failed source run 已消费，永不重复领取；只对每 Task 最新 attempt 的未消费恢复状态做选择。unchanged/requeued 后下一 claim 是 fresh：`recovery_of=null`、`source_run_id=null`，并捕获新 clean baseline。

### workspace.py
- frozen WorkspaceSnapshot 字段：repo_root:pathlib.Path, common_dir:pathlib.Path, worktree_path:pathlib.Path, spec_id:str, task_id:str, task_hash:str, prompt_hash:str, branch:str, head:str, status_records:Tuple[str,...], allowed_hashes:Dict[str,Optional[str]], captured_at:str。
- frozen RecoveryDecision 字段：kind:str (unchanged/partial/out_of_scope/conflict), changed_paths:Tuple[str,...], out_of_scope_paths:Tuple[str,...], recoverable:bool, error_code:Optional[str]。
- load_recovery_snapshot(conn:sqlite3.Connection, run_id:str, task:TaskDefinition, repo_root:pathlib.Path) -> WorkspaceSnapshot；从原 run 的本地 `workspace_snapshot` event 读取 before 基线，并核对 run/task ID、当前 task/prompt hash、base commit、common-dir、registered canonical worktree 与 metadata 映射；缺事件/任何不匹配即拒绝。recovery claim 必须把此原 before snapshot 原样写入自己的 `workspace_snapshot` event，并写上述 `recovery_claim` payload；只新增 events，不加 SQLite 表或列。
- prepare_worktree(repo_root:pathlib.Path, task:TaskDefinition, base_commit:str, *, recovery_snapshot:Optional[WorkspaceSnapshot]=None) -> WorkspaceSnapshot；fresh 路径按 metadata 固定映射 create-if-absent/validate-if-present，以 git common-dir 定位并要求 worktree clean。recovery_snapshot 非空时核对 Task/hash/prompt/base/common-dir/worktree/branch 后，允许同一 registered worktree 保留此前 allowed partial changes；不得按 fresh 路径因 dirty 拒绝，也不得清理/覆盖。两种路径均记录当前 HEAD、git status --porcelain=v1 -z 和 allowed path hashes；recovery 调用方继续把传入的原 before snapshot 用作完成比较基线，返回值是当前观察快照。branch/基线冲突结构化失败。
- compare_snapshot(before:WorkspaceSnapshot, after:WorkspaceSnapshot) -> RecoveryDecision；以 status+content hash 区分本 run changes 和先存脏改动；allowed 外变化返回 out_of_scope；有改动时只报告，不清理。

### prompts.py / results.py / run_docs.py / metrics.py
- frozen RenderedPrompt 字段：text:str, path:pathlib.Path, template_hash:str, rendered_hash:str。
- render_prompt(task:TaskDefinition, claim:Claim, snapshot:WorkspaceSnapshot, runtime_root:pathlib.Path) -> RenderedPrompt；只按 whitelist 替换，以 Run 私有路径原子写 prompt.md 并返回相对 path/hash。
- frozen ValidationReport 字段：valid:bool, errors:Tuple[str,...], result:Dict[str,Any], changed_paths:Tuple[str,...]。
- validate_result(data:Dict[str,Any], task:TaskDefinition, claim:Claim, before:WorkspaceSnapshot, after:WorkspaceSnapshot) -> ValidationReport；纯校验 schema/未知字段/time/命令回执/hash/产物/changed path/secret；不执行命令、只报告、不写 DB/Git，不能单独作为声明验证已通过的证据。
- write_summary(task:TaskDefinition, claim:Claim, result:Dict[str,Any], repo_root:pathlib.Path) -> pathlib.Path；只写指定 run summary，相对路径与脱敏通过后返回。
- export_metrics(conn:sqlite3.Connection, *, filters:Dict[str,Any], format:str) -> str；format json/csv；缺失指标保留 null/空值及 source，禁止估算。

### validation_runner.py
- `run_validations(task:TaskDefinition, claim:Claim, repo_root:pathlib.Path, *, timeout_seconds:int=300) -> Tuple[Tuple[Dict[str,Any],...], Dict[str,Any]]`；只对仍 active 且 run/task/task_hash/prompt_hash/base/worktree identity 匹配的 Claim 执行；从本地账本读取该 run 的原始 before `workspace_snapshot`，不得接受调用方传入或伪造的基线。`timeout_seconds` 为每条命令的硬超时，必须是严格整数且在 1–3600 秒范围内。
- 每个 Task.metadata.validation_commands 元素都先按 `shlex.split(posix=True)` 校验，再按声明顺序以 `subprocess` `shell=False` 在 Claim 已登记的 canonical worktree 执行；拒绝空 argv、Task/Claim 漂移及 main-root ignored `.sdd/runtime` 外不安全路径。每条命令有硬超时、独立进程组；超时时杀死并回收整个进程组，避免留下可继续改 workspace 的子进程。所有声明命令都尝试执行。超时或非零退出仍有实际进程退出码；无法启动为 `skipped`/null。任一不能启动、超时或非零退出令 receipt.valid=false，complete 不得进入成功 journal。
- 返回第一项为与 sdd-run-result/v1 `commands` 子对象完全一致的 immutable tuple：argv 是实际参数；status 为 executed/skipped；exit_code 为真实进程退出码或 null；duration_ms 由 monotonic clock 实测；summary 仅为固定 `validation passed` / `validation failed` / `validation timed out` / `validation could not start`。stdout/stderr 不得出现在 CLI、TaskEvent、result summary 或 journal 诊断中。
- 第二项为持久化在 `<main-root>/.sdd/runtime/runs/<run-id>/validation/receipt.json` 的完整 `sdd-validation-receipt/v1` Dict，精确字段为 schema、run_id、task_id、task_hash、prompt_hash、base_commit、branch、worktree（repo-relative POSIX）、before_snapshot_sha256、validation_commands_sha256、started_at、ended_at、duration_ms、commands、command_logs、after_snapshot_sha256、valid、receipt_sha256；两个时间为执行期实测 UTC，receipt.duration_ms 与每条命令的 duration_ms 均由 monotonic clock 实测。commands 的每项精确为 `{argv:[str,...],status:str,exit_code:int|null,duration_ms:int|null,summary:str}`，与第一项逐项一致；command_logs 每项精确为 `{sequence:int,stdout_path:str,stdout_sha256:str,stdout_truncated:bool,stderr_path:str,stderr_sha256:str,stderr_truncated:bool}`，sequence 为从 1 开始的声明顺序，路径均在本次唯一 invocation UUID 子目录内。receipt_sha256 是省略该字段后其余字段按 sorted-key/compact UTF-8 JSON 序列化所得 SHA-256；receipt 原子写入并 fsync。不得记录 owner/token、credential 或环境变量内容。
- raw stdout/stderr 可保留为 mode 0600 的 `.sdd/runtime/runs/<run-id>/validation/<invocation-uuid>/command-<sequence>.stdout|stderr` 私有日志，每次 invocation 使用新 UUID，避免重复执行覆盖旧日志；每条 stream 最多保留 1 MiB 前缀，同时计算完整 stream SHA-256 并标记是否截断；内容可能含 secrets。只写入确认已忽略且无 symlink 的 runtime 下，绝不回显或复制到 Git/result summary/event。receipt 的 runtime 路径相对 canonical main-root；`receipt.json` 是原子更新的最新 invocation receipt，旧 invocation 日志保持独立；runtime 不安全时失败关闭，不回退到 `/tmp` 或其他可跟踪目录。
- runner 执行后重拍 workspace snapshot，receipt 绑定 before/after snapshot hashes；命令级失败也返回并耐久保存 invalid receipt，供 `fail` 使用；complete 要求 receipt.valid=true。receipt 持久文件路径加入最终 result 的 `log_paths`（相对 canonical main-root）；complete/fail 都不得接受 actor 提供的 command rows 作为执行凭据，不得把 receipt/raw logs 加入 Git stage 或 commit。

### Task06 事件、owner 与 failed/partial recovery API
- frozen TaskEvent 字段：run_id:str, sequence:int, timestamp:str, event_type:str, payload:Dict[str,Any]。
- resolve_run_owner(conn:sqlite3.Connection, run_id:str, executor_id:str, owner_pid:int) -> OwnerIdentity；从该 run 的本地 owner_json/lease 读取既存 token，要求 executor、正整数 PID、host/PID/process-start identity 与当前存活进程完全匹配、token 与 lease owner_token 一致；不生成新 token。CLI 显式收 `--executor` 与 `--owner-pid`，token 绝不作参数、stdout/stderr、result 或日志字段。
- append_event(conn:sqlite3.Connection, run_id:str, owner:OwnerIdentity, event_type:str, payload:Dict[str,Any], *, now:str) -> TaskEvent；只接受 `observation`、`evidence`、`decision`、`action`、`result`、`next_step` 六种公开 event type 与结构化、安全的 JSON object payload；在 `BEGIN IMMEDIATE` 中校验 owner/run/hash/state，生成 UTC 时间与 sequence 并刷新 lease。首个 owner-authenticated event 原子地令 run 从 claimed 进入 running，并将服务端 UTC timestamp 写入 started_at；之后 event 不覆盖 started_at。SQLite 成功后才按同 sequence 幂等追加本地 JSONL；重放同 sequence 同 payload 成功，不同 payload 拒绝。`workspace_snapshot`、`recovery_claim`、`recovery_decision` 与 `workspace_observation` 事件仅由内部生命周期函数生成，不接受 CLI 伪造。
- record_workspace_observation(conn:sqlite3.Connection, run_id:str, owner:OwnerIdentity, snapshot:WorkspaceSnapshot, *, now:str) -> None；在 fail 文档发布前确认 active run、owner、Task/Prompt/base/worktree 绑定后持久化唯一 `workspace_observation` 事件，payload 精确为 `{"schema":"sdd-workspace-observation/v1","snapshot":<WorkspaceSnapshot JSON>}`。该本地事件不含 owner/token，且不得进入 Git summary/result/metrics。
- load_workspace_observation(conn:sqlite3.Connection, run_id:str, task:TaskDefinition, repo_root:pathlib.Path) -> WorkspaceSnapshot；只接受绑定到对应失败 run 的唯一、schema 正确 observation；核验原始 before snapshot、run/task/prompt/base/worktree/branch、allowed path hashes 与事件时间序列，不猜测或重建缺失 observation。
- finalize_failure(conn:sqlite3.Connection, run_id:str, owner:OwnerIdentity, report:ValidationReport, before:WorkspaceSnapshot, observation:WorkspaceSnapshot, *, now:str) -> TaskRun；只在失败文档 journal 已验证完成其文档-only commit 后调用；在单一 `BEGIN IMMEDIATE` 对 run owner/hash/active state CAS，核对已持久 observation 与实际 workspace 决策，关闭 lease 并写终态。`report.result.outcome` 只能导出 TaskRun `failed` 或 `blocked`；仅 retryable 的 `failed` 按决策追加既有 `requeued/unchanged` 或 `preserved_for_recovery/partial` recovery_decision。缺 observation、冲突/越界/不可确认 baseline 不得生成可重试分类，Task 应阻塞且保留现场。
- result_for_run(conn:sqlite3.Connection, run_id:str) -> Dict[str,Any]；只从 ledger `result_doc` 指向的 canonical summary 读取完整结果，核验 terminal TaskRun 与 summary 的 run/task/hash 绑定、sdd-run-result/v1 schema 和敏感内容。只读，不验 owner、不刷新 lease；terminal summary 不可用时稳定返回 `RESULT_NOT_AVAILABLE`，不得信任任意本地 runtime result.json。
- `recover_expired` 仍只把 owner 已死且 lease 过期的 active run 变为 `abandoned`；Task06 `fail` 永不伪装成 abandoned。每次重试新建 Run。第三个连续 failed outcome 保持 Run=`failed`、Task=`blocked` 并更新镜像；validated blocked outcome 也终止为 blocked。
- `claim_next` 只检查 Task 最新且未消费的 run。failed partial source 必须有 `preserved_for_recovery/partial`、唯一 observation、closed lease、Task/Prompt/base/worktree identity，且当前状态只能在剔除下述已核验文档提交后等于 observation；新 Claim.recovery_of 与 workspace_snapshot.source_run_id 指向紧邻 failed source，原 before snapshot 原样沿链复制。failed unchanged source 仅当当前状态匹配 observation 时创建普通 fresh claim，两个 source 字段均为 null。`recovery_claim` 永久消费 source；不回退更旧尝试。
- 失败文档提交复用 §6 journal/ref-CAS/index-reconciliation；committed_paths 仅含当前 run summary，及 Task 被置 blocked 时的 Task/spec/README 镜像。partial source/code changes 永不入 commit；真实 index 的非目标 entries 与预存用户 stage 精确保留。replay 只能按 journal expected result 写 failed/blocked，绝不 succeeded。
- 失败文档提交会推进 HEAD，但不重写原 `base_commit` 或 before hashes。恢复时只接受从原 base 起连续 first-parent、每项均有已完成本地 journal 的提交；每个 parent、精确文档路径集合、blob/mode 与 journal expected hashes 必须匹配。仅剔除这些已验证摘要/镜像路径后比较 source snapshot；merge、未登记提交、代码路径提交、refs/内容第三态或 journal 缺失均阻塞，保留文件与 index，不 reset/stash/clean。
- 在首次 durable `prepared` journal 前崩溃时，Task06 不得推断失败终态；owner 死亡且 lease 过期后仍只由 `recover_expired` 按 abandoned 规则处理。发现半写、损坏、未知版本或与 phase 不符的 journal 时 fail-closed 并保留现状；不得补造字段或从结果文本猜测。有效 journal 的 docs_writing 恢复只允许每条文档仍处于 recorded before hash 或 expected after hash，其他状态立即阻塞。

### cli.py / __main__.py
- main(argv:Optional[Sequence[str]]=None) -> int；stdout 仅稳定 JSON envelope {ok:bool, code:str, message:str, data:object}，诊断 stderr；退出码固定：0 成功/无待办，2 用法或定义无效，3 依赖/gate/镜像冲突，4 活跃租约/owner 冲突，5 worktree/基线冲突，6 验证/结果失败，7 journal recovery required。envelope code 是机器主契约，退出码不得随意变化。
- 内部只读 API `doctor(repo_root:pathlib.Path) -> Dict[str,Any]` 返回精确 `sdd-doctor/v1` 对象：`schema`、`healthy:bool`、`worktree_count:int`、`task_count:int`、`legacy_task_count:int`、`duplicate_task_copies:int`、`summary_count:Optional[int]`、`ledger:{present:bool,schema_check:str}`、`diagnostics:[{code:str}]`；拒绝未知/缺失字段。计数按已登记 worktree 扫描：task_count 按唯一 Task ID 去重，legacy_task_count 按无稳定 Task ID 的物理 legacy 文件跨 worktree 计数，duplicate_task_copies 为额外同 ID/同定义 hash 的副本数，summary_count 为 `scan_summaries` 返回的有效唯一 run_id 数；完全相同内容的同 run_id 摘要只计一次，不同内容的同 run_id 是扫描冲突；无法完整扫描时为 null 并报告扫描错误。不同 hash 的同 ID 是阻塞冲突，不计作可去重副本。
- `doctor` 仅检查已登记 worktree、Task/依赖/门禁声明结构/镜像/摘要契约及 ledger 路径安全；required_gates 仅按 Task schema 校验，不读取 gate registry/evidence 判断其是否 passed，满足情况由 `status` 读取。禁止 SQLite connect、维护锁、mkdir、文件写入或其他持久副作用。ledger 缺失时 `present=false,schema_check=not_initialized`，本身不构成错误；安全普通文件已存在时 `present=true,schema_check=not_run_requires_status`，并加入信息性 `ledger_status_required`，说明必须另运行 `status` 才验证 schema，不把它当作 schema PASS，也不单独令 healthy=false；符号链接、非普通文件或逃逸路径为 `present` 按观察值返回、`schema_check=unsafe` 并阻塞。`healthy` 仅表示 doctor 实际完成的静态检查及路径检查无阻塞错误，不代表 SQLite schema 已验证。诊断 code 稳定且按 code 排序；只有 `ledger_status_required` 是信息项，其余诊断阻塞健康。
- `doctor` 复用全局 JSON envelope：healthy=true 时 `ok=true,code=ok`、退出码 0；不健康时 `ok=false`，envelope `code` 为按既有类别优先序选择的首个阻塞诊断 code，`data` 始终为完整 `sdd-doctor/v1`。退出码只复用既有定义：Task/schema/Prompt 定义错误为 2，依赖/gate/重复定义/镜像冲突为 3，worktree 或不安全路径为 5，摘要验证/扫描及其他运行时检查错误为 6；doctor 不产生 4 或 7。详细人读诊断写 stderr，stdout 不输出 traceback。缺 DB 可以健康；已有 DB 只有 ledger_status_required 信息且其他检查通过时也可以健康，但不得宣称 schema 通过。
- Task05 子命令：`doctor`、`rebuild`、`status --json`、`next --claim --ide <id> --executor <id> --owner-pid <persistent-executor-pid>`、`recover --run-id <uuid>`；Task06 增加 `event --run-id <uuid> --executor <id> --owner-pid <pid> --type <type> --payload-json <object>`、`complete --run-id <uuid> --executor <id> --owner-pid <pid> --result <path>`、`fail --run-id <uuid> --executor <id> --owner-pid <pid> --result <path>`、`result --json --run-id <uuid>`、`metrics --format json|csv`。event/complete/fail 必须通过 executor、持久 owner PID/process-start identity 核验，并从本地账本解析 owner token；token 不经 CLI 参数传输。result/status/metrics 为只读查询，不需 owner principal、不刷新 lease。next 只 claim 一个；render 在 Task06，Task05 可 prompt_path=null。
- event payload 只收结构化字段，服务端生成 UTC 时间/sequence/id；刷新 lease。SQLite append 成功后 JSONL 才可按同 sequence 幂等落盘；不同 payload 同 sequence 拒绝。

## 6. 成功提交与恢复的 write-ahead journal

成功 complete 顺序固定为：读取且核对 draft result 与 active Claim/Task → 从 ledger 取原始 before snapshot → 调用 `run_validations` 实际执行全部声明命令 → complete 独立重拍 workspace 并重验 Task/Claim/base、changed paths、产物和 allowed_paths → 用 runner 实际 command rows 覆盖 draft `commands`，用首个 owner-authenticated event 的 ledger `started_at`（无 event 时为 Claim `claimed_at`）覆盖 draft `started_at`，并在上述重验结束时生成服务端 UTC `ended_at`/实际 UTC elapsed `duration_ms` → 校验最终 result → 写脱敏摘要 → 创建本地 completion journal → 更新 Task/spec/README → 精确 stage 并本地 commit。actor 提交的 commands/timestamps 不作证据；命令任一未启动、超时或非零退出时停止在 journal 前，转用 `fail` 记录失败。若系统 UTC 倒退导致 ended_at 早于 started_at，关闭 complete 且不生成成功 journal。`fail` 同样执行 runner，使用其实际 command rows 和持久 invalid receipt，决不采用 actor 命令回执；任一 DB CAS 或文档写入前都必须先创建完整 journal。

路径：<主工作树根>/.sdd/runtime/runs/<run-id>/completion.json。主工作树根通过 git worktree list --porcelain 的首项解析；journal 所在 .sdd/runtime 已忽略。首次 durable journal 必含：
schema=sdd-completion-journal/v1、run_id、task_id、owner{executor_id,host_id,pid,process_started_at,token}、base_commit、original_head、task_hash、prompt_hash、expected_result（完整且已验证的 sdd-run-result/v1 object）、terminal_outcome（succeeded/failed/blocked，必须等于 expected_result.outcome）、allowed_paths、changed_paths[{path,before_sha256,after_sha256}]、expected_docs[{path,before_sha256|null,content,after_sha256}]、committed_paths、staged_paths、index_before{git_index_path,index_sha256,committed_entries[{path,stage,mode,object_id}],other_entries_sha256}、index_observed_before（初始 null；持锁后记录全索引 hash、committed_paths entries 与其余 entries hash）、index_after（初始 null；后续记录全索引 hash、committed_paths entries 与其余 entries hash）、index_lock_owner_token（随机高熵 token）、index_lock_temp_path（index 同目录内、journal 记录的随机 basename，可空）、index_lock_identity{device,inode}|null、index_recovery_stage（not_acquired/marker_temp_durable/marker_durable/reconciliation_index_durable/lock_index_durable/ref_committed/index_installed）、candidate_commit_hash（prepared 至 index_after_prepared 为 null；commit_pending 记录必须带候选 commit hash，并在 ref CAS 前持久化）、commit_message、phase。index path 使用目标 worktree 的 git rev-parse --git-path index 解析；entries/hash 都来自真实 index，不记录凭证。index_before 在首次 journal durable 时捕获；index_observed_before 用于识别并保留 journal 创建后、拿锁前发生的非目标用户暂存变动。`committed_entries` 只含 committed_paths 的全部 stage 项；`index_sha256` 是 index 文件原始字节的 SHA-256；`other_entries_sha256` 是其余 entries 按 (path UTF-8 bytes, stage) 排序后，以字段顺序固定、无多余空白的 UTF-8 JSON 数组序列化所得 SHA-256。
`git_index.py` 冻结 API：`GitIndexError(ValueError)`；`read_index_snapshot(worktree:Path, committed_paths:Sequence[str], *, original_head:str) -> dict` 返回完整 `index_before` 结构。要求已登记 canonical worktree、目标 index 为解析出的 worktree Git dir/index 内的 no-follow regular file；解析 `git ls-files --stage -z` 并保留含空格/换行路径，拒绝无效 UTF-8、非法 mode、重复 stage 项及 index 竞态；确认 current HEAD 等于 original_head，且 committed_paths 的 stage-0 entries 与 original_head tree 完全一致、无冲突 stage。其余 entries 的摘要按上述确定性 JSON 规则计算。

`git_index_lock.py` 的 `acquire_owned_index_lock(worktree:Path, journal_path:Path)->dict` 只获取或恢复本 run 的标准 index.lock，返回已持久化的 journal。marker JSON 精确字段为 `schema="sdd-index-lock/v1"`、`run_id`、`index_lock_owner_token`、`index_before_sha256`。持有 marker 后重拍 index，目标 entries 必须仍匹配 index_before；将此时完整 index hash、目标 entries 与非目标 entries hash 记为 index_observed_before，以保留 journal 创建后新增的用户非目标暂存内容。未持有锁前不能把该观察快照当作最终 index 基线。
expected_docs 包含 Task 状态、spec/README 状态镜像、完整 run-summary 的期望 UTF-8 内容和 hash。所有路径通过 containment/symlink 校验。初次 write 和每次 phase 更新均采用同目录临时文件、flush、fsync(file)、os.replace、fsync(parent dir)；文档写入亦 write temp/fsync/replace/fsync(parent)，不会出现单文件半截内容。

phase 单向转换：
~~~text
prepared -> docs_writing -> docs_written -> index_locking -> index_after_prepared -> commit_pending -> committed -> index_reconciled -> ledger_finalizing -> complete
~~~
每个副作用前先 fsync 该 phase。跨多个文档写一半时，journal 按每路径 before/expected-after hash 判断并继续。task_hash 排除 status；每次状态更新前核验其仍等于 claim 时的 task_hash，状态更新后该 hash 保持不变，文档本身的期望内容与 hash 由 expected_docs 记录。

冻结 journal API 分为 `journal_schema.py` 与 `completion_journal.py`：前者导出 `JournalError(ValueError)`、`validate_journal(data:object)->dict`（严格拒绝未知/缺失字段和 phase 条件不满足）、`validate_phase_transition(previous:str,current:str)->None`（只接受同阶段幂等更新或单阶段前进）；后者导出 `read_journal(path:Path)->dict`（严格读取 UTF-8、拒绝重复 JSON key 和符号链接，并验证完整 schema）及 `write_journal(path:Path,data:dict,*,previous_phase:Optional[str]=None)->None`（验证完整 schema/阶段转换后以原子、耐久写入发布）。journal 在 prepared 首次写入时具有完整字段：index_observed_before、index_after、index_lock_temp_path、index_lock_identity、candidate_commit_hash 均为 null，index_recovery_stage=not_acquired；candidate_commit_hash 保持 null 至 commit_pending，之后必须为合法 Git object ID。`expected_result` 为整个已校验结果，终态由 terminal_outcome 复制，恢复不得从自由文本重新推断。

Git 提交使用独占 common-dir commit lock 与临时 index (GIT_INDEX_FILE) 构造 candidate；精确 staged_paths/committed_paths 只可含 validated Task allowed changed paths 与该 run 的 Task/spec/README/summary 白名单。真实 index 不用于构造 candidate。candidate commit tree 的本次变更路径集合须与 committed_paths/staged_paths 完全相等，mode 和 blob hash 也逐项相等。首次 journal 前快照真实 index；若 committed_paths 上已有相对 original_head 的用户 staged change 或 unmerged stage，停止，不将其纳入提交。生成 commit object 后先把 candidate commit hash durable 写入 journal。

HEAD CAS 与真实 index 的限定协调按以下顺序执行：
1. 在任何真实 index 改动前 durable 写 phase=index_locking，并确认目标 worktree 的 index 是普通文件、可读取且未被 symlink 替代。先生成安全随机 basename，将 index_lock_temp_path durable 写入 journal；再在 index 同目录以 O_CREAT|O_EXCL 创建该临时 marker，写入完整 JSON（schema=sdd-index-lock/v1、run_id、index_lock_owner_token、index_before hash），fsync 文件；随后将 index_recovery_stage=marker_temp_durable 原子写入并 fsync journal。再用同文件系统的 no-replace hard link（或等价原子 no-replace primitive）把已 fsync 的 marker 链接为标准 index.lock；若 index.lock 已存在、平台/文件系统不能保证原子 no-replace 或 link 失败，则停止，不碰现有 lock。fsync 父目录后，仅当临时 marker 与 index.lock 为同一 inode 时 unlink 临时名称并再次 fsync 父目录。这样 index.lock 要么不存在，要么从创建时起就含完整可核验 marker；不会留下本进程创建的空 lock。若 marker 临时文件写入时崩溃，它不阻塞 Git；恢复只可读取并验证其 token，不能覆盖不明文件，可另选新随机 basename 重试。
2. 读取新建 lock 的 device/inode，将 index_lock_identity 与 index_recovery_stage=marker_durable 原子写入并 fsync journal。此身份在覆盖 marker 前必须已持久化。持有 index.lock 后重新读取真实 index；committed_paths 的所有 stage/mode/object_id 必须与 index_before 相同，且相对 original_head 没有用户暂存差异或 unmerged stage；否则停止，不覆盖。将此刻真实 index 的全索引 hash、目标 entries、其余 entries hash durable 记录为 index_observed_before。journal 后、拿锁前新增的非目标用户 stage 因此进入后续保留基线。
3. 从锁下当前真实 index 复制出独立临时 reconciliation index，仅将 committed_paths 调整为 candidate commit tree 对应 entries；删除路径仅移除目标 path 的 stage-0 entry，其余所有路径及 stage 原样保留。计算并验证 index_after 的全索引 hash、committed_paths entries 与其余 entries hash；fsync 临时 index。
4. 原子持久化 phase=index_after_prepared、index_after 和 index_recovery_stage=reconciliation_index_durable。核对 index.lock 的 device/inode 仍与 journal 一致后，将完整 reconciliation index 写入同一个 index.lock 文件并 fsync（不得用替换 lock 文件的方式释放独占锁）；随后将 index_recovery_stage=lock_index_durable durable 写入 journal。若写入中崩溃，index.lock 可能不完整，但真实 index 未改且锁身份可验证；恢复可依据 durable 的 index_observed_before/index_after 重建该 lock 内容。此时 HEAD 必须仍为 original_head。
5. 将 phase=commit_pending 与 candidate hash durable 写入 journal，再运行 git update-ref <branch> <candidate> <original_head> 执行 ref compare-and-swap。HEAD 已不是 original_head 时拒绝，绝不覆盖他人提交、不 push。CAS 成功后 durable 记 phase=committed、index_recovery_stage=ref_committed。若 CAS 返回失败且 HEAD 仍为 original_head，只有在 lock token/identity 与 journal 匹配且真实 index 仍等于 index_observed_before 时，才可移除本 run 的 index.lock 并保留 journal；HEAD 已变化、lock 不明或真实 index 不符时保留 lock 并阻塞。
6. 确认 HEAD=candidate、真实 index 仍逐项等于 index_observed_before，且 index.lock 身份仍匹配后，以 os.replace(index.lock,真实 index) 原子安装 index_after 并 fsync index 目录。然后 durable 记 index_recovery_stage=index_installed、phase=index_reconciled。若在 rename 后、journal 更新前崩溃，恢复通过 HEAD=candidate 且真实 index 全 hash 等于 index_after 识别已安装状态。成功 Task 改动因此与新 HEAD 对齐；预先或并发暂存的非目标路径仍保留，且从未进入 Task commit。
7. 任何 index lock/hash/ref CAS 不匹配时不把 Run 标 succeeded。保留 journal、真实 index 和用户 stage，返回 recovery_required；绝不 reset、整体 read-tree、checkout、stash 或 clean。恢复只允许在确认 lease owner 已死、lock 的 marker token 与 journal 匹配或其 device/inode 与 durable index_lock_identity 匹配、HEAD/真实 index 符合该阶段记录时继续本 run。未知或其他进程的 index.lock 一律不删不覆盖。
DB 最后在 BEGIN IMMEDIATE 中对 run owner/hash/state CAS，再写 succeeded、Task 状态缓存与 lease closure；随后 journal phase=complete。任何失败保留 journal 和现状，CLI 不得返回 success。

Recovery 只在 lease 过期且 owner pid+process-start identity 判定已死后执行；仍活 owner 一律拒绝。另核对 host/executor/worktree path/branch/base commit/HEAD/Task/Prompt hash/允许改动清单。
- prepared/docs_writing：逐文件判断当前 hash 是 before 或 expected after；before 可继续原子写 expected，after 视为已写；第三种 hash 立即 conflict/blocked，不覆写。
- docs_written：核对文档/changed paths，durable 写 index_locking 后继续。
- index_locking：owner 必须已死。若尚无 index.lock，重新独占获取前必须确认 committed_paths 的 stage/mode/object_id 仍与 index_before 相同，且没有相对 original_head 的用户暂存差异或 unmerged stage；index_observed_before 尚未写入时，非目标 entries 可在成功持锁后重新快照并保留。若已有 lock，只有完整 marker 的 run_id/token 匹配，或其 device/inode 与 durable index_lock_identity 匹配，才认作本 run 所有。marker 临时文件只可在 basename 等于 journal 记录路径且 token/schema 精确匹配时复用；无效/未知文件不覆盖，可另选随机 basename 并 durable 记录后重试。unknown/partial marker 且无已记录身份时停止并保留。此阶段 HEAD 必须为 original_head。
- index_after_prepared：核对 owner/lock 身份、真实 index 全 hash 与 index_observed_before、目标 stage 和其余 entries hash；HEAD 必须为 original_head。若 lock 仍是 marker，按记录的 index_after 重建并 fsync lock；若 lock 已是有效 index_after，只记录 lock_index_durable；若 lock 内容为第三种状态，停止。不可把真实 index_before 的非目标 entries 当作当前值覆盖 index_observed_before。
- commit_pending：若 HEAD=original_head，candidate tree、lock 中完整 index_after 及真实 index_observed_before 均可验证时才执行 update-ref CAS；若 HEAD=candidate，说明 CAS 已成功，记录 committed；其他 HEAD 冲突并停止。真实 index 在 rename 安装前必须仍等于 index_observed_before。
- committed：HEAD 必须等于 candidate。若 index.lock 仍存在，须核对其身份、内容 hash=index_after 且真实 index=index_observed_before，再以原子 rename 安装；若 index.lock 已不存在，只有真实 index 全 hash=index_after 且目标/非目标 entries 分别匹配时，才能认定 rename 已完成并记录 index_installed/index_reconciled。若 committed_paths 变化、真实 index 为第三种状态或 lock 不属于本 run，停止保留一切。
- index_reconciled：确认真实 index 全 hash、committed_paths entries 与非目标 entries hash 都与 index_after 相符，再进入 DB finalization。
- ledger_finalizing：以幂等 DB CAS 收尾；complete：只返回原结果，不重复提交。
- 任意不匹配都保留 journal/部分文件，返回 blocker。journal 不得在独立验收前删除；recover 不运行 reset/stash/clean，不自动移除部分改动。
- fail/blocked 保存本地 result/events 与可脱敏 summary，保留部分工作树；不得把 failed 替换为 succeeded。文档-only 证据若入 Git，也用相同 journal，staged_paths 仅可包含唯一 summary/report 白名单。

## 7. 开发切片建议

每次 assignment 最多 2 个文件、最多 150 行变更；超出即拆批，不由主 Agent补写实现。

- Task04：A metadata parser（documents.py + __init__.py）；B SQLite schema/transaction（store.py + 单独 store 测试）；C worktree catalog/rebuild（catalog.py + 单独 catalog 测试）。测试放 tests/sdd_tasks；用 Python 3.9 unittest，或 pytest 时使用 --confcutdir=tests/sdd_tasks，避免根 conftest 导入业务模块。
- Task05：A selection/lease（selection.py + leases.py）；B workspace/snapshot（workspace.py + tests/sdd_tasks/test_workspace.py 分批）；C CLI assembly（cli.py + __main__.py）。每批严格不超两文件/150 行。
- Task06：A prompt/result parser（prompts.py + results.py）；B event/summary（run_docs.py + event helper）；C metrics（metrics.py + 对应测试）；D complete/fail/recover journal（独立 lifecycle 模块和测试）；E CLI 接线（cli.py + lifecycle tests）。journal 状态机测试完前不启用自动 commit。
