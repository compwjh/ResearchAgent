# Task 04 — 评审、回归与端到端验收

> 关联：[spec-036](../../specs/036-tool-source-code-viewer.md) ｜ 索引：[README](./README.md)
> 依赖：任务 03；当前状态：`待执行`

## 1. 状态与一句话目标

**待执行。** 对任务 02/03 的改动做独立评审与定向回归，并在**运行中的服务**上端到端验收
「Tool 列表能查看内部 Python 代码」，确认只读、无串台、既有接口无回归。

## 2. 背景与前置条件

- 任务 02（后端新接口）、任务 03（前端按钮与弹窗）已完成并读回确认。
- 服务运行中：`http://127.0.0.1:8000`（健康检查 `/api/health`，**不是** `/health`）。
- 用户既定要求：**不跑全量回归**，只做定向。

## 3. 数据、配置与接口

不适用（不新增持久化数据与配置）。

## 4. 实施步骤与文件边界

**允许改动**：`docs/sdd/reviews/036-*.md`、本 task 文件的回填段落。**不改任何代码文件**。

1. **需求评审**（`architect`）：评 spec-036 的问题定义、范围划死、验收可测性、与 spec-023 的边界。
   产出 `docs/sdd/reviews/036-requirement-review.md`（通过 / 打回）。
2. **技术评审**（`backend-reviewer` + `frontend-reviewer`，各评各端只评 2 个文件级别）：
   - 后端重点：`entry` 解析是否只接受注册表来源；路径是否强制仓库相对且越界有兜底；
     异常是否全部收敛为 404 而不抛 500；既有三接口响应结构未变。
   - 前端重点：是否复用 `openSkillDetail` 的序号 + `AbortController` 防串台；
     失败是否统一文案；是否引入新依赖。
   产出 `docs/sdd/reviews/036-tech-review.md`。
3. **定向回归**（`backend-tester` / `frontend-tester`）：
   - 后端：`tests/` 下 Tool 相关测试文件（按文件分批，每次全新 `--basetemp`，`env -u PYTHONPATH`）。
   - 前端：`node --check frontend/app.js` + 前端契约 pytest（如 `tests/test_frontend_paper_contract.py`）。
   产出 `docs/sdd/reviews/036-backend-regression.md`（前端结论并入验收报告）。
4. **端到端验收**（`tester`）：
   - 对 5 个注册 Tool 逐个调 `GET /api/tools/{name}/code`，核对 200、`code` 非空、
     `file` 为仓库相对路径、`lineno` 处确实是该函数定义行（用 `sed -n` 抽查 1-2 个）。
   - 未知 name → `TOOL_NOT_FOUND`；构造异常 entry → `TOOL_CODE_UNAVAILABLE` 且不泄漏路径。
   - 前端：确认按钮存在、弹窗可开、源码可见（可用静态核对 + 接口验证代替浏览器，
     若条件允许再用真实浏览器点一遍）。
   - 产出 `docs/sdd/reviews/036-acceptance-review.md`（含通过/不通过结论 + 开发主管签字栏）。

## 5. 子代理分派

| 步骤 | 角色 | 模型 | 最小上下文 |
|---|---|---|---|
| 1 | `architect` | `qwen3.8:27b-mlx` | spec-036 + `plans/036/*` |
| 2 | `backend-reviewer` / `frontend-reviewer` | `qwen3.8:27b-mlx` | spec-036 边界 + 改动文件清单 |
| 3 | `backend-tester` / `frontend-tester` | `qwen3.5:9b` | 测试文件清单 + 运行约定 |
| 4 | `tester` | `qwen3.5:9b` | spec-036 验收场景 + 运行中的服务 |

## 6. 边界与明确不做

- 本任务**不修代码**；发现问题退回任务 02/03。
- 不跑全量回归（用户既定要求）。
- 不评判与本次无关的模块。

## 7. 验收、风险与回滚

**验收**：

1. 定向回归全绿，`ruff` / `node --check` 零新增告警。
2. 5 个 Tool 全部能取到非空源码，且 `file:lineno` 真实指向入口函数定义。
3. 未知 name / 不可解析 entry 分别返回 `TOOL_NOT_FOUND` / `TOOL_CODE_UNAVAILABLE`，无 500。
4. 既有 `GET /api/tools`、`GET /api/tools/{name}`、`PATCH /api/tools/{name}` 响应结构未变。
5. 三份评审文档均为真实结论，无「待评审（未执行）」残留。

**风险**：USENIX/KB 相关 entry 未来重构导致 `lineno` 漂移 → 以**实时解析**为准，不写死行号。
**回滚**：删除任务 02 的路由与解析函数、任务 03 的按钮与弹窗即可，不影响既有行为。

## 8. 产出物、执行结果与变更日志

- 产出物：`docs/sdd/reviews/036-requirement-review.md`、`036-tech-review.md`、
  `036-backend-regression.md`、`036-acceptance-review.md`。
- 执行结果：待执行后填写。
- 变更日志：待执行后填写。
