# Task 06E：稀疏来源锚点修复与交互回归

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task 04、Task 05、历史 `source-anchor-v1` 运行时复现证据 ｜ 被依赖：Task 06 收口、Task 07
> 当前状态：`已完成`

## 一句话目标

把错误的“任意模糊文本相似即关联”替换为可证明的来源区间交集，让原文块仅跳转到实际包含它的少数 v1/v2 切片，反向点击也只回到真实覆盖的原文块。

## 当前证据

- 真实 PDF 有约 500 个 SourceBlock、v1 有 107 个 Chunk，却写入 53,120 条 anchors，近似全连接而非正常 overlap 关系。
- `backend/app/knowledge_base/infrastructure/provenance.py::_anchors()` 对每个 chunk 扫描所有 block，使用 `SequenceMatcher` 的任意正分筛选，并持久化全部结果。
- 运行时表现为点击 `#3` 无法定位 Introduction；点击 PDF 第三页块会错误跳至 `#0`。
- 前端首批装载只暴露了这个后端错误，不得用恢复全量下载、只保留前三条或按需拉取错误全量关系掩盖根因。

## 前置门禁

- 只执行 Spec 018 已确认的 `source-anchor-v2` 修订；不得改变 v1/v2 chunk 文本、向量、原件或 Qdrant Collection。
- 先在固定样本和临时 manifest 上证明关系稀疏、正确、可复现；当前用户 manifest 只能在全部定向验证通过后重建。
- `source-anchor-v1` manifest 在 v2 重建前不得作为双向点击依据，UI 必须显示稳定重建提示或禁用误导性交互。

## 执行阶段、观察点与决策依据

1. 后端开发保留 chunker 输出不变，为 chunk 构建过程产生可验证的规范化来源区间；确认每条 anchor 来自 block/chunk 的真实 `[start,end)` 交集。
2. 以 `source-anchor-v2` 取代 v1 的全对全 `SequenceMatcher`。未能精确回对齐的 chunk 标记 `SOURCE_RANGE_UNRESOLVED`，不允许模糊降级。
3. 固定样本验证标题、正文、v1 overlap、v2 跨页、Markdown，以及“无共同来源区间不建立 anchor”。
4. 后端测试通过后，前端开发只消费正确的稀疏 anchors：选择原文块时按 primary/highest coverage 跳到对应 chunks；选择 chunk 时按相同关系跳回原文块；v1 旧清单不得点击后跳到 `#0`。
5. 仅在当前文档的 chunks 与 Qdrant snapshot fingerprint 一致时重建 manifest；重建不 embedding、不下载、不写 Qdrant。真实浏览器复测 Introduction 与第三页块。

## 子任务拆分与子 Agent 分派

| 子任务 | 角色 | 允许代码范围 | 产物 |
|---|---|---|---|
| 06E-A | backend-dev（Luna xhigh） | `backend/app/knowledge_base/infrastructure/provenance.py`、对应 provenance 测试 | `sparse-anchor-backend-report.md` |
| 06E-B | backend-tester（Luna xhigh） | 只运行/补充定向后端测试，不改业务代码 | `sparse-anchor-backend-test-report.md` |
| 06E-C | frontend-dev（Luna xhigh） | `frontend/kb-inspection.js`、对应前端交互测试 | `sparse-anchor-frontend-report.md` |
| 06E-D | tester（Luna xhigh） | 不改业务代码；真实浏览器与 API 验收 | `sparse-anchor-runtime-report.md` |
| 06E-E | 主 Agent | 按成功证据执行单文档 manifest 重建、服务验证、本地提交 | Spec/Task 执行结果与提交 |

## 06E-A 分派 Prompt

```text
你是 Spec018 Task06E-A 的 backend-dev，使用临时 Luna xhigh。只读取 Spec018 的“来源锚点稀疏映射修订 source-anchor-v2”、本 Task、provenance.py 和对应固定 provenance tests。只允许修改 provenance.py、对应测试、任务报告；禁止 frontend、routes、真实 data/kb、Qdrant、embedding、Git 历史与任何 reset/stash/clean/push/merge。

实现可验证的 source-anchor-v2：每个 anchor 必须来自同一规范化来源流中 block 与 chunk 的真实字符区间交集。禁止所有 block×chunk 的 SequenceMatcher 任意正分关联；禁止人为最多 N 条截断。维持 v1/v2 chunk 文本和顺序不变。无法精确对齐必须显式 SOURCE_RANGE_UNRESOLVED，不能降回模糊匹配。映射版本升级为 source-anchor-v2，并更新必要的固定期望/测试。

必须验证：标题只关联实际包含标题的 chunks；正文块只关联真实覆盖 chunks；v1 overlap 和 v2 跨页正确；没有真实来源交集不建 anchor；关系数明显不是 chunk×block 组合爆炸。运行定向 pytest、py_compile、git diff --check。报告写入 docs/sdd/plans/018/artifacts/task-06/sparse-anchor-backend-report.md。

返回固定字段：结果状态和摘要；改动文件；测试命令、退出码和结果；产物路径；决策依据；风险与阻塞；主 Agent 后续动作；开始、结束和总耗时；可用时记录模型、token 和工具调用统计。
```

