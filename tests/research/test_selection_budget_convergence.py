from backend.app.research.application.planner import Planner


def test_search_workers_receive_global_target_budget_to_absorb_overlap():
    draft = Planner().build_plan(
        goal="比较安全研究方法与局限",
        target_paper_count=5,
        language="zh",
        source_ids=("usenix",),
        scope={"from_year": 2024, "to_year": 2024},
    )

    search_items = [item for item in draft.work_items if item["task_type"] == "search_catalog"]

    assert len(search_items) == 2
    assert [item["params"]["max_results"] for item in search_items] == [5, 5]
