# 知识库重建入口canonical ID修复

状态：本次 `canonical ID` 衔接与单文档发布一致性窄修已完成（2026-10-26；tester READY_FOR_USER、architect GO）。沿 Spec018 已有 canonical 文档及单文档重建合同修复，不新增 Spec 或改变后端接口；原始失败与历史未完成边界保留。

## 已确认事实

截图文档`d4dfd2a620384ad5bece27320661f8f0`的最终复验结果为 v1=107、v2=308；v2 manifest 状态为 `partial`（292 mapped、16 `SOURCE_RANGE_UNRESOLVED`），Qdrant v2 也为 308，且 extra/missing/payload mismatch 均为空。列表DTO返回`document_id`，旧rebuildKbPaper却取paper_id，且错误只读取detail。既有索引存在不代表重建按钮正确；最终复验的实际证据已单独落盘。

## 范围与执行

frontend-dev修复身份衔接及结构化错误/忙碌提示；frontend-reviewer独立复审，frontend-tester跑精确浏览器/静态测试；主会话负责一次真实文档重建与实际任务/产物证据。测试按能力命名，不带Spec/Task编号，放tests/frontend。历史执行记录保留Luna max；本次追加临时Luna xhigh，不修改角色配置。KB上传/删除、全库索引、记忆页、登录恢复不混入本次代码。

## 验证与交付

canonical-onlyDTO→点击重建→正确document_id/现有请求体；缺ID无请求；必要旧DTO合同；202排队与结构化错误；不会重复提交或把失败显示成功。真实部署一次重建截图目标，保存请求/响应/任务ID与v1/v2终态；未通过保持实施中。人工步骤须包括打开知识库→找到指定论文→重建→排队提示→等待进度→查看完成/失败及恢复。不删除或全库重建，不push或合main。

## 产品使用步骤与人工验收

以下步骤只验证“单文档重建入口”与用户可见恢复路径，不把隔离测试或历史运行记录当作当前真实任务的完成证明。

1. **打开目标文档**：打开当前部署的服务首页，点击左侧“知识库”，在“论文 RAG”列表找到 `How to Peel a Million- Validating and Expanding Bitcoin Clusters.pdf`。确认该行显示稳定文档身份；本轮目标 canonical `document_id` 为 `d4dfd2a620384ad5bece27320661f8f0`。
2. **提交重建**：在目标文档行点击“重建索引”（失败态则点击“重试”）。等待页面状态出现“已提交重建：…（v1 + v2，任务 <task_id> 已排队）”。这一步只允许一次有效 POST；不得连续双击，也不得使用缺失 ID 的行。
3. **确认排队证据**：只有 HTTP `202` 且响应带非空 `task_id` 才算排队成功；若看到“重建进行中：已有索引任务正在运行，请稍后查看进度”，先停止点击并等待；若看到“重建失败：…”或“重建响应缺少有效任务 ID”，保留错误文案和时间，不写成成功。
4. **等待并查看版本状态**：返回或刷新知识库列表，点击“切片检查”，在“文档”下拉框重新选择目标文档，先点 v1、再点 v2，等待“正在加载检查清单…”结束。检查器只展示已发布的真实 manifest；遇到“索引正在完成切换，检查器暂时只读”时等待切换结束，不删除文件、不触发全库重建。
5. **部分完成的预期与最终复验**：首轮真实证据曾显示 v1 为 `ready/indexed`（107 个切片），v2 为 `partial`（297 个 manifest 切片，其中 277 个可定位，20 个因图表/表格碎片显示 `SOURCE_RANGE_UNRESOLVED`），并发现 Qdrant 多出 11 个旧尾点；该首轮失败证据保留在旧产物中。随后第二次真实 v2 复验得到不同的实际切分结果：v1=107，v2 manifest=308，v2 `partial` 为 292 mapped、16 unmapped，原因均为 `SOURCE_RANGE_UNRESOLVED`；Qdrant v2=308，extra/missing/payload mismatch 全为空。两次的 297/20 与 308/16 不得伪称相同结果。UI 已核对 v2 显示“部分索引”及中文不可定位原因；不能仅因顶层文档显示 `indexed` 就把 v2 当作完整 ready，v2 的未映射项必须保留告警。
6. **最终复验边界**：此前运行中的真实 v2 重建任务 `f69932bca4e34352ac4ebf7d45722af5` 已有最终复验产物；最终状态以 `20261026-publication-recheck` 下的 JSON 与截图为准，不再把“仍在运行”写成当前状态。该复验只证明指定文档的 v1/v2 manifest 与 Qdrant 点集一致及 UI 部分状态可见，不替代 Spec018 最终全量回归、验收评审签字、部署签收或全 Spec 完成。
7. **恢复路径**：若后续查看时任务仍运行，保留页面并稍后刷新；409/busy 时等待已有任务结束；503 或 `INDEX_FINALIZE_REQUIRED` 时按页面提示稍后重试并保留当前错误。若 v2 最终为合法 `partial`，查看告警并继续使用可定位部分；若出现 `INDEX_FINALIZE_REQUIRED`、快照不一致或删除失败，不重复点击、不手动删 Qdrant 点，交由 root 按后端 fail-closed 证据处理。失败终态可点击同一行的“重试”，但每次只提交一次并记录新的 task id。

