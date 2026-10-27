# Task10 当前候选样式 API 实测

- Spec/Task：043 / Task10
- 当前候选：`498b6ded`；服务：`http://127.0.0.1:8000`；页面资源：`literature-maps.js?v=31`、`literature-maps.css?v=19`
- 运行时间：2026-10-27 13:48:08.887Z–13:48:09.010Z
- 入口：已存在地图 `0baabeae7268429c9f7e4de8098ae1d0`，不是本轮新建。
- 本轮限制：只写入一篇节点的 `color_override` 和地图 `node_style`；不创建地图、不下载 PDF、不提交分析请求。

## 基线

`baseline.json` 记录开始前 revision 182、21 节点/18 边、filled / 0.3；测试节点 `21041260a5394f42891b020128fa60fa` 的颜色覆盖为 `null`，原分组和位置一并保存。`invariants-before.json` 保存全部节点的颜色覆盖、分组、位置和 removed 标记，以及完整 view settings。

## 请求与结果

`trace.json` 按执行顺序保留 13 次真实 HTTP 调用（请求体、状态码和契约关键响应字段）：

1. `GET /graph`：200，revision 182。
2. `PATCH /node-styles`：200，颜色临时设为 `#FF8A3D`，revision 183。
3. `GET /graph`：200，读回颜色与 revision 183。
4. `PATCH /view`：200，临时设为 `outline / 0.55`，revision 184。
5. `GET /graph`：200，读回地图外观。
6. 使用 revision 182 提交颜色 PATCH：预期且实际为 **409**。
7. `GET /graph`：200，revision 仍为 184，确认冲突请求没有改变颜色或外观。
8. `GET /export`：200，schema 为 `literature-map-export-v2`。
9. `GET /graph`：200，恢复前 revision 守卫通过。
10. `PATCH /node-styles`：200，恢复原 `null` 颜色覆盖，revision 185。
11. `GET /graph`：200，确认颜色、分组、位置恢复。
12. `PATCH /view`：200，恢复原 `filled / 0.3`，revision 186。
13. `GET /graph`：200，最终检查通过。

## 最终状态

`result.json` 与 `invariants-after.json` 记录：21 节点/18 边不变；所有节点的颜色覆盖、分组、位置及 removed 标记与基线一致；地图 view settings 与基线一致。唯一持久变化是预期的 revision 从 182 增至 186（颜色/外观的四次成功写入）。未发现非预期并发 revision 变化；意图中的旧 revision 冲突后已立即 GET 核对再继续恢复。

更早的旧候选 11 请求链仍保留在 `../task10-styles-live-20261027-134340/`；本目录才是绑定当前候选 `498b6ded` 的实测记录。