## 子 Agent 返回后主 Agent 校验

- 审阅 diff，确认不存在任意相似度、全对全扫描或关系数量硬截断。
- 复跑固定 provenance suite，并检查 v1/v2 chunk 文本与 chunk_index 未改变。
- 复核 manifest 标记为 `source-anchor-v2`，旧 v1 不再可交互。
- 前端只在稀疏 anchor 已就绪时激活跳转；无关系显示稳定提示，不跳转 `#0`。
- 真实文档 rebuild 前后 Qdrant point count、payload 和 vector fingerprint 不变。

## 实时监控命令

线上子 Agent 正常运行时等待其主动返回；只在明确报错、超时或长期无返回时按需阅读其 `.codebuddy/agent-logs/spec-018/task-06e/<role>/` 日志。

## 测试与验收标准

- 500 个 block、107 个 chunks 的真实文档不再出现数量级为五万的 anchors；关系数量由实际来源覆盖决定并记录在运行报告。
- 点击 `1 Introduction` 只高亮包含该标题/对应来源范围的少数 chunks，primary 是最高真实 coverage。
- 点击 PDF 第三页来源块不会跳至无真实交集的 `#0`；反向点击保持全部真实关联高亮。
- v1 overlap、v2 跨页、Markdown、键盘 Enter/Space、窄屏切换和未映射提示回归通过。
- manifest 重建不触发 embedding、下载、Qdrant 写入或原件/metadata 修改。

## 风险、停止条件与回滚

- 不能精确复建来源区间：停止，不以相似度阈值或条数上限替代；保留 `SOURCE_RANGE_UNRESOLVED`。
- 固定 chunk 文本/索引变化、Qdrant fingerprint 不一致或测试期望无法解释：停止，不重建用户 manifest。
- manifest rebuild 失败：保留原件、metadata、向量和现有 manifest 文件；不自动删除或覆盖用户内容。
- 不执行 reset、stash、clean、push、合并 main 或清理用户修改。

## 产出物

- `docs/sdd/plans/018/artifacts/task-06/sparse-anchor-backend-report.md`
- `docs/sdd/plans/018/artifacts/task-06/sparse-anchor-backend-test-report.md`
- `docs/sdd/plans/018/artifacts/task-06/sparse-anchor-frontend-report.md`
- `docs/sdd/plans/018/artifacts/task-06/sparse-anchor-runtime-report.md`

## 执行结果

`已完成`。

- 后端稀疏映射验证：v1 旧 payload 共 107 个 chunks，107/107 成功映射，生成 566 条真实来源 anchor；未出现 block×chunk 全连接关系爆炸。
- v2 旧 payload 验证：共 308 个 chunks，290/308 成功映射，18 个无法精确回对齐的 chunks 明确标记为 `SOURCE_RANGE_UNRESOLVED`，未使用模糊匹配兜底。
- manifest 契约验证：当前清单固定使用 `source-anchor-v2`；旧 v1 manifest 进入 API 时 fail-closed，返回 409 `INDEX_REBUILD_REQUIRED`，不会把旧 anchors 交给前端。
- 前端分页验证：检查器已完成完整分页加载，不再只依赖首批关系，也不以关系数量截断来掩盖映射问题。
- 浏览器交互验证：已验证原文块到切片、切片到原文的双向点击定位；`Introduction` 仅跳转到真实关联切片，PDF 第三页块不再错误跳转到 `#0`。
- 本阶段未修改原件、元数据、Qdrant vectors 或 Collection；manifest 重建与完整 Spec018 收口仍按 Task06/07 的独立门禁执行。

## 变更日志

- 2026-09-10：用户指出“标题应只跳到实际包含它的少数切片”，否定了 53,120 条 anchor 为正常数据的错误判断；创建 source-anchor-v2 修复任务，先落盘再实施。
