# Spec029 Task06 运行时 Smoke

日期：2026-09-16（Asia/Shanghai）

## 启动

- 命令：`PORT=8500 RERANKER_ENABLED=false ./deploy/start.sh`
- 地址：`http://127.0.0.1:8500`
- 结果：FastAPI 启动完成，Research 页面真实加载；Reranker 按配置禁用。

## 浏览器证据

真实浏览器刷新 Research 页面后确认：

- 研究任务列表、详情和创建表单均可访问。
- 实际加载 `/assets/app.js?v=50`、`/assets/research-tasks.js?v=4`。
- 页面 DOM 包含全文获取区域 `research-acquisition-section`，可由任务详情按候选快照显示。
- 页面没有新增 JavaScript 错误。

## 历史未执行项（2026-09-16）

真实公开 PDF 下载/导入/索引、浏览器候选增删与显式确认、登录等待/失败重试、全文证据升级和删除重验证在初始 smoke 中尚未执行；以下为收口复验。

## 收口运行时复验（2026-09-17）

- 8500 最新代码启动后 `/api/health` 返回 HTTP 200。
- Research 任务 `3eee288b8e5a512dad3dad524d787c63` 详情返回服务端 `search_id=fd6d1c7892fd49f29ea4682393530594`；preview HTTP 200。
- 显式确认创建批次 `67eec23f-d5e3-49ef-b380-acf8313fe8db`，逐篇状态 `completed`，link 指向文档 `bfaf307d22a145b88fbf9e200df869b5`。
- v1 inspection manifest `ready/verified`，138 chunks、0 unmapped；evidence upgrade HTTP 202 返回 `fulltext`、5 个 chunk locator、page 1–12、source hash 和 generation。
- 用户已完成人工验收并明确通过；本次未人为制造登录失败或重试样本，失败恢复仍由既有 Task03/05 合同覆盖。
