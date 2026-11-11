# 复盘：Spec047 追加范围三「≥100 条真实样本 + 紧凑可展开指标卡」收口

> 复盘范围：2026-11-11 用户提出诉求 → 确认 → 实现 → Go/No-Go 调优 → 验收收口。
> 不新增 spec 编号；spec 主体、追加范围一（D7–D12）与追加范围二的收口结论、三份评审签字、原六块历史记录逐字保留、不翻案。
> 数字型验收材料以 `docs/sdd/plans/047/runs/task-16/full-regression.txt` 与 `docs/sdd/reviews/047-acceptance-review.md` §15 为准。

## 1. 用户诉求与红线

用户原话：「**样本数太小了，帮我生成多个样本，至少要100吧。然后每个指标卡片太大了，缩小点，
一些参数可以隐藏，然后点开能看到详情，但一些关键信息可以不用隐藏。**」，后明确「**确认，你实施吧**」。

继承的历史红线：

- 「**这个新的spec不要新增号码，归为047的追加功能**」→ 全部设计写进 `047` 追加范围三，不新增 spec 文件 / `plans/048/`。
- 「**功能不要降级或者关闭态，我需要看到效果**」→ 100 条真实出分，不 mock、不降采样、不靠 `degraded` 收场、不隐藏卡片。
- 反伪造：非 computed `value=null` + `detail.reason` 必填，不硬编码分数、不静默记 0、不把 `null` 显示成 `0.0000`。

## 2. 决策链

