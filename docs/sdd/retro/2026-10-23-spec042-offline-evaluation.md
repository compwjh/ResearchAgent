# Spec042 离线评测续作复盘

## 当前边界

实现候选为`145f9d6`，只影响离线评测包、兼容脚本与相应测试；不改聊天/论文/地图业务链路，无新前端或业务API。最终独立验收双签通过，Spec042已完成，详见正式验收报告。Spec043的8000服务保持运行，Spec032不恢复。没有push或合并main。

## 已证实问题与处理

1. **实验脚本不是交付工具。** Task02/03已有可行性与构造记忆探针，但正式runner遗漏上下文、双报告、错误退出和精确写回验证。复用现有包增量补齐CLI/runner/report，不另建评测框架。
2. **只检查初始URL不能证明离线。** urllib默认代理/重定向可能绕过loopback约束；统一显式无代理、拒绝重定向的HTTP传输。score POST保持单次，不能把读重试策略套用到写入。
3. **正常路径通过不能替代错误契约。** 独立评审与红测发现缺上下文记录被丢弃、错误payload泄漏、人工真值声明旁路、双文件替换失败不一致。修复后分别独立复验，历史NO-GO保留。
4. **真实API必须核对提供方实际契约。** v1 score列表不支持所用traceId过滤，首次真实运行写入成功但canonical验证失败；不能凭旧同名分数或后续人工回查看作CLI成功。改用既有exact-ID读取并继续校验ID/name/trace/value。
5. **测试毫秒退避不能当生产异步可见性窗口。** 原验证只等0.15秒，真实异步落库超出窗口。生产改为最多6次只读回查、1/2/3/4/5秒等待；测试替换时钟而非把生产等待缩短。权限/解析/字段不匹配立即失败，不盲目增加重试。
6. **服务交接必须明确进程归属。** 子任务前台会话停止后，历史PID与HTTP200不代表当前在线。主会话接管持久会话并重新探活；子Agent不再清理根持有的服务。
7. **工作目录也是数据边界。** 错误ClickHouse cwd生成仓库根access/preprocessed_configs；确认不被活动进程使用后，移至唯一临时目录可恢复归档，避免潜在敏感运行数据进入Git。未动专用数据库目录。
8. **全量偶发超时必须保留证据。** 新候选一次全量仅390px浏览器点击稳定性超时；精确独立重跑3次通过，未改代码/断言或force点击，不据此无证归咎环境。仍需相同候选完整回归通过才能收口。

## 已完成的真实结果

- 旧候选`6f644bc`完整回归3325通过，但真实score验证失败，不能交付；原失败报告与已写score均保留。
- `145f9d6`新run真实CLI退出0，9b判官3次、本次score POST一次、canonical exact验证通过，报告JSON/Markdown完成。原先失败run没有被覆盖或重放。
- 真实记忆样本缺上下文时SKIPPED/no_prior_context，无judge或score写入；构造gold不当作人工标注，human_agree_rate仍未评估。
- 事实入口：`docs/sdd/plans/042/runs/`、`final-regression-report.md`、`runtime-failure-diagnosis.md`、`task-04-integration-review.md`。

## 收口要求

最新完整回归已通过：145f9d6为3335 passed/0 failed/2合法skip/67 subtests/5 warnings。原生浏览器受锁屏影响后，采用headless Playwright正常登录既有Langfuse并只读核对同一trace的chat_quality/1.0；不篡改页面、不要求用户解锁、不声称DOM显示score UUID。人工步骤已对应真实入口，tester签READY_FOR_USER、9/10+1N/A，architect签GO，Spec完成状态与台账已同步。旧运行记录、缺人工标注与旁路token遗留不静默删除；不要求用户替Agent诊断失败。
