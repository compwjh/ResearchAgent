# Task 06：最终评审、回归、部署与复盘

> 关联：[Spec 032](../../specs/032-research-source-expansion.md) ｜ 索引：[README](./README.md)
> 依赖：Task02–05 完成；当前状态：`待执行`

## 一句话目标

完成来源复用、安全、provenance 和 Research Task 集成验收，运行唯一全量回归并部署收口。

## 完整分派 Prompt

```text
角色：双端 reviewer/tester、跨端 tester、architect；读取 Spec032、全部报告、fixtures 和 diff。
允许修改：reviews/032-*.md、plans/032/artifacts/task-06/**、对应 retro；修复退回开发 Task。
禁止真实批量抓取造成站点压力、PDF 下载、伪造外部成功、push/merge/reset/stash/clean。
验证：每源固定样本、增量缓存、provenance、单源失败、安全、前端、唯一全量回归、受控 live smoke、部署。
完成状态：三评审和签字齐全；不可用外部源有环境延期与复验步骤。
返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 字段覆盖错误、任意 URL、缓存清空或重复实现均阻塞。
- 产出评审、验收、复盘和部署证据；执行结果待填写。

## 变更日志

- 2026-09-12：创建最终收口 Task。
