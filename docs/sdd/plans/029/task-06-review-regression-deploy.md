# Task 06：最终评审、回归、部署与复盘

> 关联：[Spec 029](../../specs/029-research-fulltext-acquisition.md) ｜ 索引：[README](./README.md)
> 依赖：Task02–05 完成；当前状态：`实施中`

## 一句话目标

完成下载/导入/知识库复用审计、唯一全量回归、真实公开 PDF 证据升级、部署与复盘。

## 完整分派 Prompt

```text
角色：双端 reviewer/tester、跨端 tester、architect；读取 Spec029、Task 报告和实际 diff。
允许修改：reviews/029-*.md、plans/029/artifacts/task-06/**、对应 retro；修复退回开发 Task。
禁止绕过登录、安全规则或用户确认；禁止 push/merge/reset/stash/clean。
验证：复用矩阵、固定样本、真实公开 PDF、全文切片定位、相关安全回归、唯一全量回归、浏览器、部署。
完成状态：三份评审与签字齐全，真实环境失败有明确复验步骤。
返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 任一重复实现、安全语义退化或虚假全文证据均阻塞。
- 产出评审、验收、复盘和部署证据；自动化与服务页面 smoke 已完成，真实全文导入仍待补。

## 执行结果

- 需求/技术/验收评审文档已落盘；最终全量回归：2450 passed、1 skipped、5 warnings、67 subtests，退出码 0。
- `runtime-smoke.md` 记录真实 FastAPI 启动与 Research 页面/静态资源加载。
- 真实公开 PDF 下载、导入、索引、全文证据升级和浏览器候选确认尚未执行，因此 Spec029 保持实施中。

## 变更日志

- 2026-09-12：创建最终收口 Task。
