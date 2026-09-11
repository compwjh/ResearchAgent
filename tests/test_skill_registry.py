"""spec-023 Task03 — Skill 注册表与读写 API 测试（TDD，离线可重复）。

覆盖边界：
- .agents/skills 不存在/为空 → 200 空数组，不得 500
- SKILL.md 无 frontmatter / frontmatter 损坏 → name 回退目录名，desc/tools 空，列表不失败
- 状态文件缺失/损坏 → 全部回退 enabled=true
- GET/PATCH 不存在 name → 404（统一错误体 SKILL_NOT_FOUND）
- PATCH 参数非法（非 bool / 缺字段）→ 400（INVALID_REQUEST）
- 写状态文件必须原子
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.skills.service import SkillRegistryService

SKILL_WITH_TOOLS = """---
name: demo-skill
description: 一个示例 Skill
tools:
  - search_catalog
  - kb_search
---

# Demo

正文内容。
"""

SKILL_NO_TOOLS = """---
name: plain-skill
description: 没有声明 tools 的 Skill
---

只有正文。
"""

SKILL_NO_FRONTMATTER = """# 没有 frontmatter 的文件

正文在这里。
"""

SKILL_CORRUPT_FRONTMATTER = """---
name: "unterminated
description: 损坏的 YAML
---

正文。
"""

SKILL_MISSING_NAME = """---
description: 缺少 name 字段
---

