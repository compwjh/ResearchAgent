# Task03 桌面自动建图 MVP 独立验收裁定

日期：2026-10-19（Asia/Shanghai）
角色：独立验收裁定（backend-reviewer 复核证据）
范围：只裁定已确认 Spec043 的 Task03 纵向 MVP；不代替 Spec043 最终验收签字，不提前验收 Task04–08。

## 最终裁定

**Task03 纵向 MVP：PASS_WITH_LIMITATIONS。**

真实证据已经证明：主题创建、真实节点、真实引用/相似关系、partial 失败显示、布局保存重开、主动导入入口及既有知识库导入链均可工作。provider 的部分失败被真实保留并显示为 partial，不能把 partial 改判为全量成功，但也不能把“允许 partial 且正确显示”误判为 Task03 实现失败。

**用户可交付的 clean acceptance / Spec043 最终收口：BLOCKED。**

当前仍有真实 provider partial（2 个 rate-limit、4 个 invalid-response 单元），因此不应宣称完整关系采集成功或交付为无条件 READY。r6 的 v2 chunker 还报告 INDEX_FINALIZE_REQUIRED；这不影响本次地图导入、v1 索引或默认 v1 检索，但必须保留为后续 KB 索引维护限制。

本报告不是 Spec043 最终签字，也不要求 Task03 额外完成 Task08 全量回归。

## 对照的已确认范围与合同

- Spec043 的 Task03 目标是用户输入主题、看到真实图谱、点选论文并保存重开的桌面 MVP。
- interface-contract.md 要求引用/相似关系按真实来源保存；来源失败、429、截断和相似不可用必须显示 partial/固定错误，不得伪装成 0 边成功。
- Task03 不要求所有 provider 单元在一次真实运行中都成功；但要求 partial 真实可见，不能将 partial 当作 clean success。
- Task03 的主动入库只桥接既有安全导入链，不新增下载器；地图节点的 document_id 可先为空，显式导入成功后再关联。

## 真实 API 证据

### 建图与关系

API artifact：api-e2e.md、api-evidence.json。核心 run 为 task03-api-e2e-20261019T140606Z-r2，真实部署地址为 http://127.0.0.1:8000，服务提交为 8c79860；同一地图和作业未重复创建。

- map_id：0baabeae7268429c9f7e4de8098ae1d0
- job_id：ba6bb4f9471b43afb8b1063cdc3a883d
- 真实创建请求 HTTP 202；主题为 graph attention networks，limit=20。
- 最终 bounded retry 后：20 nodes、12 citation edges、5 similarity edges、provider_request_count=30/60。
- citation layer/job 为 partial，剩余 2 个 SEMANTIC_SCHOLAR_RATE_LIMITED 与 4 个 SEMANTIC_SCHOLAR_INVALID_RESPONSE 单元；这些失败没有被解释为“没有引用”。
- similarity layer 为 completed；5 条真实边分数均达到 0.75 阈值，保留 title_abstract basis、bge-m3 model 和内容哈希证据。
- 保存视图后 graph/map 读取保持 revision、viewport 和 node position；没有用客户端合成关系掩盖 provider 失败。

### 主动入库与知识库

最新真实 run 为 task03-api-e2e-20261019T145452Z-r6，部署提交为 1d54720。仅发起一次显式 import POST，未直接请求 PDF：

- node_id：21041260a5394f42891b020128fa60fa
- POST /api/literature-maps/0baabeae7268429c9f7e4de8098ae1d0/nodes/21041260a5394f42891b020128fa60fa/imports 返回 HTTP 202。
- 业务结果为 indexed，paper_id/document_id 均为 55afc3b8f01445429462fe78ed0d4c98；节点 GET 返回同一 document_id 和 indexed 状态。
- GET /api/kb/documents?limit=100 找到同一 immutable document；v1 chunker 为 indexed、57 chunks、progress 100。
- v2 chunker 为 failed、0 chunks、progress 0、INDEX_FINALIZE_REQUIRED。该失败被真实记录，没有被抹除或伪装为所有索引版本成功。

只读核对 data/kb/papers.json 也看到同一 document 的顶层 status=indexed、v1=57 chunks、v2=failed。当前代码的 KB ask 默认 chunker=v1，只有显式请求 v2 才使用 v2，且明确不从 v2 回退到 v1；因此 v2 失败不否定本次地图导入和默认 v1 知识库入口。generation/manifest 的瞬时 fail-closed 时序不能仅凭本报告武断归因于环境，后续归 KB index 维护处理。

## 真实浏览器证据

browser-e2e.md 的 Run 2 使用真实 Chrome，复用 map_id=0baabeae7268429c9f7e4de8098ae1d0，观察到：

- 真实地图显示 20 个节点和真实关系，页面明确显示 partial 及“已保留可用节点并标注失败阶段”，没有把 partial 渲染为成功。
- 图谱实际绘制引用箭头和相似虚线；Run 2 读取时为 11 citation + 5 similarity，后续 API bounded retry 增至 12 + 5，属于同一作业的增量结果，不是矛盾或合成边。
- 节点详情、三栏布局、详情关闭、图层切换、缩放、空白画布平移、节点拖动、重开恢复均有真实浏览器/API交叉证据。
- 截图路径：screenshots/browser-v4-real-graph.jpg、browser-v4-real-graph-detail.jpg、browser-v4-pan-reopen.jpg、browser-v4-node-drag-zoom-reopen.jpg。

