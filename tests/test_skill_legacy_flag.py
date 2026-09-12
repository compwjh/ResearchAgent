"""spec-032.2 Task01 — Skill 遗留（legacy）标记磁盘→API 透传测试（TDD，离线可重复）。

覆盖边界：
- frontmatter `status: legacy` -> legacy=True（大小写/空白容错）
- 无 status / status 为其它值 / frontmatter 缺失或损坏 / status 非字符串 -> legacy=False，不抛异常
- GET /api/skills、GET /api/skills/{name}、PATCH /api/skills/{name} 均返回 legacy 布尔字段
- 真实 .agents/skills：两个遗留 Skill legacy=true，两个编排 Skill legacy=false（列表仍返回全部）
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.skills.service import SkillRegistryService

# --- 与 tests/test_skill_registry.py 同构的最小用例，便于精确控制 frontmatter ---
SKILL_LEGACY = """---
name: legacy-skill
description: 遗留技能
tools: [some_tool]
status: legacy
---

正文。
"""

SKILL_NO_STATUS = """---
name: active-skill
description: 现行技能
tools: [some_tool]
---

正文。
"""

SKILL_STATUS_OTHER = """---
name: other-status-skill
description: 其它状态
status: active
---

正文。
"""

SKILL_STATUS_EMPTY = """---
name: empty-status-skill
description: 空状态
status:
---

正文。
"""

SKILL_STATUS_NON_STRING = """---
name: numeric-status-skill
description: 非字符串状态
status: 123
---

正文。
"""

SKILL_STATUS_LIST = """---
name: list-status-skill
description: 列表状态
status: [legacy]
---

正文。
"""

SKILL_STATUS_CASE_WS = """---
name: case-status-skill
description: 大小写与空白容错
status: "  LEGACY  "
---

正文。
"""

SKILL_CORRUPT_FRONTMATTER = """---
name: "unterminated
status: legacy
---

正文。
"""

SKILL_NO_FRONTMATTER = """# 没有 frontmatter 的文件

正文在这里。
"""


def _write_skill(root: Path, name: str, content: str) -> Path:
    directory = Path(root) / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(content, encoding="utf-8")
    return directory


class SkillLegacyScanTests(unittest.TestCase):
    """验收 1、2：扫描层的 legacy 透传与容错。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "skills"
        self.state = Path(self.tmp.name) / "skill-state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _service(self) -> SkillRegistryService:
        return SkillRegistryService(skills_dir=self.root, state_path=self.state)

    def test_status_legacy_marks_true(self):
        _write_skill(self.root, "legacy-skill", SKILL_LEGACY)
        summary = self._service().list_skills()[0]
        self.assertIs(summary.legacy, True)

    def test_status_legacy_case_and_whitespace_tolerated(self):
        _write_skill(self.root, "case-status-skill", SKILL_STATUS_CASE_WS)
        self.assertIs(self._service().list_skills()[0].legacy, True)

    def test_missing_status_marks_false(self):
        _write_skill(self.root, "active-skill", SKILL_NO_STATUS)
        self.assertIs(self._service().list_skills()[0].legacy, False)

    def test_status_other_value_marks_false(self):
        _write_skill(self.root, "other-status-skill", SKILL_STATUS_OTHER)
        self.assertIs(self._service().list_skills()[0].legacy, False)

    def test_status_null_marks_false(self):
        _write_skill(self.root, "empty-status-skill", SKILL_STATUS_EMPTY)
        self.assertIs(self._service().list_skills()[0].legacy, False)

    def test_status_non_string_marks_false(self):
        """容错回归保护：非字符串 status 不得抛异常。"""
        _write_skill(self.root, "numeric-status-skill", SKILL_STATUS_NON_STRING)
        _write_skill(self.root, "list-status-skill", SKILL_STATUS_LIST)
        by_name = {s.name: s for s in self._service().list_skills()}
        self.assertIs(by_name["numeric-status-skill"].legacy, False)
        self.assertIs(by_name["list-status-skill"].legacy, False)

    def test_corrupt_frontmatter_marks_false_without_raising(self):
        _write_skill(self.root, "corrupt-name", SKILL_CORRUPT_FRONTMATTER)
        self.assertIs(self._service().list_skills()[0].legacy, False)

    def test_missing_frontmatter_marks_false_without_raising(self):
        _write_skill(self.root, "fallback-name", SKILL_NO_FRONTMATTER)
        self.assertIs(self._service().list_skills()[0].legacy, False)

    def test_detail_and_summary_agree_on_legacy(self):
        _write_skill(self.root, "legacy-skill", SKILL_LEGACY)
        svc = self._service()
        self.assertIs(svc.get_skill("legacy-skill").legacy, True)
        self.assertIs(svc.set_enabled("legacy-skill", False).legacy, True)

    def test_legacy_does_not_affect_enabled_semantics(self):
        """遗留标记不得自动禁用，也不影响启用/禁用。"""
        _write_skill(self.root, "legacy-skill", SKILL_LEGACY)
        svc = self._service()
        self.assertIs(svc.list_skills()[0].enabled, True)
        self.assertIs(svc.list_skills()[0].legacy, True)
        self.assertIs(svc.set_enabled("legacy-skill", False).enabled, False)
        self.assertIs(svc.list_skills()[0].legacy, True)


