# Spec018 KB 重建入口前端独立复审

> 当前收口状态：本次 canonical ID/partial 展示窄修已完成；本报告历史复审结论保留，最终 tester/architect 窄修签字见 [`../../reviews/018-acceptance-review.md`](../../reviews/018-acceptance-review.md)。

复审日期：2026-10-26
复审分支：`codex/fix-kb-reindex-contract`
复审范围：只评审 `frontend/app.js` 的 KB 重建入口及 ID/错误辅助函数、`frontend/index.html` 资源版本和 `frontend/contract-tests/kb-reindex-failure-recovery.test.mjs`；不修改后端、不运行 backend pytest、不执行真实或生产 POST。

## 复审结论

**PASS（P0=0，P1=0，P2=0）**。本轮已闭合前一轮发现的两项 P1：成功响应必须同时满足 HTTP 202 与非空字符串 `task_id`；防重复锁按 canonical/legacy 归一后的文档 ID 存在于模块级集合，不依赖当前 DOM 按钮。失败、重绘、重试和不同文档并行场景均有可执行合同测试覆盖。

主会话仍需按 Spec018 计划执行唯一一次真实 canonical API 验收；本报告不把 mock、浏览器路由拦截或静态合同当作真实生产成功。

## 当前通过项

- `kbDocumentId()`（`frontend/app.js:5933-5941`）优先读取 canonical `document_id`，仅在旧 DTO 缺失时回退 `paper_id`；空 ID 在 `rebuildKbPaper()`（`:5965-5970`）直接提示“未提交请求”，不发 POST。
- 重建请求（`:5980-5985`）使用 `POST /api/kb/documents/{document_id}/reindex`，路径做 `encodeURIComponent`，请求体严格为 `{ "chunker": "all" }`。
- 成功只接受 `response.status === 202` 且 `task_id` 为非空字符串（`:5988-6001`）；200、204、202 缺任务 ID 和 202 JSON 解析失败均进入失败文案，不显示“已提交重建”。
- `kbReindexError()`（`:5943-5953`）覆盖 canonical 顶层 `error_code`/`message`/`status`，兼容嵌套 `error`、`detail` 和字符串 `detail`；`kbReindexFailureText()`（`:5956-5963`）对 409 `INDEX_ALREADY_RUNNING` 或 `status=running` 显示可行动忙碌提示。
- `kbReindexInFlight`（`:5931`）按文档 ID 加锁（`:5971-5976`），因此列表轮询/重绘后新按钮不能再次提交同一文档，而不同文档仍可并行。`finally` 先等待列表刷新，再无条件释放对应 ID（`:6007-6015`），失败后可重试。
- 状态与错误均使用 `textContent`；未引入 `innerHTML`、下载、模型调用或额外接口。上传、删除和用户草稿逻辑未改。列表额外写入 `data-document-id`（`:6050-6059`）不改变既有 `.kb-item-rebuild`/`.kb-item-remove` 结构。
- `frontend/index.html:786` 的 live app bundle 为 `app.js?v=61`，styles 继续为 `styles.css?v=61`；地图版本保持既有 `literature-maps.js?v=21` / `literature-maps.css?v=13`。

## 前一轮 BLOCK 与闭环证据

前一轮复审识别了两个 P1：缺任务 ID 的任意 2xx 会伪报排队成功；按钮级锁在列表重绘后可被替代按钮绕过。本轮合同测试先在旧实现上得到 18 项中 15 通过、3 项失败，然后实现最小修复并全部转绿。新增覆盖：

1. 202 缺 `task_id`、200 带 `task_id`、204 空响应、202 malformed JSON，均不得出现成功文案；
2. 请求 pending 时手动重绘列表并点击同 ID 新按钮，POST 仍为 1；
3. 首次 503 失败后锁释放，重绘出的后续按钮可以再次提交；
4. 不同 `document_id` 不共享锁，两个请求均可提交。

## 实际验证记录

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | JavaScript 语法通过 |
| `node --test frontend/contract-tests/kb-reindex-failure-recovery.test.mjs` | 0 | 18 passed，0 failed；包含旧失败态回归与 P1 合同 |
| `node --test frontend/contract-tests/context-meter-and-kb-count.test.mjs frontend/contract-tests/kb-reindex-failure-recovery.test.mjs` | 0 | 26 passed，0 failed |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_paper_contract.py` | 0 | 23 passed |
| `python scripts/check_test_naming.py` | 0 | passed；测试按被测能力命名，无 spec/task 编号 |
| `python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `.venv/bin/python -m pytest --collect-only -q` | 0 | 3407 tests collected，0 collecting error |
| `git diff --check` | 0 | 无空白错误或冲突标记 |

隔离 Chromium smoke 在前一阶段已验证生产 `index.html` + 真实 `app.js` 的 canonical URL/body 与双击单 POST 行为；本轮新增 P1 的竞态与异常矩阵由真实 `app.js` VM 合同直接覆盖。未运行 backend pytest、未发送真实 reindex POST、未部署。

## 读回与角色检查

- 读回确认 production script 为 `/assets/app.js?v=61`，styles 为 `/assets/styles.css?v=61`。
- 读回确认 reindex 只有 canonical document endpoint，固定 `{chunker: 'all'}`，无旧 `/api/kb/papers/{id}/reindex` 调用。
- 读回确认锁 key 来自归一后的文档 ID，不来自 `button.dataset`；`finally` 覆盖 HTTP 错误、响应状态错误、任务 ID 缺失和 JSON 解析失败。
- 读回确认新增测试文件名按能力命名：`kb-reindex-failure-recovery.test.mjs`；未运行 backend pytest。
- 未改后端公开 API、安全策略、上传、删除、生产版本之外的资源版本或用户草稿。

