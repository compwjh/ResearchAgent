# Spec018 Task02 来源锚点可行性报告（02-C / 02-D）

## 最终裁决

**`NO-GO`（严格）**

Task02 状态：`阻塞/需修订`。本报告不修改 Spec018 状态，也不放行 Task03。

原因不是匿名样本的文本匹配失败，而是硬门要求的实现级证据缺失：现有 PDF parser
只返回整页 `(page, text)`，没有与规范化文本同源的 page/line/word/bbox provenance
DTO；业务代码没有 Markdown parser/chunker；hostile PDF 的浏览器网络零请求尚未被
实际记录。根据 Task02/Spec018 的停止条件，不能把这些缺口降级为风险接受。

## 1. 范围、命令与版本

02-A 生成命令为匿名固定 fixture 生成脚本，输出目录固定为
`docs/sdd/fixtures/spec-018/`，退出码 `0`；未读取用户原件。02-B 探针命令：

```text
PYTHONPATH=. .venv/bin/python /private/tmp/spec018_audit.py
```

02-B 退出码：`0`。Git revision：
`ce049062254539df650f9a3388403fc2630fd387`。

实现版本观察：

- parser：`pymupdf-1.28.2-extract_pages_normalized-unversioned`；
- normalize：`normalize.py-unversioned`；
- mapping：`source-anchor-v1`；
- PDF chunker：现有 `build_chunks_v1` / `build_chunks_v2`；
- Markdown：业务代码未提供 parser/chunker，行号仅是 fixture oracle；
- DTO：本轮冻结 `provenance-dto-v1` schema，但尚未宣称业务实现已产出该 DTO。

固定产物 SHA-256：

- `fixture-index.json`：`1c5f96cd8c516aa17583ae579035356ecebf5843a798fe23150bb4d140b64f59`
- `provenance-dto.schema.json`：`01718f4b37a08f74b0a9bbd4c818810e145cd65d296ad2f1022c57dd866af6ed`

下表每一行均继承同一组可审计命令与退出码：02-A 匿名 fixture generator（固定
输出目录，退出码 `0`）；02-B `PYTHONPATH=. .venv/bin/python
/private/tmp/spec018_audit.py`（退出码 `0`）；02-C/02-D 固定产物读回、字段与
SHA-256 校验（退出码 `0`）。因此每个 `sample_id` 均有原件生成、只读探针和交接
校验命令记录，未把终端摘要作为唯一交接物。

## 2. 逐样本证据

表中 `bbox max/median` 是归一化坐标在 0.5×/1×/1.5×/2× 重投影比较的误差；该
数值证明独立 PyMuPDF display extraction 的稳定性，不证明现有 parser 已传递 bbox。
`probe chunks` 是 02-B 为观察既有切分器的调用次数；inspection/no-embedding guard
的切分调用为 0。

| sample_id | 原件 SHA-256 | expected JSON SHA-256 | 状态/错误 | 页/列/rotation | block/line/word | chunk/anchor | 映射率 | bbox max/median | Markdown 行号 | probe chunks | expected 集合 |
|---|---|---|---|---|---|---:|---:|---|---:|---:|---|
| `pdf-single-column-v1` | `3cc6b61497f483fcb1933919cb00f1568ad1fd609953c96e4970c772cbe4e4ec` | `a91ace4a082d86365006f353c8ecb5ac3ad4d940ec265ff87216f6e43b382ea3` | ready / — | 1 / 1 / [0] | 3 / 8 / 90 | 1 / 3 | 1.0 | 0.0 / 0.0 | — | 1 | match |
| `pdf-two-column-v1-overlap` | `33726da69e2c79bd5b3d4fe10dc14a2b64760802151b4af97b97f4bb84e99e7d` | `418a558b78e24cb2bf8e400b868cbdea34bbfe4aa3236c9bdc21ddb2575322c0` | ready / — | 1 / 2 / [0] | 3 / 39 / 229 | 2 / 6 | 1.0 | 0.0 / 0.0 | — | 1 | match；overlap=200 |
| `pdf-v2-cross-page` | `c0fccf6f1d0dde1c299ce044e63c79c2796ca981f7bcadaf62ec27db9e996468` | `cbece70d3a9296494aa4f28e1e4e27bcae89af7c9e3c09c80ea9b0c73f0e17fc` | ready / — | 2 / [1,1] / [0,0] | 2 / 11 / 129 | 1 / 2 | 1.0 | 0.0 / 0.0 | — | 1 | match；page 1→2 |
| `pdf-no-text-layer` | `05e59443707b6976afedbf1b0c1de5ad9bf62609411c902feb241b5033303252` | `b116f4a6a81b74039f9327d55420d2a266218a2fc382b1ffefb363680c6a8289` | failed / `PDF_NO_TEXT` | 1 / 0 / [0] | 0 / 0 / 0 | 0 / 0 | 0.0 | 0.0 / 0.0 | — | 1 | match（空） |
| `pdf-hostile-features` | `1bc72165cc992f88ad28ef9a6ea24438e1024c305082f03bd3d554a59d664377` | `20477b4ed7b1250adf12388b7565a305699d8f4986071f3687a8d9b0a811e4dc` | partial / `HOSTILE_FEATURES_NOT_EXECUTED` | 1 / 1 / [0] | 2 / 3 / 26 | 1 / 2 | 1.0 | 0.0 / 0.0 | — | 1 | match；网络未验证 |
| `markdown-blocks` | `0b19f1dc1a3bd687b2b9f369ce6c93998648d4f7b6c976d1ed87a78b41325e97` | `d7847f4089d88f4c5f989073eac2a3a048471a05986c3531deb694e782b2b22c` | ready / — | — | 5 / 14 / 0 | 5 / 5 | 1.0 | — | 1.0 | 0 | fixture oracle |
| `markdown-hostile` | `8adfb117879523e8858d9346307cfcfce94eb8b71d144c7453802b2973cf9f32` | `caae72931d25d856453ece2134c9af6ae41da3a7dd076b553b9ad0b87293a059` | partial / `HOSTILE_MARKDOWN_REQUIRES_SANITIZER_PROBE` | — | 6 / 11 / 0 | 6 / 6 | 1.0 | — | 1.0 | 0 | fixture oracle；实现缺失 |

