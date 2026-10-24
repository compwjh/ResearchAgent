# Spec043 Task09 修复复盘（收尾候选）

主会话纯文档记录，非独立评审；最终全量与签字未出结果前不据此标记Spec完成。

## 已验证的事实

- 用户确认Q1–Q15后分端实施；子代理本轮临时Luna max，没有修改长期模型配置。
- 标签/引用半径/鼠标锚点、持久自动摘要队列、分析历史/全文提示与提问草稿均经独立代码复核；真实fresh地图20节点中18篇摘要成功、2篇缺摘要安全跳过。S2引用补全限流保留partial，不冒充完整来源成功。
- 浏览器手动重新生成造成的合法v2曾被API验收误判为自动重复。核对请求时序与job来源后纠正，保留原失败/纠正记录，没有为误判保留额外后端改动。
- 原失败论文`1809.07041`：作者缩写T.Mei/Tao Mei使原严格作者得分0.75而被拒，修复限定已确认ID路径的唯一缩写匹配，0.80阈值及其他安全门禁保持。
- 真实入库暴露canonical来源哈希在旧记录适配时丢失；保留canonical mapping并复用严格发布路径，经合法reindex恢复verified来源和manifest，新的全文分析生成592字符与5条目标文档引用。
- 首轮全量3383 passed/1 failed/2 skipped/67 subtests，覆盖率82.41%通过；唯一失败是已改源码对应的冻结清单哈希过期。按既有维护规约只更新文件/汇总哈希，定向验证后重跑最终全量，首轮日志保留。

## 后续同类任务的执行要点（复盘，不新增全局规则）

1. 自动与手动分析验收使用明确动作记录/不同实体，跨Agent共享实体时先协调写操作，不能只凭相同source version认定重复。
2. 队列测试覆盖实际唤醒、provider异常、执行器公平性、存活租约回收与关闭竞态，不能把“字段存在”当作行为已实现。
3. 字号应测量真实CSS像素，作者样本应覆盖长名、已有et al.与缩写；合成小图通过不替代真实页面。
4. 下载、indexed、来源verified、manifest ready、全文分析完成是不同状态；验收逐项闭环，不能越过安全门禁或手写来源证据。
5. 修改受冻结清单管辖源码时同步核对维护规约和写入口登记，减少最终全量只因快照失配而返工。

## 证据入口

- [Task09](../plans/043/task-09-map-interaction-analysis.md)
- [最终回归](../plans/043/task-09-final-regression.md)
- [真实导入与全文](../plans/043/task-09-import-api-e2e.md)
- [人工案例](../plans/043/task-09-runs/20261024-211542-task09-browser-full/task-09-manual-acceptance.md)
- [部署验证](../plans/043/task-09-deployment-verification.md)

## 最终收尾

最终完整复验3384 passed/0 failed/2合法skip/67 subtests/5 warnings、exit0，覆盖率82.38%。tester与architect独立双签READY_FOR_USER（10/10），已部署8000JSv18，Spec/Task/README/台账同步完成；仅本地提交，不自动push/合main。历史失败与外部来源partial保留，不把用户尚未实际执行的人工验收写成已通过。
