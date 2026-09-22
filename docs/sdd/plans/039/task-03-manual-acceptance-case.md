> 关联：[Spec039](../../specs/039-api-e2e-manual-acceptance-protocol.md) ｜ 索引：[README](./README.md)
> 依赖：Task02；当前状态：`已完成`

# Task03：固化详细人工验收案例

## 一句话目标

定义用户可以不依赖聊天上下文直接执行的逐步验收文档格式。

## 验收案例必填字段

- 入口 URL、版本和前置条件；
- 每一步点击的控件名称；
- 点击后预期出现的提示；
- 是否需要等待、等待期间显示什么；
- 用户下一步操作；
- 成功、失败和恢复判据；
- 最终产物查看或下载路径。

## 交付门槛

十项准备度检查至少九项通过，且无 P0/P1、API E2E 失败或关键产物缺失。

## 执行结果

逐步案例协议已固化到 `.agents/skills/spec-acceptance-protocol/SKILL.md`，并以 Spec032 生成首份实例：
`artifacts/spec032-manual-acceptance.md`。每一步均包含输入/点击、点击后提示、等待条件、等待中显示、
下一步和失败恢复；当前实例因运行阻塞标记 `BLOCKED`，不允许交给用户验收。
