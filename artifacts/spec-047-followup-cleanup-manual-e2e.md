# Spec-047 追加范围五：人工验收可复现步骤（2026-11-12）

> 适用范围：遗留项清理（缓存版本 / P2 文案 / 测试布局 / 灰卡文字对比度 / 覆盖率）。**用户可见功能行为不变**，本验收用于确认清理没有引入回归。
> 服务地址：`http://127.0.0.1:8000/`（端口 8000）；启动命令见 `deploy/README.md`（常用：`./deploy/start.sh`）。
> 产物性质：纯文档，由主会话代行落盘（三处留痕：本头部 / spec 追加范围五 §7 / 状态台账收口条）。

## 0. 前置

1. 确认服务在跑：浏览器打开 `http://127.0.0.1:8000/api/health`，页面显示 `{"status":"ok", ...}` 即通过。
2. **硬刷新**浏览器（macOS `Cmd+Shift+R`）：本轮升了 `styles.css?v=77` 与 `research-tasks.js?v=26`，不刷新会命中旧缓存。
3. 若 `connection refused`：按 `deploy/README.md` 启动服务后重试；端口占用时选可用端口并替换下文地址。

## 1. 逐步点击与预期提示

| 步 | 操作 | 点击后提示 / 等待条件 | 下一步 |
|---|---|---|---|
| 1 | 打开 `http://127.0.0.1:8000/#evaluation-view` | 评测视图渲染，出现指标分组与卡片；等待状态栏不再显示「评分中…」 | 进入步 2 |
| 2 | 在运行历史中点任一 `chat-quality` 评测 run（如 `eval-009223dbf9f649f4bc3426376431e0b6`） | 渲染 **22 张**指标卡；等待卡片文本出现（通常 < 2 秒） | 进入步 3 |
| 3 | 查看 `needs_ground_truth`（缺少标注）卡片 | **10 张**：灰左边框、浅灰背景、`—`、`样本数：0`、原因文字清晰可读（深灰 `#5a5d66`，在浅灰底上对比度 6.0947:1） | 进入步 4 |
| 4 | 查看 `computed` 卡片 | **12 张**：左边框仍为绿色 `#287c43`，未被灰化 | 进入步 5 |
| 5 | 在分组里切到 `rag-retrieval` | 检索组恢复 computed 绿卡；等待重绘完成 | 进入步 6 |
| 6 | 右键 → 查看网页源代码，搜 `styles.css?v=` 与 `research-tasks.js?v=` | 首个 live 链接为 `/assets/styles.css?v=77`、脚本为 `/assets/research-tasks.js?v=26`；末尾注释区可见 `v=76` / `v=25` 兼容 marker（仅注释，不加载） | 进入步 7 |
| 7 | 点灰卡「参数与明细」展开 | `<details>` 可展开，状态与原因仍可见，**不隐藏任何卡** | 验收完成 |

## 2. 自然语言入口

本范围**不新增也不修改自然语言入口**，产品主路径无新增自然语言交互；故本项标记为「不适用（非本范围改动）」，不做形式化验证。

## 3. 失败恢复

| 现象 | 恢复动作 |
|---|---|
| 卡片仍是旧浅灰文字 / 样式未变 | 确认硬刷新已执行；查看源代码 `styles.css` 是否 `v=77`；若为 `v=76` 说明命中缓存，清缓存后再刷新 |
| `computed` 卡变灰 | 属回归：记录截图，回到 `docs/sdd/reviews/047-followup-frontend-review.md` 的 DOM 契约核对项，暂停验收并上报 |
| 22 张卡数量不符 / 卡片未渲染 | 检查 `/api/evaluation/options` 是否 200；等待评分任务结束后重试步 2 |
| 服务 5xx / 连接失败 | 按 `deploy/README.md` 重启服务；仍失败则记录具体阻塞，不宣称验收通过 |
| `v=77` marker 被当成真实 stylesheet | 检查 `frontend/index.html:913-914` 是否仍在 HTML 注释内且不含 `<link` / `<script` 标签字面串 |

## 4. 产物查看路径

| 产物 | 路径 |
|---|---|
| 浏览器计算色实测 | `docs/sdd/plans/047/runs/task-20/r1-computed-style.txt` |
| 灰卡截图 | `task-20-gray.png` |
| 部署验证（5×200） | `docs/sdd/plans/047/runs/task-20/deploy-verification.json` |
| 全量回归 / 覆盖率 | `docs/sdd/plans/047/runs/task-20/full-regression-coverage.txt`、`.exit` |
| 最终验证记录 | `docs/sdd/plans/047/runs/task-20/final-verification.md` |
| 独立评审 / 签字 | `docs/sdd/plans/047/runs/task-20/merge-review.md`、`docs/sdd/reviews/047-acceptance-review.md` §17、`docs/sdd/reviews/047-followup-frontend-review.md` |
| 复盘 | `docs/sdd/retro/2026-11-12-spec047-followup-cleanup-closure.md` |

## 5. 已知非阻塞项

Langfuse `:3000` 未启动导致 span 导出 transient 告警；浏览器控制台其它视图 4×404；全仓 185 个历史 lint 债务；无真实 GitHub Actions workflow；平台 branch protection 未配置；覆盖率报告未设阈值门禁（实测 83.02%，如实登记）。以上均不影响本验收通过。
