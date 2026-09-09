# Spec018 Task02B 来源锚点与候选重建复验报告

## 当前裁决

```text
functional_verdict=NO_GO
production_cutover_verdict=NO_GO
```

来源 DTO 的 block/chunk/anchor 集合、PDF 坐标和 Markdown 行号均通过；但固定硬门要求“每个正式 fixture 同时具有 v1/v2，且 v2 `llm_used=true`”（`docs/sdd/plans/018/task-02b-revalidate-source-anchor-feasibility.md:66-73`）。公开 `CandidateRebuildService` 对三个正式 PDF fixture 在 v2 阶段稳定返回 `V2_RULES_ONLY_LLM_NOT_USED`，候选不切 alias。因此不能放行 Task03–05，也不能把该结果包装成条件通过。

生产切换同时维持 `NO_GO`：功能门未过；即使修复 v2 门，Task02A 已明确真实 Qdrant/生产 alias 原子性与切换安全债务必须留到 Task06（`docs/sdd/plans/018/artifacts/task-02a/backend-test-report.md:7-13`），本轮未接触真实 Qdrant、用户数据或生产 alias。

## 范围、边界与时间

- 模型：`gpt-5.6-luna xhigh`，临时仅本轮。
- 开始：2026-09-09 12:49:30 +0800；结束：2026-09-09 12:52:13 +0800；约 2 分 43 秒。
- 只读消费 Task02/02A 冻结证据和当前正式入口；候选验证仅使用 `tempfile` + `FakeQdrant`。
- 未读取/写入真实 `data/kb`，未连接真实 Qdrant，未修改 backend/frontend、首轮 fixture/expected/NO-GO 或 Git 历史。
- 进展日志：`.codebuddy/agent-logs/spec-018/task-02b/backend-tester/20260909-124930.md`。

## 证据冻结

`docs/sdd/plans/018/artifacts/task-02/fixture-index.json` 共 22 条 source/expected/README/schema 记录，逐条 SHA-256 **22/22 匹配，0 漂移**。关键 source/expected hash 如下：

| sample | source SHA-256 | expected SHA-256 |
|---|---|---|
| `pdf-single-column-v1` | `3cc6b61497f483fcb1933919cb00f1568ad1fd609953c96e4970c772cbe4e4ec` | `a91ace4a082d86365006f353c8ecb5ac3ad4d940ec265ff87216f6e43b382ea3` |
| `pdf-two-column-v1-overlap` | `33726da69e2c79bd5b3d4fe10dc14a2b64760802151b4af97b97f4bb84e99e7d` | `418a558b78e24cb2bf8e400b868cbdea34bbfe4aa3236c9bdc21ddb2575322c0` |
| `pdf-v2-cross-page` | `c0fccf6f1d0dde1c299ce044e63c79c2796ca981f7bcadaf62ec27db9e996468` | `cbece70d3a9296494aa4f28e1e4e27bcae89af7c9e3c09c80ea9b0c73f0e17fc` |
| `pdf-no-text-layer` | `05e59443707b6976afedbf1b0c1de5ad9bf62609411c902feb241b5033303252` | `b116f4a6a81b74039f9327d55420d2a266218a2fc382b1ffefb363680c6a8289` |
| `pdf-hostile-features` | `1bc72165cc992f88ad28ef9a6ea24438e1024c305082f03bd3d554a59d664377` | `20477b4ed7b1250adf12388b7565a305699d8f4986071f3687a8d9b0a811e4dc` |
| `markdown-blocks` | `0b19f1dc1a3bd687b2b9f369ce6c93998648d4f7b6c976d1ed87a78b41325e97` | `d7847f4089d88f4c5f989073eac2a3a048471a05986c3531deb694e782b2b22c` |
| `markdown-hostile` | `8adfb117879523e8858d9346307cfcfce94eb8b71d144c7453802b2973cf9f32` | `caae72931d25d856453ece2134c9af6ae41da3a7dd076b553b9ad0b87293a059` |

机器 DTO schema `docs/sdd/plans/018/artifacts/task-02/provenance-dto.schema.json` 的索引 hash 为 `01718f4b37a08f74b0a9bbd4c818810e145cd65d296ad2f1022c57dd866af6ed`，也匹配冻结索引。

