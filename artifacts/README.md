# `artifacts/` 目录契约（自解释结构）

> **代行留痕**：本文件为纯文档改动，由主会话代行（符合 `AGENTS.md`「唯一允许的代行条件是改动不含任何代码文件」）。
> 三处留痕：本文件头部、`docs/sdd/spec-status-changelog.md` 对应条目、`docs/sdd/specs/047-evaluation-p2-and-observability-fixes.md` 追加范围二的「代行记录」小节。
> 生效日期：2026-11-10。触发原因：用户指出 `artifacts/task-06/` 这类裸目录「只看文件夹地址完全看不出来是哪个 spec」，要求「文件夹能看出它的结构和逻辑」。

## 1. 这个目录是什么

`artifacts/` 存放**入库的、可复核的交付物**：真实 API 成功案例（请求 / 响应 / HTTP 码）、人工验收详情与准备度矩阵、SSE / 日志证据、交接报告、回归输出。
`artifacts/` **没有被 `.gitignore` 忽略**，因此这里的东西会被 commit、会被后续 spec / review 当证据引用。

它**不是**运行期日志目录：

| 目录 | 定位 | 是否入库 | 谁写 |
|---|---|---|---|
| `artifacts/` | 交付物 / 证据，供人复核与跨 spec 引用 | **是** | 主会话、验收角色 |
| `.codebuddy/agent-logs/` | 子代理过程日志，供 `tail -f` 观察本地模型推理 | 否（`.gitignore:27`） | 各角色 agent，按 `progress-logging` skill |
| `docs/sdd/plans/NNN/runs/task-TT/` | 当前推荐的**逐次运行证据**（时间戳、命令、退出码、截图 / snapshot） | 是 | 验收 / E2E 任务 |

历史 skill 约定：`.codebuddy/skills/spec-api-acceptance/SKILL.md:11,88-94` 要求「把真实的请求体与响应原样落盘为 `artifacts/spec-*.md`」，本契约沿用该命名并补充目录层级规则，不改变其落盘要求。

## 2. 结构规则（看路径即知道归属）

```
artifacts/
├── README.md                         本契约
├── spec-NNN-<用途>.<ext>             单份交付物：文件名自带 spec 编号
├── spec-NNN-MMM-<用途>.<ext>         跨多 spec 的合并交付物
└── spec-NNN/                         多份交付物按 spec 分组
    └── task-TT/                      任务编号必须能在 docs/sdd/plans/NNN/ 找到
        └── <产物>.md | .json | .png
```

**三条硬规则**

1. **所有路径必须能反查到 spec**：要么文件名以 `spec-NNN` 开头，要么位于 `spec-NNN/` 目录下。
2. **禁止裸 `task-NN/` 目录**：`task-06` 在仓内至少有 8 种含义（Spec022 / 026 / 027 / 028 / 034 / 043 / 047 / 根 artifacts），脱离上下文不可读。任务层必须挂在 `spec-NNN/` 之下，或写在 `docs/sdd/plans/NNN/artifacts/task-NN/`（其他 spec 既有惯例）。
3. **新运行证据优先落 `docs/sdd/plans/NNN/runs/task-TT/`**：那里天然带 spec → task → 逐次运行三层结构；`artifacts/` 只放需要长期对外引用、跨 spec 复用的成品。

**反例 → 正例**

| 反例 | 问题 | 正例 |
|---|---|---|
| `artifacts/task-06/contract.md` | 看不出 spec | `artifacts/spec-032/task-06/contract.md` |
| `artifacts/eval-initial.yaml` | 无 spec、无任务 | `docs/sdd/plans/047/runs/task-10/eval-initial.yaml` |
| `artifacts/<任意无前缀名>.md` | 无法反查 | `artifacts/spec-047-<用途>.md` |

## 3. 当前目录清单

### 3.1 按 spec 分组的目录（2026-11-10 迁移后）

| 路径 | 归属 | 内容 |
|---|---|---|
| `artifacts/spec-032/task-06/` | Spec032 Task06 | 统一来源合同交接 |
| `artifacts/spec-032/task-07/` | Spec032 Task07 | CCS / NDSS / IEEE S&P 官方入口覆盖矩阵与评审合同（含 032.1 评审合同） |
| `artifacts/spec-032/task-08/` | Spec032 Task08 | 运行时集成 |
| `artifacts/spec-032/task-09/` | Spec032 Task09 | Worker / Tool 合同 |
| `artifacts/spec-032/task-10/` | Spec032 Task10 | 自动导入 |
| `artifacts/spec-032/task-11/` | Spec032 Task11 | 论文问题恢复 |
| `artifacts/spec-032/task-12/` | Spec032 Task12 | 前端报告 |
| `artifacts/spec-032/task-13/` | Spec032 Task13 | 032.1 承接交接（`carryover.md`） |
| `artifacts/spec-032/task-14/` | Spec032 Task14 | 真实导入 smoke、live  smoke 清单、竞态修复、评审回归 |

> 上述 9 个目录、16 个文件全部是 **2026-09 的 Spec032 / Spec032.1 历史交接物**，不是 047 评测台产物。
> `docs/sdd/plans/032/artifacts/` 是**另一处并存的既有落点**（含 task-04 / 08 / 14 / 15 / 16 / 17 与 `20261026-login-recovery/`），两者为历史双落点，本次不合并、不删除。

