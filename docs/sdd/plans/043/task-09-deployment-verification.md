# Task09 部署验证（阶段记录）

- 日期：2026-10-24（Asia/Shanghai）；执行者：主会话，仅服务编排与文档记录。
- 候选：`codex/spec043-map-interaction`，基线提交458da1b加本轮未提交改动；不得将该基线SHA单独冒充本轮代码版本。前后端独立代码复审GO后部署；最终验收/提交仍待完成。
- 部署时`git diff -- backend frontend`的SHA256为`2eb504c210d22977c3614d558653766903276c8703de3f6ebe471f37a61538f2`，FastAPI PID为86241；后续代码改动须重新绑定候选。
- 一致备份：`/private/tmp/researchagent-map-predeploy-_f96bwpp/`，含文献地图库schema6和memory schema8；由应用同一SQLite驱动backup，未重建/删除用户库。
- 启动：`HOST=127.0.0.1 PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh`，由主会话保持前台进程。
- 地址：http://127.0.0.1:8000/#literature-maps-view ，仅loopback。
- 实测：`/api/ready`返回ready=true（jieba/Ollama标签/embedding/Qdrant均ready）；首页与`/api/literature-maps`均200；实际HTML加载地图JS v16、地图CSS v12。
- 旧进程66643正常退出；stop脚本与旧前台清理同时删除PID文件，stop报告unlink不存在并退出1。随后确认8000已释放，新进程成功启动且上述接口通过；不把脚本退出1改写为0。
- 限制：Reranker继续关闭；Langfuse先前未运行，不声称观测可用。未执行本轮完整回归，真实API与浏览器验收进行中；知识库导入失败仍按用户要求最后处理。

## 后续

在此记录追加真实API/浏览器、导入缺陷修复后的再次部署及最终签字，不以旧候选证据替代当前版本。

## 最终修复候选阶段部署（2026-10-24）

- 前端JSv18的可读字号/KB202诊断与arXiv指定ID作者缩写修复均获独立GO，未放宽0.80阈值、ID/标题/年份/PDF安全门禁。
- 启动前确认8000无监听，未终止其他进程；新备份`/private/tmp/researchagent-map-final-backup-fpwe7k2w/`保留最新地图与memory库。沿上述命令启动，PID99033，主会话会话52460保持存活。
- 实测首页200、ready=true，实际HTML加载地图JSv18；`git diff -- backend frontend`的SHA256为`09c5e9515debce8d1824fe0268d60ead6ddd5be5e62282264d272338d4d44662`，仍是未提交工作树候选，不用旧SHA冒充本轮版本。
- 原失败节点的真实入库复验、v18浏览器窄验正在独立执行；最终全量回归与验收签字仍未完成，不标Spec已完成。

## canonical发布接缝修复部署与全文真实闭环

- 前端JSv18和arXiv缩写修复基础上，`knowledge_base/application.py` canonical mapping保留修复获独立GO；重启时确认原应用PID99033，旧进程正常退出但重复清理PID文件导致stop报告退出1，未误终止其他服务。
- 新应用PID2252，主会话会话94551，8000仅loopback，ready=true；生产源差异SHA256为`6fda3d07731f9bd820653faac22ddb9fb615fe22c393ac69e0560fe968feb059`，仍为未提交工作树候选。
- 真实入库成功后，通过原reindex接口唯一一次恢复v1，未手写来源哈希/manifest或放宽门禁；doc `ae3a1c3f7ee746bba031b06306ff3230` verified、实际PDF与indexed SHA256一致、manifest ready/100%，fullready=true。
- 唯一全文分析 `04ff00a37f8247379878ecaf7fc6703e` 完成，非空592字符、5条引用均绑定目标doc。证据见 `task-09-runs/20261024-210815-task09-full-analysis-v1/evidence.json`。这不替代最终全量、覆盖率或验收签字。

## 本地提交与最终交付绑定

- 实现与证据已本地提交为`58ab86f`（Refs: spec-043）；验证时的基线458da1b加工作树身份作为历史保留，不回写成当时已提交。
- `git diff 58ab86f -- backend frontend`为空；`git diff 458da1b 58ab86f -- backend frontend`的SHA256仍为`6fda3d07731f9bd820653faac22ddb9fb615fe22c393ac69e0560fe968feb059`，与独立双签、最终回归和已部署源一致；提交未改变运行源码，不重复重启。
- 交付前再次实测ready=true、首页200。最终全量3384 passed/0 failed/2合法skip/67 subtests/5 warnings，exit0、覆盖率82.38%；tester与architect双签READY_FOR_USER，10/10。Spec/Task/README/状态台账已同步完成，人工步骤见`task-09-manual-acceptance.md`。
- 仅本地提交，未push/合main；来源限流partial、无摘要跳过、RRF降级及Langfuse既有未运行限制均保留，不承诺所有外部论文随时可下载。
