"""spec-023 Task04 — Tool 注册表只读浏览与启停 API。

路由挂载在根 ``/api`` 下（由 ``api/routes.py`` 的 ``APIRouter(prefix="/api")`` 统一前缀）：
    GET    /api/tools            -> {tools:[{name,description,enabled}]}
    GET    /api/tools/{name}     -> 同上单个字段
    PATCH  /api/tools/{name}     -> 入参 {enabled:bool}，返回更新后的 Tool

错误体格式复用 ``routes_kb._document_error``（统一为
{error_code,message,retryable,request_id}）；404/400 均不重试。
"""

from __future__ import annotations

from typing import Any

# FastAPI 在路由签名里用 Body(...) 作默认参数是惯用法，关闭 B008 误报。
from fastapi import APIRouter, Body, Request  # noqa: B008

from backend.app.api.routes_kb import _document_error
from backend.app.platform.config import KB_DIR
from backend.app.skills.registry import build_default_tool_registry
from backend.app.skills.tool_service import ToolRegistryService

router = APIRouter()

_registry: ToolRegistryService | None = None


def get_tool_registry() -> ToolRegistryService:
    """返回进程级 Tool 注册表；路径来自配置，测试可 patch 本函数。"""
    global _registry
    if _registry is None:
        _registry = ToolRegistryService(
            registry=build_default_tool_registry(),
            state_path=KB_DIR / "skill-state.json",
        )
    return _registry


@router.get("/tools")
def list_tools(request: Request) -> dict:
    tools = get_tool_registry().list_tools()
    return {"tools": [tool.to_dict() for tool in tools]}


@router.get("/tools/{name}")
def get_tool(name: str, request: Request):
    tool = get_tool_registry().get_tool(name)
    if tool is None:
        return _document_error(404, "TOOL_NOT_FOUND", "Tool 不存在", request=request)
    return tool.to_dict()


@router.patch("/tools/{name}")
def update_tool(name: str, request: Request, payload: Any = Body(default=None)):  # noqa: B008
    if not isinstance(payload, dict) or "enabled" not in payload:
        return _document_error(400, "INVALID_REQUEST", "请求体必须包含 enabled 布尔字段", request=request)
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        return _document_error(400, "INVALID_REQUEST", "enabled 必须为布尔值", request=request)
    updated = get_tool_registry().set_enabled(name, enabled)
    if updated is None:
        return _document_error(404, "TOOL_NOT_FOUND", "Tool 不存在", request=request)
    return updated.to_dict()