class SkillLegacyApiTests(unittest.TestCase):
    """验收 3、4：API 响应含 legacy 布尔字段。"""

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

    def test_list_response_contains_legacy_boolean(self):
        _write_skill(self.root, "legacy-skill", SKILL_LEGACY)
        _write_skill(self.root, "active-skill", SKILL_NO_STATUS)
        with self._patch_registry():
            resp = self.client.get("/api/skills")
        self.assertEqual(resp.status_code, 200)
        by_name = {s["name"]: s for s in resp.json()["skills"]}
        # 列表仍返回全部（不做过滤）
        self.assertEqual(set(by_name), {"legacy-skill", "active-skill"})
        self.assertIs(by_name["legacy-skill"]["legacy"], True)
        self.assertIs(by_name["active-skill"]["legacy"], False)

    def test_get_detail_response_contains_legacy(self):
        _write_skill(self.root, "legacy-skill", SKILL_LEGACY)
        with self._patch_registry():
            resp = self.client.get("/api/skills/legacy-skill")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIs(payload["legacy"], True)
        self.assertIn("body", payload)

    def test_patch_response_contains_legacy(self):
        _write_skill(self.root, "legacy-skill", SKILL_LEGACY)
        with self._patch_registry():
            resp = self.client.patch("/api/skills/legacy-skill", json={"enabled": False})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIs(payload["legacy"], True)
        self.assertIs(payload["enabled"], False)
        self.assertNotIn("body", payload)


class SkillLegacyRealIntegrationTests(unittest.TestCase):
    """验收 3：真实 .agents/skills 上，遗留两个为 true、编排两个为 false。"""

    LEGACY_SKILLS = ("usenix-accepted-papers", "usenix-paper-catalog-search")
    ORCHESTRATION_SKILLS = ("usenix-catalog-orchestration", "usenix-download-orchestration")

    def setUp(self):
        self.client = TestClient(app)

    def test_real_list_legacy_flags(self):
        resp = self.client.get("/api/skills")
        self.assertEqual(resp.status_code, 200)
        skills = resp.json()["skills"]
        self.assertTrue(all(isinstance(s.get("legacy"), bool) for s in skills))
        by_name = {s["name"]: s for s in skills}
        for name in self.LEGACY_SKILLS:
            self.assertIn(name, by_name)
            self.assertIs(by_name[name]["legacy"], True, msg=f"{name} 应为遗留")
        for name in self.ORCHESTRATION_SKILLS:
            self.assertIn(name, by_name)
            self.assertIs(by_name[name]["legacy"], False, msg=f"{name} 不应为遗留")

    def test_real_detail_legacy_flag(self):
        resp = self.client.get("/api/skills/usenix-accepted-papers")
        self.assertEqual(resp.status_code, 200)
        self.assertIs(resp.json()["legacy"], True)


if __name__ == "__main__":
    unittest.main()
