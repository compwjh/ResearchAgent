# 任务 07：删除旧结构并验证模块边界

> 关联：[Spec017](../../specs/017-backend-bounded-context-modularization.md) ｜ 索引：[README](./README.md)  
> 依赖：任务 04、05、06；当前状态：`待执行`

## 目标

删除已迁移的旧目录和旧 import，加入可执行的模块边界检查并完成全量回归。

## 验收

- `services/`、顶层 `domain/`、`agents/`、`graphs/` 不再承载迁移范围内的业务实现或项目内 import。
- 静态边界检查确认 API 不直接依赖基础设施、domain 无外部副作用依赖、无跨业务循环依赖。
- OpenAPI/路由、完整测试、`git diff --check` 和冲突标记检查均通过。

## 风险与回滚

任何 API 或持久化契约变化都回到对应模块任务修复；不得通过恢复旧路径掩盖问题。
