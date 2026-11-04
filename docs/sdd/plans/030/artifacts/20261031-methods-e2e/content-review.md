# Spec 030 Task 10：Security Research Methodology 报告人工内容验收

- 评审日期：2026-10-31
- 对象：`20261031-methods-e2e/report.md`、`report.html`、`citations.json`、`12-matrix.json`、`13-paper-displays.json`。
- 范围：仅判定最终报告的五项人工语义 rubric；不重跑 API E2E、部署或 readiness 评估，不据此签署 Spec 收口。
- 机器结论：`10-report.json` 为 `completed`，`quality_validation.status=pass`；CJK 3,020、5 篇、4 项比较、5 条 supported finding、无 invalid evidence、无改写。`download-verification.json` 中 Markdown、HTML、citation manifest 均 HTTP 200 且哈希匹配；再次计算本地产物哈希也全部匹配。以上为机器/产物完整性结果，不替代人工判定。
- 来源核验：`12-matrix.json` 提供5条摘要级 Evidence locator，未内嵌摘要 excerpt。对照主目录 `/Users/wjh/ResearchAgent/data/paper_search/state.sqlite3` 的 catalog 原文，五篇摘要 SHA-256 均与 locator digest 一致；`13-paper-displays.json` 的标题、venue/year 与同一批 paper ID 对应，均为 USENIX Security Symposium 2022。

## 引用与 Evidence 映射

| 引用 | 论文 | paper_id | Evidence ID |
|---|---|---|---|
| [1] | Playing for K(H)eaps: Understanding and Improving Linux Kernel Exploit Reliability | `29e0052a154dc45edd232d6dfa40c76c` | `evidence-a3f09719df18a191bc77e87837839c7bf09fea47274054317da1ec71752b2902` |
| [2] | Web Cache Deception Escalates! | `240837c172070c94fb76db82dc400a9c` | `evidence-0f150b18863b9a2e845b4a90d491f14d8f34579197f0a4ea6af65fe9361bc7f5` |
| [3] | Dos and Don'ts of Machine Learning in Computer Security | `bf973b6a0943cb3d3165ec26e72e6915` | `evidence-61d97a5a835dbda58d9796823100fd242ad835b0d7f01828c009e128a460494f` |
| [4] | On the Security Risks of AutoML | `7d30bac1c3eb69f0e3dcbdf45ea5c261` | `evidence-8e875061c70b906fd85125969f442d2a453112bf2be6c28545a239c7b4270134` |
| [5] | Hiding in Plain Sight? On the Efficacy of Power Side Channel-Based Control Flow Monitoring | `506030dfdf859855c4ac72a6b64079cb` | `evidence-c27a4aa0f076f3e4a49b69cc20e4d42b3dbc291e5ccb277076b8f22b76c27fd3` |

## 五项人工语义 rubric

1. **逐篇忠实度：PASS。** `report.md` 第 15–17、21–23、27–29、33–35、39–41 行逐篇区分方法、结果与限制，证据见上表。与五篇摘要核对： [1] 专家访谈、17 个真实内核堆漏洞利用评估、利用模型和 14.87%/135.53%/67.86% 结果；[2] 页面同一性检查、缓存头启发式、404 网站比较、Alexa Top 10K 测量及 1188 个脆弱网站；[3] 30 篇论文研究与实证分析；[4] 10 种 NAS 方法比较及经验/分析证据；[5] 恶意软件构造、ARM 微控制器和代表性程序上的攻击评估。摘要没有展开的逐篇限制标作“来源未说明”，没有补写全文实验细节。

2. **比较有效性：PASS。** 第 45–55 行不止并排列举论文：第 46 行说明不同评估对象、样本规模及缺少共同抽样/统计效力依据为何不能排出代表性或证据强度；第 49 行比较研究方法组合；第 52 行对照计数、百分比、鲁棒性等测量单位，并说明缺少统一指标、不确定性与重复次数时不能换算效应；第 55 行比较专家知识、自动化测量和元评估三种证据生成路径及其未校准限制。所比较的对象都是实际研究设计，符合已批准的广义“实证评估方法”维度。报告也将 [3] 标作直接的方法学研究，将其他论文作为不同安全领域的实证评估实例，没有把“安全论文”本身当作相关性的充分理由。

