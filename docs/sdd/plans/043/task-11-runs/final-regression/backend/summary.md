# Task11 后端最终回归脱敏摘要

- 候选 HEAD：`9721cbcbbf556e25ebba8de76875540180c02830`；冻结点：`1357494b`。
- 结果：退出码 0；3183 passed、3 skipped、8 warnings、67 subtests passed；236.93 秒。
- Coverage：82.32%，门槛 80%；原始 `.coverage` 118,784 bytes，SHA-256 `f964bfee5cdb8929df6e1749779d52fdcbdaa6fb950cebec3a7b5d41b1fdfd6e`。
- 3 项 skip：2 项浏览器 E2E 经单文件预检确认由 `RUN_E2E` 缺省且需真实服务而跳过；第 3 项在全量结束后以相同隔离 env 单独复核，确认是 `tests/research/test_ollama_direct.py::RealStreamCallTests::test_real_stream_yields_tokens_and_returns_result`，真实输出为 `Ollama 不可达或无可用模型，跳过真实调用`。这项补充验证不改变全量结果。
- Ollama 单项复核退出码 0，原始日志：`/private/tmp/spec043-task11-final-backend-20261028/exit0/logs/ollama-skip.log`；证据摘要见 [`ollama-skip-verification.txt`](ollama-skip-verification.txt)。
- 运行使用 env 清空继承环境，RUN_E2E 未设置；Discovery 开关开启；无在线/LLM/S2 凭据、无服务启动。数据库、缓存、下载、浏览器 profile、TMP 与 coverage 均在 `/private/tmp/spec043-task11-final-backend-20261028/exit0/`。
- 输出：`/private/tmp/spec043-task11-final-backend-20261028/exit0/logs/pytest-full.log`；coverage XML 与原始数据均在上述目录。
- backend tree：`3990c80cf64d8f6c791164add245bd33707f1552`，冻结点一致；backend + 非前端 tests 的 489-file manifest SHA-256：`12ec7c6b133d2e97d60fa202e168a9f1a42f8df1aea4abc431bdd1f084094e16`。
- 完整委托报告：[`2026-10-28-expansion-final-backend-test.md`](../../../2026-10-28-expansion-final-backend-test.md)。