## 正式入口重放

调用 `extract_pdf_provenance` / `extract_markdown_provenance`，再调用 `build_source_provenance_bundle`；expected 中定义的 pages、blocks、chunks、anchors、状态、错误、hash、chunker/config、anchor coverage 等字段均逐项比较。集合误差均为 **0**。

| sample | status / error | blocks/chunks/anchors | PDF bbox 最大误差 | Markdown 行号准确率 | hostile 外部调用 | bundle `llm_used` |
|---|---|---:|---:|---:|---:|---:|
| `pdf-single-column-v1` | ready / null | 3 / 1 / 3 | 0.000000 | — | 0 | false |
| `pdf-two-column-v1-overlap` | ready / null | 3 / 2 / 6 | 0.000000 | — | 0 | false |
| `pdf-v2-cross-page` | ready / null | 2 / 1 / 2 | 0.000000 | — | 0 | true（注入合法 `[]`） |
| `pdf-no-text-layer` | failed / `PDF_NO_TEXT` | 0 / 0 / 0 | 0.000000 | — | 0 | false |
| `pdf-hostile-features` | partial / `HOSTILE_FEATURES_NOT_EXECUTED` | 2 / 1 / 2 | 0.000000 | — | 0 | false |
| `markdown-blocks` | ready / null | 5 / 5 / 5 | — | 1.000000 | 0 | false |
| `markdown-hostile` | partial / `HOSTILE_MARKDOWN_REQUIRES_SANITIZER_PROBE` | 6 / 6 / 6 | — | 1.000000 | 0 | false |

“hostile 外部调用”通过禁止 `socket.socket`、`urllib.request.urlopen`、`subprocess.Popen/run`、`os.system` 的进程内 spy 得到；两个 hostile 样本均为 0 次，未执行、未联网。

### 兼容性证据（非本轮主阻塞，但不得隐瞒）

冻结 expected 的历史 parser/normalize 版本字符串与当前正式 DTO 不同：

- PDF expected：`pymupdf-1.28.2-extract_pages_normalized-unversioned` / `normalize.py-unversioned`；当前：`pymupdf-display-dict-insertion-v2` / `normalize.py-v1`。
- Markdown expected：`fixture-markdown-block-parser-v1`；当前：`markdown-source-parser-v1`；normalize 版本相同。

当前纯 parser DTO 的 metrics 也不是冻结 bundle 派生 metrics 的完整投影：PDF DTO 仅返回 `page_count/block_count/line_count`（`backend/app/knowledge_base/infrastructure/parse.py:225-231`），Markdown DTO 返回 `image_count/diagnostic_count/markdown_line_exact_rate`（`backend/app/knowledge_base/infrastructure/markdown.py:189-195`），而冻结 expected 另含 `word_count/mapped_chunk_rate/anchor_count/bbox_*`。本轮没有用缺失字段伪造 exact；block/chunk/anchor 与映射硬门仍按冻结字段比较并通过。若下游要求顶层 metrics/version 全字段 exact，应另行更新冻结契约或 bundle 投影。

## FakeQdrant 候选重建

### 正常/失败矩阵

每个样本均在独立临时目录复制冻结 source，metadata 使用冻结 document/source hash；`FakeQdrant` 先以测试 seam seed `papers` physical collection。embedder 为本地定长 4 维 spy，LLM 为返回合法 `[]` 的本地 spy。

