"""Langfuse dashboard 重建（--force）幂等契约测试。

用 httpx.MockTransport + 内存态假服务打桩 httpx.get/post/delete，
不触真实 Langfuse、不执行破坏性线上重跑。

覆盖：① list_widgets 按 meta.totalPages 翻页 / limit=100 / Basic auth / 异常 fail-open；
② delete_widget 的 URL 与 auth；③ --force 只按 manifest ID 删、不按名称/全量删、
先清 placement；④ 重复 --force 两次 widget 总数不增；⑤ manifest 读写与缺失降级；
⑥ 默认模式仍跳过同名、零写入、40 widget ID 不变。
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from unittest import mock

import httpx
import pytest

from scripts import setup_langfuse_dashboards as mod

HOST = "http://langfuse.test"
AUTH = ("pk-test", "sk-test")
BASIC = "Basic " + base64.b64encode(b"pk-test:sk-test").decode()
BASE = f"{HOST}/api/public/unstable"


@dataclass
class Call:
    method: str
    url: str
    auth: tuple[str, str] | None
    params: dict[str, Any] | None
    payload: dict[str, Any] | None
    headers: dict[str, str]


class FakeLangfuse:
    """内存态 Langfuse unstable public API（不触真实服务）。"""

    def __init__(self) -> None:
        self.dashboards: dict[str, dict[str, Any]] = {}
        self.widgets: dict[str, dict[str, Any]] = {}
        self.placements: list[tuple[str, str]] = []
        self.calls: list[Call] = []
        self.conflicts = 0
        self._seq = 0
        self.fail_status_pages: set[int] = set()

    def _next(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{self._seq:04d}"

    # --- 预置 ---
    def seed_widget(self, name: str, widget_id: str | None = None) -> str:
        wid = widget_id or self._next("w")
        self.widgets[wid] = {"id": wid, "name": name}
        return wid

    def seed_dashboard(self, name: str, widget_ids: list[str]) -> str:
        did = self._next("d")
        self.dashboards[did] = {"id": did, "name": name, "description": ""}
        for wid in widget_ids:
            self.placements.append((did, wid))
        return did

    # --- transport ---
    @staticmethod
    def _resp(request: httpx.Request, status: int, payload: Any) -> httpx.Response:
        return httpx.Response(status, json=payload, request=request)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        body = json.loads(request.content or b"{}") if method == "POST" else {}

        if path == "/api/public/unstable/dashboards":
            if method == "GET":
                data = sorted(self.dashboards.values(), key=lambda d: d["name"])
                return self._resp(request, 200, {"data": data, "meta": {"totalItems": len(data)}})
            if method == "POST":
                did = self._next("d")
                self.dashboards[did] = {"id": did, "name": body["name"], "description": body.get("description", "")}
                return self._resp(request, 201, {"id": did})

        if path.startswith("/api/public/unstable/dashboards/") and path.endswith("/placements") and method == "POST":
            did = path.split("/")[-2]
            self.placements.append((did, body["widgetId"]))
            return self._resp(request, 201, {"id": self._next("p")})

        if path.startswith("/api/public/unstable/dashboards/") and method == "DELETE":
            did = path.rsplit("/", 1)[-1]
            self.dashboards.pop(did, None)
            self.placements = [(d, w) for d, w in self.placements if d != did]
            return self._resp(request, 200, {"message": "deleted"})

        if path == "/api/public/unstable/dashboard-widgets":
            if method == "GET":
                page = int(request.url.params.get("page", "1"))
                limit = int(request.url.params.get("limit", "50"))
                if page in self.fail_status_pages:
                    return self._resp(request, 500, {"message": "boom"})
                items = sorted(self.widgets.values(), key=lambda w: w["id"])
                start = (page - 1) * limit
                chunk = items[start:start + limit]
                total_pages = max(1, (len(items) + limit - 1) // limit)
                return self._resp(request, 200, {
                    "data": chunk,
                    "meta": {"page": page, "limit": limit, "totalItems": len(items), "totalPages": total_pages},
                })
            if method == "POST":
                wid = self._next("w")
                self.widgets[wid] = {"id": wid, "name": body["name"]}
                return self._resp(request, 201, {"id": wid})

        if path.startswith("/api/public/unstable/dashboard-widgets/") and method == "DELETE":
            wid = path.rsplit("/", 1)[-1]
            if any(w == wid for _d, w in self.placements):
                self.conflicts += 1
                return self._resp(request, 409, {"message": "widget still placed"})
            if wid not in self.widgets:
                return self._resp(request, 404, {"message": "not found"})
            del self.widgets[wid]
            return self._resp(request, 200, {"message": "Dashboard widget successfully deleted"})

        return self._resp(request, 404, {"message": f"unhandled {method} {path}"})


@pytest.fixture
def fake():
    state = FakeLangfuse()
    transport = httpx.MockTransport(state.handle)

    def dispatch(method: str, url: str, **kwargs: Any) -> httpx.Response:
        auth = kwargs.get("auth")
        request = httpx.Request(method, url, params=kwargs.get("params"), json=kwargs.get("json"))
        if auth is not None:
            request.headers["Authorization"] = "Basic " + base64.b64encode(
                f"{auth[0]}:{auth[1]}".encode()
            ).decode()
        state.calls.append(Call(
            method=method,
            url=str(request.url),
            auth=auth,
            params=kwargs.get("params"),
            payload=kwargs.get("json"),
            headers={k.lower(): v for k, v in request.headers.items()},
        ))
        return transport.handle_request(request)

    with (
        mock.patch.object(mod.httpx, "get", side_effect=lambda url, **kw: dispatch("GET", url, **kw)),
        mock.patch.object(mod.httpx, "post", side_effect=lambda url, **kw: dispatch("POST", url, **kw)),
        mock.patch.object(mod.httpx, "delete", side_effect=lambda url, **kw: dispatch("DELETE", url, **kw)),
    ):
        yield state


@pytest.fixture
def builder() -> mod.DashboardBuilder:
    return mod.DashboardBuilder(HOST, *AUTH)


def manifest_payload(widgets: list[dict[str, Any]], project_id: str = "proj-test") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "project_id": project_id,
        "created_at": "2026-11-09T00:00:00+00:00",
        "source": "setup_langfuse_dashboards.py",
        "widgets": widgets,
    }


def entry(widget_id: str, name: str, dashboard_index: int = 0) -> dict[str, Any]:
    return {
        "id": widget_id,
        "name": name,
        "dashboard": mod.DASHBOARDS[dashboard_index]["name"],
        "dashboard_index": dashboard_index,
        "created_at": "2026-11-09T00:00:00+00:00",
    }


# --- ① list_widgets：分页 / totalPages / Basic auth / fail-open -----------------

def test_list_widgets_paginates_by_total_pages_and_uses_basic_auth(fake, builder):
    for i in range(250):
        fake.seed_widget(f"w{i}")

    widgets = builder.list_widgets()

    get_calls = [c for c in fake.calls if c.method == "GET" and "/dashboard-widgets" in c.url]
    assert len(get_calls) == 3
    assert [c.params for c in get_calls] == [
        {"page": 1, "limit": 100},
        {"page": 2, "limit": 100},
        {"page": 3, "limit": 100},
    ]
    assert all(c.auth == AUTH for c in get_calls)
    assert all(c.headers["authorization"] == BASIC for c in get_calls)
    assert len(widgets) == 250
    assert len({w["id"] for w in widgets}) == 250


def test_list_widgets_fails_open_on_http_error(fake, builder, caplog):
    for i in range(250):
        fake.seed_widget(f"w{i}")
    fake.fail_status_pages = {2}

    with caplog.at_level("WARNING"):
        widgets = builder.list_widgets()

    assert len(widgets) == 100  # 只拿到第 1 页，异常不抛出
    assert any(r.levelname == "WARNING" for r in caplog.records)


# --- ② delete_widget：URL / auth / 404 降级 --------------------------------------

def test_delete_widget_uses_id_url_and_basic_auth(fake, builder):
    wid = fake.seed_widget("TTFT P95")

    builder.delete_widget(wid)

    deletes = [c for c in fake.calls if c.method == "DELETE" and "/dashboard-widgets/" in c.url]
    assert len(deletes) == 1
    assert deletes[0].url == f"{BASE}/dashboard-widgets/{wid}"
    assert deletes[0].auth == AUTH
    assert deletes[0].headers["authorization"] == BASIC
    assert wid not in fake.widgets


def test_delete_widget_ignores_missing_widget(fake, builder, caplog):
    with caplog.at_level("WARNING"):
        builder.delete_widget("w-gone")  # 404：已被删/从未存在，不应中断 --force

    assert any(r.levelname == "WARNING" for r in caplog.records)


# --- ③ --force：只按 manifest ID 删，先清 placement，不按名称/全量删 --------------

def test_force_deletes_only_manifest_widget_ids_after_clearing_placements(fake, builder, tmp_path):
    manifest_entries: list[dict[str, Any]] = []
    for index, spec in enumerate(mod.DASHBOARDS):
        w1 = fake.seed_widget(spec["widgets"][0]["name"])
        w2 = fake.seed_widget("TTFT P95" if index == 0 else spec["widgets"][1]["name"])
        fake.seed_dashboard(spec["name"], [w1, w2])
        manifest_entries.append(entry(w1, spec["widgets"][0]["name"], index))
        manifest_entries.append(entry(w2, "TTFT P95" if index == 0 else spec["widgets"][1]["name"], index))

    # 用户手工 widget / 看板：与脚本 widget 重名，但不在 manifest、名字不在 DASHBOARDS
    manual_name = "用户手工看板（不在 DASHBOARDS 定义里）"
    manual_widget = fake.seed_widget("TTFT P95", widget_id="w-manual")
    fake.seed_dashboard(manual_name, [manual_widget])

    manifest_path = tmp_path / "widget-manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload(manifest_entries), ensure_ascii=False), encoding="utf-8")

    mod.run(force=True, builder=builder, manifest_path=manifest_path, width=3, height=2)

    manifest_ids = {e["id"] for e in manifest_entries}
    widget_deletes = [c for c in fake.calls if c.method == "DELETE" and "/dashboard-widgets/" in c.url]
    deleted_ids = {c.url.rsplit("/", 1)[-1] for c in widget_deletes}
    assert deleted_ids == manifest_ids            # 不多不少，只按 manifest ID
    assert "w-manual" not in deleted_ids          # 重名的用户手工 widget 未被误删
    assert "w-manual" in fake.widgets
    assert manual_name in {d["name"] for d in fake.dashboards.values()}  # 用户手工看板未被删

    dash_deletes = [
        c for c in fake.calls
        if c.method == "DELETE" and "/dashboards/" in c.url and "/placements" not in c.url
    ]
    assert len(dash_deletes) == 6                 # 只删 DASHBOARDS 定义的 6 个同名看板

    # 先清 placement（删 dashboard）再删 widget，避免 409
    dash_idx = {i for i, c in enumerate(fake.calls) if c in dash_deletes}
    widget_idx = {i for i, c in enumerate(fake.calls) if c in widget_deletes}
    assert dash_idx and widget_idx
    assert max(dash_idx) < min(widget_idx)
    assert fake.conflicts == 0

    # 重建后 manifest 已更新：旧 ID 全移除、只剩新 40 个
    updated = mod.load_manifest(manifest_path)
    updated_ids = {w["id"] for w in updated["widgets"]}
    assert not (updated_ids & manifest_ids)
    assert len(updated_ids) == 40


# --- ④ 幂等：重复 --force 两次 widget 总数不增、无孤儿 ----------------------------

def test_repeated_force_rebuilds_keep_widget_total_constant(fake, builder, tmp_path):
    manifest_path = tmp_path / "widget-manifest.json"

    mod.run(force=False, builder=builder, manifest_path=manifest_path, width=3, height=2)
    assert len(fake.widgets) == 40
    assert len(fake.dashboards) == 6

    for _ in range(2):
        mod.run(force=True, builder=builder, manifest_path=manifest_path, width=3, height=2)
        assert len(fake.widgets) == 40
        assert len(fake.dashboards) == 6
        placed = {w for _d, w in fake.placements}
        assert set(fake.widgets) == placed                     # 无孤儿
        manifest = mod.load_manifest(manifest_path)
        assert {w["id"] for w in manifest["widgets"]} == set(fake.widgets)
        assert len(builder.list_widgets()) == 40

    assert fake.conflicts == 0


# --- ⑤ manifest 读写与缺失 / 损坏降级 --------------------------------------------

def test_manifest_roundtrip_and_missing_or_corrupt_degrades(tmp_path, caplog):
    path = tmp_path / "nested" / "widget-manifest.json"

    empty = mod.load_manifest(path)
    assert empty["schema_version"] == 1
    assert empty["widgets"] == []
    assert not path.exists()                    # 只读降级不创建文件

    mod.record_widgets(path, [entry("w-1", "A"), entry("w-2", "B")], project_id="proj-x")
    data = mod.load_manifest(path)
    assert data["project_id"] == "proj-x"
    assert [w["id"] for w in data["widgets"]] == ["w-1", "w-2"]
    assert all("created_at" in w and "dashboard" in w for w in data["widgets"])

    mod.record_widgets(path, [entry("w-2", "B")], project_id="proj-x")  # 幂等追加
    assert [w["id"] for w in mod.load_manifest(path)["widgets"]] == ["w-1", "w-2"]

    mod.remove_widgets(path, {"w-1"})
    assert [w["id"] for w in mod.load_manifest(path)["widgets"]] == ["w-2"]

    assert not [p for p in path.parent.iterdir() if p.suffix == ".tmp"]  # 原子写无残留

    path.write_text("{not-json", encoding="utf-8")
    caplog.clear()
    with caplog.at_level("WARNING"):
        degraded = mod.load_manifest(path)
    assert degraded["widgets"] == []
    assert any(r.levelname == "WARNING" for r in caplog.records)


# --- ⑥ 默认模式：跳过同名、零写入、40 widget ID 不变 ------------------------------

def test_default_mode_skips_existing_dashboards_with_zero_writes(fake, builder, tmp_path, capsys):
    for spec in mod.DASHBOARDS:
        ids = [fake.seed_widget(widget["name"]) for widget in spec["widgets"]]
        fake.seed_dashboard(spec["name"], ids)
    assert len(fake.widgets) == 40
    before = set(fake.widgets)

    manifest_path = tmp_path / "widget-manifest.json"
    assert mod.run(force=False, builder=builder, manifest_path=manifest_path, width=3, height=2) == 0

    assert all(c.method == "GET" for c in fake.calls)
    assert not any(c.method in ("POST", "DELETE", "PATCH") for c in fake.calls)
    assert set(fake.widgets) == before
    assert len(fake.widgets) == 40
    assert len(fake.dashboards) == 6
    assert not manifest_path.exists()
    out = capsys.readouterr().out
    assert "新建 0 个，跳过 6 个。" in out
    assert out.count("[跳过]") == 6


# --- ⑤ 补充：manifest 缺失时 --force 如实降级，历史 widget 一律不动 -------------

def test_force_with_missing_manifest_never_deletes_history_widgets(fake, builder, tmp_path):
    """无 manifest 时无法可靠区分「历史 40 widget」与用户手工 widget，一律不动。

    这是 D4 定稿的如实降级：不按名称删、不全量删；也不假装修好——重建仍会
    新建 40 个 widget（历史孤儿无法清理，待单独授权窗口 / 隔离项目验证）。
    """
    for spec in mod.DASHBOARDS:
        ids = [fake.seed_widget(widget["name"]) for widget in spec["widgets"]]
        fake.seed_dashboard(spec["name"], ids)
    assert len(fake.widgets) == 40
    history_ids = set(fake.widgets)

    manifest_path = tmp_path / "never-created.json"
    mod.run(force=True, builder=builder, manifest_path=manifest_path, width=3, height=2)

    widget_deletes = [c for c in fake.calls if c.method == "DELETE" and "/dashboard-widgets/" in c.url]
    assert widget_deletes == []                  # 零 delete_widget 调用（禁止全量删）
    assert history_ids <= set(fake.widgets)     # 历史 40 个 widget 一律保留
    assert len(fake.widgets) == 80              # 如实反映：重建新增 40，历史孤儿未清理
    assert fake.conflicts == 0
