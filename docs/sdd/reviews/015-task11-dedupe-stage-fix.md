# Spec015 Task11 去重与出版阶段修复报告

- 执行角色：junior-dev
- 执行时间：2026-09-05（Asia/Shanghai）
- 修复范围：`backend/app/services/paper_discovery_search.py`、`tests/test_paper_discovery_search.py`
- 约束：未修改 API、store、domain、frontend；未执行 commit、push、reset、stash、clean
- 进展日志：`.codebuddy/agent-logs/junior-dev-spec015-task11-dedupe-stage-fix-20260905.md`

## 修复内容

1. 无 DOI/DBLP key 时，候选身份键加入规范化作者集合，并对作者排序去重；同标题同年同会但作者不同的论文不再错误合并，作者顺序变化仍保持稳定身份。
2. 合并候选显式比较 `publication_stage`（`published > accepted > prepublication`）与 `source_kind` 优先级；低可信阶段不得替换已发表候选。
3. 合并仍保留首条候选的 `candidate_id`、`initial_rank` 等排序契约，并合并去重后的 `source_links`；胜出记录仅从另一来源补齐缺失元数据。

## 验证结果

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_paper_discovery_search.py` | 通过，22 passed |
| `.venv/bin/python -m py_compile backend/app/services/paper_discovery_search.py` | 通过 |
| `git diff --check -- backend/app/services/paper_discovery_search.py tests/test_paper_discovery_search.py` | 通过 |

新增回归覆盖作者集合身份稳定性、不同作者/不同 DOI 隔离，以及 `publication_scope=all` 中 `published` 与更丰富 `accepted` 来源冲突时阶段不被覆盖且来源链接完整保留。

## 交接结论

Task11 技术评审 T11-B4 的搜索 service 去重/阶段阻塞已修复，交由主会话继续整合并安排 Tech Lead 复评；本报告不替代 USENIX 缓存/PDF 安全和真实链路验收。
