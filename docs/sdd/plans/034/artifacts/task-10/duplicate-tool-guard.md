# Spec034 Task10 重复只读 Tool 防护

日期：2026-09-15（Asia/Shanghai）
范围：ResearchAgentRunner 单次 AgentRun 的只读 Tool 调用去重；未修改 Spec 状态，未 push/merge。

## 根因

部分本地模型在收到成功的目录结果后仍重复发出完全相同的
`search_paper_catalog` 调用。仅依赖模型自行遵守“调用一次后输出 JSON”会浪费模型循环预算，甚至导致 Search Worker 在没有结构化输出时以 `AGENT_OUTPUT_INVALID` 结束。

## 最小修复

- Runtime 在一次 AgentRun 内记录 `(tool_name, normalized_args_hash)`。
- 相同只读调用不会再次进入分发器，而是回灌稳定的
  `TOOL_ALREADY_EXECUTED` 结果，并切换到 output-only 阶段；下一轮只允许直接输出结构化结果。
- 不同参数的只读调用仍可执行；写入型 Tool 不受该去重路径影响。
- 去重不把失败或重复调用伪装成业务成功，模型仍必须返回通过角色合同和证据门禁的 JSON。

## 验证

- `tests/test_spec034_task10_backend.py`：重复目录调用只执行一次，最终 Search Worker 输出仍需通过候选 ID 合同。
- Task10 定向合同集合：80 passed，退出码 0。
- `py_compile` 与 `git diff --check`：通过。

## 边界

该防护只覆盖完全相同参数的只读调用；不同查询、来源或年份仍由现有能力白名单和预算控制。它不替代真实模型/来源 Smoke，也不放宽 `NO_VALIDATED_EVIDENCE`、`EVALUATOR_EVIDENCE_OUT_OF_SCOPE` 等 fail-closed 门禁。
