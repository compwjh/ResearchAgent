# Spec018 2026-10-21 PDF 安全与状态发布修复：技术评审

- 评审者：`/root/map_analysis_backend_review`
- 角色：独立架构师 / 安全技术评审
- 模型：当前执行 Agent（不固化模型代号）
- 分派方式：上级 Agent 分派，本 Agent 独立只读评审
- 评审日期：2026-10-21（Asia/Shanghai）
- 范围：只读 `parse.py`、`index.py`、metadata schema/patch、generation/manifest store、reindex 入口和精准测试；不修改代码、不部署、不调用真实 provider/数据、不提交。

## 结论

**BLOCK（技术评审打回，暂不派发编码）。**

总体方向正确，但当前实现方案仍缺少几个必须先冻结的安全/发布细节；现有精准测试也尚未覆盖这些失败边界。若现在编码，最容易出现“危险 OpenAction 被误放行”或“manifest 已变更但 metadata/generation 语义不一致”的不可复核状态。

## 代码事实与方案核对

### 1. 当前 parser 仍是存在性一刀切

- `backend/app/knowledge_base/infrastructure/parse.py:64-68` 的 `_ACTIVE_ACTION_RE` 将 `OpenAction` 与危险 action 名放在同一正则中。
- `parse.py:327-349` 对 Catalog 的 `OpenAction`、`AA`、`AcroForm` 只做“非 null 即 hostile”；因此真实 GAT 的安全内部 `/GoTo` 仍会被拒绝。
- `parse.py:458-505` 只在 active state 为 safe 且无坐标问题时返回 `ready`，所以不能通过调整 manifest 或 Spec043 gate 掩盖 parser 误报。

结构化白名单方向可接受，但不能简化为“从正则删除 `OpenAction`”。必须新增一个纯被动 resolver：

- 只接受 Catalog `OpenAction` 的 direct/indirect action dictionary，且 `/S` 精确为 `/GoTo`；拒绝 `/Next`，包括间接目标中的 `/Next`。
- `/D` 只接受可验证的同文档 page reference + 合法 page destination（本修复最小范围可仅放行 `[pageRef /Fit]`；named destination、远程/file target、未知数组形状统一拒绝）。
- page reference 必须能在当前 PDF 中解析为真实 page object，不能仅凭“像数字引用”放行；对象解析必须有深度/字节上限并防循环，避免恶意 PDF 造成解析 DoS。
- action/destination 解析失败、对象类型不符、目标越界或存在额外 action 链时返回 `unavailable`/既有稳定失败码，绝不降级成 safe。
- xref 扫描仍须识别 direct/indirect 的 JavaScript、`AA`、AcroForm、XFA、RichMedia、EmbeddedFiles、Launch、SubmitForm、ImportData、GoToR 以及未知 active action；安全 OpenAction 自身不能继续成为正则误报，但也不能因移除该 token 而漏掉危险对象。

### 2. worker 发布顺序的失败语义未完全闭合（P1）

当前 `backend/app/knowledge_base/infrastructure/index.py:548-562` 先执行 `update_chunker_state(... STATUS_INDEXED ...)`，再调用 `_publish_inspection_manifest()`；`_publish_inspection_manifest()`（`index.py:404-435`）写 manifest 后刷新 generation digest，但没有回写 canonical hash/status。当前 `store.py:744-781` 也只写 chunker 状态；`migration.py:403-417` 的 `patch_knowledge_document()` 不允许 hash 字段。

诊断提出“manifest 先行、再写 metadata/hash、最后刷新 generation”的方向是对的，但还没有冻结以下失败后的唯一状态：

- manifest 已写成功、metadata/hash patch 失败；
- metadata/hash 已写成功、generation digest refresh 失败；
- Qdrant upsert 成功但 manifest 写失败；
- source 在 parse/upsert 前后变化，导致 `source_sha256` 不再代表实际写入内容。

必须明确每种情况的状态、稳定 error、marker 行为和重试方式。最低安全要求是：任一后置步骤失败时，不能留下可通过 Spec043 全文 gate 的 `ready/indexed/verified` 组合；不能依赖“下次重试也许会修好”的隐式状态。metadata/hash helper 必须走严格 schema、原子写、owner/document 校验，并在最终成功后以预期 destination collection 刷新 generation digest。

