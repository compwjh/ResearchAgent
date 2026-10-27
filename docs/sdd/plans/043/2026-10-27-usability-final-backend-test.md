# Spec043 Task10 最终后端全量回归

日期：2026-10-27（Asia/Shanghai）  
角色：backend-tester  
最终候选：c17e3f5a  
进展日志：.codebuddy/agent-logs/spec-043/task-10/backend-tester/20261027-210835.md

## 结论

**PASS（Task10 后端全量 pytest 与 coverage 门槛）。** 最终候选全量运行退出码 **0**：**3130 passed, 3 skipped, 8 warnings, 67 subtests passed**。coverage 原值 **82.31%**，--cov-fail-under=80 达标。运行前单独确认两项浏览器 E2E 被仓库现有 skipif 合法跳过；最终命令完全未设置 RUN_E2E，没有启动 Chromium 或服务。

此结论只覆盖本报告中的后端 pytest/coverage；Build、Types、Lint、Security、部署与 Spec043 其他收口门禁不由此报告签署。此前错误配置和中止尝试均保留在下文作为运行器诊断历史，不改变最终正式候选结果。

## 最终正式候选全量记录

实际 pytest 命令：

    /Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests \
      --ignore=tests/frontend -p no:cacheprovider \
      --basetemp=/private/tmp/spec043-task10-final-backend-20261027/exit0/basetemp-final \
      --cov=backend --cov-report=term-missing:skip-covered \
      --cov-report=xml:/private/tmp/spec043-task10-final-backend-20261027/exit0/coverage.xml \
      --cov-fail-under=80

执行使用 env -i，PYTHON_DOTENV_DISABLED=1、PAPER_DISCOVERY_ENABLED=true、LANGFUSE_ENABLED=false；模型 API key 与在线模型清单为空，Ollama/reranker 指向无服务的 loopback。RUN_E2E 不存在于子进程环境，E2E_BASE_URL 指向 127.0.0.1:9 作为额外保护。未访问外部来源、模型或部署服务。

数据库/文件/缓存隔离位置均在 /private/tmp/spec043-task10-final-backend-20261027/exit0/：

- LITERATURE_MAP_DB_PATH、MEMORY_DB_PATH、PAPER_DISCOVERY_DB_PATH、RESEARCH_DB_PATH、AGENT_TASKS_DB
- KB_DIR、QDRANT_PATH、KB_META_PATH
- ARTICLE_DOWNLOAD_DIR、PAPER_DISCOVERY_BROWSER_PROFILE_DIR
- TMPDIR、XDG_CACHE_HOME、PYTHONPYCACHEPREFIX、pytest basetemp、coverage 文件

未全局设置 MEMORY_DIR。仓库根 conftest.py 的 autouse fixture 按用例把 backend.app.memory.markdown_store.MEMORY_DIR 指到 tmp_path/memory；只读默认值断言 test_memory_config_defaults_are_task_specified 保持实际配置。为了保护无参 session-search 默认路径，临时 pytest 插件只对其他用例把 backend.app.platform.config.MEMORY_DIR 换到该用例的临时路径。插件在 /private/tmp/spec043-task10-final-backend-20261027/corrected/plugins/offline_isolation.py，拒绝非 loopback 网络与外部 DNS，屏蔽已知运行服务端口 3000、6333/6334、8000、11434/11435，允许其他 loopback 测试服务与 Unix socket。没有改仓库的 conftest、业务代码或测试。

最终结果：退出码 **0**；3130 passed, 3 skipped, 8 warnings, 67 subtests passed，耗时 243.54s。coverage XML 的 TOTAL 为 46085 statements、8154 missed、四舍五入 82%；coverage 原始总值 **82.31%**，80% 门槛达到。8 条警告中含依赖的 SWIG/jieba 弃用警告。

### 可复用的原始覆盖率数据与来源路径

