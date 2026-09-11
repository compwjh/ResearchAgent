"""spec-023 Task03 — Skill 注册表只读浏览与启停 API。

路由挂载在根 ``/api`` 下（由 ``api/routes.py`` 的 ``APIRouter(prefix="/api")`` 统一前缀）：
    GET    /api/skills            -> {skills:[{name,description,tools,enabled}]}
    GET    /api/skills/{name}     -> 上述字段 + body
    PATCH  /api/skills/{name}     -> 入参 {enabled:bool}，返回更新后的 Skill

错误体格式复用 ``routes_kb._document_error``（统一为
{error_code,message,retryable,request_id}）；404/400 均不重试。
"""

from __future__ import annotations

from typing import Any

# FastAPI 在路由签名里用 Body(...) 作默认参数是惯用法，关闭 B008 误报。
from fastapi import APIRouter, Body, Request  # noqa: B008

from backend.app.api.routes_kb import _document_error
from backend.app.platform.config import BASE_DIR, KB_DIR
from backend.app.skills.service import SkillRegistryService

router = APIRouter()

_registry: SkillRegistryService | None = None


def get_skill_registry() -> SkillRegistryService:
    """返回进程级 Skill 注册表；路径来自配置，测试可 patch 本函数。"""
    global _registry
    if _registry is None:
        _registry = SkillRegistryService(
            skills_dir=BASE_DIR / ".agents" / "skills",
            state_path=KB_DIR / "skill-state.json",
        )
    return _registry


@router.get("/skills")
def list_skills(request: Request) -> dict:
    skills = get_skill_registry().list_skills()
    return {"skills": [skill.to_dict() for skill in skills]}


@router.get("/skills/{name}")
def get_skill(name: str, request: Request):
    skill = get_skill_registry().get_skill(name)
    if skill is None:
        return _document_error(404, "SKILL_NOT_FOUND", "Skill 不存在", request=request)
    return skill.to_dict()


@router.patch("/skills/{name}")
def update_skill(name: str, request: Request, payload: Any = Body(default=None)):  # noqa: B008
    if not isinstance(payload, dict) or "enabled" not in payload:
        return _document_error(400, "INVALID_REQUEST", "请求体必须包含 enabled 布尔字段", request=request)
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        return _document_error(400, "INVALID_REQUEST", "enabled 必须为布尔值", request=request)
    updated = get_skill_registry().set_enabled(name, enabled)
    if updated is None:
        return _document_error(404, "SKILL_NOT_FOUND", "Skill 不存在", request=request)
    return updated.to_dict()
