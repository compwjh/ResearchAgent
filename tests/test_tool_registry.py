"""spec-023 Task04 — Tool 注册表、状态文件与启停 API 测试（TDD，离线可重复）。

Tool = 执行层原子动作，注册表唯一事实源是代码（backend.app.skills.registry）。
覆盖边界：
- 注册表为空（理论不发生）→ 200 空数组，不 500
- 状态文件缺失/损坏 → 全部回退 enabled=true
- GET/PATCH 不存在 name → 404（统一错误体 TOOL_NOT_FOUND）
- PATCH 参数非法（非 bool / 缺字段）→ 400（INVALID_REQUEST）
- tools 段写入必须原子，且与 skills 段共存互不覆盖（不能把 skills 段写丢）
- 禁用 Tool 只改状态，不得删除注册项
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.skills.state_store import SkillStateStore
from backend.app.skills.tool_service import ToolRegistryService

REQUIRED_TOOL_NAMES = {
    "search_paper_catalog",
    "download_and_import_paper",
    "kb_search",
    "kb_ask",
}


def _make_service(registry=None, state_path=None, tmp_root=None):
    if state_path is None:
        state_path = Path(tmp_root.name) / "skill-state.json"
    if registry is None:
        from backend.app.skills.registry import build_default_tool_registry

        registry = build_default_tool_registry()
    return ToolRegistryService(registry=registry, state_path=state_path)


class ToolRegistryServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "skill-state.json"

    def tearDown(self):
        self.tmp.cleanup()

    # --- 注册表与状态回退 ---
    def test_empty_registry_returns_empty(self):
        svc = _make_service(registry=[], state_path=self.state)
        self.assertEqual(svc.list_tools(), [])
        self.assertIsNone(svc.get_tool("anything"))

    def test_default_registry_lists_required_tools(self):
        svc = _make_service(state_path=self.state)
        names = {t.name for t in svc.list_tools()}
        self.assertTrue(REQUIRED_TOOL_NAMES.issubset(names))
        for tool in svc.list_tools():
            self.assertTrue(tool.description)
            self.assertTrue(tool.entry)  # 每个 Tool 必须指向真实代码入口

    def test_state_missing_all_enabled_true(self):
        svc = _make_service(state_path=self.state)
        for tool in svc.list_tools():
            self.assertTrue(tool.enabled)

    def test_state_corrupt_all_enabled_true(self):
        self.state.write_text("{ this is not valid json", encoding="utf-8")
        svc = _make_service(state_path=self.state)
        for tool in svc.list_tools():
            self.assertTrue(tool.enabled)

    def test_enabled_reflects_state_file(self):
        self.state.write_text(
            json.dumps(
                {
                    "schema_version": "skill-state-v1",
                    "skills": {},
                    "tools": {"kb_search": {"enabled": False}},
                }
            ),
            encoding="utf-8",
        )
        svc = _make_service(state_path=self.state)
        by_name = {t.name: t for t in svc.list_tools()}
        self.assertFalse(by_name["kb_search"].enabled)
        # 未出现在状态文件中的 Tool 默认启用
        self.assertTrue(by_name["kb_ask"].enabled)

    def test_get_tool_unknown_returns_none(self):
        svc = _make_service(state_path=self.state)
        self.assertIsNone(svc.get_tool("nope"))

    def test_patch_unknown_tool_returns_none(self):
        svc = _make_service(state_path=self.state)
        self.assertIsNone(svc.set_enabled("nope", False))

    def test_patch_writes_tools_segment_atomically(self):
        svc = _make_service(state_path=self.state)
        updated = svc.set_enabled("kb_search", False)
        self.assertIsNotNone(updated)
        self.assertFalse(updated.enabled)
        self.assertTrue(self.state.exists())
        data = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], "skill-state-v1")
        self.assertEqual(data["skills"], {})
        self.assertEqual(data["tools"]["kb_search"]["enabled"], False)
        # 没有遗留临时文件
        self.assertFalse(any(p.name.endswith(".tmp") for p in Path(self.tmp.name).iterdir()))

    def test_disable_only_changes_state_not_registry(self):
        svc = _make_service(state_path=self.state)
        svc.set_enabled("kb_ask", False)
        # 注册项仍在，只是 enabled 变化
        self.assertIsNotNone(svc.get_tool("kb_ask"))
        again = _make_service(state_path=self.state)
        self.assertFalse(again.get_tool("kb_ask").enabled)
        # 其余注册项不受影响
        self.assertTrue(again.get_tool("kb_search").enabled)

    def test_tools_segment_coexists_with_skills_segment(self):
        # 先启用一个 skill（走既有 SkillStateStore.set_enabled）
        store = SkillStateStore(self.state)
        store.set_enabled("demo-skill", False)
        # 再启用一个 tool
        svc = _make_service(state_path=self.state)
        svc.set_enabled("kb_search", False)
        data = json.loads(self.state.read_text(encoding="utf-8"))
        # skills 段不能被 tool 写入覆盖
        self.assertEqual(data["skills"]["demo-skill"]["enabled"], False)
        self.assertEqual(data["tools"]["kb_search"]["enabled"], False)
        self.assertEqual(data["schema_version"], "skill-state-v1")

    def test_tool_enabled_re_enable_persists(self):
        svc = _make_service(state_path=self.state)
        svc.set_enabled("kb_search", False)
        svc.set_enabled("kb_search", True)
        data = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertTrue(data["tools"]["kb_search"]["enabled"])


class ToolApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "skill-state.json"
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def _patch_registry(self, registry=None):
        if registry is None:
            from backend.app.skills.registry import build_default_tool_registry

            registry = build_default_tool_registry()
        svc = ToolRegistryService(registry=registry, state_path=self.state)
        return patch("backend.app.api.routes_tools.get_tool_registry", return_value=svc)

    def test_list_tools_200(self):
        with self._patch_registry():
            resp = self.client.get("/api/tools")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("tools", body)
        names = {t["name"] for t in body["tools"]}
        self.assertTrue(REQUIRED_TOOL_NAMES.issubset(names))
        for tool in body["tools"]:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("enabled", tool)
            self.assertTrue(tool["enabled"])

    def test_get_tool_detail_200(self):
        with self._patch_registry():
            resp = self.client.get("/api/tools/kb_search")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["name"], "kb_search")
        self.assertIn("description", body)
        self.assertTrue(body["enabled"])

    def test_list_tools_empty_registry_200(self):
        with self._patch_registry(registry=[]):
            resp = self.client.get("/api/tools")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"tools": []})

    def test_get_unknown_tool_404(self):
        with self._patch_registry():
            resp = self.client.get("/api/tools/nope")
        self.assertEqual(resp.status_code, 404)
        payload = resp.json()
        self.assertEqual(payload["error_code"], "TOOL_NOT_FOUND")
        self.assertFalse(payload["retryable"])

    def test_patch_tool_updates_200(self):
        with self._patch_registry():
            resp = self.client.patch("/api/tools/kb_search", json={"enabled": False})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["name"], "kb_search")
        self.assertFalse(body["enabled"])
        self.assertTrue(self.state.exists())

    def test_patch_unknown_tool_404(self):
        with self._patch_registry():
            resp = self.client.patch("/api/tools/nope", json={"enabled": True})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error_code"], "TOOL_NOT_FOUND")

    def test_patch_missing_field_400(self):
        with self._patch_registry():
            resp = self.client.patch("/api/tools/kb_search", json={})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error_code"], "INVALID_REQUEST")

    def test_patch_non_bool_400(self):
        for bad in [{"enabled": "yes"}, {"enabled": 1}, {"enabled": None}]:
            with self.subTest(bad=bad), self._patch_registry():
                resp = self.client.patch("/api/tools/kb_search", json=bad)
            self.assertEqual(resp.status_code, 400, msg="expected 400 for %s" % bad)
            self.assertEqual(resp.json()["error_code"], "INVALID_REQUEST")

    def test_patch_preserves_skills_segment(self):
        # 通过既有 store 先写 skills 段
        SkillStateStore(self.state).set_enabled("demo-skill", False)
        with self._patch_registry():
            resp = self.client.patch("/api/tools/kb_search", json={"enabled": False})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(data["skills"]["demo-skill"]["enabled"], False)
        self.assertEqual(data["tools"]["kb_search"]["enabled"], False)


class ToolRealIntegrationTests(unittest.TestCase):
    """端到端：读取真实代码注册表，只做只读断言。"""

    def setUp(self):
        self.client = TestClient(app)

    def test_real_list_includes_required_tools(self):
        resp = self.client.get("/api/tools")
        self.assertEqual(resp.status_code, 200)
        names = {t["name"] for t in resp.json()["tools"]}
        self.assertTrue(REQUIRED_TOOL_NAMES.issubset(names))


if __name__ == "__main__":
    unittest.main()
