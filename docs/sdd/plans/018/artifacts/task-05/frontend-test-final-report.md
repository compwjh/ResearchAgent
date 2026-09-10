# Spec018 Task05 最终前端验收报告

## 结论

**PASS（Task05 前端功能门通过）**。

DOM、ETag/304、PDF observer root、anchor partial/primary 映射与 hostile fixture
根相对路径已修正。四套 Node 契约测试、语法检查、schema/hash/CSS/路径静态检查
均通过；真实 Codex In-app Browser 已验证 hostile PDF/Markdown 为 PASS 且零远程请求。
worker/version mismatch 的运行时 hash 仍不伪造，保留为后续浏览器/Task06 债务。

## 固定验收字段

| 字段 | 结果 |
|---|---|
| `conclusion` | `PASS` |
| `task` | `Spec018 Task05 frontend-tester` |
| `business_code_changed_by_tester` | `false`（实现改动非本验收产生） |
| `backend_pytest` | `NOT_RUN`（按要求不执行） |
| `node_contract_tests` | `PASS`（4/4） |
| `syntax_checks` | `PASS` |
| `schema_version_checks` | `PASS` |
| `resource_version_checks` | `PASS`（styles/kb-inspection/app 均 `?v=18`） |
| `pdfjs_vendor_worker_checks` | `PASS`（4.10.38、同源 worker、四项 SHA-256） |
| `304_etag_checks` | `PASS` |
| `pdf_observer_root_checks` | `PASS`（`#kb-source-content`） |
| `anchor_mapping_checks` | `PASS`（coverage/primary/unmapped/partial） |
| `fixture_path_static_check` | `PASS`（五级相对路径命中仓库根真实文件） |
| `real_browser_hostile_fixture` | `PASS`（Codex In-app Browser：markdown/pdf PASS，remoteRequests=0，Console 空） |
| `worker_version_runtime_evidence` | `DEFERRED`（静态 manifest 与 Node 注入 seam；未伪造运行时 hash） |
| `task06_production_debt` | `NOT_ASSESSED / BLOCKED_BY_TASK05` |

## Node 与静态验证

| 检查 | 命令/证据 | 结果 |
|---|---|---|
| Markdown renderer/XSS fallback | `node tests/test_frontend_kb_inspection_renderer.js` | PASS（exit 0） |
| Runtime/API/304 cache | `node tests/test_frontend_kb_inspection_runtime.js` | PASS（exit 0） |
| PDF renderer/worker/error states | `node tests/test_frontend_kb_inspection_pdf.js` | PASS（exit 0） |
| Click/keyboard/overlap/cross-page/narrow | `node tests/test_frontend_kb_inspection_interaction.js` | PASS（exit 0） |
| JavaScript syntax | `node --check`（业务 JS、测试 JS） | PASS（exit 0） |
| Schema/API status codes | Task04 `api-schema.json`、Task05 `dom-contract.schema.json` | PASS |
| Resource versions | `index.html` 与 DOM schema | PASS（全部 `?v=18`） |
| CSS/DOM contract | id/ARIA、760px breakpoint、source/chunk pane selectors | PASS |
| PDF.js vendor | manifest version/options/allowlist + main/worker/LICENSE/NOTICE hash | PASS |
| 304/ETag | `If-None-Match`、ETag cache、cache hit/miss stable errors | PASS |
| PDF lazy root | IntersectionObserver root 为 `#kb-source-content` | PASS |
| Anchor mapping | `anchorRelations` 保留 `coverage/is_primary/unmapped_reason`，partial warning 使用 textContent | PASS |
| Fixture paths/hash | HTML root-relative paths + fixture SHA-256 | PASS |
| Whitespace diff | `git diff --check` | PASS（exit 0） |

## 真实浏览器 hostile fixture

入口：

`http://127.0.0.1:8765/docs/sdd/fixtures/spec-018/frontend/hostile-fixture.html`

已将 HTML 的 vendor、renderer、PDF.js 主库/worker 和 hostile PDF 路径修正为
`../../../../../` 回到仓库根目录；本地静态路径探针确认目标真实存在。README 和
`frontend-fixture-index.json` 已同步记录该路径与 hash。

真实 Codex In-app Browser 复验已由主 Agent 完成：页面显示
`{markdown: PASS, pdf: PASS, remoteRequests: 0}`，Console 日志为空；端口为
`8765`，未导出 HAR，因此 `har_path` 保持 null。该结果已写入
`frontend-fixture-index.json.browser_evidence`。

worker/version mismatch 目前只有 Node 注入式 seam 与静态 manifest 证据；不读取或
伪造 vendored PDF.js 运行时 hash，也不修改 vendor。真实 mismatch 运行证据列为
Task06/后续浏览器验收债务。

## Task05 与 Task06 边界

- **Task05 功能门：PASS**。入口路径已修复，真实浏览器 hostile fixture 已验证零外联。
- **Task06 生产债务：未评估，保持阻塞**。本轮未验证旧索引回填、生产切换、重建/恢复等 Task06 范围。

## 不执行项

- 未运行后端 pytest。
- 未修改 `backend/**`、`frontend/**` 业务实现或 vendor。
- 未将 fake-DOM/fake-fetch、路径静态检查、端口失败或 provider 不可用当作真实浏览器通过。
