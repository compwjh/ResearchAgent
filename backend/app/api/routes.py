
from fastapi import APIRouter

router = APIRouter(prefix="/api")

from backend.app.api import (  # noqa: E402
    routes_article,
    routes_chat,
    routes_kb,
    routes_paper,
    routes_skills,
    routes_system,
    routes_tools,
)

router.include_router(routes_system.router)
router.include_router(routes_chat.router)
router.include_router(routes_kb.router)
router.include_router(routes_paper.router)
router.include_router(routes_article.router)
router.include_router(routes_skills.router)
router.include_router(routes_tools.router)
