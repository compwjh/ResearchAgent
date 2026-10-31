# Spec 030 Task 10：自然语言 E2E 报告人工内容验收

- 评审日期：2026-10-31
- 评审对象：`20261031-natural-e2e/report.md`、`citations.json`、`12-matrix.json`、`13-paper-displays.json`；报告 ID `f8ccfb15-0670-47fc-af6b-d78ed23ea626`，Task ID `387a5090b27550c59de86adb415eb26e`。
- 机器结论：`10-report.json` 的 `quality_validation.status=pass`，CJK 2,920、paper 5、comparison 3、supported finding 5、invalid evidence 0、revision 0；报告状态为 `completed`。这只证明机器可确定的结构和计数条件，不代替下列人工结论。
- 来源核验：矩阵的 evidence 只有摘要 locator、digest 和 `evidence_level=abstract`，没有摘要 excerpt。使用主目录 `/Users/wjh/ResearchAgent/data/paper_search/state.sqlite3` 只读核对五条 catalog 摘要；五个被引用摘要的 SHA-256 均与 matrix digest 一致。另核对 `report.html` 的解析文本，五篇章节、关键结果数字、研究缺口及核心综合结论均存在。引用编号、paper ID 与 Evidence ID 的映射如下。

| 引用 | 论文（catalog 标题） | paper_id | 报告所引 Evidence ID |
|---|---|---|---|
| [1] | Dos and Don'ts of Machine Learning in Computer Security | `bf973b6a0943cb3d3165ec26e72e6915` | `evidence-44519614fb9a207caa0862a203a7951dc728b187eb383ae3b5c0f0233ad9f797` |
| [2] | Web Cache Deception Escalates! | `240837c172070c94fb76db82dc400a9c` | `evidence-162114ae22e5563f7fa35c8102de6ec04334fc17057a9a64324b85295dd6f12c` |
| [3] | “Like Lesbians Walking the Perimeter”: Experiences of U.S. LGBTQ+ Folks With Online Security, Safety, and Privacy Advice | `c74f345888764f1ac8def289ebee0ec4` | `evidence-23f75d4d8234d2d3aeb8f5c114c8aa98f4f6dd25d4cc8faab1c13045e27cff56` |
| [4] | Playing for K(H)eaps: Understanding and Improving Linux Kernel Exploit Reliability | `29e0052a154dc45edd232d6dfa40c76c` | `evidence-0b0300e7cee17e17aab40e4f01220e54bb6abde3b66c9ef5e5c02db92ee69336` |
| [5] | Stalloris: RPKI Downgrade Attack | `932b9f2a403b4a1433151236be9173f7` | `evidence-073dbc05e4d47239cb1081582bd8973e44df4a5345541d074396b1551a43b09b` |

## 五项人工语义 rubric

1. **逐篇忠实度：PASS。** `report.md` 第 15–17、21–23、27–29、33–35、39–41 行分别给出五篇有区分的研究方法、发现和来源限制，且引用映射见上表。逐篇与主目录摘要核对：ML 论文的 30 篇文献审计及实证演示、WCD 的 404 站比较与 Alexa Top 10K 测量、14 人 queer 半结构访谈、17 个内核漏洞利用评估及 14.87%/135.53% 结果、RPKI 的至少 47% 仓库与 20.4% IPv4 空间结果均与摘要相符。五篇均把摘要未交代的限制写为“来源未说明”，没有补写全文实验细节。该 PASS 仅判转述忠实，不表示选集符合认证主题。

2. **比较有效性：FAIL。** 第 45–52 行确实对五种方法和证据类型作出具体区分，并明确把它们称为“跨域类比”；但它没有比较请求中批准的“认证安全论文研究方法”维度。`request.json` 的原始目标列出了密码凭证、网页风险认证、指针认证、TLS 服务器身份和生物活体认证；`13-paper-displays.json` 则确认这五篇均为 USENIX Security Symposium 2022，但其主题分别是 ML 安全评估、Web 缓存欺骗、LGBTQ+ 安全建议、内核堆利用和 RPKI。只有 [2] 的摘要提及认证门后的内容作为 WCD 背景，研究对象仍是缓存欺骗，并非认证机制。报告第 22、46、49 行对此作了诚实限定，却也因此确认没有完成批准主题上的有效比较。特别是 RPKI 的 validation 是路由验证，不是用户登录认证；报告第 40、49、60 行没有把它混为密码认证。

