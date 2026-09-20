# Task 02：复用审计与全文证据协议门

> 关联：[Spec 029](../../specs/029-research-fulltext-acquisition.md) ｜ 索引：[README](./README.md)
> 依赖：Spec027/028 基础合同已完成、Spec029 已进入实施；被依赖：Task03–06；当前状态：`已完成（NO-GO）`

## 一句话目标

逐项证明 Research Task 能复用既有下载、批量导入、文档索引、RAG 和切片定位，并冻结证据升级合同。

## 完整分派 Prompt

```text
角色：architect + backend-tester；读取 Spec029、本 Task、Spec015/018/021 相关接口和 Research Task 选集模型。
允许修改：plans/029/artifacts/task-02/**、tests/test_spec029_reuse_contract.py。
禁止业务实现、真实下载、真实数据变更、复制模块、push/merge/reset/stash/clean。
验证：候选→导入快照→document_id→chunk citation 的固定样本；重复、部分失败、删除文档和证据降级；git diff --check。
完成状态：为每项能力列出现有入口、缺口、调用合同和 GO/NO-GO。
报告：artifacts/task-02/reuse-evidence-gate.md；返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 若任何关键能力需要第二套实现则 NO-GO，优先抽取 facade。
- 本 Task 无业务回滚；产出复用矩阵、合同测试与报告。基础设施复用 GO，但 Research 侧审批、文档映射和全文证据桥接为 NO-GO，交给 Task03。

## 变更日志

- 2026-09-12：创建复用与证据 gate。
