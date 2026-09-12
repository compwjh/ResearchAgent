# Task 05：新增两个编排 Skill，旧的保留并标记遗留

> 关联：[spec-032.1](../../specs/032.1-usenix-skill-decoupling.md) ｜ 索引：[README](./README.md)
> 依赖：任务 01（04 提供 `fetch_paper_detail`）；当前状态：`已完成`

## 一句话目标

新增 `usenix-catalog-orchestration` 与 `usenix-download-orchestration` 两份**纯编排协议** Skill；
两份旧 Skill **原样保留**并标记遗留，使新旧并存、后续迁移。

## 执行结果

### 产出物

| 文件 | 说明 |
|---|---|
| `.agents/skills/usenix-catalog-orchestration/SKILL.md` | **新增**。检索编排协议，frontmatter `tools: [search_paper_catalog, fetch_paper_detail]` |
| `.agents/skills/usenix-download-orchestration/SKILL.md` | **新增**。下载导入编排协议，frontmatter `tools: [download_and_import_paper]` |
| `.agents/skills/usenix-accepted-papers/SKILL.md` | 保留，frontmatter 加 `status: legacy`，正文顶部加遗留提示与指向新技能的说明 |
| `.agents/skills/usenix-paper-catalog-search/SKILL.md` | 同上 |

### 新 Skill 的编写原则（防污染回归）

**只写编排协议**，六段式：定位（编排层 vs 执行层）、适用范围、输入契约、编排决策点、
固定发现链/下载链、硬边界与停止条件。

**明确不写**：研发分派纪律（文件数/行数、回传字段）、研发台账回填（Task、task-ledger）、
Git 禁止项、不存在的角色名（如 `junior-dev`）、对 spec/plan 研发过程文档的引用。

**保留两个 Skill 的拆分边界**——「搜索阶段禁止 PDF」是硬安全隔离线，未合并为一份。

### 遗留标记的落点

- frontmatter `status: legacy`：`scanner.py` 新增 `_is_legacy()` 读取，经 `SkillRecord` →
  `SkillSummary` 透传到 `GET /api/skills`（未改 `routes_skills.py`，`asdict` 自动包含）。
- 实测 API 响应：两个旧 Skill `legacy: true`，两个新 Skill `legacy: false`，列表仍返回全部 4 条。
- 前端：`app.js` 新增 `buildLegacyBadge()`，在列表与详情显示「遗留（待迁移）」；
  `index.html` 版本 `?v=39 → ?v=40`。

## 验证

| 范围 | 命令 | 结果 |
|---|---|---|
| 后端（legacy 透传） | `pytest tests/test_skill_legacy_flag.py tests/test_skill_registry.py tests/test_skill_intent.py tests/test_tool_registry.py -q` | **93 passed** |
| 前端（遗留标记契约） | `pytest tests/test_frontend_skill_legacy_contract.py tests/test_frontend_skill_tool_contract.py tests/test_frontend_paper_contract.py -q` | **43 passed** |
| 静态检查 | `node --check frontend/app.js` | OK |
| 全量定向回归 | 12 个相关测试文件 | **234 passed** |

日志：`.codebuddy/agent-logs/spec-032.1/task-05/frontend-dev/`
