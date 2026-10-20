# Spec043 Task05 前端交接报告

## 状态

**前端实现可交独立复审（PASS_WITH_LIMITATIONS）**。已按冻结 Task05 合同接入地图右侧分析与会话窄接缝；未部署、未调用真实 provider/API、未运行后端 pytest、未提交代码。真实摘要级/全文级分析与会话绑定 smoke 仍由主会话在后端门禁后执行。

## 实际改动

- `frontend/literature-maps.js`
  - 论文详情加载 `GET /nodes/{node_id}/analyses`，只读展示 `source_status`、`available_evidence_levels`、`source_versions` 与历史版本；不在打开详情时创建分析任务。
  - 新增“基于摘要分析”“基于全文分析”“关于本篇提问”按钮。请求 body 严格使用 `evidence_level` + `idempotency_key`，不接受客户端 `document_id`/URL/项目覆盖。
  - 摘要缺失/全文索引未就绪时禁用对应入口并显示可行动提示；全文就绪只显示可重新分析入口，不自动替换旧摘要结果。
  - 新增分析提交、异步 job 状态读取、完成/失败/停止状态、稳定错误和 retryable“重新分析”路径；结果明确标识“仅基于摘要”或“全文索引片段依据”，逐条以纯文本展示受控来源引用。
  - 详情关闭、切图、切节点及迟到请求均受 request generation/map/node/active 守卫保护，旧分析不会回写当前面板。
  - 会话按钮调用 `POST /nodes/{node_id}/conversation` 后，只把服务端返回的 `conversation_id` 交给既有 `openConversationFromWorkspace`；不新建聊天 UI、不向普通会话入口注入任意文档 ID。
- `frontend/literature-maps.css`：新增 scoped 分析面板、状态、历史、结果与引用样式。
- `frontend/index.html`：地图资源版本升至 `literature-maps.js?v=8`、`literature-maps.css?v=6`。
- `frontend/app.js`：导出既有 `openConversationFromWorkspace` 作为地图到现有会话页面的最小导航接缝。
- `tests/frontend/fixtures/literature_map_component.html`：增加合同 shape 的合成 analyses/job/conversation fixture，覆盖失败、重试、XSS 文本和切图延迟；不作为部署或真实 E2E 证据。
- `tests/frontend/test_frontend_map_analysis_contract.py`：新增能力命名契约测试。
- `tests/frontend/test_frontend_literature_map_contract.py`、`test_frontend_literature_map_expansion.py`：同步地图资源版本断言。

## 验证记录

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js` | 退出码 0 |
| `node --check frontend/app.js` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_analysis_contract.py`（授权 Chromium） | 退出码 0；3 passed；无 skip |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py`（授权 Chromium） | 退出码 0；16 passed；无 skip |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_feasibility.py`（单独授权 Chromium） | 退出码 0；3 passed；无 skip |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_conversation_contract.py` | 退出码 0；20 passed |
| `.venv/bin/python scripts/check_test_layout.py` | 退出码 0；`test layout: ok` |
| `.venv/bin/python scripts/check_test_naming.py` | 退出码 0；无 spec/task 编号测试名 |
| `git diff --check -- frontend tests/frontend` | 退出码 0 |
| 新增 class/CSS 对照、地图模块 `rg innerHTML` 与请求 shape 自查 | 通过；地图模块无 `innerHTML`，无客户端 `document_ids` |

组合执行地图可行性回归时曾出现一次高负载手势墙时序抖动（1777ms，单独重跑 3 passed）；未改动性能基线，也未将该次抖动记录为稳定失败。

## 三项前端自查

- class 与 CSS 对应：通过；所有新增 `literature-map-analysis*` 类均有 `#literature-maps-view` scoped 样式。
- 资源版本：通过；`index.html`、fixture、静态断言均为 JS v8/CSS v6。
- XSS/动态文本：通过；分析摘要、错误、source version、引用均以 DOM `textContent` 写入；合成 `<img onerror>` 文本未执行且无 `img[onerror]`。

## 未验证、限制与下一步

- fixture 只证明前端 DOM/API 接线；尚未有真实 API 响应、真实模型/provider、真实 canonical document/index readiness、真实全文片段引用或真实 Conversation binding smoke。
- 未启动暂停中的 8000 服务，未部署，未读取 secret，未下载 PDF，未运行后端 pytest。
- 后端合同实现由并行 backend-dev 负责；若其最终字段与 `docs/sdd/plans/043/artifacts/task-05/interface-contract.md` 不一致，应先由主会话裁决合同冲突，再调整前端。
- 下一步：frontend-reviewer 复核 DOM/XSS/版本/竞态；主会话完成后端精准验证、真实摘要/全文分析及会话绑定 E2E，再决定 Task05 验收与部署。

## 交接产物

- 本报告：`docs/sdd/plans/043/artifacts/task-05/frontend-report.md`
- 前端开发日志：`.codebuddy/agent-logs/spec-043/task-05/frontend-dev/20261020-frontend.md`
- 合成组件 fixture：`tests/frontend/fixtures/literature_map_component.html`

## 复审修复追加（2026-10-20）

### BLOCK 修复

- `frontend/index.html`：`app.js` live 资源版本由 v58 升至 v59；对应地图合同断言同步要求 v59，避免新增会话导航导出命中旧缓存。
- `frontend/literature-maps.css`：补齐 `.literature-map-analysis-history-item` 及可点击历史按钮的 scoped 样式，恢复 DOM class/CSS 双向契约。
- `frontend/literature-maps.js`：历史版本由只读文本改为可点击按钮，维护选中的 `analysis_id` 并渲染该版本旧 `result.summary`；旧结果不会被新分析覆盖。分析轮询达到 120 次时保留 queued/running，不伪造 failed，不自动 POST 新分析，显示“后台分析仍在运行；已暂停自动查询”及“重新查询”按钮；重新查询仅重置 GET 轮询窗口并复用原 analysis/job 句柄。
- `tests/frontend/fixtures/literature_map_component.html`：增加双历史版本和连续 running 的轮询上限场景；轮询测试 timer 仅为 fixture 加速，不代表生产行为。
- `tests/frontend/test_frontend_map_analysis_contract.py`：新增旧摘要点击查看、轮询上限提示/重新查询且 POST 次数保持 1 的精准断言；同步 app.js v59 与 history-item CSS 静态断言。

### 修复后验证

| 命令 | 结果 |
|---|---|
| `node --check frontend/literature-maps.js && node --check frontend/app.js` | 退出码 0 |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_map_analysis_contract.py`（授权 Chromium） | 退出码 0；4 passed；无 skip |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_literature_map_contract.py tests/frontend/test_frontend_literature_map_expansion.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_feasibility.py tests/frontend/test_frontend_conversation_contract.py`（授权 Chromium） | 退出码 0；40 passed；无 skip |
| `git diff --check -- frontend tests/frontend` | 退出码 0 |

复审遗留限制不变：未部署、未调用真实模型/provider/API、未运行后端 pytest；fixture 和精准浏览器回归不替代真实摘要/全文分析及会话绑定 smoke。
