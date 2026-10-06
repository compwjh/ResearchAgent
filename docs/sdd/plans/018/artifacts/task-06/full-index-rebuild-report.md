# 索引重建证据补录（2026-10-06）

编写者：主会话架构师，纯文档代行。此报告依据已有持久化运行记录补齐固定交接路径；**没有在本轮重新执行全库重建**，不能把补录日期当成重建日期。

## 已有运行事实

- run：`38efa91a33154fd097c61d1c745d408f`。
- 原始证据：`data/kb/rebuild-runs/<run>/state.json`、`validation.json`、`commit.json`；长期入口为 `data/kb/index-generation.json`。
- validation 时间：2026-09-10T10:14:50Z，状态 `passed`、errors 空。
- 当次候选范围：1 个文档，415 points（v1 107、v2 308）。不将这份候选的 1 个文档扩写为当前全部 40 个目录记录均已完成迁移。
- dense/sparse query probes 均 `candidate_hit=true`。
- finalize 完成时间：2026-09-10T10:31:48Z，state 为 `completed`、progress 100，observed outcome `ok`；fresh topology digest 与 expected digest 相等。
- generation marker、commit 与当前 Qdrant meta 均指向 `papers_rebuild_38efa91a33154fd097c61d1c745d408f`。
- 同 run 的旧 topology.json 是 switching 阶段快照；不能用它覆盖 finalize 后的 commit marker 与真实 alias。

## 当前读路径复核

见 [Task07 当前运行时报告](../task-07/current-runtime-readonly-report.md)：generation ready、Qdrant 可读，既有文档 v1/v2 inspection 分页完整，source HEAD/Range 和非法 ID 契约通过。

## 497 与 460 anchors 的边界

离线 sparse-anchor-backend-report 在内存重新生成 214 个 v2 chunks，得到 497 anchors；已提交的线上快照为 308 chunks、460 anchors。两者不是同一组 chunk 输入，不能以 anchor 总数相等为验收判据，也不能拿离线快照替换线上真正已写入的切片。当前线上 mapped=290、unmapped=18，分页总数自洽；后续算法对比须固定 source、chunk fingerprints、模型输出与 mapping 版本后再比较。历史离线报告缺少可复算 chunk fingerprint，无法事后证明等价，不伪造补齐。

## 尚未宣称完成的范围

- 本轮未执行旧用户目录批量重建、claim 清理或 alias 切换。
- 旧失败记录、legacy_unknown 来源状态保留；本报告不将其改成成功。
- 当前版本上传与双格式真实 E2E、性能、全量回归以 Task07 本轮报告为准；失败期间不能凭此补录签署 PASS。
