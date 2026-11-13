# SPEC-045 需求评审（Requirement Review）

> 评审者 / 角色：架构师（评审/合并）子代理 `architect`，需求评审 + 技术评审总控
> 模型：自身（当前执行任务的 Agent，不写死模型代号）
> 分派方式：`Task(subagent_name="architect")`（Gate 2 / SDD-GATE-CHECKLIST.md:65,69）
> 评审对象：`docs/sdd/specs/045-evaluation-observability-hardening.md`（全文）＋ `docs/sdd/plans/045/`（README、HANDOVER 第 8 节、task-02..08）
> 评审依据：Gate 1/Gate 2（SDD-GATE-CHECKLIST.md:52-80）、ROLE-ONBOARDING.md:11-22,33-43、AGENTS.md:116
> 关联输入：ADR 0002、两份 `045-*.md` 调研 notes 第 4/5 节、`docs/sdd/spec-status-changelog.md`、`docs/sdd/plans/045/runs/**`
> 评审阶段：**实施收口前的需求评审总控**（spec 状态 `实施中`，本轮不转 `已完成`）；本文件覆盖 2026-11-08 13:24 设计阶段 `待确认` 版评审
> 评审日期：2026-11-08

---

## 结论

**通过。**

目标清晰可测；范围（P0 + P1 共 11 项）与「明确不做」（P2 三项、Q8 设计阶段边界及后续授权解除的台账依据）完整；产品使用步骤逐步具备「点击/提示/等待条件/下一步/失败恢复/产物路径」六要素，自然语言入口优先且真实；Q10 四类证据各自有真实、可查的落盘路径。

- **P0 缺陷：无。P1 缺陷：无。**
- 本结论为**需求维度**评审，不代写验收评审、不替 tester 签字、不宣称准备度分数、不把 spec 状态改为 `已完成`；验收签字与收口由 `045-acceptance-review.md` / 主会话按 AGENTS.md 三道门禁另行完成。
- 下列「已声明边界与残留」全部按 Q1/Q3/Q7/Q8、ADR 0002、task-08「边界与明确不做」如实记录，**不计为遗漏或失败**。

---

## 逐项结论（附 `文件:行`）

### 1. 目标清晰、可测 — 通过

- 「一句话目标」（spec:16-21）三个可判定谓词：① 发布前后各跑一次评测即可判定质量涨跌（:20）；② 一个 ID 还原全链路（:20-21）；③ 观测上报拖不慢聊天、数据不越跑越胀（:21）。每个谓词都有对应验收产物（Q10 ② / ③ / ④）。
- 措辞统一为「加固与闭环」（Q3 裁决 spec:60、`domain-modeling` 锐化 ADR:94-96），未混入「修复」「自动提升质量」。
- 成功定义落成 11 项逐条「现状证据 F 编号 → 目标 → 所属 task」（spec:95-107），可逐项追溯；「边界」章（spec:187-196）把空/极值/重复/不存在/冲突/并发/失败恢复/隐私转成可测条件。
- 可测性经真实取证反证：`runs/task-08/q10-red-green-summary.md:55-171` 三项缺陷修复先红后绿；`runs/task-02/evidence.md:67-93` CLI 五类指纹 + score 幂等 delta=0。

### 2. 范围（P0 + P1 共 11 项）完整 — 通过

- Q1 裁决范围 = P0 + P1（含第 0 项）、P2 三项明确不做（spec:58）。11 项表（spec:95-107）逐条标注类别（缺陷修复 / 能力补齐 / 规格落地，Q3 spec:60）与所属 task（03–08）。
- Q7 私有 SDK 兼容层并入 05 项（spec:64,101），无游离项；06 项「打通或删除」二选一已由实施阶段裁决为 **A 打通**并回填 spec（spec:109-115、task-07:122-148），属已确认范围内细化，未扩范围。
- 任务计划（spec:308-317）与 README 任务索引（README:30-39）、HANDOVER 第 8 节（HANDOVER:83-113）三者口径一致：02 硬前置已消解、03–07 完成、08 待执行。

### 3. 「明确不做」完整（含 Q8 设计阶段边界与授权解除台账）— 通过

