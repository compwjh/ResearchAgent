# Spec034 Task10 跨端最终验收汇总

## 执行信息

- 执行角色：tester（Luna high）
- 执行日期：2026-09-15（Asia/Shanghai）
- 工作目录：`/Users/wjh/ResearchAgent`
- 分支/提交：`feature/spec-034-conversational-research-runtime` / `6d5cb3d`
- 范围：读取 Task10 计划、Spec034、backend/frontend reviewer 与 tester 交接物；执行唯一一次项目全量 pytest、全部前端 JS 合同、JS 语法、Python 编译、冲突标记与空白检查；复核服务/Ollama 前置。
- 约束：未修改业务代码、测试代码或 Spec；未执行 commit/push/merge/reset/stash/clean。

## 最终结论

**NO-GO，Spec034 不能标记为“已完成”。**

代码 reviewer 交接物中的 P0/P1 为 `0/0`；但最终跨端验收阶段仍有以下 **4 项 P1 阻塞**：

1. **全量回归失败（2 个根因，合计 15 个失败用例）**：未知 reasoning capability 的消息路径实际返回 200 而非合同要求的 503；Spec027 旧研究任务 API 的 FakeMemoryRepository 缺少 `create_idempotent_message_pair`，导致多项创建/事件/报告/上下文合同返回 503（其中一个显式 project override 为 409）。
2. **真实 Smoke 未完成**：`127.0.0.1:8000` 未监听，无法进入真实浏览器审批、真实 Planner/Search Worker/目录 Tool、三级树、报告下载链路。
3. **Ollama 未可达**：`ollama list` 退出码 1，报告为连接 `0.0.0.0:11434` 被拒绝；本轮没有取得 `resolved_model`、`reasoning_effort`、真实 Tool、`research-event:{task}:{seq}` 或 Artifact ID 证据。
4. **部署未验证**：根路径与 health 均 HTTP 000/退出码 7，未形成可复核的成功启动端口和运行时证据。

P0：0。前端 reviewer/tester 的确定性合同没有发现 P0/P1；前端 reviewer 记录的 Session-only 快速切换 stale guard 为 P2，非本轮收口阻塞。

## 验证结果

### 唯一全量 pytest

执行一次：

```bash
.venv/bin/python -m pytest -q --disable-warnings --basetemp=/private/tmp/spec034-task10-pytest.5GZcbI
```

结果：退出码 **1**；`15 failed, 1847 passed, 1 skipped, 5 warnings, 52 subtests passed`，耗时 109.55 秒。

失败证据集中为：

- `tests/test_reasoning_options_endpoint.py::test_message_path_unknown_capabilities_rejects_non_off_with_503`：实际 200，期望 503。
- `tests/test_spec027_backend_research_slice.py` 中 13 项由 `_FakeMemoryRepository.create_idempotent_message_pair` 缺失引起的创建/事件/报告/上下文链路失败，另有 `test_post_explicit_project_overrides_conversation_project` 返回 409 而非 202。

因此不能把前序 Task 的定向通过升级为 Spec034 全量通过。

### 前端 JS 合同与静态门禁

- `for f in tests/test_frontend*.js; do node "$f"; done`：退出码 0，**8/8** 合同 PASS。
- `for f in frontend/*.js; do node --check "$f"; done`：退出码 0，**6/6** 文件通过。
- `.venv/bin/python -m compileall -q backend`：退出码 0。
- `git diff --check -- .`：退出码 0。
- 精确扫描 `^(<<<<<<<|>>>>>>>)`：**0 命中**。宽扫描的 2 个 `=======` 命中是技能模板/历史 Markdown 分隔线，不是冲突标记。
- 前端交接报告另证实全部前端 Python 合同 **206 passed**、Task07–09 定向前端合同 **20 passed**、资源标签 **9/9** 带版本参数、XSS 危险 sink 为 0；本轮未再次运行 pytest，避免重复项目回归。

### 前后端交接汇总

- `backend-review-final.md`：GO，后端 P0/P1 `0/0`；批准 runtime、旧幂等 key 重放、cleanup provider/fail-closed 三项修复已关闭。
- `backend-test-report.md`：GO；Task10 合同 **5 passed**，Task04–10 固定集合 **105 passed**，Task02–09 受影响集合 **124 passed**；明确未执行真实 Smoke/部署。
- `frontend-review.md`：代码 GO，P0/P1 `0/0`，P2 `1`；真实浏览器 Smoke 因服务未启动延期。
- `frontend-test-report.md`：确定性前端 GO，但 Task10 最终浏览器验收 NO-GO；根路径/health 均连接失败。

## 真实 Smoke 与部署状态

当前没有 `docs/sdd/plans/034/artifacts/task-10/` 下的 Smoke 或部署证据文件；前后端交接报告均明确把真实 Smoke 留给主流程。复核命令及结果：

```bash
curl -sS -o /dev/null -w 'root:%{http_code} bytes:%{size_download}\\n' --max-time 5 http://127.0.0.1:8000/
# exit 7，root:000，连接被拒绝

curl -sS -o /dev/null -w 'health:%{http_code} bytes:%{size_download}\\n' --max-time 5 http://127.0.0.1:8000/api/health
# exit 7，health:000，连接被拒绝

ollama list
# exit 1：连接 http://0.0.0.0:11434 被拒绝
```

本轮未收到真实 API 的 `MODEL_UNAVAILABLE` 响应，因此不把环境探针失败伪装成某个 Smoke 业务结果。若主会话后续取得的真实 Smoke 结果为 `MODEL_UNAVAILABLE`，判定仍为 **NO-GO，Spec034 不能标记为已完成**；必须先恢复 Ollama/服务，再用固定主题“软件供应链攻击”、目标“总结 2020–2024 年 USENIX Security 论文中的攻击面与防御方法”、`time_range=2020–2024`、`source=usenix`、中文输出复验完整链路，并记录实际模型/推理档位、Tool、canonical event、三级 ProcessingStep 及 Markdown/HTML/manifest ID。

## 复验与解除阻塞命令

```bash
ollama list
./deploy/start.sh -d
curl -sS -o /dev/null -w 'root:%{http_code}\\n' http://127.0.0.1:8000/
curl -sS -o /dev/null -w 'health:%{http_code}\\n' http://127.0.0.1:8000/api/health
```

若 8000 被占用，使用 `PORT=8300 ./deploy/start.sh -d` 并将探针地址替换为 `http://127.0.0.1:8300`。服务与 Ollama 均可达后，需由主会话补做真实浏览器 Smoke；同时修复并重跑上面的唯一全量 pytest，直到 0 failed，才能进入 Tech Lead 签字、部署验证、复盘和 Spec 状态收口。

## 当前状态与交接

- Spec034：保持 `已确认`；Task10：保持 `实施中`。
- 本报告不修改 Spec 状态台账，不代替主会话的真实 Smoke、部署、复盘或 Tech Lead 签字。
- 进展日志：`.codebuddy/agent-logs/spec-034/task-10/tester/20260915-021259.md`
