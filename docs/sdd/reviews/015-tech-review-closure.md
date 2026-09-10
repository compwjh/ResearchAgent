# Spec015 Task09 收口技术复核

- 评审者：当前协作 Agent
- 角色：开发主管（Tech Lead）
- 评审时间：2026-09-05 01:35（Asia/Shanghai）
- 评审范围：Spec015、`plans/015/README.md`、Task02–09 状态、Task02–08 全部验收/技术复核产物、当前分支与工作树、自动化回归、编译/冲突/空白检查、部署可复现性
- 约束：只读复核；未修改业务代码、测试或配置；未执行 commit、push、reset、stash、clean
- 进展日志：`.codebuddy/agent-logs/techlead-spec015-task09-closure-20260905.md`

## 结论：阻塞，暂不通过

Spec015 当前不能收口，必须保持 `实施中`。离线实现与自动化回归已有较充分证据，但 Gate 5 的正式验收、真实外部链路和排序质量门禁仍未完成。尤其不能把用户明确授权 deferred 的 Task04 rerank、DBLP Venue Search/自定义会议、真实 ACM/IEEE/GUI 当作通过条件。

## 一、当前可收口项与仍未完成项

### 已有真实交接证据、可作为部分收口基础

| 范围 | 当前判断 | 证据 |
|---|---|---|
| Task02 | 条件放行，不是 Full Go | `015-task02-tech-review.md`：仅放行内置会议 publication search/OpenAlex；Venue Search 无成功 live 样本，保持 blocked |
| Task03 | 通过（收窄范围） | `015-task03-tech-review-final-signoff2.md` 与 tester 报告；41 项定向测试通过，内置会议召回/过滤/去重/OpenAlex/API 已签核 |
| Task05 | 通过（单篇/安全下载范围） | `015-task05-tech-review-recheck-final.md`、`015-task05-acceptance-review-final.md`；150 passed、修复项 11 passed、并发幂等 10/10 轮 |
| Task06–08 | 离线切片通过或部分通过，整体验收未通过 | 最新报告均保留真实登录、排序质量、GUI/外部链路或兼容性缺口，不能把切片报告升级成任务完成 |

### 收口硬阻塞

1. **Task04/A4/A14 未执行（用户授权 deferred，但仍是硬验收缺口）**。`task-04-semantic-ranking-and-rerank.md` 仍为 `待执行`；当前 `backend/app/services/paper_discovery_search.py:245-252` 的 `_score` 仍是 `SequenceMatcher` 词法分数。没有 Spec015 专属冻结的至少 12 条查询、候选快照、人工标签、时间/hash、逐查询及总体 nDCG@10/Recall@10。因此不得以 tie-break 单测或用户授权把 A4/A14 判为通过。
2. **A3 DBLP Venue Search/自定义会议阻塞**。Task02 记录 live `venue/api` 仅有 429/503，无成功样本；当前后端只有 `GET /api/papers/conferences/search`，没有 `POST /api/papers/conferences` 新增闭环。不能宣称会议搜索、新增、修改、停用全链路通过。
3. **A10/A11 真实 ACM/IEEE 登录续传阻塞**。最新 Task06/Task07/Task08 报告均确认 `.venv` 无 `playwright` 模块，且没有可核验的合法 ACM/IEEE 账户与受保护 PDF 样本。fake parser/browser、固定错误码和离线安全测试不替代 headed 登录续传。
4. **真实 GUI/窄屏验收缺失**。静态 DOM、Node 语法和契约测试不能证明 A1/A2/A7–A9 的实际交互、首屏开关隐藏、Tab/ARIA、键盘焦点、长内容窄屏布局和批次状态展示。当前 `frontend/index.html:19` 的论文导航初始仍可见；`frontend/app.js:351-357` 在没有注入 flag 时默认 `true`，存在 health 异步响应前的首屏闪现风险。
5. **真实公开 PDF/知识库链路与旧 KB 物理端到端缺失**。现有报告主要是 MockTransport/fake indexer 和旧记录单元测试；尚无真实公开 PDF 下载、真实知识库检索对账，也无真实旧 `papers.json` + `{paper_id}.pdf` 贯穿列表/检索/重建/删除的集成矩阵。
6. **正式 Gate 5 交付物未齐**。Spec 仍引用 `docs/sdd/reviews/015-acceptance-review.md`，但该文件当前不存在。Task06/07/08 的 tester 报告分别给出不通过/阻塞或部分通过结论，且没有一份 Spec015 全量 A1–A15 验收报告由 tester 出具并由 Tech Lead 签字。`docs/sdd/retro/` 下也未发现 Spec015 收口复盘文件（本复核不代行复盘）。
7. **本轮部署不可复现**。Task09 文档保留历史“首页/health/会议列表 200”的文字证据，但没有独立部署日志；本轮对 `127.0.0.1:8000/`、`/api/health`、`/api/papers/conferences` 的连接均失败（HTTP 000），因此不能将当前服务视为已运行并通过 A15。

## 二、机械与运行复核

