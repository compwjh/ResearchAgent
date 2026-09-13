"""spec-023 Task04 — Tool 注册表只读浏览与启停 API。

路由挂载在根 ``/api`` 下（由 ``api/routes.py`` 的 ``APIRouter(prefix="/api")`` 统一前缀）：
    GET    /api/tools            -> {tools:[{name,description,enabled}]}
    GET    /api/tools/{name}     -> 同上单个字段
    PATCH  /api/tools/{name}     -> 入参 {enabled:bool}，返回更新后的 Tool
    GET    /api/tools/{name}/code -> spec-034 只读入口源码视图（见下）

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
from backend.app.skills.tool_service import ToolRegistryService, resolve_tool_source

router = APIRouter()

# spec-034 M-04：TOOL_CODE_UNAVAILABLE 的 message 必须是固定文案。
# 禁止拼接 str(exc) / 异常 repr / 绝对路径 / entry 之外的任何内部路径
# （inspect.getsourcefile 天然返回绝对路径，拼进错误体即泄漏）；
# 异常详情（含 stack）只进服务端日志。
_TOOL_CODE_UNAVAILABLE_MESSAGE = "该 Tool 的入口源码不可用"

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


@router.get("/tools/{name}/code")
def get_tool_code(name: str, request: Request):
    """spec-034 — 只读返回 Tool 入口函数的源码与仓库相对 ``文件:行号``。

    - ``{name}`` 与注册名**精确相等**匹配（M-06）：不做前缀/模糊/大小写归一化，
      不存在直接 ``TOOL_NOT_FOUND``，不回退文件系统查找；
    - ``entry`` **只从注册表读取**，任何情况下不接受请求方传入的点分路径
      （含 query / body / header 变体）；
    - 禁用（``enabled=false``）的 Tool 同样可查看（M-07），不按启停状态过滤；
    - 不加缓存：每次实时解析，避免行号漂移（M-07）；
    - 不执行、不 eval、不写文件、不改注册表；
    - 所有解析失败收敛为 ``TOOL_CODE_UNAVAILABLE``（固定文案，M-04），不抛 500。
    """
    registered = get_tool_registry().get_tool_entry(name)
    if registered is None:
        return _document_error(404, "TOOL_NOT_FOUND", "Tool 不存在", request=request)
    source = resolve_tool_source(registered.entry)
    if source is None:
        return _document_error(
            404, "TOOL_CODE_UNAVAILABLE", _TOOL_CODE_UNAVAILABLE_MESSAGE, request=request
        )
    return {
        "name": registered.name,
        "entry": registered.entry,
        "file": source["file"],
        "lineno": source["lineno"],
        "language": source["language"],
        "code": source["code"],
    }
