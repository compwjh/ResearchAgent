# 复盘：Spec045 评测与可观测性加固闭环（2026-11-08 收口）

> 范围：Spec045 全 11 项加固、Task 02 硬前置消解、Task 07 收口、Task 08 集成验收。
> 分支 `feature/spec-045-evaluation-observability-hardening`；**不 push、不合 main**，
> `origin/main` 仍 `1b26c76c`。

## 1. 结果

| 项 | 结果 |
|---|---|
| 11 项加固 | 11/11 通过（详见 `docs/sdd/reviews/045-acceptance-review.md`） |
| Q10 四类证据 | 4/4 齐全，索引 `docs/sdd/plans/045/runs/task-08/q10-evidence-index.md` |
| 最终全量回归 | `4112 passed, 2 skipped, 67 subtests`，`PYTEST_EXIT=0`（779.30s） |
| 三道门禁 | 需求评审通过、技术评审通过、验收评审通过且架构师签字；准备度 **9/10**（未闭环项为流程待办，非缺陷） |
| 部署验证 | 重启后 `/api/health` 200 / PID 65665；当前版本真实 chat `completed`、kb-ask 单条 trace 9 observations |
| P0 / P1 | 0 / 0 |

## 2. 关键决策

1. **Q8 阶段边界**：设计阶段「只交付文档」的裁决仅约束设计期；用户后续确认开工并授权部署后，
   实施阶段按授权推进，原文保留作历史记录，未改需求目标。
2. **Task 07 A/B 裁决为 A 打通**：真实基准跑通后不触发「跑不起来则删除」的回退。
   四项指标全部来自真实测量（`ttft_ms` 中位、`tokens_per_sec` 改名、真实 `getrusage` 峰值 RSS、
   errors/轮次），经既有 `append_event` 事件通道送达前端，**前端零改动、不新增端点与 SSE 类型**。
   为避免半通状态，明确禁止占位值，并把裁决写回 spec 边界。
3. **真实 E2E 发现的 P1 缺陷就地修复**：真 SDK 冒烟发现 kb-ask 一次请求产生两条 trace。
   根因是 starlette `iterate_in_threadpool` 每次 `next()` 用父 context 的 `copy_context()`，
   SSE 跨 `yield` 后 `_current_trace_id` 丢失，而 `bind_request_id` 只重绑 `_request_id`；
   且 `_open_root` 未用 `with`，惰性 CM 连根 observation 都不创建。
   修复采用「kb 专用 `bind_trace_context` + 根 observation 生命周期收口」，
   **不改 `bind_request_id` 全局语义**（chat/article/conversations 从不 `start_trace`）。
4. **分端纪律**：Task 07 与 trace 修复均为纯后端，只派 `backend-dev` / `backend-reviewer` /
   `backend-tester` / `tester` / `architect`，未派 `frontend-tester`（前端零改动，如实写入验收报告）。
   含代码文件的动作全部先分派再落地。

## 3. 踩坑与修复（可复用经验）

| 现象 | 根因 / 处置 |
|---|---|
| `timeout 300 ...` → `EXIT=127` | macOS 无 `timeout`；改后台 `nohup` + 轮询，或用 `gtimeout` |
| `launchctl submit` 后 label 消失、端口无监听 | 本次执行环境未注册成功；按 `deploy/README.md` 允许的 `nohup env ... ./deploy/start.sh` 恢复，`/api/health` 200 |
| 服务未重启时真实 API 仍返回旧行为（`limit=2` 返回全量） | 无 `--reload`，新代码未部署；重启后重新取证才作数。**部署前取证不算当前版本 E2E** |
| Langfuse 登录报 `Invalid email address` | `vendor/langfuse/.env` 的值带双引号，未 `tr -d '"'` |
| 瀑布图截图可能含系统提示与召回明文 | 用最小共同祖先容器截图，并以 `hasSecret=false` 文本核对；原始 `trace-detail.json`/`observations.json` 早已删除不入库 |
| 部署验证脚本误把 `aaaaaaaa…`（31 obs）当成本次 kb-ask | fixtures 合成 trace 时间戳更「新」；改为按本次真实 `220f5fb2…`（9 obs、单条 trace）核对并重写证据 |
| 全量回归 2 失败 | ① `main.py` / `routes_kb.py` 改动后 `018` 冻结矩阵哈希未同步；② 遗留测试仍 patch 旧符号 `flush`。均按测试口径重签/适配，未放宽断言 |
| `ruff check .` 188 条、`check_test_layout.py` 4 条 EXIT=1 | 全仓存量；只对改动文件要求全绿，并用同正则单独校验新文件，如实披露 |

## 4. 分工与门禁执行

- `backend-dev`：4 轮（retention+分页、A 打通、回归修复、trace 归属修复）；
- `backend-reviewer`：Task 07 后端评审（通过，安全豁免点用恶意 payload 独立复核）；
- `backend-tester`：Task 08 真 SDK / 并发流中断 / 隐私 thinking / `--send` dashboard（精确 49 passed）；
- `architect`：需求评审、技术评审、Gate 5 验收签字；
- `tester`：跨端验收总控 `045-acceptance-review.md`（通过、9/10、签字栏留空待架构师）；
- 主会话：编排、决策、最小增量落地校验、真实 API/浏览器取证、文档与台账、部署与 commit。

三份评审有真实结论、验收签字栏已填、台账已追加、引用路径存在、复盘已落盘，满足 DoD 后转 `已完成`。

## 5. 已声明边界与后续建议（非本次范围）

- P2 三项不做：人工 gold 集（`human_agree_rate=null`）、两套分数口径统一、在线实时评测；
- `redaction.py` 值级脱敏不按 key 名过滤（避免误伤学术文本）；若未来要按 key 过滤，需新 spec；
- `setup_langfuse_dashboards.py --force` 非幂等（默认重建已验证幂等），修复需调用 vendor unstable API；
- 并列 `started_at` 场景建议补一条页序断言；retention 大规模清理宜改异步；
- 项目无覆盖率采集/阈值配置，`docs/github.md` 的 CI / 覆盖率 / PR approval 三项门禁**未验证**，
  与 Spec044 合并披露口径一致，本次不宣称通过；
- `spec-041:93` 的私有 SDK 符号升版回归要求继续保留；
- `018` 矩阵 `inventory_git_revision` 仍为历史值，按授权未动。

## 6. 交付物速查

- 证据索引：`docs/sdd/plans/045/runs/task-08/q10-evidence-index.md`
- 三份评审：`docs/sdd/reviews/045-{requirement,tech,acceptance}-review.md`
- 最终回归与部署：`runs/task-08/full-regression.txt`、`deploy-verification.json`
- 状态台账：`docs/sdd/spec-status-changelog.md` 末条（`实施中 → 已完成`）
