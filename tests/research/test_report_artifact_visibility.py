"""Published report artifact visibility through Research Session routes."""

from __future__ import annotations

import json
from types import SimpleNamespace

from backend.app.api import routes_research


def _artifact(artifact_id: str, version: int, artifact_type: str = "markdown"):
    return SimpleNamespace(
        artifact_id=artifact_id,
        research_task_id="task-1",
        report_version=version,
        artifact_type=artifact_type,
        content_hash=f"hash-{artifact_id}",
        generated_by_agent_run_id="run-1",
        created_at="2026-10-29T00:00:00Z",
        content=f"body-{artifact_id}",
        storage_ref=None,
    )


def _report(version: int, status: str, published: object, *, task_id: str = "task-1", body: str | None = None):
    payload = body if body is not None else json.dumps({"generation": {"published": published}})
    return SimpleNamespace(
        report_id=f"report-{version}",
        research_task_id=task_id,
        report_version=version,
        status=status,
        report_json=payload,
    )


class _ArtifactStore:
    def __init__(self, *, artifacts=(), reports=(), session=None, task=None):
        self.artifacts = list(artifacts)
        self.reports = list(reports)
        self.session = session or SimpleNamespace(research_task_id="task-1", to_dict=lambda: {
            "research_session_id": "session-1", "research_task_id": "task-1",
        })
        self.task = task or SimpleNamespace(
            research_task_id="task-1", owner_id=routes_research.OWNER_ID,
            goal="goal", status="running", current_plan_version=1,
            quality_profile="balanced", target_paper_count=5, language="zh",
            review_plan_first=False, project_id=None, conversation_id="conversation-1",
            created_at="2026-10-29T00:00:00Z",
        )
        self.artifact_reads = 0
        self.artifact_list_reads = 0

    def get_session(self, _session_id, _owner_id):
        return self.session

    def get_task(self, task_id, _owner_id):
        return self.task if self.task and self.task.research_task_id == task_id else None

    def list_artifacts_for_task(self, task_id, _owner_id, *, report_version=None):
        self.artifact_list_reads += 1
        return [
            item for item in self.artifacts
            if item.research_task_id == task_id
            and (report_version is None or item.report_version == report_version)
        ]

    def list_research_reports(self, task_id, _owner_id):
        return [item for item in self.reports if item.research_task_id == task_id]

    def get_research_report(self, task_id, _owner_id, *, report_version):
        return next((item for item in self.reports if
                     item.research_task_id == task_id and item.report_version == report_version), None)

    def get_artifact(self, _artifact_id, _owner_id):
        self.artifact_reads += 1
        return next((item for item in self.artifacts if item.artifact_id == _artifact_id), None)


def test_artifact_list_hides_unpublished_canonical_versions_but_keeps_legacy(monkeypatch):
    store = _ArtifactStore(
        artifacts=[_artifact("pending", 1), _artifact("published", 2), _artifact("legacy", 3)],
        reports=[_report(1, "generating", False), _report(2, "completed", True)],
    )
    monkeypatch.setattr(routes_research, "_store", lambda: store)

    result = routes_research.list_research_artifacts("session-1", report_version=None)

    assert [item["artifact_id"] for item in result["artifacts"]] == ["published", "legacy"]
    assert store.artifact_list_reads == 1


def test_artifact_list_only_exposes_downloadable_types_for_published_and_legacy_versions(monkeypatch):
    store = _ArtifactStore(
        artifacts=[
            _artifact("published-markdown", 2, "markdown"),
            _artifact("published-intermediate", 2, "intermediate"),
            _artifact("legacy-markdown", 3, "markdown"),
            _artifact("legacy-intermediate", 3, "intermediate"),
        ],
        reports=[_report(2, "completed", True)],
    )
    monkeypatch.setattr(routes_research, "_store", lambda: store)

    result = routes_research.list_research_artifacts("session-1", report_version=None)
    downloaded = routes_research.download_research_artifact(
        "session-1", "published-intermediate", mode="attachment",
    )

    assert [item["artifact_id"] for item in result["artifacts"]] == [
        "published-markdown", "legacy-markdown",
    ]
    assert downloaded.status_code == 404


def test_session_detail_only_exposes_downloadable_types_for_published_and_legacy_versions(monkeypatch):
    store = _ArtifactStore(
        artifacts=[
            _artifact("published-markdown", 2, "markdown"),
            _artifact("published-intermediate", 2, "intermediate"),
            _artifact("legacy-markdown", 3, "markdown"),
            _artifact("legacy-intermediate", 3, "intermediate"),
        ],
        reports=[_report(2, "completed", True)],
    )
    store.get_session_plan = lambda *_args: None
    store.list_session_plans = lambda *_args: []
    store.list_approvals = lambda *_args: []
    store.list_notifications = lambda *_args: []
    monkeypatch.setattr(routes_research, "_store", lambda: store)
    monkeypatch.setattr(
        routes_research, "_approval_service",
        lambda: SimpleNamespace(get_session=lambda *_args: store.session),
    )
    monkeypatch.setattr(
        routes_research, "_service",
        lambda: SimpleNamespace(reconcile_session_projection=lambda *_args: store.session),
    )

    result = routes_research.get_research_session("session-1")

    assert [item["artifact_id"] for item in result["artifacts"]] == [
        "published-markdown", "legacy-markdown",
    ]


