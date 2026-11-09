"""``list_active_projects()`` SQL 清洁（评审 LOW-2 / 本任务 C4）的行为回归锁。

删除 ``status='active' AND status!='deleted'`` 中恒真的后半条件属于零行为变更：
过滤语义仍是 active + 未删除 + 以 projects 表为唯一数据源（不扫孤儿 md）。
同时锁住 ``get_project`` / ``update_project`` / ``list_projects`` 里**仍然有效**的
``status!='deleted'`` 条件，防止本次清洁被误扩大到兄弟方法。
"""

from __future__ import annotations

from backend.app.memory.repository import OWNER_ID, MemoryRepository


def test_list_active_projects_returns_only_active_in_project_id_order(tmp_path):
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    p1 = repo.create_project(OWNER_ID, "项目甲")
    p2 = repo.create_project(OWNER_ID, "项目乙")
    p3 = repo.create_project(OWNER_ID, "项目丙（无 md 文件）")
    deleted = repo.create_project(OWNER_ID, "已删除项目")
    repo.update_project(deleted.project_id, OWNER_ID, status="deleted")
    archived = repo.create_project(OWNER_ID, "归档项目")
    repo.update_project(archived.project_id, OWNER_ID, status="archived")

    # 不写任何 projects/*.md：孤儿/缺失 md 都不该影响以表为唯一数据源的结果。
    rows = repo.list_active_projects(OWNER_ID)

    ids = [project.project_id for project in rows]
    assert set(ids) == {p1.project_id, p2.project_id, p3.project_id}
    assert ids == sorted(ids), "ORDER BY project_id 必须保留"
    assert all(project.status == "active" for project in rows)
    assert repo.list_active_projects("another-owner") == [], "owner_id 参数化绑定必须保留"


def test_sibling_project_queries_still_exclude_deleted_rows(tmp_path):
    """兄弟方法的 status!='deleted' 是有效条件，不属于本次冗余清理范围。"""
    repo = MemoryRepository(tmp_path / "memory.sqlite3")
    active = repo.create_project(OWNER_ID, "正常项目")
    deleted = repo.create_project(OWNER_ID, "已删除项目")
    repo.update_project(deleted.project_id, OWNER_ID, status="deleted")

    assert repo.get_project(deleted.project_id, OWNER_ID) is None
    assert repo.update_project(deleted.project_id, OWNER_ID, name="改名") is None
    listed, _cursor = repo.list_projects(OWNER_ID)
    assert {project.project_id for project in listed} == {active.project_id}