- **P2 三项**（spec:119-121）：① 人工标注 gold 集（`human_agree_rate` 仍 `null`）；② `research_model_outcomes.quality_score` 与 Langfuse score 口径统一；③ 在线实时评测。ADR 0002:45-46（决策 3）、ADR:78-81（代价）一致，task-08:70、task-03:62-63、task-07:81-82 逐任务重申。
- **设计阶段边界（Q8）**：spec:65「本次只交付文档」、spec:123「本期不改任何业务代码（`.py`/`.js`/`.html`/`.css`），不启用 Langfuse、不改 `.env`、不跑评测、不改配置」，Q12 状态 `待确认`（spec:69）。
- **授权解除的台账依据**（本轮重点核对，链路完整）：
  - spec:124「阶段说明（2026-11-08 接手回填）」明确 Q8 是**设计阶段**约束；用户随后确认「开始工作」并授权按 `deploy/langfuse/README.md` 部署后，实施阶段边界以用户后续授权为准，原文保留作历史裁决记录；Task 03–06 业务代码已落地、Langfuse 已启用、真实评测已跑通。
  - `docs/sdd/spec-status-changelog.md:11` 记用户「确认，你开始工作吧」→ 转 `已确认` 进入实现；`:3` 记用户澄清「原始文件指 vendor/langfuse 源码」并授权按 README 非 Docker 部署、指示子代理换档；`:9` 记 `doc-updater` 已补齐产品使用步骤三场景。
  - `plans/045/README.md:20-22` 明文「用户确认后已进入实施，Q8 的『仅交付文档』边界随之解除」；`HANDOVER.md:83-96` 记接手机器 `git pull origin main` 获取 `1b26c76c` 后 Task 02 硬前置真实消解（dual 模式 200、20 fixtures、真实 E2E、真实 CLI、score delta=0）。
  - 原技术评审 P0-1（`start-langfuse.sh:15` 硬编码路径）已由 `backend-dev` 分派修复并静态验证（changelog:9），HANDOVER:87-88 实跑 `start-infra.sh`/`start-langfuse.sh` 成功，前置已消解、不再阻塞。
- **其余「不做」**（spec:125-130）：不重构 SDK 接入、不改上报字段与瀑布图语义；不改根 `CONTEXT.md` / `docs/sdd/context/CONTEXT.md`、不新建 `CONTEXT-MAP.md`；不迁移历史数据、不改 SSE 事件协议；不 push、不合 main。与 ADR 0002:52-54、HANDOVER:121-126 一致。

### 4. 产品使用步骤可操作 — 通过（自然语言入口优先，逐项六要素齐备）

- spec:198-277 三场景全部按模板「每步：控件 / 提示 / 是否等待及等待期间状态 / 下一步 / 失败恢复 / 最终产物路径」填写，且控件与命令全部来自真实代码、附 `文件:行`：
  - **场景 ①**（spec:208-230）：CLI `python -m backend.eval_042.cli`（`backend/eval_042/cli.py:64-87`，spec:205 明确主入口是离线 CLI、不是网页按钮），含步骤 1 发布前基线（:212-218）、步骤 2 发布后（:219-224）、步骤 3 比较涨跌（:225-230）；等待态「需等待、无进度条、终端打印汇总键」（:215）、失败恢复 argparse 报错补参（:217）、产物 `runs/task-08/v1-before|v1-after/report.json|md`（:218,224）。
  - **场景 ②**（spec:232-248）：自然语言入口在浏览器 Langfuse web（:238）、等待 trace 列表（:239）、`OBSERVABILITY_MODE=dual` 失败恢复（:241）、trace ID + 四段 span + score 回写核对（:243-248）、硬前置未就绪时明确「不可执行、跳过」（:235）。
  - **场景 ③**（spec:250-266）：深度研究自然语言入口 `POST /api/research-sessions`（`frontend/research-tasks.js:3451`，spec:256）与「深度研究模式」提示（:256 引 `research-tasks.js:3465`），DevTools 等待 SSE `done` 尾包（:257 引 `routes_chat.py:191`）、T0/T1 对比、失败恢复回 task-05（:265）、产物对比表 + 瀑布图截图（:266）。
- spec:203-206「前置硬条件」把 Q9 三项硬前置与「跳过、不得判已完成」写进每个场景，spec:268-273 给出「场景 → Q10 四类证据」映射，spec:275-277 处理历史 P1-1（06/10 验收归属）。自然语言入口优先（先浏览器/对话，再 CLI 命令对比）与真实代码一致，可操作、可复核。
- 设计阶段版评审中「产品使用步骤留空」一项，已由 `doc-updater` 补齐（changelog:9、spec:200-201），本轮据实复核为**已具备**。

### 5. Q10 四类证据各自有真实落盘路径 — 通过

Evidence 根目录真实为 `docs/sdd/plans/045/runs/`（README:6,26、spec:321-322、task-08:45-49）；四类各有真实文件（`find` 核实 31 个文件、非占位）：