此外，`index_paper_chunker()` 是 `GenerationBoundIndexPort.index_document()` 的共享入口（`index.py:623-656`），修复不能只覆盖某个 API wrapper 而遗漏 direct reindex/导入路径。

### 3. 当前失败注入测试不足（P1）

本轮独立运行的既有精准测试为：

```text
.venv/bin/python -m pytest -q \
  tests/kb/test_kb_pdf_provenance.py \
  tests/kb/test_kb_tasks.py \
  tests/kb/test_kb_document_reindex.py
46 passed, 5 warnings
```

这 46 项证明了旧 provenance、任务兜底和 reindex 基线，但没有证明本修复的安全/发布门禁。诊断中列出的测试方向还必须落成实际用例，至少包括：

#### Parser 安全矩阵

1. benign Catalog `/OpenAction` `/S /GoTo` + direct page reference + `/Fit`：`ready`，无 error。
2. 同结构的 indirect action、indirect destination、有效 page reference：仍可放行；spy 证明无 action/navigation/network。
3. 无效/越界 page reference、错误 destination array、named destination 无法最终解析、`/Next`、间接循环、对象不可读/超限：`failed/PDF_PROVENANCE_UNAVAILABLE` 或既有明确 unavailable，不得 `ready`。
4. direct/indirect JavaScript/JS、AA、AcroForm、XFA、RichMedia、EmbeddedFiles、Launch、SubmitForm、ImportData、GoToR、remote/file/unknown action：仍为 hostile/partial 或 unavailable，不得因存在合法 GoTo 同时放行。
5. benign URI annotation 继续被动统计且不发起 fetch；危险链接类别仍不执行。

#### Worker 发布与 hash/generation 矩阵

1. `partial/HOSTILE_FEATURES_NOT_EXECUTED`：Qdrant upsert 后 manifest 为 `partial`，metadata 对应 chunker 为 `indexed_partial`、100%、同一稳定 error；canonical hash 为 `verified` 且 indexed hash 等于 source hash；v2 partial 不覆盖顶层 v1。
2. ready bundle：manifest 先写成功，再 metadata `indexed`/hash verified，最后 generation marker/live digest 通过 `require_generation()` 复核。
3. manifest write failure：不得先留下 `indexed`；结果为稳定 failed，不能伪造 verified/ready。
4. metadata/hash patch failure 和 generation refresh failure：必须注入并断言不会暴露 ready；marker/manifest/metadata 的最终状态与恢复动作符合上面冻结的协议。
5. Qdrant upsert failure、source hash 在解析前后变化、manifest schema/hash/generation 不匹配：稳定失败，不写成功 metadata/hash。
6. direct `index_paper_chunker()` 与 `GenerationBoundIndexPort.index_document()` 两条入口均覆盖；测试只用 fake Qdrant/临时 metadata，不调用真实 provider、真实数据或部署服务。

## 非阻塞风险与边界

- `submit_document_reindex()` 当前只返回进程内 task UUID，任务终态不持久化（`backend/app/knowledge_base/application.py:801-849`）。Spec018 修复段明确不新增任务持久化 API，因此本轮不把它升级为阻塞；报告和验收不得声称支持跨重启查询该 UUID 的终态。
- partial manifest 可能保留已经 upsert 的派生向量，这是 fail-closed 的可见结果；不得为了清理方便而把 partial 升级 ready。若要补偿删除，应另开已确认范围的索引补偿设计。
- 本技术评审不放宽 Spec043 全文 evidence gate，不执行真实 GAT 重建，不修改历史 018 完成报告。

## 进入编码前的必改清单

1. 在修复 task/实现契约中冻结结构化 destination resolver 的允许形状、间接引用、`/Next`、page reference 合法性、循环/大小上限和稳定错误码。
2. 冻结 manifest→metadata/hash→generation 的失败状态机；明确 metadata/hash patch 和 generation refresh 失败时如何保持 fail-closed，并加入 post-upsert source hash 复核。
3. 将上述 parser 安全矩阵与 worker 失败注入矩阵写成按能力命名的精准测试，先补测试再实现；不得用真实 provider、生产数据或全量回归替代。

