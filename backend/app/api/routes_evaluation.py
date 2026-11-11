"""评测台五个端点（API 层只做编排与稳定错误体）。

所有外部依赖调用都在 ``_respond`` 的 ``try/except`` 内：可预期失败按稳定错误码
返回，意外异常统一 503 ``EVAL_BACKEND_UNAVAILABLE``，绝不裸 500、绝不把
``str(exc)`` 放进响应 payload（回归清单第 11、14 条）。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Body, Request  # noqa: B008
from fastapi.responses import JSONResponse

from backend.app.evaluation import service
from backend.app.evaluation.contracts import EvaluationError, error_payload

logger = logging.getLogger(__name__)
router = APIRouter()


def _failure(code: str, request: Request) -> JSONResponse:
    body = error_payload(code, request.headers.get("X-Request-ID") or uuid.uuid4().hex)
    status = EvaluationError(code).status
    headers = {"Retry-After": "10"} if status >= 500 else {}
    return JSONResponse(status_code=status, content=body, headers=headers)


def _respond(action, request: Request):
    try:
        return action()
    except EvaluationError as exc:
        return _failure(exc.code, request)
    except Exception as exc:  # 外部依赖故障不得冒泡成裸 500
        logger.warning("evaluation unexpected failure: %s", type(exc).__name__)
        return _failure("EVAL_BACKEND_UNAVAILABLE", request)


@router.get("/evaluation/options")
def evaluation_options(request: Request):
    return _respond(service.options, request)


@router.post("/evaluation/score")
def evaluation_score(request: Request, payload: Any = Body(default=None)):  # noqa: B008
    return _respond(lambda: service.score(payload), request)


@router.get("/evaluation/runs")
def evaluation_runs(request: Request):
    return _respond(service.runs, request)


@router.get("/evaluation/runs/{run_id}")
def evaluation_run(run_id: str, request: Request):
    return _respond(lambda: service.run(run_id), request)


@router.get("/evaluation/compare")
def evaluation_compare(request: Request, a: str = "", b: str = ""):
    return _respond(lambda: service.compare(a, b), request)
