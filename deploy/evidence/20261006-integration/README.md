# 2026-10-06 分支整合与 Spec018 补验

状态：验证 PASS，独立签字通过；整合代码及验收提交 5399d56 已合回 main 并推送，远端同步回执见最后收口节。

## 整合基线

- 原整合分支：`codex/integrate-current-code-to-main@6bde372`。
- 原本地 main：`b13ecf5`；本次获取的远端 main：`7cfef4d`。
- 原未提交内容只有 Spec018 upload-closure-matrix；保存为 `cb7bf56`，不丢弃原新增上传入口。
- SSH 22 连接关闭；通过 GitHub CLI 已有认证使用 HTTPS 获取引用，未更改永久 remote/凭据配置。
- 真实新增分支：远端 main（Spec037/041），`feature/spec-042-openeval-agent-evaluation`（两个评测提交）。
- `feat/startup-readiness` 仅剩旧矩阵摘要更新，最终以当前代码重新校验。
- `backup/spec032-import-race@e00ac1c` 的功能已由 `921bc74`、`c422d45` 包含；保留备份而不重复导入旧文件。
- 其他本地/远端功能分支已被整合分支包含，无需重复 cherry-pick。

## Spec018 补验范围

保留 2026-09-10 历史 PASS，不以历史结果代替当前版本测试。补验上传入口登记、当前 PDF/Markdown HTTP 链路、双向稀疏映射、长文档性能、generation 与 alias 一致性、最终全量回归与部署。

运行目录存在历史失败索引及旧 claim；先区分旧元数据与当前权威目录，再判断需恢复的对象。不清空知识库、不覆盖源文件、不自动删除旧运行数据。

## 当前基础检查

- Ollama 标签接口 HTTP 200；`bge-m3`、`qwen3.5:9b` 和 27b 模型存在，局域网监听配置未变更。
- memory SQLite `schema_version` 为 8。
- 切片检查四份 Node 契约测试：4 passed，exit 0。
- 初次 closure-matrix 定向测试：1 passed / 1 failed；新增只读列表入口未被扫描白名单识别，正在修复，不能宣称通过。
- GitHub API 查询 main branch protection 返回 404（未配置保护）；远端 Actions 暂无运行记录。本地验证和独立评审结果须单独记录，不能伪称 CI 绿。

## 最终验证（代码候选 9a9733f）

- 全量回归：`.venv/bin/python -m pytest tests --cov=backend --cov-report=term --cov-report=json:/private/tmp/researchagent-integration-final-coverage.json -q`，exit 0，2893 passed、3 skipped、67 subtests passed，237.14 秒；总覆盖率 81.7914%。43 个文件低于 80%，未宣称逐文件达标。
- 测试命名与分类：`.venv/bin/python scripts/check_test_layout.py`，exit 0；闭环矩阵修正后 2 passed。
- 新 Markdown/PDF 均真实 POST 201，两个版本均 indexed/manifest ready、anchors 非空；HEAD 200、Range 206、ETag/304 和缺失资源 404 通过。见 `docs/sdd/plans/018/artifacts/task-07/current-api-e2e-success-report.md`。
- 服务端口 8000，启动命令 `PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh`；ready 的四项 warmup 均 ready，Qdrant/embedding/generation 正常，memory SQLite schema 为 8。
- 首页 HTTP 200；线上与工作树资源一致：`app.js?v=57`、`styles.css?v=56`、`research-tasks.js?v=15`。
- 首次失败的 10 项回归和 MIGRATION_INPUT_INVALID 上传证据全部保留；修复分别关联 ecbb91f 与 9a9733f，不以修改数据或隐藏测试取得通过。
- Langfuse 127.0.0.1:3000 当前不可用，遥测导出告警不阻塞知识库链路；reranker 本轮显式关闭，不能宣称这两个能力已验证正常。
- 万切片性能用真实 Chromium + 截获规模样本验证 DOM 分批渲染，不冒充万切片真实 API 性能；全部清单预取仍有网络优化空间。旧用户数据未被批量删除或重新重建。

## 最后收口记录

- 独立评审：`review.md` 与 `docs/sdd/reviews/018-acceptance-review.md` 当前补充节 PASS，P0/P1=0。
- 人工步骤：`docs/sdd/plans/018/artifacts/task-07/manual-acceptance.md` 第 6 节；当前成功样本已保留，可直接打开切片检查，无需重新上传或删除。
- 复盘：`docs/sdd/plans/018/artifacts/task-07/current-retrospective.md`。
- 推送前再次 fetch，所有远端功能分支均为当前候选祖先。唯一未合本地 backup/spec032-import-race 是已被新实现覆盖的历史备份，独立评审建议保留而不普通合并回引旧代码。
- 仓库未解决冲突列表为空，精确冲突标记扫描为空，diff --check 通过。
- 用户授权推送：远端 main 从 7cfef4d 更新至 5399d56，exit 0。首次 HTTPS RPC 400 中断后先核实远端未更新，再用单次 HTTP/1.1 与 postBuffer 设置重试成功；未改永久配置、未 force push。本回执后续文档提交不改变已验收代码。
