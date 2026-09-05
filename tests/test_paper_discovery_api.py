import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.app.api import routes
from backend.app.domain.paper_discovery import ConferenceSource, PaperCandidate, SearchSession
from backend.app.main import app
from backend.app.services.paper_discovery_store import PaperDiscoveryStore
from backend.app.services.paper_download import PaperDownloadError


class HealthEndpointPaperDiscoveryFlagTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("backend.app.api.routes.get_available_models", return_value=[])
    def test_health_defaults_paper_discovery_enabled(self, _mock_models):
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("PAPER_DISCOVERY_ENABLED", None)
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            set(body),
            {"status", "model", "models", "paper_discovery_enabled"},
        )
        self.assertIs(body["paper_discovery_enabled"], True)

    @patch("backend.app.api.routes.get_available_models", return_value=[])
    def test_health_reports_disabled_paper_discovery(self, _mock_models):
        with patch.dict("os.environ", {"PAPER_DISCOVERY_ENABLED": "false"}):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["paper_discovery_enabled"], False)


class PaperDiscoveryRequestContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_conference_update_invalid_body_uses_stable_422_error(self):
        response = self.client.patch("/api/papers/conferences/ccs", json={"enabled": "not-a-bool"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            set(response.json()),
            {"code", "message", "retryable", "request_id"},
        )
        self.assertEqual(response.json()["code"], "INVALID_CONFERENCE_UPDATE")
        self.assertFalse(response.json()["retryable"])

    def test_paper_search_invalid_body_uses_stable_422_error(self):
        response = self.client.post(
            "/api/papers/search",
            json={"query": "", "conference_id": "ccs"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            set(response.json()),
            {"code", "message", "retryable", "request_id"},
        )
        self.assertEqual(response.json()["code"], "INVALID_QUERY")
        self.assertFalse(response.json()["retryable"])


class PaperConferenceSearchEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        import tempfile
        self.database = tempfile.NamedTemporaryFile(suffix=".sqlite3")
        self.store = PaperDiscoveryStore(self.database.name)
        self.custom = ConferenceSource(
            conference_id="ml-sec",
            name="Machine Learning Security Workshop",
            short_name="MLSec",
            dblp_stream="conf/mlsec",
            venue_aliases=["Machine Learning Security Workshop"],
            built_in=False,
        )
        self.store.save_conference(self.custom)

    def tearDown(self):
        self.database.close()

    def test_search_matches_configured_name_short_name_and_id_case_insensitively(self):
        with patch.object(routes, "_paper_store", return_value=self.store):
            for query, expected_id in (
                ("uSeNiX", "usenix-security"),
                ("IEEE symposium", "ieee-sp"),
                ("  MLSec  ", "ml-sec"),
            ):
                with self.subTest(query=query):
                    response = self.client.get("/api/papers/conferences/search", params={"q": query})

                self.assertEqual(response.status_code, 200)
                conferences = response.json()["conferences"]
                self.assertEqual([item["conference_id"] for item in conferences], [expected_id])

    def test_search_returns_only_existing_safe_conference_payload(self):
        with patch.object(routes, "_paper_store", return_value=self.store):
            response = self.client.get("/api/papers/conferences/search", params={"q": "machine learning"})

        self.assertEqual(response.status_code, 200)
        configured = next(item for item in self.store.list_conferences() if item.conference_id == self.custom.conference_id)
        self.assertEqual(response.json()["conferences"], [routes._conference_payload(configured)])

    def test_empty_and_overlong_query_use_stable_errors(self):
        for query, expected_code in (("   ", "INVALID_CONFERENCE_QUERY"), ("x" * 101, "CONFERENCE_QUERY_TOO_LONG")):
            with self.subTest(expected_code=expected_code):
                response = self.client.get("/api/papers/conferences/search", params={"q": query})

            self.assertEqual(response.status_code, 400)
            self.assertEqual(set(response.json()), {"code", "message", "retryable", "request_id"})
            self.assertEqual(response.json()["code"], expected_code)
            self.assertFalse(response.json()["retryable"])

    def test_disabled_search_does_not_open_store(self):
        with patch.dict("os.environ", {"PAPER_DISCOVERY_ENABLED": "false"}), patch.object(
            routes, "_paper_store", side_effect=AssertionError("store must not be accessed")
        ):
            response = self.client.get("/api/papers/conferences/search", params={"q": "ccs"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "PAPER_DISCOVERY_DISABLED")


class PaperImportEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        # SQLite in-memory databases are connection-local, so use a temporary
        # file-backed store for the route's separate read connections.
        import tempfile
        self.database = tempfile.NamedTemporaryFile(suffix=".sqlite3")
        self.store = PaperDiscoveryStore(self.database.name)
        self.store.save_search(
            SearchSession("search-1", "security", "2099-01-01T00:00:00Z"),
            [PaperCandidate(
                "candidate-1", "search-1", "A Safe Paper", "ccs", "CCS", year=2025,
                authors=["Author"], pdf_url="https://papers.example/paper.pdf",
            )],
        )
        self.original_enabled = routes._paper_discovery_enabled
        self.original_settings = routes.article_settings

    def tearDown(self):
        self.database.close()

    def test_import_resolves_candidate_server_side_and_returns_result_fields(self):
        result = {
            "paper_id": "paper-1", "stored_name": "2025-CCS-A-Safe-Paper.pdf",
            "status": "indexed", "error_code": None, "existing": False,
        }
        with patch.object(routes, "_paper_store", return_value=self.store), patch.object(
            routes, "import_candidate", return_value=result
        ) as importer:
            response = self.client.post(
                "/api/papers/imports",
                json={"search_id": "search-1", "candidate_id": "candidate-1"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), result)
        candidate = importer.call_args.args[0]
        self.assertEqual(candidate.pdf_url, "https://papers.example/paper.pdf")
        self.assertEqual(importer.call_args.kwargs["conference_short_name"], "CCS")

    def test_candidate_hostname_cannot_expand_download_allowlist(self):
        routes.article_settings = routes.article_settings.model_copy(
            update={"paper_discovery_allowed_hosts": ["trusted.example"]}
        )
        try:
            self.assertEqual(routes._paper_candidate_hosts(self.store.get_candidate("search-1", "candidate-1")), {"trusted.example"})
        finally:
            routes.article_settings = self.original_settings

    def test_import_rejects_client_metadata_with_stable_validation_error(self):
        response = self.client.post(
            "/api/papers/imports",
            json={"search_id": "search-1", "candidate_id": "candidate-1", "pdf_url": "https://evil.example/x"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "INVALID_IMPORT_REQUEST")
        self.assertEqual(set(response.json()), {"code", "message", "retryable", "request_id"})

    def test_import_disabled_does_not_open_store_or_import(self):
        with patch.dict("os.environ", {"PAPER_DISCOVERY_ENABLED": "false"}), patch.object(
            routes, "_paper_store", side_effect=AssertionError("store must not be accessed")
        ), patch.object(routes, "import_candidate", side_effect=AssertionError("import must not run")):
            response = self.client.post(
                "/api/papers/imports",
                json={"search_id": "search-1", "candidate_id": "candidate-1"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "PAPER_DISCOVERY_DISABLED")

    def test_import_rejects_expired_search_before_external_import(self):
        expired = PaperDiscoveryStore(self.database.name)
        expired.save_search(
            SearchSession("expired", "security", "2000-01-01T00:00:00Z"),
            [PaperCandidate("candidate-1", "expired", "A Safe Paper", "ccs", "CCS", pdf_url="https://papers.example/x")],
        )
        with patch.object(routes, "_paper_store", return_value=expired), patch.object(
            routes, "import_candidate", side_effect=AssertionError("import must not run")
        ):
            response = self.client.post(
                "/api/papers/imports",
                json={"search_id": "expired", "candidate_id": "candidate-1"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "SEARCH_EXPIRED")

    def test_import_maps_download_errors_to_stable_status(self):
        errors = {
            "LOGIN_REQUIRED": 424,
            "DOWNLOAD_BLOCKED": 400,
            "DOWNLOAD_TIMEOUT": 424,
            "INVALID_PDF": 502,
        }
        for code, expected_status in errors.items():
            with self.subTest(code=code), patch.object(routes, "_paper_store", return_value=self.store), patch.object(
                routes, "import_candidate", side_effect=PaperDownloadError(code, "safe message")
            ):
                response = self.client.post(
                    "/api/papers/imports",
                    json={"search_id": "search-1", "candidate_id": "candidate-1"},
                )
            self.assertEqual(response.status_code, expected_status)
            self.assertEqual(response.json()["code"], code)
            self.assertEqual(set(response.json()), {"code", "message", "retryable", "request_id"})


class AcceptedPaperYearBoundaryTests(unittest.TestCase):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 5, tzinfo=tz)

    def setUp(self):
        self.client = TestClient(app)
        self.search = Mock(return_value=SimpleNamespace(records=(), warnings=(), error_code=None))
        self.service = SimpleNamespace(
            accepted_source=SimpleNamespace(search=self.search),
            default_years=5,
            default_limit=20,
            search_ttl_seconds=86400,
            store=SimpleNamespace(save_search=Mock()),
        )
        self.source = ConferenceSource(
            conference_id="usenix-security",
            name="USENIX Security Symposium",
            short_name="USENIX Security",
            dblp_stream="conf/uss",
            venue_aliases=["USENIX Security Symposium"],
            built_in=True,
            discovery_routes=[{"route_type": "usenix_accepted", "enabled": True}],
        )
        self.store = SimpleNamespace(list_conferences=lambda: [self.source])

    def _get(self, **params):
        with patch.object(routes, "_paper_discovery_enabled", return_value=True), patch.object(
            routes, "_paper_store", return_value=self.store
        ), patch.object(routes, "_paper_search_service", return_value=self.service), patch.object(
            routes, "datetime", self.FrozenDateTime
        ):
            return self.client.get("/api/papers/conferences/usenix-security/accepted", params=params)

    def test_default_years_are_the_most_recent_complete_years(self):
        response = self._get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.search.call_args.args[2], [2021, 2022, 2023, 2024, 2025])
        self.assertNotIn(2026, self.search.call_args.args[2])

    def test_explicit_current_year_is_forwarded_but_future_year_is_rejected(self):
        response = self._get(year=2026)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.search.call_args.args[2], [2026])

        self.search.reset_mock()
        response = self._get(year=2027)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "INVALID_ACCEPTED_YEAR")
        self.search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