| sample | CandidateRebuildService | v1/v2 points | alias / validation | 结论 |
|---|---|---:|---|---|
| `pdf-single-column-v1` | `V2_RULES_ONLY_LLM_NOT_USED` | — | alias `{}`，候选清理 | **硬门失败** |
| `pdf-two-column-v1-overlap` | `V2_RULES_ONLY_LLM_NOT_USED` | — | alias `{}`，候选清理 | **硬门失败** |
| `pdf-v2-cross-page` | completed | 2 / 1 | alias → `papers_rebuild_run`，validation `passed`，fingerprint `006fce9691bab36d7656d41d0da4eecb95637550cdeace8aaaf72fed8ea4e446` | 通过 |
| `pdf-no-text-layer` | `PROVENANCE_BUILD_FAILED` | — | alias `{}`，只保留 seeded `papers` | 预期 fail-closed |
| `pdf-hostile-features` | `V2_RULES_ONLY_LLM_NOT_USED` | — | alias `{}`，候选清理 | **硬门失败** |
| `markdown-blocks` | completed | 5 / 1 | alias → `papers_rebuild_run`，validation `passed`，fingerprint `37f7a78273cbcac6418bf704a81eb26ae0149068222311cd216d24c5d91851f4` | 通过 |
| `markdown-hostile` | completed | 6 / 1 | alias → `papers_rebuild_run`，validation `passed`，fingerprint `69489437942b47d7435ffe2c665b8d09ab342771611a94d38fac7be0cc77d677` | 通过 |

失败均未切换 alias。通过项的公开 validation 返回 `passed`，point ID 唯一、chunk index 连续，FakeQdrant 中候选 alias 与 v1/v2 point 数量如表；未使用真实 Qdrant。

### v2 阻塞的可复现原因（P0）

生产代码在 `backend/app/knowledge_base/infrastructure/candidate_rebuild.py:797-805` 对每个 chunker 建 bundle，并将 v2 的 `not bundle.llm_used` 或降级诊断统一拒绝为 `V2_RULES_ONLY_LLM_NOT_USED`。`provenance.py:285-294` 只有 `_build_chunks` 实际调用并成功解析 LLM 时才置 `llm_used=true`。

对三个失败 PDF，正式 `_pdf_chunk_pages` 按页拼接同页 display blocks；规则阶段没有可供 v2 LLM 判定的候选边界，因此即便注入合法 `[]`，LLM spy 也不会被调用，bundle 为 `llm_used=false`。这不是测试伪造或网络失败，而是公开入口的确定性结果。修复应明确以下其一并重新冻结/验收：

1. 保留 v2 “每个正式 fixture 必须 `llm_used=true`”门：修正 PDF v2 的候选边界/调用语义，使同页多 block 也发生一次合法 LLM 判定；或
2. 若产品定义“无候选边界时无需 LLM”，则修改 Task02B 固定硬门与验收 expected，不能在本轮报告中放宽。

在修复前，Task02B 第 69、73 行要求的“每个正式 fixture v1/v2、v2 `llm_used=true`”明确未满足，故 `functional_verdict=NO_GO`。

### 隔离候选动作与恢复

- dry-run：`status=completed`；embedding 调用 **0**；`ensure_collection/upsert/delete/create_alias/delete_alias` 写操作 **0**；runtime 目录不存在。FakeQdrant 仅发生 inventory read。
- alias before failure：注入 `create_alias` 前置异常，返回 `INJECTED_FAILURE`，候选保留、alias 未建立、state=`switching`。
- alias after/unknown：注入 `create_alias` 后置异常，alias 已指向候选、state=`switching`；公开 `resume_switch` 重新读取并完成，最终 `status=completed`，不重复猜测旧拓扑。
- no-text：`PROVENANCE_BUILD_FAILED`，不建立有效候选 alias。

这些结果支持 failure 不切换与恢复主链，但不能抵消三个正式 PDF 的 v2 硬门失败。

## 命令、退出码与数量