3. **综合发现支持：PASS。** 第 56–60 行至少给出三条跨论文综合判断：选集中没有一篇以用户认证机制为主要对象且 WCD 仅相邻；五篇方法组合不能推出认证论文的方法偏好；摘要级证据不能升级为全文/部署结论。它们各自覆盖至少两篇不同论文，引用 [1]–[5]，并有可辨识的关系或边界解释，不只是逐篇发现复述或句尾堆 ID。矩阵的三个 claim（`claim-1cd4cea4523a21fb56eadf1124a72e9f0e7597b01dea72bc21a36114aa6b4059`、`claim-7bcc0058f4fed5c1116f914c621bb2e2e7d011dbc1f4e74b9568d8af0847e0fc`、`claim-99c9aa09ea3bb5ad47f5296c8580e91a0cbd7eebf4c0ebf9a28c03b42da040ff`）各关联五篇论文的摘要 Evidence。此 PASS 仅说明这些跨篇判断对当前五篇摘要有支持，不把它们变成认证研究发现。

4. **研究缺口与未知：PASS。** 第 64–67 行将缺口标为“推断性缺口”，把结论限制在所纳入摘要；第 65–66 行明确说明未报告不等于相关活动不存在。第 9、22、40、49、60 行也区分 Web 认证门背景、RPKI 路由验证与用户认证机制。对这五篇摘要未报告的观察窗口、代表性和部署细节，没有写成肯定的缺失事实。这里不对选集以外认证论文的纵向结果作有无判断，也不能把本段读成“认证领域没有纵向结果”。

5. **非填充内容：PASS。** 第 15–52 行有具体方法、样本/测量规模、数值结果和证据类型差异；第 56–67 行将这些事实用于限定跨篇推断和缺口。虽有若干范围提醒重复出现，但并非依靠重复模板、目录卡片或通用背景凑足字符数；逐篇信息和至少三条综合结论均可辨识。

## 人工总判定与范围说明

- **人工语义验收：FAIL（4 PASS / 1 FAIL）。** Task 10 规定任何一项人工 FAIL 即语义验收 FAIL。
- **研究主题交付：FAIL。** 这份报告忠实且克制地总结了五篇实际摘要，也准确说明它们大多与认证无关；但机器选集没有覆盖用户指定的认证机制类别，因而方法比较、主要发现与证据边界不能代表目标认证安全研究。WCD 与“认证门”一词的关联不等同于研究认证机制。内容忠实度 PASS 不得解释为目标已完成。
- **状态边界：** 本文只给出独立人工内容验收，不签署 Spec 完成或 `READY_FOR_USER`；本次没有重跑 API E2E、部署或十项 readiness 评估。当前报告的机器 `completed` 状态不改变上述人工 FAIL。

## 证据路径

- 报告正文与行号：`docs/sdd/plans/030/artifacts/20261031-natural-e2e/report.md`
- 报告机器质量结论：`docs/sdd/plans/030/artifacts/20261031-natural-e2e/10-report.json`
- 摘要级 evidence locator：`docs/sdd/plans/030/artifacts/20261031-natural-e2e/12-matrix.json`
- 引用到 Evidence ID 映射：`docs/sdd/plans/030/artifacts/20261031-natural-e2e/citations.json`
- 实际标题、venue、year：`docs/sdd/plans/030/artifacts/20261031-natural-e2e/13-paper-displays.json`
- 自然语言目标与认证类别：`docs/sdd/plans/030/artifacts/20261031-natural-e2e/request.json`
- 摘要原文（只读核查）：`/Users/wjh/ResearchAgent/data/paper_search/state.sqlite3`
