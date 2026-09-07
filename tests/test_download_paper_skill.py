import unittest
from unittest.mock import patch

from backend.app.article_assistant.application.download_paper_skill import (
    SKILL_NAME,
    WORKER_MODEL,
    build_download_plan,
    skill_status,
)
from backend.app.article_assistant.domain.article import ArticleCandidate


class _FakeModel:
    def __init__(self, content):
        self._content = content

    def invoke(self, _prompt):
        return type("Response", (), {"content": self._content})()


def _public_candidate() -> ArticleCandidate:
    return ArticleCandidate(
        candidate_id="candidate-public",
        title="A Public Paper",
        pdf_url="https://example.com/public.pdf",
        pdf_url_status="public_pdf",
    )


class DownloadPaperSkillTests(unittest.TestCase):
    def test_build_plan_rejects_wrong_worker_model(self):
        with self.assertRaises(ValueError):
            build_download_plan(_public_candidate(), "qwen3:8b")

    def test_build_plan_rejects_non_public_candidate(self):
        candidate = ArticleCandidate(
            candidate_id="c-non-public",
            title="Login Paper",
            pdf_url="https://example.com/paper.pdf",
            pdf_url_status="login_required",
        )
        with self.assertRaises(ValueError):
            build_download_plan(candidate)

    def test_build_plan_rejects_non_https_url(self):
        candidate = ArticleCandidate(
            candidate_id="c-http",
            title="Http Paper",
            pdf_url="http://example.com/paper.pdf",
            pdf_url_status="public_pdf",
        )
        with self.assertRaises(ValueError):
            build_download_plan(candidate)

    def test_build_plan_returns_structured_message(self):
        candidate = _public_candidate()
        with patch(
            "backend.app.article_assistant.application.download_paper_skill.create_chat_model",
            return_value=_FakeModel('{"user_message": "已确认可下载，可由后端保存并完成校验。"}'),
        ):
            plan = build_download_plan(candidate)
        self.assertEqual(plan["skill_name"], SKILL_NAME)
        self.assertEqual(plan["execution_mode"], "public_download")
        self.assertEqual(plan["candidate_id"], "candidate-public")
        self.assertEqual(plan["pdf_url"], "https://example.com/public.pdf")
        self.assertTrue(plan["output_filename"].endswith(".pdf"))
        self.assertIn("已确认可下载", plan["user_message"])

    def test_build_plan_intercepts_untrusted_model_output(self):
        # The worker model tries to smuggle a URL, file path and command.
        # None of these may override the backend-determined values.
        candidate = _public_candidate()
        smuggled = (
            '{"user_message": "ok", "pdf_url": "http://evil/x.pdf", '
            '"command": "rm -rf /", "output_filename": "../../secrets.pdf"}'
        )
        with patch(
            "backend.app.article_assistant.application.download_paper_skill.create_chat_model",
            return_value=_FakeModel(smuggled),
        ):
            plan = build_download_plan(candidate)
        self.assertNotIn("command", plan)
        self.assertEqual(plan["pdf_url"], "https://example.com/public.pdf")
        self.assertNotIn("../", plan["output_filename"])
        self.assertEqual(plan["user_message"], "ok")

    def test_build_plan_falls_back_on_non_json(self):
        candidate = _public_candidate()
        with patch(
            "backend.app.article_assistant.application.download_paper_skill.create_chat_model",
            return_value=_FakeModel("this is not json"),
        ):
            plan = build_download_plan(candidate)
        self.assertEqual(plan["execution_mode"], "public_download")
        self.assertLessEqual(len(plan["user_message"]), 300)

    def test_build_plan_falls_back_on_overlong_message(self):
        candidate = _public_candidate()
        long_message = '{"user_message": "' + ("x" * 400) + '"}'
        with patch(
            "backend.app.article_assistant.application.download_paper_skill.create_chat_model",
            return_value=_FakeModel(long_message),
        ):
            plan = build_download_plan(candidate)
        self.assertLessEqual(len(plan["user_message"]), 300)
        self.assertNotIn("x" * 400, plan["user_message"])

    def test_skill_status_reports_metadata_and_path(self):
        status = skill_status([WORKER_MODEL])
        self.assertEqual(status["skill_name"], SKILL_NAME)
        self.assertIn("skill_path", status)
        self.assertIn("version", status)
        self.assertIn("declared_name", status)
        self.assertIn("worker_model_available", status)


if __name__ == "__main__":
    unittest.main()