所有样本的原件、expected JSON、README 相对路径和 SHA-256 已同时登记在
`fixture-index.json`；该 index 也登记 DTO schema SHA-256。

重复文本 tie-break：anchor 按 `coverage` 降序、再按 source block ordinal、chunk
按 `chunk_index` 升序；双栏样本保留左列→右列顺序。v1 overlap 的 200 字符保留，
没有压扁成一对一；v2 样本保留跨页 `page_end=2`。

## 3. 真实 Qdrant payload（只读）

读取路径为 `data/kb/qdrant/collection/papers/storage.sqlite` 的 SQLite
`mode=ro`；没有建立第二个 Qdrant client（现有服务持有锁），没有调用 embedding、
切分、upsert 或 delete。

- point 数：`1132`；payload keys 每个 point 均包含
  `paper_id,file_name,page,page_end,section,chunker,is_citation,chunk_index,text,uploaded_at`。
- chunker 计数：`v1=633`，`v2=499`；paper 数 `5`。
- point ID SHA-256：`bd8445d9dd0f2268934fc77507f1319b8fb1c2caa0ee283f4bc2571748fc7c22`。
- payload fingerprint SHA-256：`4a9caaf704a2a7ac075b91daf25889dce0626c083f6bc3dc17d7b6aba14944a3`。
- fingerprint canonical JSON 按 Spec 的 `(chunker, chunk_index)` 排序；相同 key 的 tie 保留只读 point-id 顺序。
- 每个 `(paper_id,chunker)` 的 duplicate/gap 均为 `0/0`。
- storage SQLite、`meta.json`、`.lock` 前后 hash 不变；`data/kb/papers.json` 前后 hash 不变。

Qdrant payload 只有现有检索字段，没有 source block、line、word 或 bbox 字段；因此
不能凭 payload 反推 PDF provenance，也没有向量重建或 payload 写入证据。

## 4. 调用计数与安全门

| 检查路径 | embedding | 切分 | Qdrant upsert | Qdrant delete | 结果 |
|---|---:|---:|---:|---:|---|
| inspection/no-embedding guard | 0 | 0 | 0 | 0 | PASS |
| 02-B PDF fixture observation | 0 | 5 | 0 | 0 | PASS；5 次仅为 probe 读取既有纯函数 |

embedding spy 配置为“调用即失败”，实际调用数为 0。hostile PDF 静态观察为
remote URI=1、widget=1、attachment=1、catalog JavaScript action=1；网络探针为
`NOT_EXECUTED_NO_BROWSER`，不能宣称非本地网络请求为 0。

## 5. 02-C 硬门审计

通过项：

- 三个正常 PDF fixture 的 expected chunk 集合均 100% match；
- 正常 PDF 坐标重投影 bbox 最大误差 `0.0 ≤ 0.005`；
- Markdown fixture oracle 行号精确率 `1.0`；
- Qdrant duplicate/gap 为 `0/0`；
- inspection guard 的 embedding/切分/upsert/delete 均为 `0`；
- Qdrant 和用户 metadata 前后 hash 不变；
- `pdf-no-text-layer` 没有被错误标记为 ready，错误码为 `PDF_NO_TEXT`。

未通过项（任一项即 No-Go）：

1. `extract_pages_normalized` 只返回整页字符串；无法证明规范化文本、字符区间、
   line/word/bbox 来自同一 `PdfSourceProvenanceV1` DTO。`provenance_dto_from_existing_parser=false`。
2. 业务代码没有 Markdown parser/chunker；Markdown 的 100% 只是固定 fixture oracle，
   不是实现级证据。`markdown_parser_implemented=false`。
3. hostile fixture 的浏览器网络记录未执行，不能证明除本地 source/worker 外请求数为 0。
   `hostile_network_proven=false`。

## 6. 02-D handoff closure

已确认并冻结：

- 7 个匿名原件、7 个 expected JSON、7 个 README 已位于 `docs/sdd/fixtures/spec-018/`；
- `fixture-index.json`、`provenance-dto.schema.json` 和本报告均存在；
- 原件/expected/schema SHA-256、命令、退出码、git revision、版本、统计、调用计数、
  Qdrant fingerprint 和失败码均已记录；
- 02-C 结论严格为 `NO-GO`，Task03 放行条件未满足；
- 未修改 `backend/**`、`frontend/**`、用户 `data/kb`、Qdrant 内容、Git 历史或 Spec 状态。

下一步必须先补齐同源 PDF provenance DTO、Markdown parser/chunker 与 hostile 浏览器
网络证据，再修订 Task02 并重新走需求/技术复审；本轮不得进入 Task03。
