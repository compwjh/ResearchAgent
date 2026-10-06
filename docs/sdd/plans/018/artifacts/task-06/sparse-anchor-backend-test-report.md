# Task06 sparse-anchor backend test report（当前补充）

## 结论范围

本文件记录的是 2026-10-06、最终候选 `9a9733f` 工作树上的当前补充测试，不是 2026-09 历史运行的重述，也不改写或伪造历史证据。

本次只验证后端测试中的 sparse encoding/index/upsert 合同与 source-anchor provenance 合同。测试使用项目 fixture、mock/FakeQdrant 或 pytest 临时目录；本次没有启动服务、调用真实 API、写入用户 `data/kb` 或操作真实 Qdrant Collection。

## Sparse 定向测试

命令：

```text
.venv/bin/python -m pytest -q tests/kb/test_kb_services.py -k 'sparse'
```

结果：退出码 `0`，`7 passed, 70 deselected in 0.88s`。

覆盖的当前测试包括：

- 混合语言 tokenization；
- sparse index 确定性、有界性及不依赖 Python 内置 hash；
- sublinear term-frequency 权重；
- 空文本返回空 sparse vector；
- Qdrant collection 配置 sparse IDF；
- upsert 同时写入 dense 与 sparse 向量。

## Source-anchor provenance 定向测试

命令：

```text
.venv/bin/python -m pytest -q tests/kb/test_kb_source_provenance_bundle.py -k 'anchor or mapping or cross_page or overlap or repeated_text'
```

结果：退出码 `0`，`8 passed, 16 deselected, 5 warnings in 0.87s`。

覆盖的当前测试包括：

- 双栏 overlap 固定 bundle 投影；
- 重复文本按精确 source range 顺序消歧；
- unresolved chunk 不生成 anchor 且不走 fuzzy fallback；
- source/block 同投影 mapping 归一化；
- 跨 block 连字符 source range 精确保持；
- v2 display block 保留；
- malformed anchor locator 被 schema 拒绝；
- Markdown anchor serialized boundary 被 public builder 拒绝。

## 证据边界

- 本轮 sparse/anchor 补充测试：`15 passed`，退出码均为 `0`。
- 报告原始输出：`/private/tmp/spec018-sparse-anchor-targeted.log`。
- 这些测试不证明真实用户文档的全量 sparse/anchor 迁移、不证明真实 Qdrant Collection 状态，也不替代真实 API 上传→索引→inspection E2E。
- 最终候选全量后端回归另见 `docs/sdd/plans/018/artifacts/task-07/current-full-regression-report.md` 的追加记录；本文件只补 sparse/anchor 当前测试证据。
