# Spec043 最终候选部署记录

当前候选 `a328932` 的运行时、全量、浏览器与部署验证已通过，tester 与 architect 已完成最终双签，Spec043 状态已由主会话同步为已完成。本文记录部署证据，不替代用户实际人工验收；`READY_FOR_USER` 不等于用户已通过。

## 当前候选 a328932（2026-10-22）

- 主会话核实旧 PID29261 是本项目8000服务后发送TERM，确认进程和监听均退出，再启动新候选；没有并发打开生产Qdrant。
- 实际命令：`PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh`；前台会话3216，监听PID55445，仅绑定127.0.0.1:8000。
- 真实GET `/api/ready` 返回 `ready=true`，jieba、Ollama tags、embedding、Qdrant均ready。主页/资源与实际全文消息接口由独立tester继续验证。
- 全量回归在唯一临时数据根执行，与生产服务分离；最终结果未产生前仍不标Spec完成。前端资源未改，期望styles59/map CSS10/map JS13，须由运行时报告确认。
- 本次仅本地部署，不push、不合并main；Reranker禁用和既有Langfuse不可用限制保持真实记录。
- 独立当前候选运行时复验已通过：ready/health/home和三个实际资源HTTP200，两张地图与全文历史可读；真实全文会话POST的SSE13事件正常以completed结束，sources仅目标document。证据见[当前候选运行时报告](final-candidate-runtime.md)。该报告的BLOCKED指其单独不能替代完整验收，非运行时失败；完整回归及浏览器签字另行汇总。
- 最终完整回归真实退出0：3224 passed、0 failed、2 skipped、67 subtests passed、5 warnings，时间09:19:28Z–09:31:55Z；两个skip是既有RUN_E2E guard，当前真实API/浏览器另行通过，未人工排除失败。
- 当前候选1440/375浏览器只读复核通过，两图21/17与21/18、全文历史v1/v2、普通详情关闭及无横溢均验证。移动列表立即快照命中180ms动画，延迟180–600ms后hidden且不拦截，非实现缺陷；见[浏览器报告](final-candidate-browser.md)。

## 候选 134dce4

- 分支：`codex/spec043-literature-map`；本地提交，未推送、未合并 main。
- 启动：`PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh`，前台会话 `57709`，监听 PID `24666`。
- 地址：`http://127.0.0.1:8000/`；地图入口 `/#literature-maps-view`。
- 启动后 `/api/ready` 首次返回 `ready=false`（Qdrant 预热中），随后真实返回 `ready=true`；jieba、Ollama tags、embedding、Qdrant 均 ready。不能以首次 HTTP 200 代替依赖就绪。
- 首页真实 GET 成功。实际 link/script 标签引用 `styles.css?v=58`、`literature-maps.css?v=10`、`literature-maps.js?v=13`；HTML 注释里的旧版本不是当前加载版本。
- SQLite schema 只读检查：普通 `sqlite3 -readonly` 返回无法打开文件，保留为检查失败；随后 URI `mode=ro&immutable=1` 读取 `schema_version` 为 `8`。此检查只证明主文件的 schema，不读取或宣称包含运行中 WAL 的最新业务数据；业务接口另行验收。
- Reranker 显式禁用，按已有 RRF 降级运行，不宣称精排可用。Langfuse 的既有外部依赖限制不计作已通过。
- fresh map API E2E 已在候选 `1a3ff26` 完成；Task07 375/390/1440 浏览器复验已 PASS。`map_regression_preflight` 首轮独立隔离回归已 BLOCK（3191 passed / 18 failed / 14 skipped / 67 subtests / 5 warnings；提权浏览器诊断 16 passed 不能替代全量）；运行中 job 的 stop 保留成果与进程重启恢复已有真实 PASS 证据。root 正在分派同范围修复与重跑，最终部署与签字仍未完成，不具备最终收口条件。

记录由主会话纯文档落盘；服务再次停止/重启必须追加实际状态，不沿用历史 PID 声称在线。

## 134dce4 真实验收后暂停

历史候选 `134dce4` 的 fresh map `35a56c6f2da84fca85fc3c21dfa0055c` 首次创建因 `SEMANTIC_SCHOLAR_RATE_LIMITED` 产生 0 节点，API 门禁 BLOCK；该失败和当时 global-nav 遮挡、390/桌面未跑的证据保留，不覆盖后续候选结果。后续 `1a3ff26` 受控 retry 已完成真实 20 节点/11 citation/5 similarity、preview 45→apply1→21节点/17边，Task07 浏览器 375/390/1440 已 PASS。证据分别见 `live-api-e2e.md` 与 Task07 `browser-e2e.md`。

主会话核实 PID24666 为本次8000 uvicorn 后发送 TERM，暂停服务以修复静态资源；不能继续声明8000在线。原失败证据与运行数据均保留，未启动全量回归、未推送远程。

## 候选 1a3ff26 重新部署

- 独立前端复审 GO，P0/P1/P2 均为0后，本地提交导航关闭修复；未push或合main。
- 命令仍为 `PORT=8000 RERANKER_ENABLED=false ./deploy/start.sh`；前台会话62307，监听PID26999。
- `/api/ready` 先为false（embedding预热），后为true，四项warmup均ready；首页GET成功。
- 真实资源标签为styles59、map CSS10、map JS13；旧版本HTML注释不计。
- 真实375/390/桌面浏览器复验和原失败 job 的一次受控 retry 已由独立 tester 完成并记录 PASS/partial 边界；`map_regression_preflight` 首轮全量已独立隔离执行并 BLOCK，运行中 job stop/restart 也已由 live API 完成；root 正在分派同范围修复与重跑，最终退出码/数量和最终部署仍待回填。

## 同候选运行中作业重启补验

主会话通过真实POST创建临时地图e567077ddacc495dad8773c8018bc13c、作业ef5723506184480687a84495d334caff（HTTP202），保存创建响应、job与events后，job真实为running/discover、accepted_count=0、provider_request_count=0。随后TERM已验证PID26999，确认旧进程完全退出，才以同一命令/同一候选1a3ff26重新启动。

当前前台会话2490、监听PID29261；预热后ready=true。真实结果已落盘于`runs/20261021-155409-1a3ff26-restart-recovery/evidence.json`：同一 map/job 在 TERM→重启后继续，events 1–8 单调、20 node ID 与 external ID 均无重复，最终 20 nodes/23 edges，结论为 restart recovery PASS（provider partial warning 保留）。stop 也已在 retry artifact 的递归 `temp_result` 中真实通过：job `3e5ba79d825349448bfe5852b7e1a747` 从 running/references 20 nodes 经 POST stop 200 到 stopped，node 20 保留。现有正式验收地图及KB未删除；最终全量由另一tester使用临时隔离数据执行，与此重启测试分离。
