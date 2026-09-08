# Spec018 Task02 02-B：Provenance / mapping probe 草稿

本草稿仅记录匿名 fixture 与现有后端实现的只读观察，最终裁决见同目录
`source-anchor-feasibility-report.md`。探针没有调用 embedding，也没有打开可写 Qdrant
client；真实 Qdrant 由 SQLite `mode=ro` 读取并用前后 hash 证明未变。

## 命令与版本

- 探针：`PYTHONPATH=. .venv/bin/python /private/tmp/spec018_audit.py`，退出码 `0`。
- Git revision：`ce049062254539df650f9a3388403fc2630fd387`。
- 解析：PyMuPDF `1.28.2`；业务入口 `extract_pages_normalized`。
- 现有 parser 输出：`List[Tuple[int, str]]`；不输出 page width/height/rotation、block、line、word 或 bbox。
- 现有切分：`build_chunks_v1` 保持页内切分；`build_chunks_v2` 可跨页，但不携带 provenance。
- 对齐规范：NFKC、CRLF→LF、去行尾空白、连续水平空白折叠；probe 记录了
  `mapping_algorithm_version=source-anchor-v1`。

## 只读结果

- `pdf-single-column-v1`：1 页、1 列、3 blocks / 8 lines / 90 words；v1 1 chunk，3 anchors，映射率 1.0。
- `pdf-two-column-v1-overlap`：1 页、2 列、3 blocks / 39 lines / 229 words；v1 2 chunks，6 anchors，检测到 200 字符 overlap，映射率 1.0。
- `pdf-v2-cross-page`：2 页、1+1 列、2 blocks / 11 lines / 129 words；v2 1 chunk，`page=1,page_end=2`，2 anchors，映射率 1.0。
- `pdf-no-text-layer`：1 页、0 blocks / 0 lines / 0 words，v1 空切片，观察到 `PDF_NO_TEXT` 失败语义。
- Markdown fixture 的行号 oracle 为 100% 精确，但业务代码没有 Markdown parser/chunker，不能把 fixture oracle 当作实现证据。
- hostile PDF 静态含 1 remote URI、1 widget、1 embedded attachment、catalog JavaScript action；本轮没有浏览器网络记录，故 hostile 网络门禁未证明。

## 调用计数

| 路径 | embedding | 检查路径切分 | fixture 探索性切分 | upsert | delete |
|---|---:|---:|---:|---:|---:|
| no-embedding / inspection guard | 0 | 0 | — | 0 | 0 |
| 02-B PDF fixture probe | 0 | — | 5 | 0 | 0 |

Qdrant 只读存储、`meta.json`、`.lock` 和 `data/kb/papers.json` 前后 hash 均未变化。

## 02-B 判断

匿名样本能够展示 v1 overlap、v2 跨页和块级 oracle，但不能证明现有 parser 生成
Spec018 要求的同源 PDF provenance DTO；Markdown 实现也不存在。因此 02-C 必须
按严格门禁给出 `NO-GO`，不能进入 Task03。
