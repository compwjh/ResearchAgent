# Task 07：评审、验收、部署与复盘

> 关联：[Spec 018](../../specs/018-knowledge-document-chunk-inspector.md) ｜ [任务索引](./README.md)
> 依赖：Task06；当前状态：`已完成`（2026-10-06 当前版本补验通过；历史完成结果保留）

## 一句话目标

完成独立评审、全量回归、部署和真实运行时验收，全部通过后才将 Spec 018 标记为已完成并创建本地提交。

## 当前证据

- 独立验收报告 [`docs/sdd/reviews/018-acceptance-review.md`](../../reviews/018-acceptance-review.md) 判定 `PASS`，允许 Spec018 收口。
- 最终全量回归按长期规则只执行一次：`.venv/bin/python3.11 -m pytest -q`，结果为 `956 passed, 0 failed, 1 skipped, 38 subtests passed`。
- 已部署服务在 `http://127.0.0.1:8000` 完成 health、文档列表、v1/v2 检查清单、原件 Range 和错误契约 smoke；用户已验证双栏切片交互。
- 历史 snapshot/automatic-upgrade 评审只作审计历史；一个旧 PDF v2 后台 `indexing` 与 reranker disabled 已在验收报告中如实记录为非阻塞遗留。

## 前置门禁

- Task02A、Task02B 与 Task03–06 全部完成，所有缺陷已闭环。
- `papers` alias、运行状态、元数据与 manifest 均处于完成态。
- 工作树范围不包含用户无关修改或敏感运行数据。

## 思维链（可审计执行设计）

1. 独立 reviewer 先验证实现、复用边界和全库替换协议。
2. 单端 tester 分别验证后端与前端，跨端 tester 汇总真实浏览器验收。
3. 验证文档、状态台账、测试、敏感信息和 Git 范围。
4. 直接部署并做运行时验证；失败不假绿。
5. 完成复盘、状态更新和本地原子提交，不 push、不合并 main。

## 子 Agent 分派

- backend-reviewer：后端与 rebuild/alias/finalize 审计。
- frontend-reviewer：DOM、依赖、XSS、版本与交互审计。
- backend-tester / frontend-tester：单端回归。
- tester：跨端浏览器与最终 acceptance review。

## 固定验收 Prompt

```text
你是 Spec018 的 tester。只依据已落盘 Spec、Task02A/02B、Task03–06 结果、独立单端评审和实际部署版本验收，不依赖聊天。逐项验证：PDF/Markdown 原件与真实 v1/v2 切片、dense+sparse、候选全库重建报告、papers alias、旧 Collection 删除、manifest finalize、失败/中断恢复、服务重启、不可变原件、删除再提交新 document_id、v1 重叠、v2 跨页、双向点击、partial、桌面/窄屏、键盘、XSS/路径安全、问答/RRF/reranker 和现有知识库回归。

必须确认检查页面或服务启动不会隐式重建旧索引；未迁移状态返回 INDEX_REBUILD_REQUIRED，finalize_pending 返回 INDEX_FINALIZE_REQUIRED。Hostile PDF/Markdown 必须用真实浏览器证明除同源 source/worker/API 外零网络请求。任何一项失败则结论不通过。报告不得包含原文、完整向量、绝对私人路径、Cookie、Token 或第三方异常。
```

## 子 Agent 必须返回

- 结果状态和验收结论。
- 改动/评审/测试文件与产物路径。
- 全部命令、退出码、通过数量与耗时。
- alias、文档/point/manifest 数量和查询结果。
- 浏览器桌面/窄屏、安全网络观测。
- 风险阻塞与主 Agent 后续动作。

## 主 Agent 校验

- 需求、技术、后端、前端和验收评审均为真实独立产出。
- Spec 验收项、产品步骤与证据逐项对应。
- 冲突标记和敏感信息扫描为零。
- 服务实际启动；最终回复给出可点击地址、实际端口和启动命令。

## 实时监控

在线 Agent 正常运行时等待主动返回；只在明确超时、错误、长期无返回或用户要求时检查日志。

## 测试与验收标准

- 后端定向、前端静态、全量 pytest、HTTP 冒烟和真实浏览器桌面/窄屏全部通过。
- 删除 SQLite/Qdrant 派生运行缓存不影响长期原件与元数据；按协议可重新构建。
- Git 暂存仅包含 Spec018 允许范围，无用户数据、日志、密钥、Cookie 或 Token。

## 风险、停止条件与回滚

- 验收不通过则 Spec 保持实施中并回退责任 Task。
- 不恢复旧 vectors，不使用 reset/stash/clean；只按 rebuild 状态执行受控恢复。
- 只做本地 commit，不 push、不合并、不清理用户无关修改。

## 产出物

- 独立评审、`docs/sdd/reviews/018-acceptance-review.md`、复盘、部署证据、状态台账与本地 commit。

## 执行结果

### 验收与回归

- tester 独立验收：`PASS`，报告见 [`docs/sdd/reviews/018-acceptance-review.md`](../../reviews/018-acceptance-review.md)。
- 最终全量回归：命令 `.venv/bin/python3.11 -m pytest -q`，退出码 `0`，`956 passed / 0 failed / 1 skipped / 38 subtests passed`。
- 任务阶段遵循长期规则，仅运行各 Task 相关定向测试；Spec 收口阶段统一运行上述一次全量回归。

### 部署与运行时

- 服务保持运行于 `127.0.0.1:8000`，health、知识库 health、documents、inspection v1/v2、source Range 和非法 ID smoke 全部通过。
- 已知遗留：`MAD-HTLC...pdf` v2 仍可能处于后台 `indexing`/`INSPECTION_BUILDING`，未伪造为完成；reranker 按当前配置禁用。

### 收口签字

- 架构师（自身）已核对验收报告、状态台账、最终回归和部署证据，同意将 Spec018 标记为 `已完成`。

## 变更日志

- 2026-09-08：创建 Task。
- 2026-09-09：最终验收改为全库候选重建、alias/finalize、不可变原件与运行时门禁，不再验收旧 point 快照恢复。
- 2026-09-10：独立 tester 完成最终验收与一次全量回归，架构师签字收口；同步 Spec、状态台账和长期测试范围规则。
- 2026-10-06：当前整合候选补验完成：全量 2893 passed / 3 skipped / 67 subtests，真实新 PDF/Markdown 双版本 indexed/ready，首页 HTTP 200；独立架构师签字通过。证据在 `artifacts/task-07/current-*-report.md`，人工步骤见 `manual-acceptance.md` 第 6 节，复盘见 `current-retrospective.md`。旧失败证据和非阻塞债务保留。
