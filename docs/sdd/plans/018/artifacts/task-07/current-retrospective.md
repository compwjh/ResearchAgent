# 2026-10-06 Spec018 补验复盘

纯文档由主架构师落盘；生产实现、测试与复审分别由子 Agent 执行。此次临时模型分派不形成长期规则。

## 结果

候选 9a9733f 全量 exit 0：2893 passed、3 skipped、67 subtests，coverage 81.7914%。新 Markdown/PDF 均真实上传 201，v1/v2 ready、anchors 非空；首页和健康检查成功。独立架构师签字见 `docs/sdd/reviews/018-acceptance-review.md` 当前补充节，人工步骤见 `manual-acceptance.md` 第 6 节。

## 问题与修复依据

- 分支整合带入启动恢复 marker，但冻结元数据 schema 未注册该字段，导致整库校验失败及新上传 MIGRATION_INPUT_INVALID。修复同时覆盖迁移保留与严格日期/key 校验，而非删除旧数据或放开 additionalProperties。
- 来源预检应使用实际 registry；应用层入口统一导出 Semantic Scholar 客户端，API 不直接越层导入 infrastructure。
- 测试目录移动和旧 Worker 参数留下陈旧断言。按现行领域契约改测试并保留真实失败记录，没有降低生产身份/provenance 验证。
- 部署不能只看 ready 布尔值，必须分别核验 embedding、Qdrant、generation、SQLite schema 与实际静态版本；重启后四项 warmup ready。

## 不冒充完成的事项

- 两份新样本不能证明旧资料库约 40 条记录全部迁移或重建完成；现有用户资料未清空。
- 10,000 切片 Chromium 性能样本为合成规模测试，真实网络清单全量预取仍需后续优化。
- Langfuse collector 3000 不可用、reranker 本轮显式关闭；未声称观测与 rerank 已验收正常。
- 人工准备度 9/10；本轮浏览器实读列表和入口，未重复完整文件选择器上传及双向点击，不能冒充新 UI E2E。

## Git 与协作

main/Spec042/startup 分支新增内容已整合；旧备份分支的实现已被新提交覆盖，保留备份而不普通合并回引旧代码。最终 main 推送与部署版本记录见 `deploy/evidence/20261006-integration/README.md`。
