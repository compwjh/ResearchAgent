# pdf-no-text-layer

- 原件：`pdf-no-text-layer.pdf`
- 期望：`pdf-no-text-layer.expected.json`
- 目标状态：`failed`
- 观察：匿名固定样本；坐标/行号/切片快照由 02-B 只读探针生成。
- 安全边界：不读取用户文档；不调用 embedding；不写 Qdrant。
