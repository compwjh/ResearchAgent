# Spec032 真实自然语言研究 E2E（复审运行）

## 结论

**BLOCKED（不冒充完整 E2E）**

本轮使用新的真实 conversation/session/run，已通过自然语言 Intake、计划生成、预算约束、计划批准、候选评估，并选中 5 篇 USENIX Security 2024 候选。任务主状态为 `completed`，已产生非空的 artifact-backed Markdown 报告（标题“深度研究报告”，7649 个字符、5 个行内 catalog 引用）。

但自动导入未在有界窗口内完成：观察到 3 个条目仍为 `downloading`，2 个条目以 `KB_IMPORT_FAILED` 失败且 issue 仍为 `open`；5 个条目均没有 `paper_id`/`document_id`。同一任务的 Evidence Matrix 返回 `MATRIX_NOT_READY`，版本化 `GET /reports/1` 返回 `REPORT_NOT_READY`，因此没有把 artifact 报告冒充为 canonical `ResearchReport`，也没有声称新旧版本链接验收通过。

## 运行身份与请求

- `run_id`: `spec032-task14-research-e2e-reviewed-20261008T000748Z`
- 代码：`HEAD 4e0cec9`，分支 `codex/spec032-final-acceptance`
- 服务：`http://127.0.0.1:8000`，启动会话 `26208`；`/api/ready` HTTP 200，warmup 项均 ready
- 健康检查默认模型：`qwen3.8:27b`；本轮自然语言请求显式使用 `qwen3.5:9b`、`reasoning_effort: off`，未修改全局模型或阈值
- 自然语言请求：`POST /api/conversations/messages` HTTP 200，内容明确包含 USENIX Security 2024、security/privacy、比较至少 5 篇方法与局限、最多 5 篇、目标论文数 5、中文 Markdown/行内引用
- 真实实体：conversation `439062c163f949cb8a8f1718e4763a59`，session `da70204dd1eb46f7a48652dd2a1118b1`，intake draft `776540fdb3534165899605a985ecb88a`，task `fc83662fd8f15748b57ed7f49ad32445`

## Intake、计划与批准证据

计划版本为 `1`，`output_hash` 为 `90d76ed9b03b2873f66253426bf825b68f8eff9c8c1cbaf8d59accde0d94e43d`。解析出的显式约束和预算均为：

- `min_paper_count = 5`
- `max_paper_count = 5`
- `target_paper_count = 5`
- 计划预算 `target_paper_count = 5`

使用 `POST /api/research-sessions/{session_id}/commands` 的 `approve_plan`，`subject_version=1`、上述 hash、幂等键 `plan-approval:da70204dd1eb46f7a48652dd2a1118b1:1`。响应创建真实 task `fc83662fd8f15748b57ed7f49ad32445`，不是 mock 或伪造 ID。

## 真实执行状态

- 任务最终状态：`completed`
- 目标论文数：`5`
- 候选评估阶段选择数：`5`
- 搜索实体：`53961c1b4cf94b96a5d4c531e78c91e5`
- 选中的 catalog IDs：
  - `4e6322a23b92a271dbec9906c51fe0ab` — GhostRace
  - `57e0402f82fe2ce354bea423b201fde3` — DNN-GP
  - `9793a4a35caad52ee99f926ae7c90810` — Cascade
  - `bb826cac3486a295d93eb9b6cea0a6f8` — DARKFLEECE
  - `ef9e0846844e5b02834163586ea6ddc9` — Stop, Don't Click Here Anymore

自动导入批次 `5ab07fc9-b1ef-4a13-925e-5596997b889f` 只包含上述 5 个条目，未超过范围。最后一次受控读取显示：GhostRace、Cascade 为 `failed / KB_IMPORT_FAILED`；DNN-GP、DARKFLEECE、Stop… 为 `downloading`。失败 issue 数为 2，均 `status=open`，可用动作仅由服务返回的 `retry/upload` 决定；本轮没有重试、上传、删除或 reindex。

## 报告与可读产物

已有真实 task 报告端点：

`GET /api/research-tasks/fc83662fd8f15748b57ed7f49ad32445/report` → HTTP 200。

- `report_id`: `artifact:8e1e792c014a442ca23a0c37925ba6fb`
- `status`: `completed`
- `limitations.artifact_backed`: `true`
- Markdown 标题：`深度研究报告`
- Markdown 字符数：`7649`
- 行内 catalog 引用数：`5`
- 报告选集数：`5`

Session artifact 列表 HTTP 200，版本 `1` 提供 markdown、html 和 citation manifest。Markdown artifact 的只读查看/下载路径为：

`/api/research-sessions/da70204dd1eb46f7a48652dd2a1118b1/artifacts/8e1e792c014a442ca23a0c37925ba6fb/download?mode=attachment`

该路径实测 HTTP 200，`text/markdown; charset=utf-8`，8197 bytes。

## 阻塞边界

- `GET /api/research-tasks/fc83662fd8f15748b57ed7f49ad32445/evidence-matrix?plan_version=1` → HTTP 409 `MATRIX_NOT_READY`。
- `GET /api/research-tasks/fc83662fd8f15748b57ed7f49ad32445/reports/1?format=json` → HTTP 404 `REPORT_NOT_READY`。
- 因 Matrix 尚未就绪，本轮没有调用会必然失败的 canonical `POST /reports`，也没有生成伪造的 `ResearchReport`、版本链接或导入文档 ID。
- 报告 artifact 与导入状态分别如上；artifact 的存在不能证明 5 篇论文已成功导入，也不能替代 canonical versioned report。

## 交接建议

后续应先由 backend/recovery 角色定位 `KB_IMPORT_FAILED` 与 Matrix 未就绪的真实根因，在独立 review 和重新部署后，以全新 run 重新验证。不得沿用本轮 task 的失败导入状态冒充通过。

详细脱敏请求、响应摘要、实体 ID、状态转移、artifact 哈希和 HTTP 证据见同目录的 `current-research-e2e-reviewed-evidence.json`。未保存 API key、Cookie、`.env` 或隐藏推理。
