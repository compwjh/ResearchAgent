
from fastapi import APIRouter

router = APIRouter(prefix="/api")

from backend.app.api import routes_article, routes_chat, routes_conversations, routes_kb, routes_paper, routes_system  # noqa: E402

router.include_router(routes_system.router)
router.include_router(routes_chat.router)
router.include_router(routes_kb.router)
router.include_router(routes_paper.router)
router.include_router(routes_article.router)
router.include_router(routes_conversations.router)