| 决策 | 依据 | 结论 |
|---|---|---|
| 归入 047 追加范围三、状态 `待确认 → 已确认 → 实施中` | `AGENTS.md` 强制流程第 3/4/5 条；范围扩大（数据集规模 / `max_items` / 超时预算 / 卡片交互） | 用户确认后才动业务代码；台账逐条记录 |
| Gate 2 由 `architect` 独立评审 | 需求评审 §15「通过」P0=0/P1=0；技术评审「追加范围三」「通过」P0=0/**P1=4** | 4 项 P1 均属 spec 内部口径冲突 / 实现断点，书面裁决沉淀为 **spec §13.1**，不改目标 / 公开接口 / 用户行为，**不退回 `待确认`** |
| Go/No-Go 硬判据统一为 900s | `spec:818` 写「>300s 判 No-Go」，与 900.0s 预算冲突（评审 P1-1） | 硬判据 = 900s 内 100 条、22 项 computed 全量 `sample_count≥100` 且 `value` 非 null；300s 仅为优化目标线 |
| 超时常量收敛单一真源 | `service.py:37` 才是 `score():257` 生效真源（评审 P1-2） | 删除重复定义、从 `contracts` import；前端 `900000` 对齐；补一致性测试 |
| `call_ollama` 输出上限 | `judge_client.py:160` 固定 `num_predict=160` 会截断 B=20 批量 JSON（评审 P1-3） | 允许**可选**形参、默认 160 不变、仅批量调用覆盖；§7「不改 `eval_042` 既有映射」的唯一例外，写入交接报告 |
| chat 集唯一数据源 | `load_chat_items()` 只读 042 文件且过滤条目级 `synthetic`，新增 gold 样本根本不会进入打分（评审 P1-4） | `gold/builtin-chat-quality.json` 的 `items` 实打实 ≥100；文档级 / 条目级 `synthetic` 分层；`item_count` 同源 |
| 首轮 NO_GO 的处置 | 27B × 100 条 → HTTP 504 / 900.016s | **不降采样、不靠 degraded、不改写判据**；配置级重试（9b）GO + 范围内性能缺陷修复，最终部署版本 GO |
| 选项区样本数补丁 | 真实 Chromium 快照发现 §8 ① 未落地（下拉只有 label） | `frontend-dev` 最小补丁 + `?v=77`，复审 / 回归通过 |

## 3. 事实链（可复核）

- 三份内置集：`rag-retrieval` **128**、`intent-classification` **120**、`chat-quality` **120**（20 条 042 冻结 trace + 100 条 KB 派生）；`scripts/generate_evaluation_samples.py` 只读 KB、只写三份 gold、复跑 sha256 一致、不含分数字段。
- 契约：`DEFAULT_MAX_ITEMS=100` / `MAX_ITEMS=200` / `SCORE_TIMEOUT_SECONDS=900.0`；前端 `900000`；五端点 / 22 key / 5 group / 稳定错误码不变。
- Go/No-Go 三轮真实 HTTP：① 27B 旧代码 504/900.016s **NO_GO**；② 9b 旧代码 200/671.261s **GO**；③ 9b **最终部署版本（共享生成修复后）** 200/**596.084s** **GO**。
- 浏览器实测：选项区 `（128/120/120 条样本）`；22 张卡 `padding:8px` / `gap:5px` / `value:18px`；5 组标题；`<details>` 默认收起、点击展开 7 行参数；`null→—`；`needs_ground_truth` 原因可见；按 5 组展示 22 项 delta；无 `[object Object]`、无 `<script>` 注入。
- 定向回归：后端 `346 passed` → 修复后 `351 passed`；前端 `509 passed` → 补丁后 `514 passed`；`node --check` 0、`ruff` / `py_compile` 0。命令 / 退出码 / 通过数见两端 `*-regression.md`。

## 4. 踩过的坑（供后续复用）

1. **规格内部自相矛盾**：Go/No-Go 写 300s、预算写 900s，若不在实现前裁决，实测达标也会被误判失败。
2. **同名常量两份定义**：`contracts.py` 与 `service.py` 各有一份 `SCORE_TIMEOUT_SECONDS`，只改前者等于没改。
3. **批量协议撞输出上限**：`num_predict=160` 对单条判官够用，对 B=20 的 JSON 数组必被截断；首次真实冒烟 243.25s / 11 项 degraded 即由此叠加超长 prompt 导致。
4. **数据管线断点**：只把 gold 文件写大不够，打分对象仍从 042 文件加载 → 样本数永远停在 20；必须让 `load_chat_items()` / `list_datasets()` / `score()` 同源。
5. **静态评审无法证明性能**：2 条 65s 外推 100 条不可靠；必须真实跑 100 条 Go/No-Go，且不能用内部函数 / mock 冒充。
6. **默认模型差异巨大**：基准脚本默认取 `options.models[0]`（27B）而冒烟用 9B，两者耗时差一个量级；基准必须显式记录所用模型。
7. **重复生成**：`judge_metrics` 与 `answer_quality_metrics` 各生成一遍 100 条（10 批），是 900s 超时主因之一；改为 `score()` 一次生成并分发（5 批）。
8. **升版打断精确断言**：`test_evaluation_asset_versions.py` 锁 `[75]/[72]`，每次改 JS 都要同步 4 个静态契约测试；新增兼容 marker 必须是纯属性片段，否则污染 `_live_versions` 正则。
9. **只有浏览器实测才能发现的缺口**：spec §8 ① 写「选项区显示样本数」，静态契约全绿但下拉仍只有 label；验收前必须真实打开页面读 DOM。
10. **daemon 线程超时不可取消**：`_call_with_deadline` 返回 504 后线程仍可能占用 Ollama，重跑基准前须确认无残留负载。

## 5. 分工与交付物（RACI 落地）

| 角色 | 实际产出 |
|---|---|
| `architect`（Gate 2） | `reviews/047-requirement-review.md` §15、`047-tech-review.md`「追加范围三」、4 项 P1 书面裁决 |
| `backend-dev` | 三份 gold、生成脚本、批量化、4 项 P1 落地、共享生成修复、契约测试、`runs/task-14/implementation.md` |
| `frontend-dev` | 紧凑卡片 / `<details>` 折叠 / `?v=76→77` / 选项区样本数、`runs/task-15/implementation.md` |
| `backend-reviewer` / `frontend-reviewer` | 初评 + 两轮集中复审，均「通过」P0=0/P1=0 |
| `backend-tester` / `frontend-tester` | 单端定向回归与补丁后复跑（后端 351、前端 514） |
| `tester` + 主会话 | 跨端验收 §15、真实 API / 浏览器 E2E、全量回归、部署验证、状态台账、复盘、本地 commit |

## 6. 已知非阻塞项（如实登记，未虚报全绿）

- 修复后**未单独复测** `qwen3.8:27b-q4_K_M × 100 条`；选该大模型时可能触发 `EVAL_SCORE_TIMEOUT`，按 spec §8 ⑤ 失败恢复（换 9b 或减小 `max_items`）处理。
- `chat-quality` 集下检索 / 意图 10 项按跨 dataset 早退为 `needs_ground_truth` + `reason`，不是关闭态、不是 0 分。
- 判官 10 批与约 100 次真实 `hybrid_search` 未进一步压缩。
- 其它视图 4 个会话接口 404、Langfuse `:3000` 未启动、历史 wall-clock flaky、`check_test_layout.py` 的 4 个 spec-045 历史编号测试 —— 均与本次改动无关。

## 7. 后续可选（不在本次已确认范围）

- 把 7-rubric 批量判官与 `chat_quality` 批量判官合成一次调用（再省 5 批），需新增协议与解析测试，风险较高，本次按「风险高就不做」跳过。
- 批量检索上下文以减少约 100 次 `hybrid_search`；须保证不缓存假值、不破坏 Qdrant 单进程约束。
- 为大模型组合提供自适应批次 / 预算提示，而非仅返回 `EVAL_SCORE_TIMEOUT`。

## 8. 纪律

不 push、不合 main、不 force push，`origin/main` 仍 `1b26c76c`；服务由 Agent 实际重启并验证 `/api/health` 200；
最终回复给出可点击地址与实际端口。收口清单、全量回归命令 / 退出码 / 通过数、验收签字见
`docs/sdd/reviews/047-acceptance-review.md` §15 与 `docs/sdd/spec-status-changelog.md`。
