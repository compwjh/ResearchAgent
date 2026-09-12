# Spec 033 实施计划索引

> 关联 spec：[033 USENIX 解析器与真实页面结构对齐](../../specs/033-usenix-parser-real-page-alignment.md)

## 目标

把 `backend/app/paper_discovery/infrastructure/usenix_paper_parser.py` 从「按理想化 fixture 解析」改为
「按真实 usenix.org DOM 解析」，消除两条断链：

- **断链一（列表页）**：字段类名在 `<div>` 上而非 `<p>` 上 → 作者 100% 丢失。
- **断链二（详情页）**：`citation_*` meta 块按页条件输出 → 无该块的页面必然 `USENIX_PARSE_FAILED`。

## 任务顺序

| 编号 | 任务 | 角色 | 依赖 | 状态 |
|---|---|---|---|---|
| 01 | 编写 spec-033 | 架构师(自身) | — | 完成 |
| 02 | [列表页字段匹配放宽到任意元素](./task-02-listing-field-matching.md) | `backend-dev` | 01 | 已完成 |
| 03 | [详情页三级回退](./task-03-detail-fallback.md) | `backend-dev` | 02 | 已完成 |
| 04 | [评审、回归与端到端验收](./task-04-review-regression-acceptance.md) | `backend-reviewer` / `backend-tester` / `tester` / `architect` | 03 | 已完成 |

## 收口结果（2026-09-12）

| 门禁 | 结论 | 文档 |
|---|---|---|
| 需求评审 | 通过（附意见，4 MEDIUM + 6 LOW + 1 INFO，已回填 spec） | [033-requirement-review.md](../../reviews/033-requirement-review.md) |
| 技术评审 | 通过（0 CRITICAL / 0 HIGH，2 MEDIUM 已整改） | [033-tech-review.md](../../reviews/033-tech-review.md) |
| 后端定向回归 | 未引入回归（5 批 16 文件，311/311） | [033-backend-regression.md](../../reviews/033-backend-regression.md) |
| 验收评审 | 通过（0 / 0 / 0），开发主管**签字放行** | [033-acceptance-review.md](../../reviews/033-acceptance-review.md) |

**端到端实测**：失效化 2022 全部 178 个 fetch unit 并清空目录摘要后**强制真实重抓** → 检索 176 条、
失败事件 0、`catalog_papers` 2022 作者 **176/176**、摘要 **176/176**、可疑作者 0、获奖标记 0。
`degraded=true` 经证据链归因为 **reranker 缺失**（`rerank_score` 全 NULL + 启动日志 RRF 降级），**非解析器缺陷**。

**遗留（非本 spec）**：reranker 模型 `data/models/qwen3-reranker-0.6b-q8_0.gguf` 缺失 → 检索恒 RRF 降级，建议独立运维项跟进。

## 并发提示（重要）

`backend/app/paper_discovery/infrastructure/usenix_paper_parser.py` 当前工作区**已有 spec-032.1 的未提交改动**
（新增 `.field-name-field-paper-description` 摘要抽取）。本 spec 的两个任务只允许**在其之上追加**，
禁止整文件重写、禁止 `git checkout` 该文件、禁止回退 spec-032.1 的改动。

## 真实页面样本（供任务使用）

已抓取到 `/tmp`（如失效可按下表 URL 重新抓取）：

| 文件 | URL | 特征 |
|---|---|---|
| `/tmp/l_ac42a2e5acc3c28fd58a084ec5d6de23.html` | `https://www.usenix.org/conference/usenixsecurity22/technical-sessions` | 256 篇，字段类名在 `<div>` 上 |
| `/tmp/l_e19ef3cd65a06856406f58f5f248c1bc.html` | `https://www.usenix.org/conference/usenixsecurity22/summer-accepted-papers` | 97 篇 |
| `/tmp/list24.html` | `https://www.usenix.org/conference/usenixsecurity24/summer-accepted-papers` | 82 篇 |
| `/tmp/list25.html` | `https://www.usenix.org/conference/usenixsecurity25/cycle1-accepted-papers` | 245 篇 |
| `/tmp/live_maia.html` | `https://www.usenix.org/conference/usenixsecurity22/presentation/maia` | 详情页，**无** `citation_*` |
| `/tmp/q_xie-xiang.html` | `https://www.usenix.org/conference/usenixsecurity24/presentation/xie-xiang` | 详情页，**无** `citation_*` |
| `/tmp/q_liu-fengrun.html` | `https://www.usenix.org/conference/usenixsecurity24/presentation/liu-fengrun` | 详情页，**无** `citation_*` |
| `/tmp/q_zhang-qingzhao.html` | `https://www.usenix.org/conference/usenixsecurity24/presentation/zhang-qingzhao` | 详情页，**有** 21 个 `citation_author`（回归样本） |
| `/tmp/p_liu-yuxin.html` | `https://www.usenix.org/conference/usenixsecurity25/presentation/liu-yuxin` | 详情页，**有** `citation_*`（回归样本） |

## 运行测试的前置约定

- 一律 `env -u PYTHONPATH .venv/bin/python -m pytest`（`PYTHONPATH` 会注入沙箱 shim）。
- 每次必须给**全新的** `--basetemp=/tmp/xxx`，复用旧目录会因既有目录 `mkdir` 变 `PermissionError` 而假红。
- 多文件一起跑容易超过前台时限被 SIGTERM（退出码 137），按文件分批跑。
