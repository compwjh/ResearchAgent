# Task 06：统一来源 ID、权威、返回合同与旧回归

> 关联：[Spec032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md) ｜ 审计：[资产与缺口](./asset-gap-audit.md)
> 依赖：新版 Spec032 确认、Task02–05 资产可读；当前状态：`已完成（Task06 定向验证通过）`

## 一句话目标

冻结七来源可共同实现的 `SourceAdapter`/`SourceResult`/`ImportResult` 版本化合同，消除 ID、authority、返回类型冲突并修复既有三条定向回归。

## 前置证据与硬约束

- 只以现有 `aggregate_source_adapters.py`、各 `*_publication_source.py`、`source_authority.py`、`source_registry.py`、`paper_discovery_store.py` 为输入，优先提取 Protocol/适配层，不复制网络客户端。
- 规范 ID 为 `usenix/dblp/ieee_sp/ccs/ndss/openalex/crossref`；已有 `ieee-sp/acm-ccs/acm_ccs` 存储值须提供受控迁移/别名读取，不静默丢记录。
- authority 数值越小越权威，但**字段取得来源**决定 rank；Crossref/聚合字段不能因挂在会议 Adapter 下就标成官网。统一错误码、缺失状态、覆盖统计、产物句柄与耗时。

## 实施与文件边界

后端角色：修改 `backend/app/paper_discovery/domain/**`、现有来源 Adapter/Registry/Store 的必要合同接缝及对应 `tests/test_spec032_*`；不碰 frontend、报告合成和 Spec031/034 在途文件。先冻结纯类型/序列化测试，再逐来源加薄适配，最后处理 SQLite 旧 ID 迁移。线上 Agent 不受本地 Ollama 的“两文件/约 150 行”限制；若临时使用本地 Ollama 才按该限制拆分。

## 定向验证与停止条件

- 三个现有 authority 失败用例修正后通过，同时新增“低权威不能覆盖官方字段”“同一真实来源 rank 一致”“旧 ID 迁移不丢记录”。
- 七来源输出同一 schema version；错误/空值/部分结果可序列化，未知来源与任意 URL fail-closed。
- 只运行合同及受影响 Adapter/Store 测试、静态检查和 `git diff --check`；不跑全量回归。迁移无法保证可逆时停止并报告，不删旧目录。

## 交接与产出

写 `artifacts/task-06/contract.md`：字段与状态表、旧→新 ID 映射、测试命令/退出码、改动文件、剩余风险。子 Agent 返回结果状态、摘要、改动文件、验证与产物路径、决策依据、阻塞和主 Agent 下一动作；主 Agent 读回合同与真实 diff 后放行 Task07/08。执行结果：已完成；统一契约已接入七来源，Task07 官网目录抓取未提前实现。

## 变更日志

- 2026-09-20：从原 Task02–05 的合同缺口拆出，避免将历史 Adapter 存在误判为统一协议已完成。
- 2026-09-20：Luna high 子 Agent 完成统一契约、来源 ID/authority 归一化、旧 SQLite 别名迁移和薄包装；主 Agent 复跑 206 个 Task06 相关测试，ruff、compileall、git diff --check 均通过，放行 Task07。