| 检查 | 本轮结果 | 判定 |
|---|---|---|
| 分支/基线 | `feature/spec-015-security-paper-discovery`，HEAD=`c17c7f4`（与 `main` 同 commit） | 分支目标正确；未提交实现仍在工作树 |
| 工作树范围 | 检查时 104 项：23 个已跟踪修改、81 个未跟踪；本报告新增后当前为 106 项（23 个已跟踪修改、83 个未跟踪），包含后端、前端、测试和 SDD 产物 | 范围尚未形成可提交的收口提交；不执行提交以避免掩盖阻塞 |
| `git diff --check` | 退出码 0 | 通过 |
| 冲突标记扫描 | 排除 `.git`/`.venv`/vendor 后 0 命中 | 通过 |
| 论文/批次/下载安全定向回归 | `112 passed, 5 warnings, 9 subtests` | 离线切片通过；不等于真实验收 |
| 全量 pytest | `521 passed, 5 warnings, 38 subtests`，退出码 0 | 自动化回归通过；不解除外部与质量门禁 |
| Python 编译 | `.venv/bin/python -m compileall -q backend tests`，退出码 0 | 通过 |
| Playwright | `.venv/bin/python` 中 `find_spec("playwright")` 为 `None` | A10/A11/真实 GUI 环境阻塞 |
| 运行时 smoke | 8000 端口有系统监听记录，但本轮三次 curl 均无法连接，HTTP 000 | 本轮无可复核部署/health 证据 |
| 已跟踪敏感运行产物 | 未发现 browser profile、Cookie、HAR、trace、video、项目运行 PDF 或日志；仅有 vendor 测试 PDF | 当前 Git 产物扫描通过；不替代 profile 内容和真实浏览器审计 |

## 三、A1–A15 收口判定

| 验收点 | 收口判定 | 当前依据/缺口 |
|---|---|---|
| A1 独立入口 | 部分通过，不能签收 | API/静态契约有证据；真实 GUI、首屏关闭无闪现和在途行为未验 |
| A2 默认范围 | 部分通过，不能签收 | 配置/单测存在；无真实 GUI 与完整冻结契约 |
| A3 自定义会议 | **阻塞** | Venue Search 无成功样本，新增 POST 闭环不存在 |
| A4 语义检索 | **阻塞** | Task04 待执行，当前为词法 `_score`，无 embedding/rerank 质量证据 |
| A5 主会过滤 | 部分通过 | 有混流 fixture；缺四会完整冻结结果和新鲜 live 快照 |
| A6 降级 | 部分通过 | DBLP/OpenAlex/fake browser 错误码通过；缺 reranker 与公开 PDF 实链路 |
| A7 单篇导入 | 部分通过 | 安全下载/命名/补偿离线通过；缺真实公开 PDF 与 KB 检索对账 |
| A8 批量导入 | 部分通过 | 状态机/租约/并发 CAS 离线通过；缺真实服务重启和 UI 状态证据 |
| A9 去重幂等 | 部分通过 | 单元和注入并发测试通过；缺数据库、文件、索引三介质真实闭环 |
| A10 ACM 登录 | **阻塞** | Playwright 与合法账号/受保护样本缺失 |
| A11 IEEE 登录 | **阻塞** | Playwright 与合法账号/受保护样本缺失 |
| A12 命名兼容 | 部分通过 | 旧字段/路径单测通过；缺旧物理文件端到端矩阵 |
| A13 安全异常 | 部分通过 | 离线 SSRF/PDF/脱敏矩阵通过；真实 DNS rebinding、peer/浏览器链路未验 |
| A14 排序质量 | **阻塞** | 冻结标注集、hash、nDCG/Recall 结果不存在 |
| A15 回归交付 | **不通过** | 当前全量自动化绿灯，但没有本轮可连接服务、真实 GUI/公开 PDF/登录、A14 和完整旧 KB 证据 |

## 四、Gate 5 与收口清单裁决

- 任务状态虽在 spec、`plans/015/README.md` 与各 task 文档间基本一致，但必需任务并非全部 `已完成`：Task04=`待执行`，Task06–09=`实施中`。
- 需求评审和设计技术评审文件存在且有历史真实结论；这不替代验收评审。
- Spec 引用的正式 `015-acceptance-review.md` 不存在，且验收报告没有 Tech Lead 全量签字；收口清单“验收签字”未勾。
- `spec-status-changelog.md` 已记录 Task09 进入实施中，但没有 Spec015 → 已完成条目；这符合当前阻塞状态。
- Spec015 专属复盘尚未发现；收口清单“复盘已落盘”未勾。
- 当前不应将 spec、README、Task06–09 改为完成，也不应创建本地收口 commit。保留现状并等待真实门禁证据。

## 五、解除阻塞的最小条件

1. 用户授权 deferred 的 Task04 仍需明确作为后续硬门禁：执行排序实现，先冻结标注集，再由 tester 输出可追溯 nDCG/Recall 与降级证据。
2. DBLP Venue Search 恢复后取得成功 live 样本，再实现/验收自定义会议新增与完整配置链路；在此之前保持 A3 blocked。
3. 在受控环境安装固定版本 Playwright，由用户使用合法 ACM/IEEE 权限完成 headed 登录、受保护 PDF 续传及无凭证日志/产物审计。
4. 完成真实 GUI/窄屏、公开 PDF→KB、旧物理 KB 集成矩阵，并在实际启动服务上复验首页、health、会议、搜索、单篇/批量导入和 KB 查询。
5. tester 形成真实存在的 `docs/sdd/reviews/015-acceptance-review.md`，逐项覆盖 A1–A15；Tech Lead 在同一报告中签字后，才可按收口清单更新状态、复盘并提交。

## 签字

- 开发主管（Tech Lead）：**阻塞，暂不通过**
- 签字时间：2026-09-05 01:35（Asia/Shanghai）
