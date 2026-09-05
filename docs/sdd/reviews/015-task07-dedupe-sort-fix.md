# Spec015 Task07 跨响应去重与稳定排序修复记录

- 执行角色：junior-dev
- 执行时间：2026-09-05 00:41（Asia/Shanghai）
- 修复范围：仅 `frontend/app.js`；未修改后端、HTML、CSS 或测试
- 进展日志：`.codebuddy/agent-logs/junior-dev-spec015-task07-dedupe-sort-fix-20260905.md`
- 约束：未执行 commit、push、reset、stash、clean；未在本修复中新增 `innerHTML`、URL 或 Cookie 输入面

## 修复内容

1. 跨会议响应按强身份优先去重：先比较规范化 DOI，再比较规范化 DBLP key，只有双方都没有强身份时才回退到规范化标题、年份和会议身份。不同 DOI 的同标题记录不会被错误合并。
2. 候选胜出记录继续携带自身的 `searchId`；写入 `candidateSearchIds` 时使用胜出记录的服务端 `search_id`，未改写候选与搜索会话的归属映射。
3. 稳定排序依次比较 `final_score`、`rerank_score`、`retrieval_score` 降序；`rank`、`initial_rank` 升序；年份降序；规范化标题、规范化 DOI/DBLP key、规范化 `candidate_id`、`responseIndex`、`candidateIndex` 升序。缺失或非有限数值稳定排在有值项之后。
4. 论文结果的既有 DOM 安全边界保持不变，动态论文字段仍使用 `textContent`、属性 API 和节点 API；导入请求仍只提交服务端 opaque ID。

## 验证结果

| 检查 | 结果 |
|---|---|
| `node --check frontend/app.js` | 通过，退出码 0 |
| 前端契约与论文相关回归 | 通过，`102 passed, 9 subtests passed` |
| `.venv/bin/python -m pytest -q tests/test_frontend_paper_contract.py tests/test_paper_discovery_api.py tests/test_paper_import_batch_api.py tests/test_paper_discovery_search.py tests/test_paper_import_batch_service.py tests/test_paper_import_batch_store.py tests/test_paper_import.py tests/test_paper_import_identity.py tests/test_paper_download.py tests/test_paper_download_security.py` | 通过 |
| `git diff --check -- frontend/app.js` | 通过，退出码 0 |

## 交接结论

去重身份优先级和完整稳定排序已落地，交由主会话继续执行 Task07 完整验收与 Tech Lead 复核。本记录不替代真实浏览器或 ACM/IEEE 合法账号验收。