## 交接

前端 P1 复审通过。请 root 在最终评审后按 Spec018 计划对指定 canonical 文档执行唯一一次真实 API 验收，并落盘 HTTP 202、非空 `task_id`、v1/v2 终态与产物路径；真实验收前不得把 Spec 标记为完成。

## 本角色独立复审追记（2026-10-26）

本节是本角色对当前实际 diff 的独立复核，保留上方 author/协作记录，不以其测试数字作为本角色证据。

### 独立结论

**GO（P0=0，P1=0，P2=0；仅限本次 KB 重建前端增量）**。

- P1-01 通过：当前成功分支（`frontend/app.js:5988-6002`）严格要求 HTTP 202 与非空、trim 后的字符串 `task_id`；缺 ID、错误 JSON、204 或非 202 均走失败文案。
- P1-02 通过：`kbReindexInFlight`（`:5931`）按 canonical/legacy 归一后的 document ID 加锁；重绘后的替代按钮仍被阻止，不同 document 可并行，失败路径在列表刷新后释放锁并允许重试。
- canonical endpoint/body、零 ID 零 POST、409 running 非成功、结构化 message/code、XSS/版本、上传/删除/用户草稿边界均未见回归。

### 本角色独立验证

- `node --test frontend/contract-tests/kb-reindex-failure-recovery.test.mjs`：退出码 0，18 passed。
- `node --test frontend/contract-tests/context-meter-and-kb-count.test.mjs frontend/contract-tests/kb-reindex-failure-recovery.test.mjs`：退出码 0，26 passed。
- `.venv/bin/python -m pytest --confcutdir=tests/frontend -q tests/frontend/test_frontend_paper_contract.py`：退出码 0，23 passed。
- `node --check frontend/app.js`、`python scripts/check_test_naming.py`、`python scripts/check_test_layout.py` 和目标 `git diff --check`：均退出码 0。

未运行 backend pytest、真实 API、服务/部署或生产 POST；GO 不替代 root 对指定 canonical 文档的唯一一次真实重建验收，也不代表 Spec018 已完成。

## 本角色独立复审增量追记（2026-10-26 `indexed_partial`，最终）

本节针对当前实际工作树在上述 P1 闭环后的窄范围增量独立复核；范围为 `frontend/app.js`、`frontend/styles.css`、`frontend/index.html`、`frontend/contract-tests/kb-reindex-failure-recovery.test.mjs` 及受影响 `tests/frontend` 版本契约。未改业务代码，未运行 backend pytest、真实 API/生产 POST 或部署。

### 独立结论

**GO（P0=0，P1=0，P2=0；仅限 Spec018 KB 重建前端增量）**。

- `document_id` 优先、`paper_id` 仅作旧 DTO 回退、canonical endpoint/body、HTTP 202 + 非空字符串 `task_id` 门禁，以及模块级 document-level in-flight 锁均保持通过；本轮 partial 展示未改变重建策略，渲染真实 DTO 不产生额外 POST。
- 真实 `indexed` 顶层 + v1 `indexed`/107 + v2 `indexed_partial`/297 + `SOURCE_RANGE_UNRESOLVED` DTO 被正确投影：保留顶层“已索引”元数据和两版徽章，增加 scoped `status-indexed_partial`/amber 样式及中文提示“部分切片无法精确定位原文，已保留可用索引；可进入切片检查”，不误判为失败或全量成功。
- 原始原因码只写入 DOM `title`；新增/变更动态内容使用 `textContent`、`dataset`、属性赋值或 `encodeURIComponent`，未引入新的 `innerHTML`/HTML 拼接 XSS sink。
- `frontend/index.html` 的 live bundle/styles 为 `app.js?v=62` / `styles.css?v=62`；literature map 资源仍为 `literature-maps.js?v=21` / `literature-maps.css?v=13`，fixture 与受影响静态契约同步。

### 本轮精确验证证据

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `node --check frontend/app.js` | 0 | JavaScript 语法通过 |
| `node --test frontend/contract-tests/kb-reindex-failure-recovery.test.mjs` | 0 | 19 passed，0 failed，0 skipped；含真实 `indexed_partial` DTO 合同 |
| `node --test frontend/contract-tests/context-meter-and-kb-count.test.mjs frontend/contract-tests/kb-reindex-failure-recovery.test.mjs` | 0 | 27 passed，0 failed，0 skipped |
| `.venv/bin/python -m pytest -q tests/frontend/test_frontend_paper_contract.py tests/frontend/test_frontend_composer_layout.py tests/frontend/test_frontend_map_analysis_contract.py tests/frontend/test_frontend_map_mobile_contract.py` | 0 | 46 passed，0 failed |
| `.venv/bin/python scripts/check_test_naming.py` | 0 | `test naming check passed` |
| `.venv/bin/python scripts/check_test_layout.py` | 0 | `test layout: ok` |
| `git diff --check -- frontend/app.js frontend/styles.css frontend/index.html frontend/contract-tests/kb-reindex-failure-recovery.test.mjs tests/frontend` | 0 | 通过，无空白/冲突标记错误 |

前端增量复审无需提出修复项。GO 不替代 root 对指定 canonical 文档执行唯一一次真实 API 验收，也不代表 Spec018 已完成；真实验收仍须记录 HTTP 202、非空任务 ID、v1/v2 终态和产物路径。
