# 任务 05 — 接入知识库检索链路

> 关联：[spec-014](../../specs/014-kb-reranker.md) ｜ 索引：[README](./README.md)
> 依赖：任务 04；当前状态：`进行中`

## 一句话目标

把批量客户端接到现有 dense + sparse + RRF 链路，在最终 `top_k` 截断前重排更大的候选池，并完整保留 spec-012 行为。

## 流程目标

```text
dense 30 + sparse 30 → RRF/去重 → rerank candidates 20
→ 成功：按 rerank score 排序 → top_k
→ 失败/关闭：保持 RRF 排序 → top_k
```

## 实施步骤

1. 在配置模块增加 spec 定义的 enabled、base URL、candidate count 与超时项，并做安全解析。
2. 移除现有逐条 `ChatOllama.invoke()` 生成式打分，不保留双实现开关。
3. 调整 `hybrid_search`：RRF 后先截取 rerank candidate count，再调用批量客户端，最后截取 `top_k`。
4. 禁用、0/1 候选或客户端降级时保持 RRF 顺序。
5. 确认 dense/sparse 两路继续使用同一 Qdrant filter，RRF key 继续包含 chunker。
6. 保持 `Hit` 既有构造兼容；新增字段必须有默认值。
7. 补充服务层测试，证明排名第 6–20 的候选可以经 rerank 进入最终 top 5。

## 涉及文件与子代理拆分

- 分派 A（`junior-dev`）：`backend/app/core/config.py` 与 rerank 配置测试。
- 分派 B（`junior-dev`）：`backend/app/services/kb/retrieve.py` 与相应服务测试，若总行数超过 150 再拆测试分派。
- 与 spec-013 同名文件发生冲突时，本任务只在独立 worktree实现，不直接覆盖当前工作树版本。

## 边界与回归保护

- `KB_RERANK_CANDIDATES < top_k` 时实际候选至少提升到 `top_k`，避免返回条数不足。
- candidate 配置非数字或小于 1 时回退默认并告警，应用不能导入失败。
- Reranker 不得在 Qdrant 写锁内运行。
- citation 问题仍能纳入参考文献，普通问题仍排除 citation。
- v1/v2、paper_id 过滤和跨页信息完全保留。

## 明确不做

- 不调整 RRF_K、embedding、BM25 或 Qdrant 查询参数的默认值。
- 不改变问答 prompt、上下文拼装和引用渲染。
- 不做分数阈值过滤；只排序后取 `top_k`。

## 验收标准

- 成功与降级两条路径均在最终一步截取 `top_k`。
- mock Reranker 能把 RRF 第 6–20 名提升到最终结果。
- 禁用或异常时结果与改动前 RRF 前 `top_k` 一致。
- spec-012 的过滤与版本隔离测试全部通过。

## 风险、回滚与产出

- 风险：候选增多导致文档传输和推理变慢；以 20 为固定默认并通过 Task 07 基准验证。
- 回滚：设置 `RERANKER_ENABLED=false`；必要时移除调用恢复 RRF。
- 产出：配置、检索接入、回归测试和执行记录。
- 执行结果：
  - 配置新增 enabled/base URL/model path/API model/candidates/timeout/server bin，非法值告警并回退默认；删除旧 `RERANKER_MODEL` 聊天打分开关。
  - 检索改为 RRF 后候选、20 条为上限调用一次批量客户，最后才截 `top_k`；`Hit` 新增默认为 `None` 的当请求重排字段。
  - 特定测试、客户端测试、路由测试和配置测试共 `269 passed` （含 29 个 subtests）；`py_compile` 与 `git diff --check` 通过。

## 变更日志

| 时间 | 角色 | 动作 |
|---|---|---|
| 2026-09-02 | 架构师(自身) | 创建任务计划，状态为待执行 |
| 2026-09-02 | 架构师(自身) | Task 04 通过独立测试后启动配置与检索集成 |
| 2026-09-02 | 初级开发（协作 Agent） | 交付 Reranker 配置、候选池接入和重排字段映射 |
| 2026-09-02 | 架构师(自身) | 隔离分支全量回归通过 269 个测试，任务转完成 |
