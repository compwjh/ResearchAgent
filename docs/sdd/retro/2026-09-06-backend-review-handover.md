# 复盘：本地子代理评审中断后的主会话承接（2026-09-06）

## 事实经过

- 2026-09-06 13:48 与 14:33 两次分派 `backend-reviewer`（本地 `qwen3.8:27b-mlx`）评审 spec-015 的 USENIX slug 修复，两次日志都只写到「步骤 1：技能加载」便中断（`.codebuddy/agent-logs/backend-reviewer-015-20260906-134828.md`、`-143350.md`）。
- 期间电脑重启。恢复后由用户决定：本次 backend-review 由主会话（架构师）直接承担。
- 主会话按 `backend-reviewer.md` 的角色职责完成评审，产出 `docs/sdd/reviews/015-backend-review.md`，结论 WARNING（1 HIGH：新代码路径无测试）。

## 结论与经验

1. **子代理日志只有步骤 1 ≠ 配置错误**。两次日志格式规范、进度百分比正常，说明模型已启动并按技能要求落盘，中断原因在宿主（重启/超时）而非模型或配置。判断依据写在 `docs/sdd/retro/2026-09-02-subagent-timeout-mlx.md` 的经验仍然成立：**先查历史日志再排查配置**。
2. **小范围改动适合主会话直接评审**。本次改动仅 1 个源文件 + 1 个测试（+165 行），本地 27B 子代理单次分派需 3–8 分钟且易被环境打断；主会话读全文 + diff + 调用链 + 跑一次全量 pytest 即可闭环，性价比更高。**分派阈值建议：单文件、无并发/事务语义的补丁，主会话直接评；跨文件/含并发边界的改动再派子代理。**
3. **角色边界仍要守**。主会话代执行时，仍按 `backend-reviewer.md` 走完整流程（git diff → 读全文 → 核对调用链 → 回归验证 → 报告落盘 → 进展日志落盘），未改业务代码、未越界评前端。
4. **测试覆盖缺口是最容易漏掉的缺陷类型**。本提交修了两处，只给一处补了测试；`_listing_for` 的修复无测试且位于 Task14 同步路径，回退不会被现有 619 个用例发现。**规则化：评审时必须逐条比对「提交说明里的每个修复点」与「新增测试」，缺一个即记 HIGH。**
5. **契约等价性要显式验证**。本次改动看似改变失败判定，实际 `error_code` 与 warnings 语义与改前等价——这类「看着像破坏性变更、实际无契约影响」的判定，必须落到代码行比对，而不是读提交说明。

## 补充（同日稍晚）：backend-tester 再次出现「依赖缺失」伪失败

- **现象**：`backend-tester`（qwen3.5:9b）回报「全量 pytest 因 `langchain_ollama` 缺失无法运行」，A1 判 FAIL；并把 `.codebuddy/agents/*.md` 的改动当成 A3 不通过。
- **复核**：venv 中 `langchain_ollama` 存在（`.venv/bin/python -c "import langchain_ollama"` 正常）；用 `.venv/bin/python -m pytest tests/ -q` 得 **626 passed / 0 failed**。`.codebuddy/agents/*.md` 在本次会话开始前就已修改，与本次改动无关。
- **根因**：子代理未严格使用仓库 venv 解释器。这是历史坑的重演——提交 `5d527ad` 曾专门固化「先 source .venv」的验证命令，说明**写进 agent 定义仍不足以约束 9b 模型**。
- **规则化（新增）**：
  1. tester 类子代理回报「依赖缺失 / 大面积失败」时，主会话**必须先用 venv 复跑一次再判定**，不得直接采信写入验收结论。
  2. 判定「改动文件范围」时，必须以任务开始前的 `git status` 快照比对，不能把会话前已存在的改动算作本次引入。
  3. 给子代理的 prompt 里，venv 路径要写成**绝对路径命令**（`/path/.venv/bin/python -m pytest ...`），不要只写「用 venv」这类描述性要求。

## 后续动作

- 按报告「强制约束清单」补 `_listing_for` 与显式 `cycle` 分支测试（可由 `backend-dev` 承接，属小改动）。
- 明确 USENIX 受控年份下界，消除默认 5 年窗口内的常驻 `USENIX_UNAVAILABLE` 告警。
