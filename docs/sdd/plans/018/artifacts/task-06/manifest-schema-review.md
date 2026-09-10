# Spec018 Task06 manifest schema 修复独立 backend review

## 结论

```text
结论：GO（仅针对本次 manifest schema 修复的隔离功能门）
新增 P0/P1：无
生产索引切换授权：NO-GO（本评审不覆盖 Task06 既有生产门禁）
真实 Qdrant / 真实 data/kb 写入：false
```

本次修复正确处理了真实 PDF 重建暴露的 `MANIFEST_SCHEMA_INVALID`：在
manifest 边界对 PDF block 和 line 做显式白名单投影，保留冻结 schema 要求的
顶层坐标字段，并为 PDF 生成规范 locator。冻结 schema validator、PDF/Markdown
跨格式探针和候选重建回归均通过。没有发现额外字段泄漏、当前契约字段丢失，或
Markdown/anchor/chunk 的回归。

## 评审范围与依据

- `backend/app/knowledge_base/infrastructure/inspection.py:123-192`
- `tests/test_kb_document_foundation.py:123-158`
- `docs/sdd/plans/018/artifacts/task-03/inspection-manifest.schema.json`
- `docs/sdd/plans/018/task-06-legacy-backfill-and-resilience.md`
- `docs/sdd/plans/018/artifacts/task-06/manifest-schema-fix-report.md`

评审为只读；未启动服务、未访问真实 Qdrant、未修改业务代码或 `data/kb`。

## 逐项核对

### 1. PDF block 显式白名单：PASS

`_manifest_block()` 的 PDF 分支只复制冻结 `pdfBlock` 的源字段：
`block_id`、`ordinal`、`display_ordinal`、`page`、`text`、`raw_text`、`start`、
`end`、`bbox`、`normalized_bbox`、`lines`、`block_type`、`heading_path`。
随后写入冻结 schema 要求的 `locator={kind: "pdf_bbox", page, bbox}`，其中
locator bbox 使用 `normalized_bbox`。因此 parser/bundle 的未来或诊断字段不会
直接泄漏到 manifest；顶层 raw/normalized bbox 均保留。

### 2. PDF lines 投影：PASS

当 `lines` 为序列时，每个 Mapping 只投影 `ordinal`、`text`、`start`、`end`。
parser 提供的每行 `bbox` 与 `normalized_bbox` 按冻结 `$defs.line` 的
`additionalProperties: false` 契约有意不进入 manifest；这不会丢失 manifest
允许的字段，且顶层 block 坐标仍可用于 PDF 定位。缺失必需 line 字段或非法
非 Mapping 元素会在最终 schema 校验处 fail-closed，而不是绕过白名单。

### 3. Markdown 无回归：PASS

Markdown 分支也从显式冻结字段投影，保留 `locator`、heading、行范围、内联资源
和 diagnostics，并补齐 page/page_end 等 schema 默认值。locator 仍规范化为
`markdown_lines`；anchor 仍从投影 block 的 `start/end` 生成 block_range，chunk
仍由 payload 与 bundle fallback 生成，Markdown chunk_range 仍由 start_line /
end_line 决定。

### 4. 额外字段与数据完整性：PASS

只读探针对所有 PDF fixture 的全部生成 block 检查字段集合等于冻结
`pdfBlock.properties`，对全部 line 检查字段集合等于冻结 `line.properties`，
并逐字段比较 PDF block 坐标、locator 和 line 四字段值。对 Markdown probe
检查 block/chunk/anchor 字段集合并通过完整 Draft 2020-12 schema 验证。

## 证据

- 新增 foundation 回归锁定 PDF 顶层 `bbox`、`normalized_bbox`、规范
  `pdf_bbox` locator，以及 line 四字段白名单（测试文件 123-158 行）。
- `build_inspection_manifest()` 在返回前仍使用冻结
  `inspection-manifest.schema.json` 做 Draft 2020-12 校验；未放宽 schema 或
  `additionalProperties`。
- 自定义只读字段探针结果：
  - `pdf-single-column-v1.pdf`：3 blocks、8 lines、1 chunk、3 anchors，0 schema errors。
  - Markdown probe：3 blocks、3 chunks、3 anchors，0 schema errors。
  - 全 PDF fixtures：hostile 2 blocks/2 anchors、single-column 3/3、two-column
    3/6、v2-cross-page 2/4 均通过；no-text fixture 无 chunks，按预期不构建 manifest。
- 未观察到 `data/kb`、Qdrant、服务或网络副作用。

## 风险与边界

- 当前没有阻塞风险。白名单的有意取舍是：PDF 每行 bbox 几何属于 parser
  诊断数据，不属于冻结 manifest line schema；需要消费每行几何的功能不能从
  manifest 假定该字段存在。
- 维护风险（P2）：若冻结 schema 未来新增 block/line 字段，必须同步更新这里的
  projection 与回归测试；否则新字段会被有意丢弃或由 schema 校验拒绝。这是
  当前 fail-closed 设计的预期行为，不构成本轮 NO-GO。
- 本 GO 只覆盖 manifest projection 与相关隔离回归，不覆盖真实 Qdrant、alias
  切换、生产维护窗口、原件全集校验或 Task06 总体 cutover 门禁。

## 主 Agent 后续动作

1. 将本报告与 `manifest-schema-fix-report.md` 纳入 Task06 交接汇总。
2. 保持 Task06/Spec018 既有真实索引切换门禁；本报告不得作为
   `--confirm-replace` 或真实 alias/Collection 操作授权。
3. 若未来冻结 manifest schema 变更，更新 PDF/Markdown projection 的白名单与
   跨格式字段集合回归。

## 测试命令、退出码与耗时

| 命令/检查 | 退出码 | 结果 | 耗时 |
|---|---:|---|---:|
| `python -m pytest -q tests/test_kb_document_foundation.py` | 0 | 10 passed（5 warnings） | 0.15s |
| `python -m pytest -q tests/test_kb_source_provenance_bundle.py` | 0 | 19 passed（5 warnings） | 0.93s |
| `python -m pytest -q tests/test_kb_pdf_provenance.py` | 0 | 25 passed（5 warnings） | 0.35s |
| `python -m pytest -q tests/test_kb_candidate_rebuild.py` | 0 | 62 passed（5 warnings） | 7.86s |
| PDF/Markdown 字段集合、值保真、Draft 2020-12 schema 只读探针 | 0 | PDF/Markdown 全部断言通过 | 0.06s |
| 全 PDF fixture projection/schema 只读探针 | 0 | 4 个有文本 PDF 通过；no-text 无 chunks 按预期跳过 | 0.11s |
| `git diff --check` | 0 | 通过 | 0.20s |

## 交接物

- 本报告：`docs/sdd/plans/018/artifacts/task-06/manifest-schema-review.md`
- 进展日志：`.codebuddy/agent-logs/spec-018/task-06/backend-reviewer/20260910-000000.md`

