# Spec034 Task10 最终验收复核

## 结论

**NO-GO（Spec034 暂不能标记为已完成）**。

代码与自动化门禁已通过；唯一全量回归已恢复为 0 failures。真实服务和浏览器页面可达，真实 Intake→Plan→Approval→Runner→三级事件流可复现；但两次真实模型运行均因本机 Ollama 模型未返回 Runtime 所需结构化 Tool/JSON 而进入 `MODEL_UNAVAILABLE → partial`，没有成功报告 Artifact。因此核心成功 Smoke 尚未满足。

## 验证结果

| 检查 | 结果 |
|---|---|
| 最终全量 pytest（`--basetemp=/private/tmp/spec034-final-pytest2`） | **1863 passed, 5 warnings, 52 subtests；退出码 0；227.82s** |
| reasoning/Spec027 回归失败子集 | 75 passed；退出码 0 |
| Task04–Task10 后端定向合同 | 105 passed；退出码 0 |
| 前端 JS 合同 / Node 语法 | 8/8、6/6 通过 |
| Python compile、diff-check、冲突扫描 | 通过 |
| `GET /api/health`、`GET /` | HTTP 200、真实浏览器页面可达 |
| 真实研究 Smoke | Intake/批准/运行/三级事件通过；最终 `partial`，无 Artifact，阻塞收口 |

## 阻塞项

1. 本机 `qwen3.8:27b` 只有 completion 能力；临时切换 `qwen3.8:27b-q4_K_M` 后虽能完成基础 chat，但对研究 Tool schema 返回普通文本，不产生 `tool_calls` 或角色结构化 JSON。
2. 因此缺失成功 Run 的 `resolved_model/reasoning_effort`、真实 Tool 结果和 Markdown/HTML/manifest ID；不能用 Fake Runtime 或手工数据替代。
3. 复验需提供能遵守 `ROLE_OUTPUT_FIELDS` 的模型/适配器，再重复固定 USENIX 研究输入。

## 代码回归修复

- 未知 reasoning capability 在写入消息前稳定返回 503。
- 旧 Spec027 入口增加最小 `create_idempotent_message_pair` adapter，并保留旧入口显式项目覆盖语义；新 Session endpoint 继续对项目 mismatch fail-closed。

报告对应真实证据：[smoke-report.md](./smoke-report.md)。
