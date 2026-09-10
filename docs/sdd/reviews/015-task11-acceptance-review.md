# Spec015 Task11 + Task12 验收评审

- 评审角色：测试（QA）
- 执行模型：gpt-5.6-luna，high（本次调度）
- 验收时间：2026-09-05 03:40–03:55（Asia/Shanghai）
- 关联 Spec：[015-security-paper-discovery.md](../specs/015-security-paper-discovery.md)
- 关联任务：[Task11](../plans/015/task-11-usenix-accepted-and-arxiv-fallback.md)、[Task12](../plans/015/task-12-usenix-paper-skill.md)
- Tech Lead 复评：[015-task11-tech-review-final.md](./015-task11-tech-review-final.md)
- 进展日志：`.codebuddy/agent-logs/tester-spec015-task11-acceptance-20260905.md`
- 约束：只验收；未修改业务代码、测试或配置；未执行 reset、stash、clean、commit、push。

## 结论

**通过（Task11 + Task12 实现验收范围）。**

定向论文、安全、导入、旧 KB、API 与 Skill 检查均通过；全仓回归通过。该结论不等同于 Spec015 全量产品验收，也不改变当前 Spec015/Task11/Task12 文档仍为 `待确认`/`待执行` 的 SDD 流程状态。真实公网 DOM/PDF、DNS/peer 和服务运行时证据不在本次离线 fixture 验收中。

## 验收矩阵

| 验收点 | 结论 | 证据 |
|---|---|---|
| USENIX accepted listing/detail 显式链接与 allowlist | 通过 | `tests/test_usenix_paper_parser.py`、`tests/test_usenix_publication_source.py`；只接受 `https://www.usenix.org/conference/.../presentation/...`，详情 PDF 必须是页面显式 HTTPS 同源链接，拒绝外站、非 HTTPS、userinfo/query/fragment/猜测路径。 |
| official PDF → prepublication → 严格 arXiv 回退 | 通过 | Source fixture 证明正式 PDF 优先；伪 magic、截断/不可读、超限、重定向失败会尝试 prepublication；两类均失败后才调用 arXiv，且 `publication_stage` 正确保留。 |
| arXiv 3 秒节流、缓存、失败码 | 通过 | `tests/test_arxiv_adapter.py` 覆盖严格间隔、缓存、有限重试、429/HTTP/解析失败码；固定 `export.arxiv.org` API，abs/PDF 仅允许 `arxiv.org`/`export.arxiv.org` HTTPS。 |
| publication_scope 与 API 默认完整年份 | 通过 | `PaperSearchRequest` 仅接受 `published/accepted/all`；搜索 service 按 scope 路由；accepted API 默认排除当前未完成年份（冻结 2026 时为 2021–2025），显式当前年份允许，未来年份稳定拒绝。 |
| PaperCandidate/SQLite 来源字段 roundtrip 与旧库迁移 | 通过 | 临时旧 schema 启动迁移成功；旧候选默认 `published/dblp`；新 `arxiv/prepublication` 候选的 `arxiv_id`、`source_page_url`、`source_links` 保存读取一致；定向 store/search 测试通过。 |
| 跨来源去重、published 阶段优先 | 通过 | search fixture 覆盖 DOI、DBLP key、标题+作者集合+年份身份；作者不同不误合并，作者顺序稳定；`published > accepted > prepublication`，合并保留来源链接与缺失元数据补全。 |
| 项目级 Skill 与 CodeBuddy 适配器发现、安全边界 | 通过 | `.agents/skills/usenix-accepted-papers/SKILL.md` 为 50 行主 Skill；`.codebuddy/skills/usenix-accepted-papers/SKILL.md` 为 10 行薄适配器，均引用真实 Spec/Task/README，明确角色、来源顺序、allowlist、阻塞与 Task/SQLite 回填；无凭证字面量赋值、任意 URL 或 Chrome profile 操作。 |

## 实际验证

### 论文相关完整回归

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
  tests/test_paper_import.py \
  tests/test_paper_import_batch_api.py \
  tests/test_paper_import_batch_service.py \
  tests/test_paper_import_batch_store.py \
  tests/test_legacy_kb_integration.py \
  tests/test_frontend_paper_contract.py -rs
```

结果：退出码 `0`，`130 passed, 5 warnings, 9 subtests passed`。

### 全仓回归

`.venv/bin/python -m pytest -q -rs`

结果：退出码 `0`，`552 passed, 5 warnings, 38 subtests passed in 90.18s`。警告为 PyMuPDF/底层类型弃用提示，不影响验收。

### 编译与仓库安全检查

- `.venv/bin/python -m py_compile`：Task11 source/parser、arXiv、search/store/domain、API routes/schemas 全部通过。
- `node --check frontend/app.js`：退出码 `0`。
- `git diff --check`：退出码 `0`。
- 全仓冲突标记扫描：0 命中。
- Skill 引用路径：全部存在；行数均低于 500 行。
- 凭证赋值形式（Authorization/Bearer/password/cookie/api-key/access-token/secret）扫描：0 命中。

## 限定说明

本报告使用冻结 fixture、注入 HTTP transport/resolver 和本地 SQLite 临时库验证离线行为；未访问任意外部站点，未读取认证信息。按照项目 Skill，若真实运行时发现非 allowlist 链接、认证/验证码、无效 PDF、限流或不确定 arXiv 匹配，应停止对应路线并保留稳定错误码。Spec015 当前流程状态仍需用户明确确认后方可进入后续门禁，QA 不代改状态。

## 签字

- 测试（QA）：**通过（Task11 + Task12 实现验收范围）**
- 开发主管（Tech Lead）：待签字
