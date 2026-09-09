# Spec018 Task02A-D candidate rebuild report

## 结果

**Task02A-D 的 P0 修复已完成，候选重建协议可在隔离临时目录与 FakeQdrant 上验证。**
本报告只覆盖实现交接，不代替 Task02A-E 的独立后端验收或 Task02B 的复测结论。

## 改动职责

- `backend/app/knowledge_base/infrastructure/candidate_index.py`：显式
  `destination`/`document_id` 的 `CandidateIndexPort`、Qdrant 适配器与故障可注入
  `FakeQdrant`；绑定本 run candidate/alias，未绑定或正式 collection/未授权 retire 均拒绝，
  使用 SDK 要求的 `change_aliases_operations=Sequence[operation]` 参数，不读写 metadata。
- `backend/app/knowledge_base/infrastructure/candidate_rebuild.py`：严格元数据权威
  预检、source hash/解析、v1+v2 bundle 复用、dense+sparse 候选写入、候选验证、
  topology matrix、FSM、固定字段 exclusive lock、原子 heartbeat、intent/observed
  事件、alias switch、finalize/cleanup 恢复和 stale preflight 检测；unknown after-effect
  停留恢复态，validation/commit/topology artifact 均做 SHA-256 与 fresh topology 复核。
- `backend/app/knowledge_base/rebuild_index.py`：维护命令；无参数为 dry-run，实际
  替换、resume、finalize、cleanup 均需显式 `--confirm-replace`，stale recovery
  必须传 `RUN_ID`，支持注入 index/stub 而不创建真实 client。
- `backend/app/knowledge_base/infrastructure/chunkers.py`：修复 Markdown v2 对
  `None` 页码的错误强转，保持 PDF 行为不变。
- `tests/test_kb_candidate_rebuild.py`：扩展到 37 个隔离测试，覆盖双 dry-run、锁/确认
  竞态、未绑定 allowlist、alias malformed/exception、动作已生效/unknown 恢复、
  finalize/cleanup 恢复、payload/text/vector/anchor/config 篡改、malformed sparse、
  artifact hash、RuntimeStore 目录 fsync、Qdrant alias API strict stub 和全写 spy。

## P0 关闭项

| P0 | 关闭证据 |
|---|---|
| P0-1 | 未绑定或弱 port 没有写删面；`bind_candidate`/`authorize_retire` 双端口 allowlist 加 run-scoped object capability；正式/current target 删除必须经过 intent + fresh topology + 强制授权；任意 confirm/resume/cleanup 写路径在 CLI 先要求 `--confirm-replace`。 |
| P0-2 | lock schema 固定九字段；显式 `--recover-stale-lock RUN_ID`，PID、state、topology、action 四重证明，malformed/歧义 fail closed，heartbeat 原子落盘。 |
| P0-3 | intent/observed 均记录 previous target、sequence、expected/actual topology digest；run state 固定记录初始/validated topology；post-success alias error 可 resume，unknown after-effect 不会 completed，外部 alias 漂移 fail closed，后续 alias 更新可删除同一 run 旧 collection。 |
| P0-4 | alias 异常/空/多/unknown target fail closed；cleanup fresh topology 且保护 alias 引用候选；`finalizing`/`finalize_pending` 均可 resume。 |
| P0-5 | 三份 Task02A schema 为 Draft 2020-12 闭合 DTO；运行时使用 `Draft202012Validator`，validation 覆盖完整 payload/text digest、dense/sparse value、anchor/config/model、llm、query、fingerprint 和时间字段；resume 从候选 collection 独立重算，state+validation 协同篡改稳定失败。 |
| P0-6 | dry-run 前后 lock/topology digest 比较返回 `PREFLIGHT_STALE`；双并发 dry-run、confirm 竞态及全写 spy 均有测试。 |
| P0-7 | Qdrant alias 更新向 SDK 传 operation Sequence；严格不联网 API-compatible stub、动作 before/after/unknown、锁/目录 fsync 失败、cleanup、后续 alias、malformed topology、弱 port 和外部拓扑漂移均有证据。 |
| P0-8 | 本文件与 `implementation-contract.md` 已更新；三份 schema 与运行实例均纳入交接。 |

## 固定产物

- `candidate-rebuild-run.schema.json`
- `topology-inventory.schema.json`
- `candidate-validation.schema.json`
- `implementation-contract.md`

三份 schema 均为 Draft 2020-12；运行状态、拓扑和候选验证分别拥有稳定版本字段、
闭合对象和 fail-closed 枚举。运行时会先调用 `Draft202012Validator.check_schema`，
再校验实例。

## 证据

| 项目 | 结果 |
|---|---|
| dry-run 写操作 | 0：不创建 runtime/lock、候选 Collection、embedding 或 metadata/source 写入 |
| 隔离 build | 1 authoritative document；v1=3 points、v2=1 point；dense=4、sparse=1,048,576 |
| validation | `passed`；point ID 唯一、chunk index 连续、hash/payload/vector/query probe 通过 |
| 首次切换 | physical `papers` 删除后建立 `papers` alias 指向候选；候选保留 |
| alias 失败 | 候选保留，状态停在 `switching`，intent/observed 均落盘；动作已生效后报错可 resume |
| finalize 失败 | 状态 `finalize_pending`，`resume-finalize` 可幂等收敛；`finalizing` 也可恢复 |
| cleanup 失败 | 状态 `cleanup_pending`，`cleanup-failed` 可重试且保护 alias 引用候选 |
| 空权威集合 | `NO_DOCUMENTS_TO_REBUILD`，不创建候选 |
| 拓扑歧义 | `safe_to_switch=false`，不猜测、不删除 |

## 检查命令

- `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py`：退出码 **0**，37 passed。
- `.venv/bin/ruff check backend/app/knowledge_base/infrastructure/candidate_index.py backend/app/knowledge_base/infrastructure/candidate_rebuild.py backend/app/knowledge_base/rebuild_index.py tests/test_kb_candidate_rebuild.py`：退出码 **0**。
- `.venv/bin/python -m pytest -q tests/test_kb_chunkers.py tests/test_kb_source_provenance_bundle.py tests/test_kb_markdown_provenance.py tests/test_kb_pdf_provenance.py`：此前退出码 **0**，90 passed；本轮实现未触碰这些测试对应逻辑。
- 三份 schema `python -m json.tool` 与 Draft 2020-12 `check_schema`：退出码 **0**。
- 本 Task Python 文件 `py_compile`、`git diff --check`：退出码 **0**。

## 边界与后续

- 未运行真实 metadata、`data/kb`、真实 Qdrant 或替换命令；未定义/持久化
  `InspectionManifest`，未恢复 snapshot、`LegacyUpgradeStore`、逐文档 `must_not`、
  自动升级或旧索引回滚。
- 主 Agent 后续应重新运行 Task02A-E 的 backend-tester/backend-reviewer，核对真实
  Qdrant 客户端版本兼容性、全部中断注入矩阵和三份 schema 的机器校验，再决定是否
  进入 Task02B。P0 已关闭不等于 E 门禁自动通过。
