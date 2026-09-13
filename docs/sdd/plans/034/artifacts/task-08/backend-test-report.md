# Spec034 Task08 后端验收报告

## 结论

**GO**。Task08 后端固定合同、Task02–07/Spec027/conversations 定向回归、Fake/Store 补充探针、py_compile、聚焦 Ruff 与 diff-check 全部通过；未发现当前后端验收阻塞。

本次仅验收：未修改业务代码、未修改测试代码、未执行 commit/push/merge/reset/stash/clean。

## 命令与结果

| 检查 | 命令摘要 | 退出码 | 结果 |
|---|---|---:|---|
| Task08 合同 | `.venv/bin/python -m pytest -q tests/test_spec034_task08_backend.py` | 0 | **19 passed**，0.56s |
| Task08 + Task02–07 + Spec027/conversations 定向回归 | `.venv/bin/python -m pytest -q tests/test_spec034_task08_backend.py tests/test_spec034_task02_contract.py tests/test_spec034_task03_contract.py tests/test_spec034_task04_contract.py tests/test_spec034_task05_contract.py tests/test_spec034_task06_contract.py tests/test_spec034_task07_backend.py tests/test_spec027_backend_research_slice.py tests/test_spec027_runtime_contract.py tests/test_conversations_api.py tests/test_memory_repositories.py` | 0 | **246 passed, 5 subtests passed**，8.22s |
| 补充 Fake/Store 探针 | `.venv/bin/python -m pytest -q /private/tmp/spec034_task08_extra_probe.py` | 0 | **4 passed**，0.34s |
| Python 语法 | `find backend -type f -name '*.py' -print0 \| xargs -0 .venv/bin/python -m py_compile` | 0 | 通过 |
| 聚焦 Ruff | `.venv/bin/ruff check [Task08 及受影响后端文件/合同测试] --select E9,F63,F7,F82,I001 --output-format concise` | 0 | `All checks passed!` |
| diff 空白检查 | `git diff --check --` | 0 | 通过 |
| 冲突标记扫描 | `rg -n '^<<<<<<<\|^=======\|^>>>>>>>' backend tests/test_spec034_task08_backend.py docs/sdd/plans/034/artifacts/task-08 .agents/skills/research-report-synthesis` | 0（无匹配） | 通过 |
| 下载路径守卫探针 | `.venv/bin/python -c '...download_research_artifact("s","../../secret")...'` | 0 | `storage_ref/path download guard: PASS` |

系统解释器曾运行同一 Task08 命令并以退出码 1 失败（18 passed、导入 `routes_research` 时 `ModuleNotFoundError: fastapi`）；按项目部署约定切换 `.venv/bin/python` 后全绿。该项为解释器依赖差异，不是业务测试失败。

## 固定探针覆盖

1. **验证与输入安全**：literal `True` verified/validated 标记；未验证候选拒绝；标题/heading 的 URL、路径、Prompt/凭据样式拒绝；Spec027 的恶意论文 `title/abstract` 不进入研究结构；固定 Markdown→HTML 转义并拒绝 raw HTML、`javascript:`、事件属性。
2. **上下游 allowlist 与隔离**：Search→Evaluator 对 candidate、evidence/citation ref、source、source_refs 做绑定；伪造 `attacker`/跨源引用拒绝。补充探针证明 Synthesizer 只消费自身祖先链 Evaluator 的 validated candidate，Critic 注入不会进入 synthesis 输入。
3. **空证据与重试归因**：无 kept/evidence 不调用 Synthesizer，任务收敛 `partial/NO_VALIDATED_EVIDENCE`；continuation 从 `limit_reached` 父 Run 恢复，最终成功 Run ID 归因到全部报告 Artifact。
4. **Artifact**：内容 hash 必须匹配；同 `(task, report_version, artifact_type)` 不覆盖；owner join 隔离；并发插入后重新核对 hash；下载仅接受 artifact ID + owner 绑定，拒绝任意路径/storage_ref，返回固定下载类型/安全响应头。
5. **通知**：`completed`、`partial`、`failed`、`waiting_approval`、`interrupted` 五类均可写入且 owner `event_seq` 单调；幂等键去重；非 owner read 被拒绝；owner read 使用 unread→read CAS；通知 SSE heartbeat、cursor replay 和新事件补发通过。

## 真实运行边界

- `ollama list`：退出码 0，列出 11 个本地模型。
- `curl -sS --max-time 5 http://127.0.0.1:11434/api/tags`：退出码 7，Ollama HTTP 服务本轮未监听；未把模型列表冒充真实 Agent 成功。
- `curl -sS -I --max-time 5 https://www.usenix.org`：退出码 0，HTTP 200。
- `curl -sS -I --max-time 5 https://dblp.org`：退出码 0，HTTP 200。
- 本轮未执行真实目录同步或真实端到端研究链路；确定性验收均使用固定 Fake/Store，避免外部依赖结果污染结论。

## 阻塞与后续边界

- 当前后端验收阻塞：无。
- 5 个 subtests 为既有参数化子测试计数，不是失败；没有新增 warning 阻断。
- 本轮未跑全量 pytest、真实 Ollama Agent smoke 或跨端浏览器验收；Spec 收口仍需总控完成全量回归、前端验收、部署/运行时验证及状态台账更新。

## 日志

- 进展日志：[backend-tester 日志](/Users/wjh/ResearchAgent/.codebuddy/agent-logs/spec-034/task-08/backend-tester/20260913-134937.md)
