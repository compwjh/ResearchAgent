
from fastapi import APIRouter

router = APIRouter(prefix="/api")

from backend.app.api import common, routes_article, routes_chat, routes_kb, routes_paper, routes_system  # noqa: E402

router.include_router(routes_system.router)
router.include_router(routes_chat.router)
router.include_router(routes_kb.router)
router.include_router(routes_paper.router)
router.include_router(routes_article.router)

# 兼容层：把各子模块顶层符号重新导出到 `routes`，使历史测试
# `patch.object(routes, "<symbol>")` 仍能命中真实 handler（拆分前这些都定义在
# routes 模块上）。注意：此处只重新导出，子模块自身的 `router` 不受影响。
import sys as _sys

_module = _sys.modules[__name__]
_submodules = (common, routes_chat, routes_kb, routes_system, routes_paper, routes_article)
# `article_settings` 是共享可变状态：agent-settings handler 会重新绑定
# `routes_article.article_settings`，故不在此做静态 re-export，而是走下面的
# 模块级 `__getattr__`，让 `routes.article_settings` 始终反映最新值
# （测试与 common helper 都通过该 facade 读取）。
for _sub in _submodules:
    for _name, _val in vars(_sub).items():
        if _name == "article_settings":
            continue
        if not _name.startswith("__") and _name != "router":
            setattr(_module, _name, _val)


def __getattr__(name):
    if name == "article_settings":
        from backend.app.api import routes_article
        return routes_article.article_settings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
