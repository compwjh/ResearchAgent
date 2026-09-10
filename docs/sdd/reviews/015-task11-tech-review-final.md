# Spec015 Task11 最终技术复评（Tech Lead）

- 评审角色：开发主管（Tech Lead）
- 评审模型：自身（本次调度要求：`gpt-5.6-luna/high`）
- 评审时间：2026-09-05（Asia/Shanghai）
- 适用 Skill：`.agents/skills/usenix-accepted-papers/SKILL.md`
- 评审范围：Task11 全部实现及四项修订、USENIX/arXiv 来源链、PDF probe、publication_scope/API、候选来源字段/SQLite、跨来源去重、下载安全与旧回归
- 评审约束：只读复核；未修改业务代码、测试或配置，未执行 reset/stash/clean/commit/push
- 进展日志：`.codebuddy/agent-logs/techlead-spec015-task11-final-20260905.md`

## 结论

**通过（Task11 实现范围；流程门禁保留）。**

前次五项阻塞已全部修复并经实际代码复核和新增 fixture 验证：accepted API 默认完整年份、USENIX cache/节流、统一 SSRF/大小/重定向/魔数 probe、作者集合与出版阶段去重，以及损坏 PDF 的页可读性回退。当前未发现新的实现级 P0/P1 阻塞。

注意：Spec015 当前仍标记 `待确认`，Task11 计划仍标记 `待确认`。本报告只表示当前实现切片的技术复评通过，不改变 SDD 确认、QA 真实来源验收或最终部署门禁。

## 关键契约复核

| 维度 | 实际证据 | 判定 |
|---|---|---|
| 固定来源链与 allowlist | parser 只接受 `https://www.usenix.org` 的显式 presentation/媒体链接；source 固定服务端 USENIX route；arXiv API 固定 `export.arxiv.org`，abs/PDF 仅允许两个 arXiv HTTPS origin | 通过（离线） |
| USENIX → prepublication → arXiv 顺序 | `usenix_publication_source.py:187-192` 先 probe 正式再 probe prepublication；两者均失败才进入 `:100-115` 的 arXiv fallback | 通过 |
| PDF 安全与有效性 | `usenix_publication_source.py:152-183` 复用 `download_candidate()`，固定 allowlist、逐跳重定向、DNS/peer seam、64 MiB/头部/总超时、严格 `%PDF-` 和默认 fitz 页可读性；截断 PDF fixture 已回退 prepublication | 通过（fixture/注入 seam） |
| 缓存与节流 | `usenix_publication_source.py:57-76,138-231` 使用 URL/查询 TTL cache 和线程安全最小间隔预约；arXiv adapter 保留缓存、有限重试及至少 3 秒请求间隔 | 通过（离线） |
| 严格 arXiv 匹配 | 标题 0.90、作者集合 0.80、年份严格相等；不确定返回 `ARXIV_MATCH_UNCERTAIN`，不产生导入信号 | 通过 |
| publication_scope/API | `routes.py:452-461` 默认只取最近完整年份，拒绝未来显式年份；请求 schema 仅接受受控 year/cycle/q/limit，不接受 URL；POST scope 透传 published/accepted/all | 通过 |
| 来源字段/SQLite | `PaperCandidate` 追加 stage/source/page/arXiv/source_links；store 对旧表增量迁移，保留 schema v1、默认 published/dblp 和快照往返 | 通过 |
| 跨来源去重 | `paper_discovery_search.py:264-269,364-430` 纳入规范化作者集合，DOI/DBLP key 优先；阶段优先级 published > accepted > prepublication，来源链接合并保留 | 通过 |
| 错误降级与旧回归 | source/ArXiv 失败只返回稳定 warning/error；OpenAlex、下载、导入和旧 store 回归均通过 | 通过（离线） |

## 验证证据

实际执行：

```text
.venv/bin/python -m pytest -q \
  tests/test_usenix_paper_parser.py \
  tests/test_usenix_publication_source.py \
  tests/test_arxiv_adapter.py \
  tests/test_paper_discovery_search.py \
  tests/test_paper_discovery_store.py \
  tests/test_paper_discovery_api.py \
  tests/test_paper_download.py \
  tests/test_paper_download_security.py \
  tests/test_paper_import.py
```

结果：**退出码 0，93 passed，5 warnings，9 subtests passed**。

`PYTHONPATH=. .venv/bin/python -m py_compile` 对 Task11 相关 8 个实现文件通过；`git diff --check` 通过。警告仅为 PyMuPDF/底层类型弃用提示，不影响退出码。

## 四项修订的最终判断

- T11-B1 accepted API 默认年份：已修复并由冻结 2026 年测试证明得到 2021–2025；显式 2026 可用，2027 被稳定拒绝。
- T11-B2 USENIX cache/节流：已修复并由重复查询 fixture 证明列表、详情和 PDF 不重复请求；route 的最小间隔实际生效。
- T11-B3 统一安全 probe：已修复并由伪魔数、超限和恶意重定向 fixture 证明；`follow_redirects=True` 的注入 client 也不会跟随外域。
- T11-B4 作者/阶段去重：已修复并由不同作者隔离、作者顺序稳定及 `publication_scope=all` published/accepted 冲突 fixture 证明。
- T11-P1 损坏 PDF 可读性：已修复；正式响应即使带 `%PDF-` 但 fitz 不可读取，也会继续 prepublication，测试已通过。

## 保留边界与后续门禁

- 本次是离线技术复评，不替代真实 USENIX 外网 DOM/公开 PDF、DNS rebinding 与实际 peer 证据、arXiv 限流、服务启动和完整 KB 导入验收。
- `_get_text()` 与默认真实 HTTP client 的连接 peer 证据仍需 QA 在运行环境记录；MockTransport 仅作为注入 seam。
- 依照项目级 Skill，若页面跳出 allowlist、出现认证信息、PDF 无法读取或 arXiv 匹配不确定，运行时必须停止相应路线并保留稳定错误码，不得放宽规则。
- Spec015/Task11 仍待用户确认，不能仅凭本报告把 spec 或 Task 标记完成。

## 签字

- 开发主管（Tech Lead）：**当前协作 Agent，签字：通过（Task11 实现范围）**
- 签字时间：2026-09-05（Asia/Shanghai）