| 类别 | 真实落盘路径 | 取证内容（`文件:行`） |
|---|---|---|
| ① 红绿测试 | `docs/sdd/plans/045/runs/task-08/q10-red-green-summary.md` + 4 份日志 `red-03-sampling.log` / `red-04-flush.log` / `red-09-redaction-thinking.log` / `green-current-code.log` | q10-red-green-summary.md:1-5,28-43,162-175（03/04/09 三项隔离副本 RED→GREEN，仓库 `backend/**` 零改动 :20-21）；三处真实失败断言 :63,99,132-140；green-current-code.log `21 passed in 0.97s` |
| ② 评测产物 | `docs/sdd/plans/045/runs/task-02/eval-baseline/report.json` + `report.md`（重跑 `eval-rerun/` 同对） | `report.json:53,56,58,60,63` 五类指纹 `dataset_sha256`/`judge_model_digest`/`prompt_sha256`/`seed=42`/`tie_break_rule`；`evidence.md:67-87` 命令、退出码、真实 score 回写；`task-08` 引用该产物（q10-red-green-summary.md:9、HANDOVER:93） |
| ③ 可查 trace | `docs/sdd/plans/045/runs/task-08/sdk-smoke.json` + `trace-attribution-fix.json` + `runs/task-02/trace-summary.json` / `real-chat-sse.txt` | `trace-attribution-fix.json:24-59` 真实 ID `1979780db30c4349b843af34346bd296`、9 observations、四段 phase span、7 scores、根 observation `ended=true`（:42-51）、chat 链路未回归（:60-77）；`sdk-smoke.json:18-41,89-95` 真 SDK 4.15.1 私有符号形状 + 四段 span/completion_start_time/7 scores；`evidence.md:33-65` trace `98b91aa3…` 五条 observations |
| ④ 瀑布图截图 | `docs/sdd/plans/045/runs/task-08/waterfall.png`（393×565 PNG，已只读打开核对四段 `phase:load/prefill/decode/overhead` 可见、顺序正确） | 与 `trace-attribution-fix.json:37-40` 四段 span 归属一致；配套 `dashboard-contract.json`（真 `--send` + 看板契约）、`runs/task-07/benchmark-card.png` + `benchmark-card-browser.txt`（真实 Chromium 四项指标） |

- 硬前置（Q9）已消解：`HANDOVER.md:83-96`、`runs/task-02/evidence.md:7-20`（双栈四端口、dual 模式 traces/scores 200、health 200）、`:22-31`（20 fixtures）、`:33-43`（真实 SSE E2E）。
- `ADR 0002:40-44` 验收证据集四类缺一不验收，四类均已「写明保存路径」，符合 Q10（spec:67,140-147）与 ADR 决策 2。

---

## 已声明边界与残留（如实写入，不作为遗漏或失败）

