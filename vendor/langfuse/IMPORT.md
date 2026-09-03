# Langfuse v4.27.0 vendor import

本目录是 Spec 013 Task 07 的项目内二次开发基线。

- 来源：`/Users/wjh/opt/langfuse-src/langfuse`
- 版本：`4.27.0`
- 导入方式：保留源码、workspace 配置和锁文件；排除 `node_modules/`、`.next/`、`.git/`、缓存、日志、coverage、dist 与运行时 `.env`。
- 原始目录不是 Git 工作树；后续修改只允许在本项目的 `vendor/langfuse` 下进行，并通过项目 Git 提交追踪。
- 运行时环境变量不得复制进仓库；使用 `deploy/langfuse/env.example` 和外部 `.env`。

导入前校验与文件清单见 [`docs/sdd/plans/013/langfuse-v4.27-import-manifest.md`](../../docs/sdd/plans/013/langfuse-v4.27-import-manifest.md)。
