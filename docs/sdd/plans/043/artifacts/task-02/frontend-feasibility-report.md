# Task02 前端 SVG 200 节点双档可行性报告

## 范围与结论

本报告只覆盖隔离的合成 SVG 样例，不代表生产 `frontend/` 已实现或已发布地图入口；未修改生产前端、后端、数据库、API 或启动业务服务。

**结论：前端 SVG 交互方案 GO（仅限 Task03 进入桌面地图实现的前端可行性前提）。**

真实 Chromium headless 浏览器分别验证了保留 34 边的 baseline 与 620 边的 representative high-load 档。两档都渲染 200 个节点并完成缩放、平移、拖动、选择；布局迭代固定上限 8 次 RAF，交互后不重新布局。该结论不覆盖真实 API 数据、生产地图组件、手机 Task07 或端到端部署；Task02 总体是否放行仍由后端真实 provider/embedding 门禁合并裁决。

## 隔离样例与证据

- Fixture：[literature_map_performance.html](../../../../../tests/frontend/fixtures/literature_map_performance.html)
- 测试：[test_frontend_map_feasibility.py](../../../../../tests/frontend/test_frontend_map_feasibility.py)
- baseline 截图：[literature-map-200-nodes.png](screenshots/literature-map-200-nodes.png)
- high-load 截图：[literature-map-200-nodes-high-load.png](screenshots/literature-map-200-nodes-high-load.png)
- 机器证据：[browser-evidence.json](browser-evidence.json)

Fixture 通过 `file://` 直接加载，无网络请求、无框架、无外部脚本。两档均为 synthetic 数据，不计入真实论文/API 验收：

| 档位 | 节点 | 总关系 | 引用边 | 相似边 | 短标签 |
|---|---:|---:|---:|---:|---:|
| baseline（默认） | 200 | 34 | 16 | 18 | 8 |
| high（`?profile=high`） | 200 | 620 | 310 | 310 | 8 |

High 档保留 baseline 的 34 条边，再增加 294 条引用边与 292 条相似边，覆盖 200 节点在相似 top-3 关系规模下的代表性渲染负载；边仍明确按引用/相似两层分开，未把 synthetic 关系当作真实数据。

## 实测性能事实与阈值

以下为浏览器页面内 `performance.now()` 记录，不把事件处理耗时冒充帧耗时：

| 指标（最终状态） | baseline | high | 门槛 |
|---|---:|---:|---:|
| 布局迭代 / 布局 RAF | 8 / 8 | 8 / 8 | `<= 8` |
| 最大布局 RAF 工作耗时 | 约 0.4ms | 约 1.2ms | `< 50ms` |
| 最大渲染 RAF 工作耗时 | 约 0.1ms | 约 0.2ms | `< 50ms` |
| 最大渲染 wall（事件到 RAF flush） | 约 13.7ms | 约 15.2ms | `< 250ms` |
| 最大 gesture wall（整段模拟手势） | 约 179ms | 约 794ms | `< 1000ms` |
| 最大 pointer handler 工作耗时 | 约 0.1ms | 约 0.1ms | `< 50ms` |
| longtask observer | 支持，0 条 | 支持，0 条 | `0 条` |

`gesture wall` 包含自动化输入序列本身，故 high 档明显大于单次 RAF wall；它用于捕获卡住的整段交互，不替代每帧工作/flush 指标。最终机器记录以 [browser-evidence.json](browser-evidence.json) 为准。

## 交互事实

浏览器测试对 baseline 与 high 两档均实际完成并断言：

1. 读取 200 个 `data-node-id` 节点与对应引用/相似边数量，确认 high 档达到 620 条关系。
2. 点击“放大”，观察缩放从 `1` 变为 `1.2`；布局迭代仍为 8。
3. 在 SVG 背景拖动，观察 `panX/panY` 非零；仅调度视图 RAF。
4. 拖动 `node-17`，确认节点坐标变化；仅更新该节点及相邻边，不触发新的布局迭代。
5. 点击 `node-17`，确认 `data-selected=true` 与选择状态记录。
6. 执行一轮快速平移事件，分别记录 handler、render frame、render wall、gesture wall 与 longtask，不以单一 0.1ms 数字代表整体帧耗时。

## 方案边界与手机提示

- SVG 使用单一 `viewport` group 变换承载缩放/平移；节点拖动和视图更新分别按 RAF 合并，避免每次 pointermove 做全量布局。
- 引用边和相似边保留不同的 `data-edge-kind`、实线/虚线视觉区分；相似关系是 synthetic 负载，不代表真实阈值结果。
- 标签只保留每 25 个节点一个作者/年份短标签；完整标题在真实产品中应由详情面板提供，本 fixture 仅通过 `aria-label` 保持节点可识别。
- fixture 在窄屏降低画布高度并保留 `touch-action: none`，可作为后续触控适配的起点；未执行手机验收，也不将本报告作为 Task07 通过证据。

## 验证记录

- `.venv/bin/python -m pytest -q -s tests/frontend/test_frontend_map_feasibility.py`：退出码 0，3 passed；含 baseline/high 两档真实 Chromium 浏览器运行。
- `node -e '...new Function(inlineScript)...'`：退出码 0，fixture 内联 JavaScript 解析成功。
- `git diff --check`：退出码 0。
- 初次受限环境启动 Chromium 曾因 macOS Mach port 权限阻塞；按授权使用现有 `.venv` 浏览器后取得上述真实证据，未以静态检查冒充性能通过。

## 风险与下一步

- 这是合成图可行性证据，不替代真实 API 创建/引用/相似关系证据；Task03 应先冻结真实节点/边 schema，再将同样的受限调度策略接入生产组件。
- 8 次 bounded layout 是当前 fixture 的可观测上限，不是生产布局质量承诺；生产实现需在不拖动时运行有限布局，并在交互时保持增量更新。
- 生产地图尚未实现、未部署、未启动；本任务无可访问服务地址或端口。