正文。
"""


def _write_skill(root: Path, name: str, content: str) -> Path:
    directory = Path(root) / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(content, encoding="utf-8")
    return directory


class SkillRegistryServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "skills"
        self.state = Path(self.tmp.name) / "skill-state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _service(self) -> SkillRegistryService:
        return SkillRegistryService(skills_dir=self.root, state_path=self.state)

    # --- 目录边界 ---
    def test_missing_skills_dir_returns_empty(self):
        svc = SkillRegistryService(skills_dir=self.root / "nope", state_path=self.state)
        self.assertEqual(svc.list_skills(), [])
        self.assertIsNone(svc.get_skill("anything"))

    def test_empty_skills_dir_returns_empty(self):
        self.root.mkdir(parents=True)
        self.assertEqual(self._service().list_skills(), [])

    # --- frontmatter 解析 ---
    def test_list_parses_frontmatter(self):
        _write_skill(self.root, "demo-skill", SKILL_WITH_TOOLS)
        skills = self._service().list_skills()
        self.assertEqual(len(skills), 1)
        skill = skills[0]
        self.assertEqual(skill.name, "demo-skill")
        self.assertEqual(skill.description, "一个示例 Skill")
        self.assertEqual(skill.tools, ["search_catalog", "kb_search"])
        self.assertTrue(skill.enabled)

    def test_name_falls_back_to_dir_without_frontmatter(self):
        _write_skill(self.root, "fallback-name", SKILL_NO_FRONTMATTER)
        summary = self._service().list_skills()[0]
        self.assertEqual(summary.name, "fallback-name")
        self.assertEqual(summary.description, "")
        self.assertEqual(summary.tools, [])
        # body 保留全文（经详情接口获取）
        detail = self._service().get_skill("fallback-name")
        self.assertIsNotNone(detail)
        self.assertIn("没有 frontmatter", detail.body)

    def test_corrupt_frontmatter_falls_back(self):
        _write_skill(self.root, "corrupt-name", SKILL_CORRUPT_FRONTMATTER)
        skill = self._service().list_skills()[0]
        self.assertEqual(skill.name, "corrupt-name")
        self.assertEqual(skill.description, "")
        self.assertEqual(skill.tools, [])

    def test_missing_name_key_falls_back_to_dir(self):
        _write_skill(self.root, "dir-as-name", SKILL_MISSING_NAME)
        skill = self._service().list_skills()[0]
        self.assertEqual(skill.name, "dir-as-name")

    def test_tools_defaults_to_empty(self):
        _write_skill(self.root, "plain-skill", SKILL_NO_TOOLS)
        skill = self._service().list_skills()[0]
        self.assertEqual(skill.tools, [])

    def test_body_excludes_frontmatter(self):
        _write_skill(self.root, "demo-skill", SKILL_WITH_TOOLS)
        skill = self._service().get_skill("demo-skill")
        self.assertIsNotNone(skill)
        self.assertIn("正文内容", skill.body)
        self.assertNotIn("description:", skill.body)

    # --- 状态文件 ---
    def test_state_missing_all_enabled_true(self):
        _write_skill(self.root, "demo-skill", SKILL_WITH_TOOLS)
        self.assertTrue(self._service().list_skills()[0].enabled)

    def test_state_corrupt_all_enabled_true(self):
        _write_skill(self.root, "demo-skill", SKILL_WITH_TOOLS)
        self.state.write_text("{ this is not valid json", encoding="utf-8")
        self.assertTrue(self._service().list_skills()[0].enabled)

    def test_state_disables_skill(self):
        _write_skill(self.root, "demo-skill", SKILL_WITH_TOOLS)
        self.state.write_text(
            json.dumps({"schema_version": "skill-state-v1", "skills": {"demo-skill": {"enabled": False}}, "tools": {}}),
            encoding="utf-8",
        )
        self.assertFalse(self._service().list_skills()[0].enabled)

    def test_get_skill_unknown_returns_none(self):
        _write_skill(self.root, "demo-skill", SKILL_WITH_TOOLS)
        self.assertIsNone(self._service().get_skill("nope"))

    def test_patch_unknown_skill_returns_none(self):
        self.assertIsNone(self._service().set_enabled("nope", True))

    def test_patch_creates_state_and_returns_summary(self):
        _write_skill(self.root, "demo-skill", SKILL_WITH_TOOLS)
        updated = self._service().set_enabled("demo-skill", False)
        self.assertIsNotNone(updated)
        self.assertFalse(updated.enabled)
        # 状态文件已原子写入
        self.assertTrue(self.state.exists())
        data = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], "skill-state-v1")
        self.assertEqual(data["tools"], {})
        self.assertEqual(data["skills"]["demo-skill"]["enabled"], False)
        # 没有遗留临时文件
        self.assertFalse(any(p.name.endswith(".tmp") for p in Path(self.tmp.name).iterdir()))

    def test_patch_persists_across_calls(self):
        _write_skill(self.root, "demo-skill", SKILL_WITH_TOOLS)
        svc = self._service()
        svc.set_enabled("demo-skill", False)
        self.assertFalse(svc.list_skills()[0].enabled)


class SkillApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "skills"
        self.state = Path(self.tmp.name) / "skill-state.json"
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def _patch_registry(self):
        svc = SkillRegistryService(skills_dir=self.root, state_path=self.state)
        return patch("backend.app.api.routes_skills.get_skill_registry", return_value=svc)

    def test_list_skills_empty_200(self):
        self.root.mkdir(parents=True)
        with self._patch_registry():
            resp = self.client.get("/api/skills")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"skills": []})

    def test_list_skills_with_entries_200(self):
        _write_skill(self.root, "demo-skill", SKILL_WITH_TOOLS)
        with self._patch_registry():
            resp = self.client.get("/api/skills")
        self.assertEqual(resp.status_code, 200)
        skills = resp.json()["skills"]
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]["name"], "demo-skill")
        self.assertEqual(skills[0]["tools"], ["search_catalog", "kb_search"])
        self.assertTrue(skills[0]["enabled"])
        self.assertNotIn("body", skills[0])

    def test_get_skill_detail_includes_body(self):
        _write_skill(self.root, "demo-skill", SKILL_WITH_TOOLS)
        with self._patch_registry():
            resp = self.client.get("/api/skills/demo-skill")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["name"], "demo-skill")
        self.assertIn("正文内容", body["body"])

    def test_get_unknown_skill_404(self):
        with self._patch_registry():
            resp = self.client.get("/api/skills/nope")
        self.assertEqual(resp.status_code, 404)
        payload = resp.json()
        self.assertEqual(payload["error_code"], "SKILL_NOT_FOUND")
        self.assertIn("request_id", payload)
        self.assertFalse(payload["retryable"])

    def test_patch_skill_updates_200(self):
        _write_skill(self.root, "demo-skill", SKILL_WITH_TOOLS)
        with self._patch_registry():
            resp = self.client.patch("/api/skills/demo-skill", json={"enabled": False})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["name"], "demo-skill")
        self.assertFalse(payload["enabled"])
        self.assertTrue(self.state.exists())

    def test_patch_unknown_skill_404(self):
        with self._patch_registry():
            resp = self.client.patch("/api/skills/nope", json={"enabled": True})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error_code"], "SKILL_NOT_FOUND")

    def test_patch_missing_field_400(self):
        _write_skill(self.root, "demo-skill", SKILL_WITH_TOOLS)
        with self._patch_registry():
            resp = self.client.patch("/api/skills/demo-skill", json={})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error_code"], "INVALID_REQUEST")

    def test_patch_non_bool_400(self):
        _write_skill(self.root, "demo-skill", SKILL_WITH_TOOLS)
        for bad in [{"enabled": "yes"}, {"enabled": 1}, {"enabled": None}]:
            with self.subTest(bad=bad), self._patch_registry():
                resp = self.client.patch("/api/skills/demo-skill", json=bad)
            self.assertEqual(resp.status_code, 400, msg=f"expected 400 for {bad}")
            self.assertEqual(resp.json()["error_code"], "INVALID_REQUEST")

    def test_missing_skills_dir_api_200(self):
        # 目录不存在不得 500
        with patch(
            "backend.app.api.routes_skills.get_skill_registry",
            return_value=SkillRegistryService(skills_dir=self.root / "missing", state_path=self.state),
        ):
            resp = self.client.get("/api/skills")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"skills": []})


class SkillRealIntegrationTests(unittest.TestCase):
    """端到端：默认注册表读取真实 .agents/skills，仅做只读断言。"""

    def setUp(self):
        self.client = TestClient(app)

    def test_real_list_includes_usenix_skills(self):
        resp = self.client.get("/api/skills")
        self.assertEqual(resp.status_code, 200)
        names = {s["name"] for s in resp.json()["skills"]}
        self.assertIn("usenix-accepted-papers", names)
        self.assertIn("usenix-paper-catalog-search", names)


if __name__ == "__main__":
    unittest.main()
