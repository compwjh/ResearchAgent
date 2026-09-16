"""会话深链 `/c/{conversation_id}` 的服务端兜底。

前端用 `window.location.pathname` 做客户端路由（``app.js`` 里 `/c/<id>` 的匹配），
因此直接访问或刷新深链时，服务端必须回 ``index.html``，否则会拿到 JSON 404、页面打不开。
同时 `/api/*` 未命中的请求仍必须是真正的 404，不能被兜底伪装成 200 的 HTML。
"""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_conversation_deep_link_returns_index_html() -> None:
    with TestClient(app) as client:
        response = client.get("/c/a2490306a9e24eecb92f89e51f2580c3")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert response.text.startswith("<!DOCTYPE html>")


def test_unknown_api_path_returns_404_json() -> None:
    with TestClient(app) as client:
        response = client.get("/api/definitely-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_index_root_still_serves_html() -> None:
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
