# Task08 真实浏览器导出验收

## 结论

**PASS（候选 `1a3ff26`，授权 Playwright Chromium，真实 `http://127.0.0.1:8000/#literature-maps-view`）。** 未创建地图、未打开预览、未调用分析 POST、未重索引或操作服务；仅对 fresh map 使用一次正常“适应”保存必要 viewport。

## 真实入口与等待

1. 桌面 1440×900 通过全局导航“文献地图”进入地图页。
2. 在“我的地图”列表普通点击 `Task08 live graph attention networks 24134dce4api`，确认目标地图加载后等待标题和图谱 SVG 出现。
3. 普通点击工具栏“适应”，等待图谱稳定。
4. 普通点击“JSON”，等待浏览器下载完成；普通点击“PNG”，等待浏览器下载完成。
5. 页面状态提示“PNG 已下载；快照只包含当前图谱、标题和图例”。最终桌面截图：[final-browser-export.png](screenshots/final-browser-export.png)。

## 地图与导出证据

- 候选：`1a3ff26`；地图 ID：`35a56c6f2da84fca85fc3c21dfa0055c`；标题：`Task08 live graph attention networks 24134dce4api`。
- JSON：[task08-live-map-export.json](exports/task08-live-map-export.json)，真实下载保存路径 `docs/sdd/plans/043/artifacts/task-08/exports/task08-live-map-export.json`；schema `literature-map-export-v1`；map ID 匹配；**21 nodes / 17 edges**；所有边端点均属于导出节点。
- JSON 安全扫描未命中 `owner_id`、密码、API key、authorization、内部绝对路径、`ResearchAgent` 或 hidden prompt 字段。
- PNG：[task08-live-map-export.png](exports/task08-live-map-export.png)，真实下载保存路径 `docs/sdd/plans/043/artifacts/task-08/exports/task08-live-map-export.png`；PNG signature 有效、**960×772、75,290 bytes**；Chromium 以 `file://` 直接打开成功。视觉核对仅见地图标题、21 节点/17 关系计数、节点/边与图例，无页面工具条、详情面板或浏览器 UI。
- 服务端 POST 监听为 **0**；未执行额外 pan/viewport 写入。