| 检查 | 结果 |
|---|---|
| 固定 Prompt 的 Python stdin 只读重放（22 hash、7 formal parser/bundle、hostile spy、7 FakeQdrant 候选、dry-run 与 alias failure/resume） | 退出码 0；22/22 hash；7/7 来源集合通过；3 个候选主链样本通过、3 个 v2/1 个无文本失败按上表记录；真实数据/Qdrant 写入 0 |
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_source_provenance_bundle.py tests/test_kb_pdf_provenance.py tests/test_kb_markdown_provenance.py` | 退出码 0；**97 passed**，5 warnings；pytest 6.24s，wall 6.69s |

## 风险与主 Agent 动作

### P0（当前阻塞）

- CandidateRebuildService 对 `pdf-single-column-v1`、`pdf-two-column-v1-overlap`、`pdf-hostile-features` 无法满足 v2 `llm_used=true`，导致正式候选不能构建完成/切换。请先修复实现或正式修改并重新冻结 Task02B 硬门，然后完整重跑本报告；在此之前保持 Task03–05 阻塞。

### P1（来源契约漂移）

- 当前 parser/source version 与冻结 expected 不一致，parser DTO metrics 不含冻结 bundle 派生字段。当前 block/chunk/anchor 硬门通过，但需要主 Agent 决定是更新 expected 的版本/投影，还是在 bundle 输出中补齐并由 schema/test 机器校验；不能默默依赖聊天解释。

### 生产安全债务（当前不作为功能放行理由）

- 真实 Qdrant SDK/服务端 alias 原子性、维护窗口切换、生产拓扑与其他 Task06 安全门本轮未验证；Task02A 报告已将其明确延期，不能把 FakeQdrant `passed` 当成生产切换通过。

## 签字

**Task02B backend-tester：NO-GO（独立复验）**

报告写入本文件；历史 Task02/02A fixture、expected、NO-GO 文档未修改。

---

# Task02B Tech Lead 独立诊断（2026-09-09 12:55–13:05 +0800）

## 裁决

```text
root_cause=PRODUCTION_PROVENANCE_V2_INPUT_ADAPTER
tester_stub_verdict=VALID
backend_dev_required=YES
functional_verdict=NO_GO（本次诊断不放宽既定 v2 llm_used=true 硬门）
production_cutover_verdict=NO_GO
```

三个失败不是 tester 的 LLM stub 配置错误，也不是 `[]` 判决不可解析；是正式 PDF provenance→v2 chunker 适配丢失了同页 block 边界，导致 `build_chunks_v2()` 合法地认为没有需要 LLM 判定的候选，从而没有调用 LLM。

## 根因证据

1. 正式 parser DTO 本身有正确 block：`pdf-single-column-v1` 为 3 blocks、`pdf-two-column-v1-overlap` 为 3 blocks、`pdf-hostile-features` 为 2 blocks；bbox/ordinal 未漂移。
2. `provenance.py:_pdf_chunk_pages`（约 `:195-217`）按页收集 display blocks，并在 `raw_pages = [(page, "".join(parts)) ...]`（约 `:207`）把同页多个 block 无分隔拼成一个 page text。`_build_chunks()`（约 `:253-294`）对 v1/v2 共用这条输入路径。
3. 对三个失败样本正式重放输出：

   ```text
   pdf-single-column-v1: parser_blocks=3, v2_blocks=1, boundaries=[0], candidates=[], llm_calls=0, llm_used=False
   pdf-two-column-v1-overlap: parser_blocks=3, v2_blocks=1, boundaries=[0], candidates=[], llm_calls=0, llm_used=False
   pdf-hostile-features: parser_blocks=2, v2_blocks=1, boundaries=[0], candidates=[], llm_calls=0, llm_used=False
   pdf-v2-cross-page: parser_blocks=2, v2_blocks=2, candidates=[1], llm_calls=1, llm_used=True
   ```

4. `chunkers.py:280-305` 的规则预筛在单 block 输入上只返回首块 `[0]`；`_judge_by_llm()` 对空 `candidates` 明确返回 `False`，所以没有发生 stub 调用。相反，`chunkers.py:164-171` 的既有测试已经证明合法空列表 `"[]"` 会被解析并使 `llm_used=True`。
5. 进程内只读构造保留 parser block 边界的 v2 输入（每个 display block 作为一个 `(page,text)` 输入）后，三个失败样本均为 `llm_calls=1, llm_used=True`；这排除了 stub 输出、网络和 JSON 判决问题。

## 最小修复范围

必须由 `backend-dev` 修复正式实现，不能修改 fixture/expected 或在报告中把 `llm_used=false` 伪装为通过：

- 在 `provenance.py` 的 PDF **v2 专用**输入适配中保留同页 display block 边界（例如按稳定 display ordinal 生成多个 page/block 输入，或等价地使用明确 block 分隔），让 v2 对未被规则预筛的 block 至少执行一次合法 LLM 判定。
- 保留 v1 当前 `_pdf_chunk_pages` 行为，避免为修 v2 改变既有 v1 单页/双栏 anchor/chunk exact 结果；不得直接把全局 `"".join` 改成可能破坏 v1 fixture 的分隔策略而不跑回归。
- 增加三个 PDF fixture 的公开回归：spy 调用次数至少/恰为 1（按最终 batch 设计冻结）、`llm_used=true`、`degradation_diagnostics=[]`，并再次运行 `CandidateRebuildService` 确认 v1/v2 point、alias/validation 主链完成。
- 继续验证 hostile PDF 不执行活动内容、不联网；合法 `[]` 判决必须保留为空边界结果而非降级。

不需要修改 parser DTO、PyMuPDF、固定 source/expected 或 tester 的 LLM stub；`build_chunks_v2` 的“无候选时不调用 LLM”行为本身与当前实现语义一致，真正缺口在 provenance 的 PDF-v2 输入形状。

## 命令、退出码与证据行号

| 检查 | 结果 |
|---|---|
| 正式 parser + `_pdf_chunk_pages` + `_to_blocks` + `_rule_boundaries` + bundle spy（四 PDF） | 退出码 0；三个失败样本 0 次调用，cross-page 1 次调用 |
| 保留 parser block 边界后直接 `build_chunks_v2(..., llm=lambda _: "[]")` | 退出码 0；single=1、two-column=1、hostile=1 次调用，均 `llm_used=True` |
| `.venv/bin/python -m pytest -q tests/test_kb_source_provenance_bundle.py tests/test_kb_chunkers.py tests/test_kb_pdf_provenance.py` | 退出码 0；71 passed，5 warnings |
| 当前 Task02B 报告 FakeQdrant 正式重建矩阵 | 三个 PDF v2 硬门失败、未切 alias；cross-page/Markdown通过 |

## 主 Agent 后续动作

1. 分派 `backend-dev` 只修 `provenance.py` 的 PDF-v2 block-preserving 输入适配并补对应后端测试；禁止改 fixture/expected 逃避硬门。
2. 修复后重新跑完整 Task02B 正式重放和 FakeQdrant 候选重建，确认三个 PDF 的 v2 `llm_used=true`、validation passed、alias 完成。
3. 在上述复跑完成前保持 Task02B `functional_verdict=NO_GO`，Task03–05 不放行；真实 Qdrant/生产切换仍留 Task06。

## Tech Lead 签字

**诊断结论：生产功能缺陷，必须 backend-dev 修复；当前报告 NO-GO。**

本轮未修改业务代码、fixture、expected 或历史 NO-GO；日志：`.codebuddy/agent-logs/spec-018/task-02b/architect/20260909-125522+0800.md`。

---

# 修复轮最终复验（2026-09-09 13:02:07–13:05:00 +0800）

> 本节是本报告的**最新结论**；上方首轮 NO-GO 与独立诊断历史保持不动。

## 最新裁决

```text
functional_verdict=GO
production_cutover_verdict=DEFERRED_SECURITY_DEBT
```

修复后的 `provenance.py` 为 PDF v2 增加保留 display-block 边界的输入适配，未改变 v1 page-level 输入。三个首轮失败 PDF 均真实通过 `CandidateRebuildService` 的 v2 `llm_used=true`、dense/sparse/payload、validation、alias 主链。因此按 Task02B 固定 Prompt，功能可放行 Task03–05；真实 Qdrant/生产切换安全债务仍延期 Task06，Task06 不放行。

## 固定证据与正式入口复验

- `fixture-index.json` 22/22 source/expected/README/schema SHA-256 匹配，0 漂移。
- 7/7 固定样本经 `extract_pdf_provenance` / `extract_markdown_provenance` + `build_source_provenance_bundle` 重放；expected 定义的 pages、blocks、chunks、anchors、status/error、hash/config 字段均 0 mismatch。
- PDF bbox 最大绝对误差：`0.000000`；Markdown 行号准确率：`markdown-blocks=1.000000`、`markdown-hostile=1.000000`。
- hostile PDF/Markdown 禁止 socket、urlopen、subprocess、os.system 后均 0 次外部调用；no-text 保持 `failed/PDF_NO_TEXT`。
- 首轮报告中记录的 parser/source version 字符串与冻结 expected 历史版本差异仍存在；纯 parser DTO metrics 与冻结 bundle 派生 metrics 投影仍不完全相同。该兼容性风险未被伪造成 exact，但不属于本轮 Task02B 明确的 block/chunk/anchor、bbox、Markdown 行号或候选 v2 硬门，列为 P1 观察项。

## 三个此前失败 PDF 的候选结果

均使用独立 `tempfile`、冻结 source 副本、`FakeQdrant` 和本地 embedder/LLM spy；没有真实 data/kb 或真实 Qdrant 写入。

| sample | v1/v2 points | LLM calls | v2 `llm_used` | validation / alias | collection fingerprint |
|---|---:|---:|---|---|---|
| `pdf-single-column-v1` | 1 / 1 | 1 | true | passed / `papers → papers_rebuild_run` | `f4ab4a9fb7b30e11ae4ecb76e270b95be97976842eba912ed496d2dee5b57305` |
| `pdf-two-column-v1-overlap` | 2 / 2 | 1 | true | passed / `papers → papers_rebuild_run` | `c1747f6e4c8f464555a67d842038f5aef77384d5ac802cd87bba8323805384e2` |
| `pdf-hostile-features` | 1 / 1 | 1 | true | passed / `papers → papers_rebuild_run` | `406a14ec66b583ba8cb0127143a242be2e8f61fda7093c6753b5c9a239a8dfc1` |

其余候选结果：

- `pdf-v2-cross-page`：2 / 1，`llm_used=true`，validation passed，fingerprint `006fce9691bab36d7656d41d0da4eecb95637550cdeace8aaaf72fed8ea4e446`。
- `markdown-blocks`：5 / 1，`llm_used=true`，validation passed，fingerprint `37f7a78273cbcac6418bf704a81eb26ae0149068222311cd216d24c5d91851f4`。
- `markdown-hostile`：6 / 1，`llm_used=true`，validation passed，fingerprint `69489437942b47d7435ffe2c665b8d09ab342771611a94d38fac7be0cc77d677`。
- `pdf-no-text-layer`：按预期 `PROVENANCE_BUILD_FAILED`，不建立 alias；这是固定失败样本的 fail-closed 验收，不计入可建候选失败。

所有通过样本 point ID 唯一，chunk index 无重复/缺口，dense/sparse vector 与 payload 完整；每个 v2 bundle 的合法 `[]` LLM 判定实际调用 1 次且无 degradation diagnostics。修复证据位于 `backend/app/knowledge_base/infrastructure/provenance.py:220-249`，v2 分支调用位于 `:283-294`，候选硬门仍位于 `backend/app/knowledge_base/infrastructure/candidate_rebuild.py:797-805`。

## 隔离候选、dry-run 与恢复

- dry-run：`completed`；embedding **0** 次；`ensure_collection/upsert/delete/create_alias/delete_alias` 写操作 **0**；runtime 目录不存在。
- alias before failure：`INJECTED_FAILURE`，alias 未建立，候选保留，state=`switching`。
- alias after/unknown failure：alias 已指向候选，state=`switching`；公开 `resume_switch` 完成并保持 alias 正确指向。
- no-text 与任何硬失败均不切换默认 alias。

## 命令、退出码与耗时

| 检查 | 结果 |
|---|---|
| 固定 Prompt Python stdin 探针：22 hash、7 parser/bundle、bbox/Markdown 行号、hostile spy、7 CandidateRebuildService、dry-run、alias failure/resume | 退出码 **0**；22/22 hash；7/7 来源集合；6/6 可建样本候选通过；no-text 预期 fail-closed |
| `.venv/bin/python -m pytest -q tests/test_kb_candidate_rebuild.py tests/test_kb_source_provenance_bundle.py tests/test_kb_pdf_provenance.py tests/test_kb_markdown_provenance.py` | 退出码 **0**；**100 passed**，5 warnings；pytest 6.34s，wall 6.80s |

## 放行边界与后续动作

- **放行 Task03–05：是。** 来源锚点和隔离候选功能主链已满足本轮固定硬门。
- **放行 Task06：否。** 真实 Qdrant SDK/服务端 alias 原子性、生产维护窗口、真实拓扑/网络故障和剩余切换安全债务仍须 Task06 验证；其状态为 `DEFERRED_SECURITY_DEBT`，不得用 FakeQdrant 结果替代。
- 主 Agent 后续应保留本节最新 GO 与上方历史 NO-GO，按 Task02B 变更日志推进 Task03–05，同时将 parser/version/metrics 投影漂移作为 P1 契约收敛项跟踪。

模型：`gpt-5.6-luna xhigh`（临时，仅本轮）；复验耗时约 3 分钟。

最新进展日志：`.codebuddy/agent-logs/spec-018/task-02b/backend-tester/20260909-130207.md`。

**Task02B backend-tester 修复轮签字：功能 GO；生产切换 DEFERRED_SECURITY_DEBT。**

---

# Task02B Tech Lead 最终只读签字（2026-09-09 13:05–13:18 +0800）

## 独立复核裁决

```text
functional_verdict=GO
production_cutover_verdict=DEFERRED_SECURITY_DEBT
task03_05_release=ALLOWED
task06_release=BLOCKED
```

我对 tester 最新修复轮报告没有采信式签字，而是重新读取 `provenance.py` diff/新增测试，并以临时目录、冻结 fixture 副本和 `FakeQdrant` 重放正式入口。结论与最新报告一致：PDF-v2 的 display-block 输入适配已修复，三个此前失败样本的功能硬门已关闭；真实 Qdrant/生产切换安全债务仍不能放行 Task06。

## 证据核对

- `fixture-index.json` 实际逐条重算为 **22/22 SHA-256，0 漂移**；未发现 fixture、expected 或 README 变更。
- 七份固定样本的 baseline parser/bundle projection 重放为 **7/7**：pages、blocks、chunks、anchors、status/error、source hash、chunker/config 与映射计数均通过；PDF bbox 最大绝对误差 **0.000000**，两个 Markdown 样本行号准确率 **1.000000**。
- PDF-v2 的正式 injected-LLM 路径单独复核：`pdf-single-column-v1`、`pdf-two-column-v1-overlap`、`pdf-hostile-features` 均各触发 1 次合法 `[]` 判定，`llm_used=true`、`degradation_diagnostics=[]`；`pdf-v2-cross-page` 同样通过。
- 以正式 `CandidateRebuildService`、临时 metadata/source 副本、4 维本地 embedder、`FakeQdrant` 重放：上述三个 PDF 均 `status=completed`，v1/v2 point 数分别 `1/1`、`2/2`、`1/1`，validation=`passed`，alias=`papers → papers_rebuild_*`；no-text fixture 按契约 `PROVENANCE_BUILD_FAILED` 且不切 alias。Markdown 两份样本亦完成 v1/v2 主链。
- 定向 pytest：退出码 **0**，**100 passed**，5 warnings；`ruff check` 退出码 **0**；针对实现/测试的 `git diff --check` 退出码 **0**。

注：cross-page 的冻结 bundle oracle 以无注入 LLM 的 baseline 配置保持 `llm=disabled`；CandidateRebuildService 的功能门使用注入合法 `[]`，其运行时配置为 `llm=injected`。这是两条不同的验证目的，不将配置差异伪装成同一 exact oracle。

## 残余风险与边界

- parser/source version 与冻结历史 expected 字符串、纯 parser metrics 与 bundle 派生 metrics 的投影差异仍按最新报告列为 P1 契约观察项；本轮 block/chunk/anchor、bbox、Markdown 行号及 v2 候选功能门均未发现阻塞。
- 真实 Qdrant SDK/服务端 alias 原子性、生产拓扑/网络故障、维护窗口和切换安全门未由 FakeQdrant 证明，继续由 Task06 处理；不得以本轮功能 GO 代替生产切换批准。

## 最终签字

**Tech Lead：功能 GO，可放行 Task03–05；生产切换 DEFERRED_SECURITY_DEBT，Task06 当前阻塞。**

本轮仅追加本节与层级日志，未修改业务代码、fixture、expected、Spec/Plan 或 Git 历史。
