# Spec 030 ReportDeliveryService canonical publication review

日期：2026-10-29 20:45（Asia/Shanghai）  
范围：只读评审 `ReportDeliveryService.prepare_canonical` / `finalize_canonical`、`tests/research/test_report_publication.py` 与 `2026-10-29-report-publication-handoff.md`。未修改业务代码。

## 当前复审结论（2026-10-29 20:56）：PASS（仅复审的两项 P1 修复）

两项初审 P1 均已在当前快照修复并通过窄复审；原 BLOCK 结论和复现记录保留在下方，作为修复前审查历史。本结论只覆盖 canonical publication helper 的这两项问题，不替代 API routes 的 unpublished Artifact 隔离评审。

- canonical body 现在由服务端依据 owner/task 的持久 selection、同 plan 的 Evidence Matrix 和 canonical `report_content` 重渲染。Markdown、HTML、manifest 均与服务端结果比较；不一致在 Artifact/message 写入前 fail closed。`generation.store_state.rewrite_count` 限制为 0–2，并必须与重新计算的质量对象 `revision_count` 一致。
- link 保护现在核实当前 session final message 的 owner、conversation、父 activity、role/status，再通过更高版本 Markdown Artifact 的内容 hash 和固定 activity idempotency key 确认版本；不再依赖较新 canonical `ResearchReport` row 才保护新 link。
- 定向测试：`/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_publication.py`，退出码 0，20 passed。
- 独立临时库探针：分别伪造 Markdown、HTML、manifest，均收到 `REPORT_RENDER_INVALID` 且无 Artifact/message 写入；修改 durable rewrite count 但不匹配 canonical quality 时被拒绝；较新 legacy Markdown Artifact + activity key、无 canonical report row 的 session link 在旧版 replay 后保持不变。
- 本轮未发现这两项范围内的新 BLOCK。

## 初审结论（2026-10-29 20:45）：BLOCK

当前定向测试通过，身份绑定、发布 CAS 前后的消息/通知顺序和一般恢复路径都有实现；但有两个可独立复现的用户可见正确性缺陷：服务接受与 canonical `report_content` 无关的 Markdown/HTML/manifest，且旧版回放在较新 final link 没有 canonical report row 时会把 session link 覆盖回旧报告。修复并增加回归用例前，不建议通过 publication helper 评审。

## Findings

### [初审 P1；当前复审已关闭] Artifact hash 只证明了调用方输入稳定，未证明它来自 canonical renderer

位置：`backend/app/research/application/report_synthesis.py:950-985`，后续 Artifact 与消息只对 `context["contents"]` 做逐字/hash 比较：`:1066-1078`、`:1185-1201`、`:1246-1256`。

`_canonical_delivery_context` 确认 `rendered.report.report_content` 和 `quality_validation` 等于数据库 canonical payload，但 Markdown 和 HTML 只需是非空字符串；manifest 只检查版本、report ID 和 citations 是 list。它没有从已绑定的 canonical content/context 调用确定性 renderer，也没有验证 renderer provenance 或可复算的 canonical digest。因此一个错误/替换的 renderer 参数可以保持 report ID/version/content/quality 完全正确，却把任意正文写成三种“canonical”Artifact，并把同一错误 Markdown 写入待发布消息。Artifact 的 SHA-256 随后只对这份不可信输入求值，不构成来源证明。

**独立探针：**使用测试的临时 SQLite fixture，保留 canonical `report_content`、quality、IDs 和 citation manifest 不变，仅将传入的 Markdown/HTML 换为 `# Forged body unrelated to report_content` / `<h1>Forged</h1>`。`prepare_canonical` 成功，持久 Artifact 和消息正文均为 forged 值（`forged_renderer_accepted=True`）。没有改动项目数据。

这与交接契约中“用 canonical `report_content` 重渲染；Artifact 内容只能取此结果”不符（`docs/sdd/plans/030/2026-10-29-report-publication-handoff.md:28,40`）。建议在该信任边界重新执行 canonical renderer 并与传入结果逐字段比较，或在 service 侧验证等价的可信 renderer provenance/digest；manifest 也应与 canonical renderer 的结果一致。

