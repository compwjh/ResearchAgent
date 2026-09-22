"""spec-023 Task04 — Tool 注册表、状态文件与启停 API 测试（TDD，离线可重复）。

Tool = 执行层原子动作，注册表唯一事实源是代码（backend.app.skills.registry）。
覆盖边界：
- 注册表为空（理论不发生）→ 200 空数组，不 500
- 状态文件缺失/损坏 → 全部回退 enabled=true
- GET/PATCH 不存在 name → 404（统一错误体 TOOL_NOT_FOUND）
- PATCH 参数非法（非 bool / 缺字段）→ 400（INVALID_REQUEST）
- tools 段写入必须原子，且与 skills 段共存互不覆盖（不能把 skills 段写丢）
- 禁用 Tool 只改状态，不得删除注册项

spec-034 — ``GET /api/tools/{name}/code`` 只读入口源码视图，覆盖边界：
- 5 个注册 Tool 全部返回非空 ``code``，``lineno`` 满足 M-01 判据
- M-03 负例：entry 落到模块对象 / 类对象 → ``TOOL_CODE_UNAVAILABLE``，且不得返回整文件/整个类体
- M-04：错误 ``message`` 为固定文案，不含异常详情与绝对路径
- M-06：名称精确匹配，不接受请求方传入的点分路径
- M-07：禁用的 Tool 仍可查看；既有三接口响应结构逐字不变
"""

import ast
import json
import re
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.platform.config import BASE_DIR
from backend.app.skills.models import ToolEntry
from backend.app.skills.registry import build_default_tool_registry
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


def _entry_func_name(entry: str) -> str:
    """entry 的最后一段即真实函数/方法名（Tool 名与函数名不必相同）。"""
    return entry.rsplit(".", 1)[-1]


def _assert_m01_lineno(case, payload) -> None:
    """M-01 判据：``lineno`` 是源码块首行 —— 该行是 ``def <name>``，
    或是装饰器行且其后首个非装饰器行是 ``def <name>``。

    禁止使用「第 lineno 行必须含 def」这一判据（带装饰器时首行是装饰器行）。
    ``<name>`` 取 ``entry`` 最后一段（如 ``kb_search`` → ``hybrid_search``）。
    """
    code = payload["code"]
    lineno = payload["lineno"]
    func_name = _entry_func_name(payload["entry"])
    case.assertTrue(code, msg="code 不得为空")
    case.assertIsInstance(lineno, int)
    case.assertGreaterEqual(lineno, 1)

    # code 必须是「源码块原文」，其首行即 lineno 行
    file_lines = (BASE_DIR / payload["file"]).read_text(encoding="utf-8").splitlines()
    case.assertEqual(file_lines[lineno - 1].strip(), code.splitlines()[0].strip())

    node = ast.parse(textwrap.dedent(code)).body[0]
    case.assertIsInstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    case.assertEqual(node.name, func_name)

    if code.lstrip().startswith("@"):
        # 首行是装饰器行 → lineno 落在装饰器行，def 在其后
        case.assertTrue(node.decorator_list, msg="首行为装饰器行时必须解析出装饰器")
        case.assertEqual(node.decorator_list[0].lineno, 1)
        def_line = file_lines[lineno - 1 + (node.lineno - 1)]
        case.assertTrue(
            def_line.lstrip().startswith("def "),
            msg=f"装饰器行之后的首个非装饰器行应为 def，实际 {def_line!r}",
        )
        case.assertGreater(node.lineno, 1, msg="带装饰器时 lineno 必须落在装饰器行而非 def 行")
    else:
        case.assertRegex(file_lines[lineno - 1].lstrip(), rf"(async\s+)?def\s+{re.escape(func_name)}\b")