- 原始 .coverage 数据：/private/tmp/spec043-task10-final-backend-20261027/exit0/.coverage（118,784 bytes）
- source file 清单：/private/tmp/spec043-task10-final-backend-20261027/exit0/coverage-source-files.txt（210 个绝对路径，均位于本工作树的 backend/）
- coverage debug data 完整记录：/private/tmp/spec043-task10-final-backend-20261027/exit0/coverage-source-paths.txt
- XML 报告：/private/tmp/spec043-task10-final-backend-20261027/exit0/coverage.xml

后续前端覆盖率运行可复制上述 .coverage 后基于副本使用 --cov-append，并保持同一工作树 source paths；本次保留的原始后端数据不被合并改写。

### 可复核日志

- 最终原始 pytest 日志：/private/tmp/spec043-task10-final-backend-20261027/exit0/logs/pytest-full.log
- 两项 E2E 收集日志：/private/tmp/spec043-task10-final-backend-20261027/exit0/logs/e2e-collect.log
- 两项 E2E skip 日志：/private/tmp/spec043-task10-final-backend-20261027/exit0/logs/e2e-skip.log
- 脱敏摘要：[task-10-runs/final-regression/backend/summary.md](task-10-runs/final-regression/backend/summary.md)

## 隔离诊断与失败尝试记录（不计入最终候选结果）

1. 初始全量误设 PAPER_DISCOVERY_ENABLED=false 并覆写全局 MEMORY_DIR。结果：3087 passed, 46 failed, 3 skipped, 58 subtests passed，退出码 1，coverage 81.89%。42 个 paper-discovery 测试和 3 个子测试因关闭功能而收到 PAPER_DISCOVERY_DISABLED/503；1 个 memory 配置用例因覆写默认目录而失败。开关恢复且 DB 继续隔离后，单项 paper API 复验退出码 0，1 passed、2 subtests passed。
2. 严格网络守卫启动在约 1% 前由主会话指令中止，退出码 2，无测试汇总，不计结果。随后守卫调整为只阻止外网与已知 live 服务端口，允许 loopback 测试服务和 Unix socket。
3. 一次更正配置的完整尝试错误设置 RUN_E2E=0。测试使用 skipif(not os.environ.get("RUN_E2E"))，非空字符串 "0" 使 skip 条件为假，两个 E2E fixture 尝试启动 Chromium；隔离 HOME 下 Chromium executable 缺失，启动时 setup error。结果为 3130 passed, 1 skipped, 2 errors, 67 subtests passed，coverage 82.30%，退出码 1。错误发生在 browser launch 检查阶段，未打开页面/服务。
4. 按主会话授权，在 RUN_E2E 完全缺省的子进程中单独收集并运行那两项：收集退出码 0，准确收集 2 项；skip-only 运行退出码 0，2 skipped in 0.01s。之后本报告所列唯一正式全量退出码 0。

## 版本与改动边界

本轮最终全量在候选 commit c17e3f5a 上运行。该提交的 backend tree hash 为 2142945a4c8dd89da5a477d9def745507c4fdc25，与冻结点 5d42211a:backend 完全相同。报告整理时当前 HEAD 已前进到 498b6ded；该提交包含前端与文档变更，backend tree hash 仍为 2142945a4c8dd89da5a477d9def745507c4fdc25，且 `git diff --quiet c17e3f5a HEAD -- backend tests ':!tests/frontend'` 通过。因此当前候选与本轮被测候选的后端源码及后端测试相同；前端/文档变化不属于本报告范围。backend 与后端 tests 工作区无改动。

## VERIFICATION REPORT

- **Build：** 未运行（本委托只要求后端全量 pytest）。
- **Types：** 未运行。
- **Lint：** 未运行。
- **Tests：** PASS（3130 passed、3 skipped、8 warnings；67 subtests passed）。coverage 82.31%，80% 门槛达到。
- **Security：** 未运行。
- **Diff：** PASS；后端源码树绑定被测候选 c17e3f5a，且与当前 HEAD 498b6ded 的 backend tree 完全相同，无后端工作区差异。
- **部署/真实 API：** 未运行；本角色未启动服务或调用真实服务。

后端最终全量与 coverage 门禁已通过。本报告不替代其他角色、部署验证或 Spec043 总体验收签字。