## 当前产物与签收边界

- 前端合同、生产 markup 隔离 smoke 与最新定向回归：`docs/sdd/plans/018/2026-10-26-reindex-entry-test.md`。
- 后端实现、独立复审与定向回归：`docs/sdd/plans/018/2026-10-26-reindex-entry-backend.md`、`2026-10-26-reindex-entry-backend-review.md`、`2026-10-26-reindex-entry-backend-test.md`。
- 首轮真实请求/响应与失败状态（保留）：`docs/sdd/plans/018/artifacts/20261026-reindex-entry/reindex-request-response.json`、`reindex-status.json`；来源区间与 20 个合法 unresolved 及 11 个旧尾点不一致诊断：`docs/sdd/plans/018/2026-10-26-reindex-entry-range-diagnosis.md`。
- 最终真实复验产物：[`document-status.json`](artifacts/20261026-publication-recheck/document-status.json)、[`inspection-v2.json`](artifacts/20261026-publication-recheck/inspection-v2.json)、[`point-manifest-comparison.json`](artifacts/20261026-publication-recheck/point-manifest-comparison.json)、[`reindex-response.json`](artifacts/20261026-publication-recheck/reindex-response.json)；UI 截图：[`knowledge-base.png`](artifacts/20261026-publication-recheck/knowledge-base.png)。
- 最终复验摘要：v1=107；v2 manifest/Qdrant=308；v2 `partial`=292 mapped/16 unmapped；extra/missing/payload mismatch 均为空。2026-10-26 窄修验收已由 tester 评为 `READY_FOR_USER`、架构师签字 `GO`，本次范围完成；这不扩展为 Spec018 其他历史/全量潜在范围的重新收口。

## 2026-10-26 窄修收口（当前状态）

- 范围：canonical `document_id` 请求衔接、HTTP 202 + 非空 `task_id`、结构化 409/503、指定文档发布前点集一致性、v2 partial 原因可见。
- 真实证据：目标文档 v1=107、v2=308，v2 为 292 mapped/16 `SOURCE_RANGE_UNRESOLVED`；manifest/Qdrant `extra/missing/payload mismatch` 均为空；验收准备度 `10/10`。
- 签字：[`docs/sdd/reviews/018-acceptance-review.md`](../../reviews/018-acceptance-review.md) 的本次追加栏为 tester `READY_FOR_USER`、architect `GO`。
- 边界：旧 297/20 unresolved/11 尾点诊断及其它 Spec018 历史范围均保留，不被本次 308/16 结果覆盖。
