"""临时兼容转发（Spec017 Task05）：parse 已迁至 backend.app.knowledge_base.infrastructure.parse。

本文件仅为迁移期过渡，使尚未更新的引用方继续可用；将在 Task05 收尾阶段删除，
不应作为新的依赖目标。

实现说明：为使旧路径引用方获得与真实模块同一对象，保证 patch.object 旧模块 与
旧模块 is infrastructure.parse 均成立，避免 import * 生成独立子模块导致 patch 失效，
此处将本模块在 sys.modules 中替换为真实模块别名。
"""

import sys

import backend.app.knowledge_base.infrastructure.parse as _real

sys.modules[__name__] = _real    # 旧路径 sys.modules 别名到真实模块
