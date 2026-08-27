import unittest

from backend.app.api.routes import download_outcome


class DownloadOutcomeTests(unittest.TestCase):
    def test_unavailable_pdf_has_actionable_message(self):
        outcome, message = download_outcome("not_found")
        self.assertEqual(outcome, "not_found")
        self.assertIn("文章页面", message)
        self.assertIn("合法下载地址", message)

    def test_login_and_rate_limit_are_distinguishable(self):
        login_outcome, login_message = download_outcome("login_required")
        rate_outcome, rate_message = download_outcome("rate_limited")
        self.assertEqual(login_outcome, "login_required")
        self.assertIn("登录", login_message)
        self.assertEqual(rate_outcome, "rate_limited")
        self.assertIn("限流", rate_message)


if __name__ == "__main__":
    unittest.main()
