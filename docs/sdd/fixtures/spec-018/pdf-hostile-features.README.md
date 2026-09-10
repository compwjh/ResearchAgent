# pdf-hostile-features

- 原件：`pdf-hostile-features.pdf`
- 期望：`pdf-hostile-features.expected.json`
- 目标状态：`partial`
- 观察：匿名固定样本；坐标/行号/切片快照由 02-B 只读探针生成。
- 安全边界：不读取用户文档；不调用 embedding；不写 Qdrant。
