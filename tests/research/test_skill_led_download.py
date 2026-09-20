import unittest
from unittest.mock import MagicMock, patch

from backend.app.article_assistant.application.download_paper_skill import (
    COOKIE_SESSION,
    LITERATURE_MUTUAL_AID,
    POW_CHALLENGE,
    PUBLIC_HTTPS,
    OpenCliUnavailable,
    build_skill_plan,
    decide_download_method,
    download_under_skill,
    fetch_cookies_via_opencli,
)
from backend.app.article_assistant.domain.article import ArticleCandidate


def _public_candidate() -> ArticleCandidate:
    return ArticleCandidate(
        candidate_id="c-public",
        title="Public Paper",
        pdf_url="https://example.com/public.pdf",
        pdf_url_status="public_pdf",
    )


def _login_candidate(source_name="Elsevier", url="https://elsevier.com/paper") -> ArticleCandidate:
    return ArticleCandidate(
        candidate_id="c-login",
        title="Login Paper",
        pdf_url=url,
        article_url=url,
        source_name=source_name,
        pdf_url_status="login_required",
    )


class DecideDownloadMethodTests(unittest.TestCase):
    def test_public_https_is_public(self):
        self.assertEqual(decide_download_method(_public_candidate()), PUBLIC_HTTPS)

    def test_ablesci_uses_literature_mutual_aid(self):
        self.assertEqual(decide_download_method(_login_candidate(source_name="科研通", url="https://ablesci.com/x")), LITERATURE_MUTUAL_AID)

    def test_pmc_uses_pow_challenge(self):
        self.assertEqual(decide_download_method(_login_candidate(source_name="PMC", url="https://pmc.ncbi.nlm.nih.gov/x")), POW_CHALLENGE)

    def test_fallback_is_cookie_session(self):
        self.assertEqual(decide_download_method(_login_candidate(source_name="Elsevier", url="https://elsevier.com/x")), COOKIE_SESSION)


class OpenCliTests(unittest.TestCase):
    @patch("backend.app.article_assistant.application.download_paper_skill.shutil.which", return_value=None)
    def test_fetch_cookies_raises_when_opencli_missing(self, _mock_which):
        with self.assertRaises(OpenCliUnavailable):
            fetch_cookies_via_opencli()


class DownloadUnderSkillTests(unittest.TestCase):
    def test_public_path_yields_skill_fields(self):
        with patch(
            "backend.app.article_assistant.application.download_paper_skill.download_article",
            return_value=iter([{"type": "result", "file_path": "/tmp/x.pdf"}]),
        ):
            events = list(download_under_skill(_public_candidate(), MagicMock()))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["skill_name"], "download-paper")
        self.assertEqual(events[0]["download_method"], PUBLIC_HTTPS)

    def test_non_public_without_opencli_yields_error_event(self):
        with patch(
            "backend.app.article_assistant.application.download_paper_skill.fetch_cookies_via_opencli",
            side_effect=OpenCliUnavailable("本机未安装 opencli"),
        ):
            events = list(download_under_skill(_login_candidate(), MagicMock()))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(events[0]["skill_name"], "download-paper")
        self.assertEqual(events[0]["download_outcome"], "source_unavailable")
        self.assertIn("opencli", events[0]["user_message"])


class BuildSkillPlanTests(unittest.TestCase):
    def test_public_plan_is_skill_led_public(self):
        with patch("backend.app.article_assistant.application.download_paper_skill.build_download_plan", return_value={"user_message": "ok"}):
            plan = build_skill_plan(_public_candidate())
        self.assertEqual(plan["skill_name"], "download-paper")
        self.assertEqual(plan["orchestration"], "skill_led")
        self.assertEqual(plan["download_method"], PUBLIC_HTTPS)
        self.assertFalse(plan["requires_credentials"])
        self.assertEqual(plan["user_message"], "ok")

    def test_restricted_plan_requires_credentials(self):
        plan = build_skill_plan(_login_candidate())
        self.assertEqual(plan["download_method"], COOKIE_SESSION)
        self.assertTrue(plan["requires_credentials"])
        self.assertIn("opencli", plan["user_message"])


if __name__ == "__main__":
    unittest.main()