浏览器 Run 2 的候选提交为 8c79860，r6 导入部署为 1d54720；git diff 8c79860..1d54720 -- frontend 无输出，前端交互证据未被后续后端身份/导入修复改动。r6 的导入成功来自真实 API；浏览器报告没有在 1d54720 上重复点击导入按钮，因此不把 UI 点击后的成功提示冒充为已观察。

## Task03 准备度矩阵

| # | 检查项 | 结果 | 证据与限制 |
|---:|---|---|---|
| 1 | 服务启动并可访问 | PASS | r2/r6 的 /api/ready HTTP 200；浏览器入口可访问 |
| 2 | 真实 API 创建入口 | PASS | POST 真实返回 HTTP 202，map/job 可追溯 |
| 3 | 主路径参数解析 | PASS | topic、limit=20 持久化；真实选出 20 个节点 |
| 4 | 作业/实体状态推进 | PASS | queued → running/discover/references/similarity → partial/finished |
| 5 | 前端处理中/partial 显示 | PASS | Chrome 观察到 partial banner、阶段和可用节点提示 |
| 6 | 用户知道等待/下一步 | PASS | partial 文案、刷新状态和节点详情/图层操作路径可见；不把失败单元当成功 |
| 7 | 核心真实图谱产物 | PASS_WITH_LIMITATIONS | 20 节点、12 citation、5 similarity 真实存在；citation 仍 partial |
| 8 | 失败可操作恢复 | PASS | 固定 429/invalid/PDF 诊断、bounded retry 与 partial 保留均可追溯 |
| 9 | 页面/API 状态一致 | PASS | 浏览器关系/partial 与 graph API 交叉核验；布局重开保持 revision/viewport/position |
| 10 | 无上下文可复现步骤 | PASS | api-e2e、api-evidence、browser-e2e、截图和本报告含真实 ID/路径/限制 |

Task03 MVP 证据为 9 项 PASS、1 项 PASS_WITH_LIMITATIONS；没有发现新的 Task03 P0/P1 代码缺陷。用户 clean acceptance 仍因真实 provider partial 而 BLOCKED；该结论不等同于要求所有 provider 单元必须完整成功。

## 当前阻塞与后续边界

1. 真实 citation 仍 partial：2 个 rate-limit、4 个 invalid-response 单元。partial 是合同允许的真实失败状态，当前 UI/API 已正确保留；但完整关系采集不能宣称完成，需后续受控 retry/provider response-shape 处理。
2. v2 chunker 的 INDEX_FINALIZE_REQUIRED：不影响本次导入句柄、v1/57 chunks 或默认 v1 检索；不在 Task03 重构地图导入链，归后续 KB index maintenance 处理，并保留现有 fail-closed 证据。
3. 1d54720 上尚未重新做一次浏览器导入点击成功提示复核；API r6 已证明真实导入和 v1 KB 可见性，UI 成功提示仍应在后续受控浏览器回归中补证。

未完成且不应倒灌到 Task03：

- Task04：扩展/引用预览确认、停止与 retry 语义、失败单元精细补缺。
- Task05：AI 分析与 conversations。
- Task06：人工分组与 JSON/PNG 导出。
- Task07：手机触控与移动布局。
- Task08：最终全量回归、最终验收评审、部署收口与 Spec043 状态签字。

## 允许的后续动作

- 可基于本报告的 PASS_WITH_LIMITATIONS 进入后续 Task 的依赖编排，但不得把 Task03 记录为 Spec043 已完成或把当前地图 partial 改称完整成功。
- 在交给用户人工验收前，需补一份当前部署版本的浏览器导入点击证据，并由主会话按 Spec acceptance protocol 重新判断 READY_FOR_USER/BLOCKED。
- 不应为 v2 失败修改地图导入合同、重建地图数据或重复创建 provider 作业；KB 维护应保持 document_id、v1 证据和 v2 失败证据可追溯。

**本报告结论：PASS_WITH_LIMITATIONS（Task03 纵向 MVP 真实门禁通过但有明确 provider/KB 限制）；用户 clean acceptance 与 Spec043 最终签字：BLOCKED。**

架构师阶段签字：主会话，2026-10-19 23:00 +08:00。接受上述真实阶段结论，进入Task04，不修改provider partial或异步v2失败事实；不作为Spec最终验收签字。

### 当前浏览器导入成功态补证

随后frontend-tester在当前部署真实浏览器确认同一GAT节点 `download_status=indexed`、document `55afc3b8f01445429462fe78ed0d4c98`，知识库显示对应PDF及v1已索引57片段，见 `browser-e2e.md` 末节与 `screenshots/browser-v4-indexed-node.jpg`。未重复提交导入；不能把该状态复核冒充为新一次点击下载。已索引节点仍可点击加入、缺少已有文档入口记录为同组件小缺陷，由Task04前端修正。阶段结论不变，最终Spec仍未签字。
