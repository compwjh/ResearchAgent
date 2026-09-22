# Spec032 Task09 Worker Tool 合同

日期：2026-09-20

## 结论

统一 Worker Tool 名为 `paper_discovery`，机器可读 envelope 版本为 **`worker-tool-v1`**。它只接受注册来源与两种操作：`discover`、`import`。来源专用 Skill 只规定调用顺序和停止条件；网络、缓存、来源解析、URL 安全、PDF 下载和 KB 导入仍复用既有实现。

实现文件：

- `backend/app/paper_discovery/application/worker_tool.py`：`PaperDiscoveryToolFacade`、`WorkerToolResult`、`validate_worker_tool_result` 和冻结的 `WORKER_TOOL_SCHEMA`。
- `backend/app/skills/registry.py`：注册 `paper_discovery`，entry 指向 facade 的真实方法。
- `backend/app/skills/tool_dispatch.py`：将 Tool 输出为 JSON envelope，未注册来源/操作不会进入既有来源路径。
- `.agents/skills/ieee-sp-catalog-orchestration/SKILL.md`
- `.agents/skills/ccs-catalog-orchestration/SKILL.md`
- `.agents/skills/ndss-catalog-orchestration/SKILL.md`
- `.agents/skills/usenix-catalog-orchestration/SKILL.md`、`usenix-download-orchestration/SKILL.md`：增加统一 Tool 入口，保留旧兼容 Tool。

## 请求 schema（冻结）

```json
{
  "type": "object",
  "properties": {
    "operation": {"type": "string", "enum": ["discover", "import"]},
    "source_id": {"type": "string", "enum": ["usenix", "dblp", "ieee_sp", "ccs", "ndss", "openalex", "crossref"]},
    "scope": {"type": "object"},
    "candidate": {"type": "object"}
  },
  "required": ["operation", "source_id"],
  "additionalProperties": false
}
```

`discover` 的 `scope` 只允许 `query`、`years`、`limit`、`publication_scope`、`route`、`conference_id`；不允许 URL、Cookie、Authorization、Token 或自定义根地址。`import` 的候选必须携带标题，并且来源必须与请求的 `source_id` 一致。候选中的 URL 仍逐个通过服务器固定白名单；不会从候选 URL 推导 allowlist。

## 返回 schema（冻结）

每次调用都包含以下公共字段；没有候选时 `candidate_id` 为 `null`，错误时 `error` 为对象或 `null`。

```json
{
  "schema_version": "worker-tool-v1",
  "tool": "paper_discovery",
  "operation": "discover",
  "source_id": "ieee_sp",
  "status": "completed",
  "candidate_id": null,
  "provenance": {
    "ieee_sp:doi:10.1/example": {"title": "ieee_sp", "year": "ieee_sp"}
  },
  "payload": {
    "source_result": {
      "schema_version": "source-contract-v1",
      "source_id": "ieee_sp",
      "operation": "discover",
      "status": "completed",
      "scope": {"years": [2024], "route": "official"},
      "coverage": {"candidate_count": 1},
      "papers": [],
      "error": null,
      "artifact_handles": {},
      "elapsed_ms": 0
    },
    "candidates": []
  },
  "error": null,
  "elapsed_ms": 3
}
```

`error` 固定为 `{ "code": "...", "retryable": false, "message": "..." }`（message 可省略）；不持久化异常 repr。导入成功的 `payload.import_result` 使用既有 `ImportResult` 的 `source-contract-v1`，必须包含稳定 `candidate_id` 与可信 `document_id`。

## 来源执行样例与证据边界

| Skill | discover 输入 | 当前证据 | import 行为 |
|---|---|---|---|
| USENIX | `source_id=usenix`, `query + years` | 复用既有 USENIX accepted/DBLP 受控路径 | 只接受候选冻结链接，复用既有安全导入 |
| IEEE S&P | `source_id=ieee_sp`, `years=[2024]`, `route=official` | Task07 `verified_sample`；其它年度不得冒充已验证 | IEEE 链接未被服务器白名单授权时返回 `UNAUTHORIZED_URL`，保持 blocked |
| ACM CCS | `source_id=ccs`, 批准年份 | 官网覆盖当前 `NO-GO`，只能如实 partial/blocked | 复用安全导入，失败保留 retryable |
| NDSS | `source_id=ndss`, 批准年份 | 官网覆盖当前 `NO-GO`，只能如实 partial/blocked | 复用安全导入，失败保留 retryable |

验证器 `validate_worker_tool_result` 对 USENIX 与 IEEE S&P 2024 使用同一版本/字段规则；它不会因来源不同放宽 schema。

## 失败与明确不做

- 未知来源、停用来源、未知操作、候选来源不匹配和任意 URL：fail-closed，返回稳定错误码。
- Skill 不包含抓取脚本、HTML/PDF 解析、缓存、登录、下载器或研发/Git 调度规则。
- 未改 frontend、Research Graph 大重构、模型路由或报告。

## 验证记录

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_spec032_task09_worker_tools.py` | 4 passed，退出码 0 |
| `.venv/bin/python -m pytest -q tests/test_tool_registry.py tests/test_tool_executor.py tests/test_skill_registry.py tests/test_usenix_detail_tool.py tests/test_fetch_paper_detail_dispatch.py tests/test_spec032_task06_contract.py tests/test_spec032_task07_official_catalog.py tests/test_catalog_runtime.py` | 128 passed，21 subtests passed，退出码 0 |
| `.venv/bin/python -m py_compile backend/app/paper_discovery/application/worker_tool.py backend/app/skills/registry.py backend/app/skills/tool_dispatch.py` | 通过，退出码 0 |
| `.venv/bin/ruff check backend/app/paper_discovery/application/worker_tool.py backend/app/skills/registry.py backend/app/skills/tool_dispatch.py` | 通过，退出码 0 |
| `git diff --check` | 待 Task09 收口时复跑 |

## 风险与主 Agent 下一步

IEEE S&P 2024 已有官网样本，但其 PDF/登录导入链尚未在本 Task 宣称完成；CCS/NDSS 官网年份保持未验证。主 Agent 应复核 facade 的真实应用 Store 注入、跑完整受影响来源回归和 `git diff --check`，再决定是否将 Task09 标记完成并进入 Task10。