3. **综合发现支持：PASS。** 第 59、60、61、63 行至少四条跨论文推断分别总结设计多样性、证据类型与指标不可直接合并、评估假设需要检验、样本规模不等于证据强弱；各条均引用至少两篇不同论文。例：第 61 行引用 [3][4][1]，将 ML 评估陷阱、NAS 脆弱性分析与内核专家意见和实验不一致结合，得出有限的跨领域方法学判断；第 59、60、63 行各引用五篇摘要。矩阵中逐篇 claim 是单篇事实，但人工判定依据是报告正文的跨篇推断及其多篇 citation 映射，不以机器 finding 计数代替语义判断。

4. **研究缺口与未知：PASS。** 第 67–70 行把缺口限定为摘要信息粒度，并区分推断性缺口与作者陈述的开放问题。第 67 行明确保留 [3] 对过去十年、30 篇顶级安全会议论文的研究范围，只指出其他列举论文的时间粒度未说明；第 68–69 行说明样本选择、统一指标和统计不确定性未在摘要展开，没有断言这些工作未做。报告没有把既有的十年文献审计说成不存在，也没有把报告未说明的结果升级为肯定事实。

5. **非填充内容：PASS。** 逐篇段落包含不同方法、研究对象、规模或结果；四个比较段分别谈对象/规模、方法组合、测量单位和证据生成路径；综合发现和缺口在这些事实之上限定可比性。部分结论互有关联，但不是通用背景或模板重复来凑字数，内容具有可辨识信息。

## 主题覆盖说明与总判定

- **方法论主题相关性：PASS。** 选集中有直接的方法学评估陷阱研究、文献方法审计、网站测量、受控/实证攻击评估、专家访谈及分析模型；不同领域正是请求明确允许的比较范围。论文 [3] 的方法审计与其余实证评估设计形成可解释的比较对象。
- **用户研究覆盖边界：** 现有摘要中明确的人类参与研究是 [1] 对内核安全专家的访谈；它可作为专家访谈/人类参与的定性证据，但不是终端用户研究。报告没有把它夸写为用户体验研究。若“用户研究”必须狭义指终端用户，当前选集对此子类覆盖有限；这不改变五项 rubric 中有证据支撑的比较 PASS，但交付时应保留此范围说明。
- **人工语义验收：PASS（5/5）。** 五项 rubric 均通过；逐篇来源忠实，比较解释了方法关系和可比性限制，综合发现由多篇有效摘要支持，未知和缺口没有否定已报告结果，内容非填充。
- **结论边界：** 本文只签署人工内容 rubric；不表示 Task 10 的 API E2E、人工步骤、十项 readiness 或 Spec 收口已完成。机器 `completed/published` 状态不能替代这些独立门禁。

## 证据路径

- 自然语言研究请求：`docs/sdd/plans/030/artifacts/20261031-methods-e2e/request.json`
- 最终报告与行号：`docs/sdd/plans/030/artifacts/20261031-methods-e2e/report.md`
- 报告机器质量字段：`docs/sdd/plans/030/artifacts/20261031-methods-e2e/10-report.json`
- 摘要 Evidence locator：`docs/sdd/plans/030/artifacts/20261031-methods-e2e/12-matrix.json`
- 论文标题、venue/year：`docs/sdd/plans/030/artifacts/20261031-methods-e2e/13-paper-displays.json`
- Citation 到 Evidence ID 映射：`docs/sdd/plans/030/artifacts/20261031-methods-e2e/citations.json`
- 三个下载文件的状态与哈希：`docs/sdd/plans/030/artifacts/20261031-methods-e2e/download-verification.json`
- 摘要原文核对（只读）：`/Users/wjh/ResearchAgent/data/paper_search/state.sqlite3`
