# Spec 015 Task13–17 需求复审

> 评审角色：Tech Lead（由架构师在主会话接手落盘；原 tech-lead 子代理因本地 27B 上下文耗尽未落盘）
> 关联：`docs/sdd/specs/015-security-paper-discovery.md`、`docs/sdd/plans/015/task-14-usenix-incremental-catalog.md` 至 `task-17-review-acceptance-deploy-retro.md`
> 当前结论：**通过**

## 评审范围

Task14（USENIX 增量目录同步）、Task15（LangGraph / 目录 RAG / 冻结结果）、Task16（来源进度卡片与 10 条分页交互）、Task17（复用审计 / 验收 / 部署 / 复盘）的需求可测性与验收覆盖。

## 验收点映射

| 验收点 | 对应任务 | 判定 |
|---|---|---|
| A16 增量目录缓存命中 | Task14（缓存单元 / 304 / 内容哈希 / 重启恢复）+ Task17 | 覆盖；边界可测（Task14 主 Agent 回填校验第 3、5、103 条） |
| A17 来源进度卡片 | Task15（`search_source_progress` 两来源状态）+ Task16（两卡片 UI） | 覆盖；状态枚举与中文文案映射明确 |
| A18 RAG 独立 collection + 固定 10 条分页 | Task15（独立 collection / metadata_hash 增量 / RRF / 冻结不可改写）+ Task16（前端固定分页） | 覆盖；冻结后不可更新、10/10/1 可测 |
| A19 并发领取 / 租约恢复 | Task13（`acquire_fetch_unit` 原子领取 / 租约）+ Task14（按 unit 租约抓取）+ Task15（图并行共享租约） | 覆盖；并发 10 轮 / 租约过期恢复可测 |
| A20 复用审计 | Task13 审计（已通过）+ Task17 验收矩阵 | 覆盖 |

## 需求结论

- **范围清晰**：Task14–17 严格限定为「USENIX 优先增量目录 + LangGraph 异步 + 独立 RAG + 来源进度/分页 + 验收部署」，无需求蔓延；「明确不做」清单（spec 第 467–486 行）已划死范围。
- **边界可测**：每个任务均含思维链、测试与验收标准、主 Agent 回填校验清单，验收点 A16–A19 均有可数证据项。
- **歧义 / 遗漏**：未发现需求级歧义；Task16 依赖 PM 文案复核（子任务A）作为前端契约前置，已在门禁固定；Task14 四种官方页面结构已给出确定性 fixture 种子。

## 遗留（不阻塞通过）

- 真实 USENIX 网络检索 / 导入需在 Task17 运行时验收，受外部网络环境约束，按 spec 风险条款标记阻塞而非降低标准。
- Spec017 文件保持独立，不得纳入本范围提交 / 验收 / 部署。

## 结论

**通过**，可进入技术复审与用户确认后实现。
