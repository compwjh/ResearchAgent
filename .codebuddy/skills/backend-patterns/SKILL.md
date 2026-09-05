---
name: backend-patterns
description: 本项目后端（Python/FastAPI/SQLite/Qdrant）实现模式：分层边界、store 规范、并发领用、UTC 时间、安全复用、常用验证命令。backend-dev / backend-reviewer / backend-tester 必读。
---

# 后端实现模式

## 分层

`backend/app/api/routes.py`（HTTP 装配）→ `backend/app/services/`（业务）→ `backend/app/domain/`（纯数据契约）。
**领域层禁止 import FastAPI / httpx / Qdrant**，以保证可单测、可迁移。

## SQLite store 规范（以 `services/paper_discovery_store.py` 为范本）

- 连接固定 `PRAGMA journal_mode=WAL`、`foreign_keys=ON`、`busy_timeout=5000`，**不另建连接层**。
- 版本存 `schema_meta` 单行表（表达式唯一索引 `ON schema_meta((1))` 防多行）。
- 升版流程：**单事务内**先建表/加列 → 再升 `schema_meta.version`；DDL 全用 `IF NOT EXISTS`、加列用 `PRAGMA table_info` 判存在，保证**幂等**；任一失败**整体回滚**。
- 并发领用（如 `acquire_fetch_unit`）用**单条条件 UPDATE + `cursor.rowcount`** 判定成功，禁止 SELECT-then-UPDATE（存在检查与写入之间的竞态）。租约过期（`lease_expires_at < now`）允许被其他 owner 恢复领取。
- 时间统一 `_utcnow()`（RFC3339 UTC，带 `Z`）；UTC 字符串可直接字典序比较。
- 冻结结果类的写入用 `ON CONFLICT ... DO NOTHING`，保证不可改写。

## 安全

URL 校验与下载一律复用 `paper_download_security.py` + `paper_download.py`，不重写、不旁路。

## 常用验证命令

```bash
.venv/bin/python -m py_compile <改动文件>
.venv/bin/python -m pytest -q tests/<相关后端测试>
cd /Users/wjh/ResearchAgent && git diff --check
```
