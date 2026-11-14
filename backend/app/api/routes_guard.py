"""Spec050 Task03：任务内单动作确认与 guard-event-v1 事件读取。

路径/状态码按 Gate 2 冻结要求保持为最小草案；越权访问遵循既有资源隐藏策略
（只返回当前 owner 的记录，不泄露他人动作是否存在）。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.guard import service
from backend.app.guard.contracts import EVENT_SCHEMA_VERSION
from backend.app.memory.repository import OWNER_ID

router = APIRouter(prefix="/guard", tags=["guard"])


class DecisionRequest(BaseModel):
    choice: Literal["allow", "reject", "cancel"]
    args_hash: str = Field(default="", max_length=128)


@router.get("/actions")
def list_pending_actions(limit: int = 50) -> dict:
    return {
        "schema_version": "guard-action-v1",
        "records": service.pending_actions(OWNER_ID, limit=limit),
    }


@router.post("/actions/{action_ref}/decision")
def decide_action(action_ref: str, request: DecisionRequest) -> dict:
    decision = service.decide(
        action_ref,
        owner_id=OWNER_ID,
        choice=request.choice,
        expected_args_hash=request.args_hash,
    )
    if decision.reason_code in {"ACTION_NOT_FOUND", "ACTION_NOT_PENDING", "ACTION_ALREADY_DECIDED"}:
        raise HTTPException(status_code=409, detail={"code": decision.reason_code})
    return {
        "action_ref": action_ref,
        "outcome": decision.outcome.value,
        "reason_code": decision.reason_code,
        "message": decision.message,
    }


@router.get("/events")
def list_guard_events(limit: int = 50) -> dict:
    payload = service.events(OWNER_ID, limit=limit)
    payload["schema_version"] = EVENT_SCHEMA_VERSION
    return payload


@router.get("/status")
def guard_status() -> dict:
    return {
        "enabled": service.guard_enabled(),
        "policy_version": "guard-policy-v1",
        "strategy_version": "guard-strategy-v1",
        "event_schema_version": EVENT_SCHEMA_VERSION,
    }