## 技术评审签字

**独立架构师 / 安全技术评审：BLOCK。** 需求评审已 GO，但技术评审必须在上述 P1 细节和测试落盘后复审通过，之后主 Agent 才可按后端文件边界派发编码。

---

## 2026-10-21 修复合同窄复审（最终）

本节是对上方 BLOCK 的复审追加，不改写历史结论。复审范围仅为新增的
`repair-contract.md`（第 1–26 行）及其在 Spec018 中的引用；不宣称业务代码已经实现，也不把旧的 46 项基线测试当作本修复的验收。

### 三项阻塞逐项核验

| 原 P1 | 合同证据 | 复审结论 |
|---|---|---|
| 页引用白名单边界不足 | `repair-contract.md:7-11` 明确禁止执行 action/JS/导航/附件/网络；OpenAction 仅允许本文件页目标或严格 GoTo 字典，拒绝 `Next`、文件字段、未知键/动作；`[pageRef /Fit]` 的页 xref 必须真实属于当前文档，远程/错误/额外元素不放行；最多 4 层间接引用、visited 防循环、单对象 16KiB、数组最多 8 项，超限/不可解析走 `PDF_PROVENANCE_UNAVAILABLE`，危险/未知 active 结构保持 partial。 | **PASS（合同层面）**。这已冻结此前缺失的形状、间接解析、循环/资源上限、`Next` 与 unknown fail-closed 规则。实现时不能把“可选其他数值形状”扩大为 named/字符串/远程目标，也不能因放行内部 GoTo 而跳过其它危险对象扫描。 |
| manifest→metadata→generation 与源 hash 失败语义未闭合 | `repair-contract.md:15-20` 固定先后顺序：索引后重检原件 hash 与 canonical hash；manifest 先行且成功前不得写 indexed；严格 schema/原子 metadata 写入状态与 hash；metadata 后才刷新 generation，并以 `require_generation()`、manifest 和源 hash 复核；manifest、metadata、generation refresh/verify 各失败路径均进入受控 failed 或 `INDEX_FINALIZE_REQUIRED`，不得伪造 ready/verified，gate 对中间态 fail-closed。 | **PASS（合同层面）**。合同也明确复用 publication mutation lock、不得新造发布器，覆盖了此前担心的 helper 提前刷新 marker 和 source drift。实现必须让 direct index/reindex 共享该顺序，不能只修 API wrapper。 |
| 真实故障注入与无执行/无网络测试不足 | `repair-contract.md:24-26` 要求真实构造 PDF 覆盖间接 GoTo/Fit、裸数组、恶意动作、`Next`、unknown、非本地页、循环/过深/过大/畸形结构，并断言无执行/网络；同时要求真实临时 manifest/generation store 注入 manifest 写、metadata 原子写、generation refresh/verify、索引期间源文件变化等失败，断言无假成功且全文 gate 拒绝中间态。 | **PASS（合同层面）**。测试要求已从 mock happy path 提升为能力矩阵与真实临时存储故障注入；恢复 GAT/Spec043 全文分析与问答被明确放在 GO 后，不以本轮设计复审冒充运行验收。 |

### 最终技术裁决

新增合同已逐条补齐此前三项 P1 的必要安全边界和可验证失败语义，未发现仍需在合同层面阻塞编码的 P0/P1。故本次窄复审结论为：

**GO（技术合同复审通过，可按后端边界派发实现）。**

该 GO 仅表示修复合同足以进入编码，不表示当前旧实现已经安全，也不表示真实 GAT 恢复、真实全文分析/问答或发布运行验证已通过。编码完成后必须实际落地上述 parser 矩阵、临时 manifest/generation store 故障注入和 no-execution/no-network 断言，再由后端回归与独立安全复审确认；本轮未重跑旧 46 项基线，未调用真实 provider/数据，未部署，未修改业务代码。

**独立架构师 / 安全技术评审：GO（2026-10-21，修复合同窄复审）。**