### [初审 P1；当前复审已关闭] 较新 legacy final message 没有 ResearchReport 行时，旧版本重放会覆盖 session link

位置：`backend/app/research/application/report_synthesis.py:1023-1044`。保护分支只遍历 `list_research_reports()`，且只有当更新版本对应的 activity message 被找到时才保留当前 `final_message_id`（`:1024-1039`）；否则无条件将 link 更新为正在重放的旧消息（`:1040-1044`）。legacy `deliver()` 可以写 Artifact、activity message 和 session link，但并不创建 canonical `ResearchReport` 行（`:1325-1415`）。

**独立探针：**先准备并发布 canonical 版本 N，再创建版本 N+1 的 legacy-style activity（没有 N+1 `ResearchReport` row），将 session `final_message_id` 指向它，然后重放版本 N 的 `prepare_canonical`。结果 `legacy_newer_link_preserved=False`，session link 被覆盖成旧版本 N 的消息。

现有测试 `tests/research/test_report_publication.py:408-443` 只建了较新的 canonical reservation/report row，覆盖了保护分支的正路径，但没有覆盖 legacy history 的兼容情形。应按当前 link/message 的独立可靠顺序判断，不要仅依赖 newer canonical row 才保护更新 link；同时添加“较新 legacy activity 无 canonical row”的回归测试。

## 已确认通过的边界

- **Owner/task/session/report/plan/version/reservation 绑定：通过。** helper 重读 owner-scoped task、session、report 和 request-key reservation，并验证 WorkItem 输入绑定，见 `report_synthesis.py:749-948`；测试对 task、owner、session、plan/version mismatch 做了无写入断言（`test_report_publication.py:188-244`）。
- **发布前不完成/不通知：通过。** prepare 创建 pending message、notification 为空，已有 completed message 在 unpublished 状态下被拒绝（`report_synthesis.py:1176-1209`；测试 `test_report_publication.py:150-186,247-263`）。finalize 先要求 durable `completed + published=true`，之后才把消息转 completed 并发 completed notification（`report_synthesis.py:1223-1235,1290-1316`）。
- **发布后的尾阶段恢复：服务层通过。** finalize 对 pending/completed 消息及幂等通知可重放；定向测试覆盖 publish 后通知失败，再次 finalize 补通知（`test_report_publication.py:371-405`）。发布后可用 prepare 补齐原版本消息/artifacts 的重放也有断言（`:299-330`）。该结论限于服务层调用可再次到达；完整业务恢复入口不在本轮审查范围。
- **Artifact hash 冲突及不可变内容：通过，但依赖上文指出的来源缺口。** 对已存 Artifact 会比较 hash、正文和末次 AgentRun ID（`report_synthesis.py:1066-1078,1246-1256`）。这证明已有值与本次调用方提供的值一致，不证明该值由 canonical renderer 生成。

## 未发布隔离的范围说明

服务层在 publish 前会有意创建 Artifact 和 pending message，并在 prepare 返回中给出 Artifact IDs；它自身不构成外部读取隔离。交接文件明确要求 API list/download 按 canonical `completed + published=true` 过滤（handoff `:41-42,51`）。本次未评审路由，因此此处不签署端到端 unpublished artifact concealment；该门禁需结合独立 routes review 才能关闭。

## 验证记录

| 检查 | 命令/探针 | 结果 |
|---|---|---|
| Publication 精确测试 | `/Users/wjh/ResearchAgent/.venv/bin/python -m pytest -q tests/research/test_report_publication.py` | 退出码 0；16 passed（1.19s） |
| Forged renderer 反例 | 临时目录 SQLite fixture；仅篡改传入 Markdown/HTML | prepare 接受，Artifact/message 写入 forged 内容；复现 P1 |
| Legacy 新 link 反例 | 临时目录 SQLite fixture；版本 N+1 只建 legacy activity/link、不建 ResearchReport，再 replay N | link 被覆盖回 N；复现 P1 |

