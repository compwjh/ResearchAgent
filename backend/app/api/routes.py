
from fastapi import APIRouter

from backend.app.api import (
    routes_article,
    routes_chat,
    routes_conversations,
    routes_kb,
    routes_paper,
    routes_research,
    routes_skills,
    routes_system,
    routes_tools,
)

router = APIRouter(prefix="/api")

router.include_router(routes_system.router)
router.include_router(routes_chat.router)
router.include_router(routes_kb.router)
router.include_router(routes_paper.router)
router.include_router(routes_article.router)
router.include_router(routes_conversations.router)
router.include_router(routes_research.router)
router.include_router(routes_research.session_router)
router.include_router(routes_skills.router)
router.include_router(routes_tools.router)
