# Spec 015 Task13–17 技术复审与复用审计

> 评审角色：Tech Lead
> 关联：`docs/sdd/specs/015-security-paper-discovery.md`、`docs/sdd/plans/015/task-13-catalog-contract-and-reuse-audit.md` 至 `task-17-review-acceptance-deploy-retro.md`
> 当前结论：**待评审（未执行）**

## 强制评审材料

评审 Agent 必须读取以下落盘材料，不依赖聊天上下文：

1. Spec015 的“现有实现复用与替换边界（实现硬约束）”。
2. Spec015 的 schema v2、异步 JSON、LangGraph、RAG、失败和验收契约。
3. Task13–17 全文，尤其完整分派 Prompt 与主 Agent 校验步骤。
4. 执行前评审时读取当前相关模块和测试；实现后复审还必须读取 `015-task13-reuse-audit.md` 与实际 Git diff。

## 设计审查

- [ ] schema v2 七张表、状态、唯一约束、外键、迁移/回滚和数据保留无未决项。
- [ ] 抓取单元能表达同一年多个 cycle/summer/fall 页面；completed/partial/failed 不混淆。
- [ ] 受控年度入口、同源路径、条件请求、内容哈希、租约和当前年份重验证规则完整。
- [ ] LangGraph 节点和状态转换固定，来源并行但不绕过同源节流/租约。
- [ ] 网络、解析、embedding、Qdrant、rerank 均不在 SQLite 事务或全局锁内。
- [ ] 目录与个人知识库 collection 隔离，metadata_hash 增量索引和索引失败隔离明确。
- [ ] USENIX字段权威、DBLP只补空值、DBLP-only无官方摘要不展示。
- [ ] POST 202、状态事件游标、10条冻结分页、过期和错误码完整。
- [ ] 搜索与导入边界明确，搜索阶段没有 PDF 请求。
- [ ] 进程重启、节点重试、并发领取和冻结结果不可变均可测试。

## 复用审计

以下每行必须在实现后填写“复用符号、调用位置、测试证据、结论”；出现新的平行实现且无可复现必要性即打回。

| 能力 | 现有实现 | 允许变化 | 实现后证据 | 结论 |
|---|---|---|---|---|
| PDF安全下载/校验 | `paper_download.py` | 仅适配目录ID输入 | 待执行 | 待评审 |
| URL/DNS/重定向/SSRF | `paper_download_security.py` | 增加受控元数据origin，不弱化策略 | 待执行 | 待评审 |
| 单篇导入saga | `paper_import.py` | 从冻结结果读取候选 | 待执行 | 待评审 |
| 批量/租约/恢复 | import batch模块 | 新搜索用独立表，复用状态思想但不复制导入流程 | 待执行 | 待评审 |
| 身份/命名 | identity/normalization模块 | 扩展catalog id | 待执行 | 待评审 |
| USENIX parser/source | 现有两个USENIX模块 | 扩展元数据和持久单元，删除搜索PDF probe | 待执行 | 待评审 |
| DBLP | `dblp_publication_source.py` | 改为辅助补全 | 待执行 | 待评审 |
| SQLite | `paper_discovery_store.py` | 在现有连接/迁移框架升级v2 | 待执行 | 待评审 |
| BGE-M3/RRF/reranker | `services/kb/*` | 参数化collection/payload/filter | 待执行 | 待评审 |
| Playwright | `paper_browser_manager.py` | 不参与USENIX元数据同步 | 待执行 | 待评审 |

## 打回条件

- 新建第二套下载、安全、导入、批任务、身份规范化、embedding、RRF或reranker实现。
- 为了兼容而保留会绕过全局目录的旧同步生产路径或新旧双写。
- 以进程内缓存代替SQLite，或在搜索阶段请求PDF。
- 让DBLP覆盖USENIX官方字段、生成关键词、显示无官方摘要的DBLP-only记录。
- 缺少迁移回滚、并发租约、重启恢复、partial/failed或固定分页测试。
- 引用不存在的报告、无退出码测试或聊天结论作为证据。

## 评审结论

待评审（未执行）。评审完成后只能填写“通过”或“打回”；通过时必须填写独立评审者、时间、实际diff基线、复用审计表和剩余风险。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-05 | 架构师（自身） | 将代码复用分析固化为新流程技术复审材料和逐项审计表；未执行评审 |
