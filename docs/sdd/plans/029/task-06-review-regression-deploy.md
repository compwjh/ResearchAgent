# Task 06：最终评审、回归、部署与复盘

> 关联：[Spec 029](../../specs/029-research-fulltext-acquisition.md) ｜ 索引：[README](./README.md)
> 依赖：Task02–05 完成；当前状态：`已完成`

## 一句话目标

完成下载/导入/知识库复用审计、唯一全量回归、真实公开 PDF 证据升级、部署与复盘。

## 完整分派 Prompt

```text
角色：双端 reviewer/tester、跨端 tester、architect；读取 Spec029、Task 报告和实际 diff。
允许修改：reviews/029-*.md、plans/029/artifacts/task-06/**、对应 retro；修复退回开发 Task。
禁止绕过登录、安全规则或用户确认；禁止 push/merge/reset/stash/clean。
验证：复用矩阵、固定样本、真实公开 PDF、全文切片定位、相关安全回归、唯一全量回归、浏览器、部署。
完成状态：三份评审与签字齐全，真实环境失败有明确复验步骤。
返回固定交接字段。
```

## 主 Agent 校验、风险与产出

- 任一重复实现、安全语义退化或虚假全文证据均阻塞。
- 产出评审、验收、复盘和部署证据；已验证默认 generation reader、持久化 `search_id`、公开 PDF 导入、v1 检查清单和全文证据升级。真实用户登录等待和失败重试仍由既有批量导入契约覆盖，不在本次成功样本中人为制造失败。

## 执行结果

- 需求、技术和验收评审均已更新为通过；Task06 定向回归：`35 passed`（Spec029）与 `80 passed / 5 subtests`（跨 Spec 受影响集合），退出码均为 0。
- 真实运行时：8500 服务健康 HTTP 200；搜索任务 `5054282f61f8417a987b44156188f0a0` 冻结 227 条 USENIX 目录结果（DBLP 跳过导致整体 partial，不影响 USENIX 结果）。
- 真实 Research 链：任务 `3eee288b8e5a512dad3dad524d787c63` 的服务端 `search_id` 为 `fd6d1c7892fd49f29ea4682393530594`；预览 HTTP 200 且无下载副作用；确认后批次 `67eec23f-d5e3-49ef-b380-acf8313fe8db` 完成，候选 `b839eca81d1c3e4d` 映射文档 `bfaf307d22a145b88fbf9e200df869b5`。
- 真实全文：索引任务 `06ea5c95e4ae40fe9e670379df68a1fb` 生成 v1 manifest，`status=ready`、`source_hash_state=verified`、`mapped_count=138`、`unmapped_count=0`；证据升级返回 `to_level=fulltext`、5 个真实 chunk ID、页码 1–12、source SHA-256 和 generation `38efa91a33154fd097c61d1c745d408f`。
- 最终全量回归：`COMPACTION_SUMMARY_MODE=rule .venv/bin/python -m pytest -q` → 退出码 0，`2486 passed, 1 skipped, 5 warnings, 67 subtests passed in 153.00s`。
- 最新代码已部署至 `http://127.0.0.1:8500`，启动命令为 `PORT=8500 RERANKER_ENABLED=false ./deploy/start.sh`。远程核对显示 `origin/main` 已是本地 `main` 的祖先，GitHub main 无待合并提交；未合并的 `origin/feat/startup-readiness` 是无关的 Spec018 文档分支，未越界合并。

## 变更日志

- 2026-09-12：创建最终收口 Task。