def test_artifact_list_fails_closed_for_noncompleted_or_malformed_canonical_rows(monkeypatch):
    store = _ArtifactStore(
        artifacts=[
            _artifact("draft", 1), _artifact("bad-json", 2), _artifact("completed-unpublished", 3),
            _artifact("nonboolean-published", 4), _artifact("legacy", 5),
        ],
        reports=[
            _report(1, "draft", True),
            _report(2, "completed", True, body="not-json"),
            _report(3, "completed", False),
            _report(4, "completed", "true"),
        ],
    )
    monkeypatch.setattr(routes_research, "_store", lambda: store)

    result = routes_research.list_research_artifacts("session-1", report_version=None)

    assert [item["artifact_id"] for item in result["artifacts"]] == ["legacy"]


def test_artifact_download_checks_owner_task_and_publication_before_content(monkeypatch):
    store = _ArtifactStore(
        artifacts=[_artifact("pending", 1), _artifact("published", 2)],
        reports=[_report(1, "generating", False), _report(2, "completed", True)],
    )
    monkeypatch.setattr(routes_research, "_store", lambda: store)

    hidden = routes_research.download_research_artifact("session-1", "pending", mode="attachment")
    assert hidden.status_code == 404
    assert json.loads(hidden.body)["error"]["code"] == "ARTIFACT_NOT_FOUND"
    assert store.artifact_reads == 1

    visible = routes_research.download_research_artifact("session-1", "published", mode="attachment")
    assert visible.body == b"body-published"
    assert store.artifact_reads == 2


def test_artifact_download_preserves_legacy_version_without_canonical_row(monkeypatch):
    store = _ArtifactStore(artifacts=[_artifact("legacy", 3)])
    monkeypatch.setattr(routes_research, "_store", lambda: store)

    result = routes_research.download_research_artifact("session-1", "legacy", mode="attachment")

    assert result.status_code == 200
    assert result.body == b"body-legacy"


def test_artifact_routes_validate_session_and_task_before_reading_artifacts(monkeypatch):
    store = _ArtifactStore(artifacts=[_artifact("a1", 1)], session=None, task=None)
    store.session = None
    store.task = None
    monkeypatch.setattr(routes_research, "_store", lambda: store)

    listed = routes_research.list_research_artifacts("missing-session", report_version=None)
    downloaded = routes_research.download_research_artifact("missing-session", "a1", mode="attachment")

    assert listed.status_code == 404
    assert downloaded.status_code == 404
    assert store.artifact_list_reads == 0
    assert store.artifact_reads == 0

    store.session = SimpleNamespace(research_task_id="task-1")
    monkeypatch.setattr(
        routes_research, "_approval_service",
        lambda: SimpleNamespace(get_session=lambda *_args: store.session),
    )
    session_detail = routes_research.get_research_session("session-with-missing-task")
    assert session_detail.status_code == 404

    listed = routes_research.list_research_artifacts("session-with-missing-task", report_version=None)
    downloaded = routes_research.download_research_artifact(
        "session-with-missing-task", "a1", mode="attachment",
    )
    assert listed.status_code == 404
    assert downloaded.status_code == 404
    assert store.artifact_list_reads == 0
    assert store.artifact_reads == 0


def test_session_detail_uses_the_same_published_artifact_filter(monkeypatch):
    store = _ArtifactStore(
        artifacts=[_artifact("pending", 1), _artifact("published", 2), _artifact("legacy", 3)],
        reports=[_report(1, "generating", False), _report(2, "completed", True)],
    )
    store.get_session_plan = lambda *_args: None
    store.list_session_plans = lambda *_args: []
    store.list_approvals = lambda *_args: []
    store.list_notifications = lambda *_args: []
    monkeypatch.setattr(routes_research, "_store", lambda: store)
    monkeypatch.setattr(
        routes_research, "_approval_service",
        lambda: SimpleNamespace(get_session=lambda *_args: store.session),
    )
    monkeypatch.setattr(
        routes_research, "_service",
        lambda: SimpleNamespace(reconcile_session_projection=lambda *_args: store.session),
    )

    result = routes_research.get_research_session("session-1")

    assert [item["artifact_id"] for item in result["artifacts"]] == ["published", "legacy"]
