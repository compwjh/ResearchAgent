import json
from types import SimpleNamespace

from backend.app.research.application.session_plan_generation import build_session_plan_output


class _IntakeStore:
    def __init__(self, fields):
        self.fields = [
            SimpleNamespace(field_name=name, value_json=json.dumps(value, ensure_ascii=False))
            for name, value in fields.items()
        ]

    def list_intake_fields(self, _draft_id, _owner_id):
        return list(self.fields)


def test_approved_intake_topic_reaches_each_search_query_without_replacing_objective():
    objective = "比较 USENIX Security 2022 认证安全论文的方法与证据边界"
    store = _IntakeStore({
        "topic": "authentication security",
        "objective": objective,
        "time_range": {"from": 2022, "to": 2022},
        "sources": ["usenix"],
        "language": "zh",
        "constraints": ["target_paper_count:5", "min_paper_count:5"],
    })
    session = SimpleNamespace(intake_draft_id="draft-1", current_plan_version=0)

    plan = build_session_plan_output(store, session, "owner")

    search_items = [
        item for item in plan["work_items"]
        if item["task_type"] == "search_catalog"
    ]
    assert len(search_items) >= 2
    assert all("authentication security" in item["params"]["query"] for item in search_items)
    assert plan["objective"] == objective
    critic = next(item for item in plan["work_items"] if item["task_type"] == "check_coverage")
    assert critic["params"]["goal"] == objective
