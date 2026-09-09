# Spec018 Task02A-D implementation contract

本契约描述 02A-D 的候选全库重建边界；它不是最终 `InspectionManifest`，也不授予
真实库切换权限。

## 允许的写入面

- 所有 Collection 写入必须经 `CandidateIndexPort`，并在本 run 绑定唯一
  `candidate_collection`；未绑定或不等于候选的正式 collection、当前 alias target、
  任意未授权 retire target 均拒绝。
- 未绑定的 port 没有任何写/删能力；服务发现缺失 binder 时立即 fail closed，不能
  通过注入一个任意 destination 绕过 run scope。
- `authorize_retire()` 是绑定 port 的必需能力：缺失、弱签名或未绑定均 fail closed；
  绑定时注入仅存于当前服务实例的 run-scoped capability，不能用 run id 字符串伪造。
  只有 intent 的 `previous_target` 与 fresh topology 同时证明目标仍是本 run 原目标时，
  才可授权删除 physical/current collection；alias 名称也绑定到本 run 的默认 alias。
- Qdrant `update_collection_aliases` 的 `change_aliases_operations` 值必须是当前 SDK
  要求的 operation `Sequence`，不得包成 `ChangeAliasesOperation` 外层对象。
- 测试和验证只使用 `tempfile`、`FakeQdrant` 或不联网的 API-compatible stub；不读写
  `data/kb`、真实 Qdrant、frontend 或 Git 历史。

## 命令与确认门

- 无参数维护命令是只读 dry-run；执行 build/switch、resume 或 cleanup 必须显式
  `--confirm-replace`。
- `--recover-stale-lock RUN_ID` 只能作用于同一 run；没有明确 run id、PID 仍存活、
  state/topology/action 任一证明不匹配、锁 JSON malformed 或存在歧义时均 fail closed。
- lock JSON 固定包含 `schema_version/run_id/owner/pid/host/token/command/started_at/heartbeat_at`；
  heartbeat 使用临时文件、fsync、原子 replace 和目录 fsync。

## FSM、拓扑与恢复

- 状态顺序为 `preflight → building → validating → ready_to_switch → switching →
  finalizing → completed`，失败分支为 `finalize_pending` 或 `cleanup_pending`。
- 每个外部动作写入 before intent 和 after/unknown observed，包含
  `previous_target`、动作序号、预期/实际 topology digest；动作已生效但调用报错时，
  resume 依据新鲜拓扑收敛，不重复猜测。after topology 不可观测时只能停留在恢复态，
  禁止进入 completed 或继续破坏性动作。
- run state 固定记录 `previous_target`、`initial_topology_digest` 和
  `validated_topology_digest`；resume 先要求 fresh inventory 等于最近 observed topology，
  漂移时不得删除外部 collection。
- alias 查询异常、空/多 target、unknown target、多候选及 stale preflight 均拒绝；
  cleanup 重新读取拓扑，绝不删除任意 alias 引用的候选。合法的“现有 alias target +
  本 run 新 candidate”组合可继续收敛。

## 候选验证与 schema

- `candidate-rebuild-run.schema.json`、`topology-inventory.schema.json`、
  `candidate-validation.schema.json` 均为 Draft 2020-12 闭合运行 DTO，并由
  `Draft202012Validator` 在运行时校验。
- validation 必须覆盖 source hash、payload/anchor/config/model fingerprint、
  v1/v2 与 `llm_used`、dense finite/dimension、sparse sorted-unique/range/finite/
  nnz、point-id/chunk-index 唯一连续性、query digest/top document IDs/candidate hit、
  text digest、完整 dense/sparse value digest、collection fingerprint 和 `validated_at`；
  payload、text、vector、anchor 或 config/model 任一篡改必须收敛为
  `CANDIDATE_VALIDATION_FAILED`。
- `validation.json` 与 `topology.json` 在 resume/finalize/cleanup 前重新做 schema、SHA-256、
  fresh topology 和 point-total 双检，并从 Candidate collection 的 payload/text、anchors、
  dense/sparse vectors 和固定配置独立重算 fingerprint；state 与 validation 的协同篡改
  不能自证。commit 的 collection fingerprint 必须非空且等于验证值。
- state、artifact 和 lock 的目录 fsync 失败统一为稳定错误并阻止 success/completed；旧文件
  保持可恢复，临时文件不冒充成功结果。
- 失败只生成临时 run artifact，不切换默认 alias；成功后才允许 switch/finalize。

## 验收边界

以下命令在本工作树上通过，且不连接真实 Qdrant：

```text
.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py
.venv/bin/ruff check backend/app/knowledge_base/infrastructure/candidate_index.py backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/rebuild_index.py tests/test_kb_candidate_rebuild.py
```

本契约仍需 Task02A-E 独立 reviewer/tester 复核后，才可作为进入 Task02B 的放行依据。
