"""Spec050 Task03：任务内单动作确认与 guard-event-v1 事件读取。

路径/状态码按 Gate 2 冻结要求保持为最小草案；越权访问遵循既有资源隐藏策略
（只返回当前 owner 的记录，不泄露他人动作是否存在）。
"""

from __future__ import annotations

import json
import time
from typing import Any, Iterator, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.app.guard import service, store
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


@router.get("/stream")
def stream_guard_events(request: Request, limit: int = 50) -> StreamingResponse:
    """SSE 增量推送 guard 事件；guard 关闭时仍可读取历史事件，但不做新校验。"""
    last_event_id = request.headers.get("last-event-id", "").strip()
    return StreamingResponse(
        event_stream(OWNER_ID, last_event_id=last_event_id, limit=limit),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _guard_frame(record: dict[str, Any]) -> str:
    """冻结帧格式：真实事件帧带 id:/event:/data:；心跳是合成帧，不带 id:。"""
    payload = {
        "type": "guard",
        "schema_version": EVENT_SCHEMA_VERSION,
        "record": record,
    }
    return (
        f"id: {record['event_id']}\n"
        "event: guard\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


def event_stream(
    owner_id: str,
    *,
    last_event_id: str = "",
    limit: int = 50,
    poll_seconds: float = 1.0,
    heartbeat_seconds: float = 15.0,
) -> Iterator[str]:
    """轮询 guard-event-v1 公共投影，只推未见过的 event_id。

    - Last-Event-ID 命中时只推游标之后的增量；找不到游标则推全量（最近 limit 条）。
    - 每 heartbeat_seconds 发一次 `: heartbeat`（合成帧不带 id:）。
    - 生成器被关闭（GeneratorExit）时正常退出，不留后台任务。
    """
    seen: set[str] = set()
    initialized = False
    last_flush = time.monotonic()
    try:
        while True:
            try:
                records = store.list_events(owner_id, limit=200)
            except Exception:
                records = []
            ids = [str(record.get("event_id") or "") for record in records]
            if not initialized:
                initialized = True
                if last_event_id and last_event_id in ids:
                    cursor = ids.index(last_event_id)
                    seen.update(ids[cursor:])
            fresh = [
                record for record in reversed(records)
                if str(record.get("event_id") or "")
                and str(record.get("event_id") or "") not in seen
            ]
            for record in fresh:
                seen.add(str(record["event_id"]))
            batch = fresh[-limit:] if limit > 0 else fresh
            for record in batch:
                yield _guard_frame(record)
                last_flush = time.monotonic()
            if time.monotonic() - last_flush >= heartbeat_seconds:
                yield ": heartbeat\n\n"
                last_flush = time.monotonic()
            time.sleep(poll_seconds)
    except GeneratorExit:
        return
