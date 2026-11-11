"""processing-steps 读取契约：无参扁平形状不变 + 可选 cursor/limit 游标分页。

现有前端拉取路径不带任何查询参数，必须继续拿到与改动前逐字段一致的
``{"steps": [...]}``；带参调用才返回切片与 next_cursor / has_more。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.memory.repository import OWNER_ID, MemoryRepository
from backend.app.platform.bootstrap import override_provider

BASE = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
STEP_COUNT = 7


def _seed_steps(tmp_path, *, owner_id=OWNER_ID, count=STEP_COUNT, label_prefix="label"):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    conversation = repo.create_conversation(owner_id)
    message = repo.create_message(conversation.conversation_id, owner_id, "assistant", "ok")
    with repo.transaction() as db:
        for index in range(count):
            started = (BASE + timedelta(seconds=index)).isoformat()
            db.execute(
                "INSERT INTO processing_steps(step_id, message_id, kind, logical_sequence, "
                "label, status, summary, started_at, completed_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    f"{label_prefix}-{index:03d}", message.message_id, "phase", index,
                    f"{label_prefix}-{index}", "completed", "ok", started, started,
                ),
            )
    return repo, message.message_id


@pytest.fixture
def client_and_message(tmp_path):
    repo, message_id = _seed_steps(tmp_path)
    # 不进入 `with TestClient(app)`，避免触发 lifespan 启动钩子；只替换组合根解析。
    with override_provider("memory_repository", repo):
        yield TestClient(app), message_id, repo


def test_without_params_keeps_historical_flat_shape(client_and_message):
    """回归基线：无参响应体只有 steps 键，且与 repository 既有读取逐字段一致。"""
    client, message_id, repo = client_and_message
    response = client.get(f"/api/messages/{message_id}/processing-steps")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"steps"}
    assert [step["step_id"] for step in body["steps"]] == [
        f"label-{index:03d}" for index in range(STEP_COUNT)
    ]
    assert body["steps"] == [step.to_dict() for step in repo.list_processing_steps(message_id, OWNER_ID)]


def test_pagination_returns_ordered_slices_with_cursor_and_has_more(client_and_message):
    """带 limit/cursor 返回正确切片，逐页拼接必须与无参全量列表完全一致。"""
    client, message_id, _repo = client_and_message
    flat = [
        step["step_id"]
        for step in client.get(f"/api/messages/{message_id}/processing-steps").json()["steps"]
    ]

    seen, cursor, pages = [], None, 0
    while True:
        params = {"limit": "2"}
        if cursor is not None:
            params["cursor"] = cursor
        response = client.get(f"/api/messages/{message_id}/processing-steps", params=params)
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"steps", "next_cursor", "has_more"}
        assert 0 < len(body["steps"]) <= 2
        seen.extend(step["step_id"] for step in body["steps"])
        pages += 1
        assert pages <= 10, "cursor must advance instead of repeating the first page"
        if not body["has_more"]:
            assert body["next_cursor"] is None
            break
        assert body["next_cursor"]
        cursor = body["next_cursor"]

    assert seen == flat
    assert pages == 4


@pytest.mark.parametrize(
    "params",
    [
        {"limit": "0"},
        {"limit": "201"},
        {"limit": "abc"},
        {"cursor": "not-a-cursor"},
        {"limit": "2", "cursor": "not-a-cursor"},
    ],
)
def test_invalid_pagination_params_return_400(client_and_message, params):
    """参数越界/非法必须 400，而非被静默忽略或冒泡成 422/500。"""
    client, message_id, _repo = client_and_message
    response = client.get(f"/api/messages/{message_id}/processing-steps", params=params)
    assert response.status_code == 400
    assert "code" in response.json()["detail"]


def test_pagination_keeps_owner_isolation(client_and_message, tmp_path):
    """分页路径同样按 owner JOIN 过滤，不得泄露他人消息的步骤。"""
    client, _message_id, repo = client_and_message
    conversation = repo.create_conversation("someone-else")
    foreign = repo.create_message(conversation.conversation_id, "someone-else", "assistant", "secret")
    with repo.transaction() as db:
        started = BASE.isoformat()
        db.execute(
            "INSERT INTO processing_steps(step_id, message_id, kind, logical_sequence, "
            "label, status, summary, started_at, completed_at) VALUES (?,?,?,?,?,?,?,?,?)",
            ("foreign-step", foreign.message_id, "phase", 0, "secret", "completed", "ok", started, started),
        )

    assert client.get(f"/api/messages/{foreign.message_id}/processing-steps").status_code == 404
    response = client.get(
        f"/api/messages/{foreign.message_id}/processing-steps", params={"limit": "2"}
    )
    assert response.status_code == 404


def test_repository_page_is_owner_scoped_and_returns_stable_slices(tmp_path):
    """仓储层：owner 不匹配返回空页；匹配时切片稳定且游标可续读。"""
    repo, message_id = _seed_steps(tmp_path)
    assert repo.list_processing_steps_page(message_id, "someone-else", limit=3)[0] == []
    first, cursor, has_more = repo.list_processing_steps_page(message_id, OWNER_ID, limit=3)
    assert [step.step_id for step in first] == ["label-000", "label-001", "label-002"]
    assert has_more is True and cursor
    second, _cursor2, has_more2 = repo.list_processing_steps_page(
        message_id, OWNER_ID, cursor=cursor, limit=3
    )
    assert [step.step_id for step in second] == ["label-003", "label-004", "label-005"]
    assert has_more2 is True