1. `human_agree_rate` 仍为 `null`（P2 人工 gold 集明确不做）：spec:119,32（F2）、ADR 0002:28-29,78-79、`runs/task-02/eval-baseline/report.json:6`（实际 `"human_agree_rate": null`）、`runs/task-02/evidence.md:104`。评测结论仍是相对回归基线，不宣称绝对准确率。
2. `research_model_outcomes.quality_score` 与 Langfuse score 两套口径仍不统一（P2）：spec:120,47（F17）、ADR 0002:80-81、`045-evaluation-module-survey.md:226`、`HANDOVER.md:123`。
3. 在线实时评测不做：spec:121、ADR 0002:45-48,62、task-08:70。
4. `redaction.py` 按值级脱敏、**不按 key 名过滤**（避免误伤含 `token` 等词的学术文本的设计取舍）：`backend/app/platform/observability/redaction.py:9-10,29-41,60-70`、`task-06:90-92`、`trace-attribution-fix.json:98`；已由真实链路测试刻画（`sdk-smoke.json:203-221` 合成凭据真链路隐私回归 `plaintext_credential_in_stored_trace=false`、`q10-red-green-summary.md:124-158` 15 用例红转绿）。
5. `setup_langfuse_dashboards.py --force` 非幂等：`dashboard-contract.json:92-104`（删除 dashboard 不级联删 widget 的 DEFECT 只读核验，**默认重建已验证幂等** `dashboard-contract.json:59-90`：6 dashboard/40 widget ID 与名称多重集不变；`--force` 未真实重跑、只读核验 `:11-14,102-103`）。属业务脚本、超出本 spec 边界，明确「reported, not fixed」（:93）。
6. `018` 冻结矩阵 `inventory_git_revision` 仍为 `8b0cde1`：`docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json:3`、`task-07:183`；矩阵哈希两次重签均已验证 `2 passed`（`tests/kb/test_kb_upload_closure_matrix.py:15,43` 两用例、`backend-review.md:35` 按 `:83-88` 算法重算 `MATCH=True`、3 字段同步），`inventory_git_revision` 未授权改动、保持原样。
7. 并列 `started_at` 时无参与分页行序可能不同但**集合一致**：`backend-review.md:33-38`（无参 `ORDER BY started_at, logical_sequence`、分页 `ORDER BY started_at, step_id`，逐页拼接与全集集合一致）、`task-07:179-180`。分页本身不重不漏、稳定，判已知边界非缺陷。
8. retention 默认启动期同步执行：`task-07:181-182`（`EVENT_RETENTION_ENABLED` 默认 `True`、启动期同步；当前阈值下不删行，未来大规模清理应改异步）、`backend-review.md:42-45`、`config.py:234-239`（90 天/10 万行/VACUUM 保守阈值）、`task-07:158` 真实 DB `deleted=0`。
9. Langfuse 读回 `GET /api/public/traces/{id}` 对 kb trace 返回空数组，改用 `observations?traceId=` / `scores` 端点核对：`trace-attribution-fix.json:10`（`public_api_quirk`）、`sdk-smoke.json:100-103,137-138,172-174` 用两类专用端点取证。属 Langfuse v4 读回怪癖，非本 spec 缺陷。
10. `spec-041:93` 的私有 SDK 符号升版回归要求仍保留：`docs/sdd/specs/041-langfuse-trace-detail-and-waterfall.md:93`（原文：每次 langfuse 升版后必须跑 1 次回归）、`ADR 0002:82-84`、`task-08:18,92`、`sdk_compat.py:1-14`（封装只保证退化可发现 + 修复点唯一，不保证不退化）。真 SDK 冒烟已补（`sdk-smoke.json:18-41`），但升版回归要求不撤销。
11. Spec045 明确「不 push、不合 main」：spec:130、`task-08:76`、`task-07:83`；当前工作分支 `feature/spec-045-evaluation-observability-hardening`（HEAD `f8106ff9`）**未合并、未推送**，`origin/main` 仍停在 `1b26c76c`（本轮 `git branch --show-current` / `git rev-parse origin/main` 只读核实）。HANDOVER:6,10-13 记的是更早一次设计阶段交接 push，不改变本轮工作分支不推送不合并的事实。

---

## P0 / P1 缺陷列表

| 级别 | 数量 | 说明 |
|---|---|---|
| P0 | 0 | 无 |
| P1 | 0 | 无 |

> 上述「已声明边界与残留」11 项均为 Q1/Q3/Q7/Q8、ADR 0002、task-08 边界内已声明并如实取证的设计取舍或后续阶段项，按 task-08:90-92 要求如实声明，**不得写成遗漏或失败**。设计阶段版评审的 P1-1（06/10 未列入 Q10 四类证据编号表）已在 spec:275-277 与 task-07:157-162 显式声明验收归属，闭环；技术评审设计阶段 P0-1（环境前置）已消解（见本文件第 3 节台账）。
> 本评审不打回，故无「回到某个 task」的缺口项。

---

## 评审边界声明（纪律）

- 本文件只做**需求评审**（目标 / 范围 / 明确不做 / 产品使用步骤 / Q10 证据落盘路径），与 `045-tech-review.md` 技术维度分工；不代写 `045-acceptance-review.md`、不替 `tester` 签字（Gate 5 由 tester 出报告 + architect 签字，本轮不出签字结论）、不宣称任何准备度分数、不把 spec 状态改为 `已完成`。
- 状态口径如实说明：spec 头部状态字段仍为 `已确认`（spec:5），而 `README.md:4` 与 `spec-status-changelog.md:3` 记为「已确认（实施中）」、spec:324 与用户本轮口径为「实施中」。该头部字段与流程阶段的措辞差异属主会话收口时应同步的台账项，按「禁止改 spec 状态」纪律本轮不改动，也绝不改为 `已完成`；本评审标题所称 `实施中` 为用户给定的流程阶段口径。
- 收口前仍须由主会话/tester 补齐的项（不在本评审结论内）：最终全量回归 + 覆盖率、`045-acceptance-review.md` 与 tester/architect 双签、部署验证、`docs/sdd/retro/` 复盘、`spec-status-changelog.md` 的 `实施中 → 已完成` 条目与本地 `git commit`（`task-08:50-57,84-87`；不 push、不合 main）。spec 当前保持 `实施中`。
- 逐项结论均基于 `Read` / `Grep` / `git` 只读事实并附 `文件:行`（Gate 2:72），无「应该没问题」式结论；本轮只读评审，未改业务代码/测试/spec 状态，未 `git commit` / `push` / 合 main。