### 3.2 根级平铺文件（文件名自带 spec 编号，结构已自解释）

| 归属 | 文件 | 用途 |
|---|---|---|
| Spec011 | `spec011-kb-ask-e2e-20261105.sse` | KB ask 真实 SSE 流 |
| Spec029/030/031 | `handoff-spec029-030-031.md`、`spec029-030-031-api-sample.md` | 交接报告、合并 API 成功案例 |
| Spec030 | `spec030-evidence-matrix-sample.json` | 证据矩阵样例 |
| Spec032 | `spec032-api-e2e-success.md`、`spec032-manual-acceptance.md`、`spec032-readiness-matrix.md` | API 成功案例、人工验收、准备度矩阵 |
| Spec035 | `spec035-online-model-runtime-verification.md` | 在线模型运行时验证 |
| Spec040 | `spec040-api-e2e-20260920T1813+0800.md`、`spec040-manual-acceptance.md`、`spec040-readiness-matrix.md` | API / 人工验收 / 准备度 |
| Spec044 | `spec044-api-sample.md`、`spec044-b-domain-e2e.json`、`spec044-b-domain-e2e.py`、`spec044-full-regression.log`、`spec044-processing-steps-rag.json`、`spec044-processing-steps.json`、`spec044-sse-rag-success.txt`、`spec044-sse-rag.txt`、`spec044-sse-raw.txt` | API 样例、E2E、回归日志、处理步骤与 SSE 证据 |
| Spec047 | `evaluation-p0-p1-p2-test-checklist.md`、`spec-047-evaluation-console-manual-e2e.md`、`spec-047-force-idempotency-manual-e2e.md` | 测试清单、评测台 / `--force` 幂等人工验收详情 |

### 3.3 遗留命名（不合规，暂不重命名，登记备查）

| 文件 | 状态 | 说明 |
|---|---|---|
| `langfuse-waterfall.html` | tracked | 观测瀑布图，无 spec 前缀；被既有观测文档引用，重命名需单独变更 |
| `observability-samples.json` | tracked | 观测样例，同上 |
| `jd-agent-infra-capability-map.md` | **untracked** | 未纳入版本库的能力图，非任何 spec 交付物；保留原样，不删除、不误提交 |

> 本清单不把遗留文件伪装成合规产物；后续若重命名，须同步全仓引用并追加本表记录。

## 4. 旧路径 → 新路径映射表

历史归档报告中的旧路径按 `AGENTS.md`「历史归档报告中的旧路径不随改名重写」约定**保留原文**，由本表解释；活跃文档（spec032 正文、032.1 验收评审、plans/032 索引、skill 约定）已同步到新路径。

| 旧路径 | 新路径 |
|---|---|
| `artifacts/task-06/` | `artifacts/spec-032/task-06/` |
| `artifacts/task-07/` | `artifacts/spec-032/task-07/` |
| `artifacts/task-08/` | `artifacts/spec-032/task-08/` |
| `artifacts/task-09/` | `artifacts/spec-032/task-09/` |
| `artifacts/task-10/` | `artifacts/spec-032/task-10/` |
| `artifacts/task-11/` | `artifacts/spec-032/task-11/` |
| `artifacts/task-12/` | `artifacts/spec-032/task-12/` |
| `artifacts/task-13/` | `artifacts/spec-032/task-13/` |
| `artifacts/task-14/` | `artifacts/spec-032/task-14/` |

**仍保留旧写法的文件（有意、非断链）**：`docs/sdd/spec-status-changelog.md`（状态台账是时间线记录，不因迁移改写历史措辞）、
其他 spec 的 `plans/NNN/artifacts/task-NN/` 相对路径（本就不是本目录，不在迁移范围）、
`.codebuddy/agent-logs/**`（被 `.gitignore` 忽略的过程日志，记录当时事实）。
Spec032 / 032.1 范围内的活跃引用（spec 正文、plans 顶层、032.1 两份评审、fixture README、产物自引用）已全部同步到新路径。

**已修复的断链**：`docs/sdd/plans/032.1/task-08-local-session-usenix-skill.md` 原链接 `../032/artifacts/task-13/carryover.md` 指向不存在的文件，实际产物是 `artifacts/task-13/carryover.md`；迁移后统一指向 `../../../../artifacts/spec-032/task-13/carryover.md`。

## 5. 新增产物该放哪（决策顺序）

1. 是「当前 spec 某次运行的证据」→ `docs/sdd/plans/NNN/runs/task-TT/`（优先）。
2. 是「一份需要长期对外引用的成品 API 成功案例 / 人工验收详情」→ `artifacts/spec-NNN-<用途>.md`。
3. 是「同一 spec 下多份互相引用的交接物」→ `artifacts/spec-NNN/task-TT/`。
4. 是「子代理过程日志」→ `.codebuddy/agent-logs/spec-NNN/task-TT/<role>/`（不入库）。
5. 不确定时，先问「只看这个路径，能不能说出它属于哪个 spec、哪个任务、是什么类型」；答不上来就是命名不合格。