class ToolCodeApiTests(unittest.TestCase):
    """spec-034 — GET /api/tools/{name}/code（只读，实时解析，不加缓存）。"""

    ALL_TOOL_NAMES = {
        "search_paper_catalog",
        "download_and_import_paper",
        "fetch_paper_detail",
        "kb_search",
        "kb_ask",
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "skill-state.json"
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def _patch_registry(self, registry=None):
        if registry is None:
            registry = build_default_tool_registry()
        svc = ToolRegistryService(registry=registry, state_path=self.state)
        return patch("backend.app.api.routes_tools.get_tool_registry", return_value=svc)

    def _get_code(self, name, registry=None, **kwargs):
        with self._patch_registry(registry):
            return self.client.get(f"/api/tools/{name}/code", **kwargs)

    def _single_entry_registry(self, name, entry):
        return [ToolEntry(name=name, description="测试用注册项", entry=entry)]

    # --- 正常路径：5 个注册 Tool 全覆盖（含类方法与模块函数两种 entry 形态）---
    def test_all_registered_tools_return_non_empty_code(self):
        for name in sorted(self.ALL_TOOL_NAMES):
            with self.subTest(tool=name):
                resp = self._get_code(name)
                self.assertEqual(resp.status_code, 200)
                payload = resp.json()
                self.assertEqual(payload["name"], name)
                self.assertTrue(payload["entry"])
                self.assertEqual(payload["language"], "python")
                self.assertTrue(payload["code"])
                self.assertTrue(payload["file"].endswith(".py"))
                _assert_m01_lineno(self, payload)

    def test_class_method_and_module_function_entries(self):
        # 类方法形态 X.Y
        resp = self._get_code("search_paper_catalog")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["entry"].endswith(".PaperDiscoverySearchService.search"))
        # 模块函数形态
        resp = self._get_code("kb_search")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["entry"].endswith(".retrieve.hybrid_search"))

    def test_decorated_route_function_returns_decorator_line(self):
        """被装饰的 kb_ask：返回原始函数源码，lineno 落在装饰器行（M-01）。"""
        resp = self._get_code("kb_ask")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        lines = payload["code"].splitlines()
        self.assertTrue(lines[0].lstrip().startswith('@router.post("/kb/ask")'), msg=lines[0])
        self.assertIn("def kb_ask(", payload["code"])
        file_lines = (BASE_DIR / payload["file"]).read_text(encoding="utf-8").splitlines()
        self.assertTrue(file_lines[payload["lineno"] - 1].lstrip().startswith("@"))
        # def 行在 lineno 之后（实证 lineno=952 为装饰器行，def 在 953）
        self.assertNotIn("def kb_ask", file_lines[payload["lineno"] - 1])
        _assert_m01_lineno(self, payload)

    def test_file_is_repo_relative_and_body_has_no_absolute_path(self):
        for name in sorted(self.ALL_TOOL_NAMES):
            with self.subTest(tool=name):
                resp = self._get_code(name)
                payload = resp.json()
                self.assertFalse(payload["file"].startswith("/"))
                self.assertTrue((BASE_DIR / payload["file"]).is_file())
                self.assertNotIn("/Users", resp.text)
                self.assertNotIn(str(BASE_DIR), resp.text)

    # --- M-03 负例：解析终点不得是模块对象 / 类对象 ---
    def test_module_entry_is_unavailable_and_not_whole_file(self):
        registry = self._single_entry_registry("module_entry", "backend.app.api.routes_kb")
        resp = self._get_code("module_entry", registry=registry)
        self.assertEqual(resp.status_code, 404)
        payload = resp.json()
        self.assertEqual(payload["error_code"], "TOOL_CODE_UNAVAILABLE")
        self.assertFalse(payload["retryable"])
        self.assertNotIn("code", payload)
        # 不得返回整文件源码
        self.assertNotIn("import ", resp.text)
        self.assertLess(len(resp.text), 1000)

    def test_class_entry_is_unavailable_and_not_class_body(self):
        registry = self._single_entry_registry("class_entry", "backend.app.skills.models.ToolEntry")
        resp = self._get_code("class_entry", registry=registry)
        self.assertEqual(resp.status_code, 404)
        payload = resp.json()
        self.assertEqual(payload["error_code"], "TOOL_CODE_UNAVAILABLE")
        self.assertNotIn("code", payload)
        self.assertNotIn("def to_dict", resp.text)

    def test_builtin_entry_is_unavailable(self):
        registry = self._single_entry_registry("builtin_entry", "builtins.len")
        resp = self._get_code("builtin_entry", registry=registry)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error_code"], "TOOL_CODE_UNAVAILABLE")
        self.assertNotIn("code", resp.json())

    def test_unresolvable_entry_is_unavailable(self):
        registry = self._single_entry_registry(
            "broken_entry", "backend.app.no_such_module_xyz.no_such_func"
        )
        resp = self._get_code("broken_entry", registry=registry)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error_code"], "TOOL_CODE_UNAVAILABLE")
        self.assertNotIn("code", resp.json())

    def test_empty_entry_is_unavailable(self):
        registry = self._single_entry_registry("empty_entry", "")
        resp = self._get_code("empty_entry", registry=registry)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error_code"], "TOOL_CODE_UNAVAILABLE")

    def test_out_of_repo_source_is_unavailable_without_leaking_path(self):
        """解析到的文件不在仓库根目录内（软链/越界）→ 不可用，且不泄漏该路径。"""
        with patch("backend.app.skills.tool_service._REPO_ROOT", Path(self.tmp.name)):
            resp = self._get_code("kb_search")
        self.assertEqual(resp.status_code, 404)
        payload = resp.json()
        self.assertEqual(payload["error_code"], "TOOL_CODE_UNAVAILABLE")
        self.assertNotIn("code", payload)
        self.assertNotIn(str(self.tmp.name), resp.text)
        self.assertNotIn("/Users", resp.text)
        self.assertNotIn("retrieve.py", resp.text)

    # --- M-04：固定文案，不含异常详情 ---
    def test_error_message_is_fixed_text_without_exception_details(self):
        module_resp = self._get_code(
            "module_entry",
            registry=self._single_entry_registry("module_entry", "backend.app.api.routes_kb"),
        )
        broken_entry = "backend.app.no_such_module_xyz.no_such_func"
        broken_resp = self._get_code(
            "broken_entry", registry=self._single_entry_registry("broken_entry", broken_entry)
        )
        module_body = module_resp.json()
        broken_body = broken_resp.json()
        # 两种不同的失败原因得到完全相同的 message → 固定文案
        self.assertEqual(module_body["message"], broken_body["message"])
        message = module_body["message"]
        self.assertTrue(message.strip())
        for leaked in (
            "/",
            "\\",
            "Traceback",
            "Error",
            "No module named",
            "inspect",
            broken_entry,
            str(BASE_DIR),
            "routes_kb",
        ):
            self.assertNotIn(leaked, message, msg=f"message 泄漏了 {leaked!r}")

    # --- M-06：名称精确匹配，不接受请求方传入的点分路径 ---
    def test_unknown_name_returns_tool_not_found(self):
        resp = self._get_code("nope")
        self.assertEqual(resp.status_code, 404)
        payload = resp.json()
        self.assertEqual(payload["error_code"], "TOOL_NOT_FOUND")
        self.assertFalse(payload["retryable"])
        self.assertNotIn("code", payload)

    def test_dotted_path_as_name_is_rejected(self):
        for name in (
            "backend.app.api.routes_kb",
            "backend.app.api.routes_kb.kb_ask",
            "backend.app.api.routes_kb:kb_ask",
            "KB_SEARCH",
            "kb",
        ):
            with self.subTest(name=name):
                resp = self._get_code(name)
                self.assertEqual(resp.status_code, 404)
                self.assertEqual(resp.json()["error_code"], "TOOL_NOT_FOUND")

    def test_request_cannot_override_entry(self):
        """entry 只从注册表读取：query / header / body 均不得改变结果。"""
        baseline = self._get_code("kb_search").json()
        overridden = self._get_code(
            "kb_search",
            params={"entry": "backend.app.api.routes_kb"},
            headers={"X-Entry": "backend.app.api.routes_kb"},
        ).json()
        self.assertEqual(overridden, baseline)
        self.assertTrue(baseline["entry"].endswith(".retrieve.hybrid_search"))

    # --- M-07：禁用的 Tool 仍可查看；既有三接口响应结构不变 ---
    def test_disabled_tool_still_returns_code(self):
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
        with self._patch_registry():
            detail = self.client.get("/api/tools/kb_search")
            resp = self.client.get("/api/tools/kb_search/code")
        self.assertFalse(detail.json()["enabled"])
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["code"])

    def test_existing_endpoints_response_shape_unchanged(self):
        expected = {"name", "description", "enabled"}
        with self._patch_registry():
            listing = self.client.get("/api/tools")
            detail = self.client.get("/api/tools/kb_search")
            patched = self.client.patch("/api/tools/kb_search", json={"enabled": True})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(set(listing.json().keys()), {"tools"})
        for tool in listing.json()["tools"]:
            self.assertEqual(set(tool.keys()), expected)
        self.assertEqual(set(detail.json().keys()), expected)
        self.assertEqual(set(patched.json().keys()), expected)
        self.assertNotIn("entry", detail.json())

    def test_code_endpoint_does_not_touch_state_file(self):
        with self._patch_registry():
            resp = self.client.get("/api/tools/kb_search/code")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
