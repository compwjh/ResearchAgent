# Spec043 Task10 后端最终回归摘要

本轮在候选 c17e3f5a 上测试；backend tree hash 为 2142945a4c8dd89da5a477d9def745507c4fdc25，与冻结点 5d42211a 相同。整理报告时当前 HEAD 为 498b6ded，其 backend tree hash 相同，且从 c17 到当前 HEAD 的 backend/后端 tests diff 为空；最终测试后 backend 与后端 tests 无工作区差异。

最终正式全量仅排除 tests/frontend，启用 --cov=backend --cov-fail-under=80。运行时启用 paper discovery、未设置 RUN_E2E、关闭 dotenv 和 observability；数据库、KB、下载目录、缓存、coverage 与 pytest 临时目录都在 /private/tmp/spec043-task10-final-backend-20261027/exit0/。MEMORY_DIR 未全局覆写：默认值断言保留实际配置，其他用例的 session-search 配置路径经临时 pytest 插件隔离。网络 guard 仅阻止外网/已知 live service，允许其他 loopback 测试服务与 Unix socket。

结果：退出码 **0**；**3130 passed, 3 skipped, 8 warnings, 67 subtests passed**，243.54s。Coverage 原值 **82.31%**，80% 门槛达到。E2E 两项先经独立 collect/skip 检查确认均合法 skip；最终运行未启动 Chromium、服务、模型或真实来源。

此前错误 isolation run（46 个环境诱发失败）、严格 guard 中止、RUN_E2E=0 setup error 均作为独立历史 attempt 保留在完整报告中，不计入最终候选结果。

原始日志：/private/tmp/spec043-task10-final-backend-20261027/exit0/logs/pytest-full.log
Coverage XML：/private/tmp/spec043-task10-final-backend-20261027/exit0/coverage.xml
原始 .coverage：/private/tmp/spec043-task10-final-backend-20261027/exit0/.coverage
Source files（210 paths）：/private/tmp/spec043-task10-final-backend-20261027/exit0/coverage-source-files.txt
Coverage data paths：/private/tmp/spec043-task10-final-backend-20261027/exit0/coverage-source-paths.txt
临时网络/memory 插件：/private/tmp/spec043-task10-final-backend-20261027/corrected/plugins/offline_isolation.py
完整报告：[2026-10-27-usability-final-backend-test.md](../../../2026-10-27-usability-final-backend-test.md)

