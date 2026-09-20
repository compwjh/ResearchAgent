import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.app.api import common, routes_paper
from backend.app.main import app
from backend.app.paper_discovery.application.paper_discovery_search import PaperDiscoverySearchService
from backend.app.paper_discovery.domain.paper_discovery import (
    CatalogPaper,
    ConferenceSource,
    PaperCandidate,
    SearchJob,
    SearchResult,
    SearchSession,
)
from backend.app.paper_discovery.infrastructure.paper_discovery_store import PaperDiscoveryStore
from backend.app.paper_discovery.infrastructure.paper_download import PaperDownloadError


class HealthEndpointPaperDiscoveryFlagTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("backend.app.api.routes_system.get_available_models", return_value=[])
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

    @patch("backend.app.api.routes_system.get_available_models", return_value=[])
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

    def test_legacy_sync_paper_search_route_is_removed(self):
        response = self.client.post(
            "/api/papers/search",
            json={"query": "", "conference_id": "ccs"},
        )

        self.assertEqual(response.status_code, 404)


class PaperConferenceSearchEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as self.database:
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
        with patch.object(routes_paper, "_paper_store", return_value=self.store):
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
        with patch.object(routes_paper, "_paper_store", return_value=self.store):
            response = self.client.get("/api/papers/conferences/search", params={"q": "machine learning"})

        self.assertEqual(response.status_code, 200)
        configured = next(item for item in self.store.list_conferences() if item.conference_id == self.custom.conference_id)
        self.assertEqual(response.json()["conferences"], [common._conference_payload(configured)])

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
            routes_paper, "_paper_store", side_effect=AssertionError("store must not be accessed")
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
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as self.database:
            self.store = PaperDiscoveryStore(self.database.name)
        self.store.save_search(
            SearchSession("search-1", "security", "2099-01-01T00:00:00Z"),
            [PaperCandidate(
                "candidate-1", "search-1", "A Safe Paper", "ccs", "CCS", year=2025,
                authors=["Author"], pdf_url="https://papers.example/paper.pdf",
            )],
        )
        self.original_enabled = common._paper_discovery_enabled
        self.original_settings = common.article_settings

    def tearDown(self):
        self.database.close()

    def test_import_resolves_candidate_server_side_and_returns_result_fields(self):
        result = {
            "paper_id": "paper-1", "stored_name": "2025-CCS-A-Safe-Paper.pdf",
            "status": "indexed", "error_code": None, "existing": False,
        }
        with patch.object(routes_paper, "_paper_store", return_value=self.store), patch.object(
            routes_paper, "import_candidate", return_value=result
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
        common.article_settings = common.article_settings.model_copy(
            update={"paper_discovery_allowed_hosts": ["trusted.example"]}
        )
        try:
            self.assertEqual(
                common._paper_candidate_hosts(self.store.get_candidate("search-1", "candidate-1")),
                {"trusted.example", "usenix.org", "www.usenix.org"},
            )
        finally:
            common.article_settings = self.original_settings

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
            routes_paper, "_paper_store", side_effect=AssertionError("store must not be accessed")
        ), patch.object(routes_paper, "import_candidate", side_effect=AssertionError("import must not run")):
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
        with patch.object(routes_paper, "_paper_store", return_value=expired), patch.object(
            routes_paper, "import_candidate", side_effect=AssertionError("import must not run")
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
            with self.subTest(code=code), patch.object(routes_paper, "_paper_store", return_value=self.store), patch.object(
                routes_paper, "import_candidate", side_effect=PaperDownloadError(code, "safe message")
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
        cached_paper = SimpleNamespace(
            catalog_paper_id="cached", publication_stage="accepted", conference_id="usenix-security",
            year=2025, title="Cached Accepted", normalized_title="cached accepted", authors=["Ada"],
            abstract="cached", doi=None, dblp_key=None, official_page_url="https://www.usenix.org/paper",
            official_pdf_url="https://www.usenix.org/paper.pdf",
        )
        self.list_catalog_papers = Mock(
            side_effect=lambda _conference_ids, years, **_kwargs: [cached_paper] if 2025 in years else []
        )
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
        self.store = SimpleNamespace(
            list_conferences=lambda: [self.source],
            list_catalog_papers=self.list_catalog_papers,
            save_search=Mock(),
        )

    def _get(self, **params):
        with patch.object(routes_paper, "_paper_discovery_enabled", return_value=True), patch.object(
            routes_paper, "_paper_store", return_value=self.store
        ), patch.object(routes_paper, "_paper_search_service", return_value=self.service), patch.object(
            routes_paper, "datetime", self.FrozenDateTime
        ):
            return self.client.get("/api/papers/conferences/usenix-security/accepted", params=params)

    def test_default_years_are_the_most_recent_complete_years(self):
        response = self._get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.list_catalog_papers.call_args.args[1], [2021, 2022, 2023, 2024, 2025])
        self.assertNotIn(2026, self.list_catalog_papers.call_args.args[1])
        self.search.assert_not_called()

    def test_explicit_current_year_is_forwarded_but_future_year_is_rejected(self):
        response = self._get(year=2026)
        self.assertEqual(response.status_code, 424)
        self.assertEqual(self.list_catalog_papers.call_args.args[1], [2026])
        self.assertEqual(response.json()["code"], "CATALOG_NOT_READY")

        self.list_catalog_papers.reset_mock()
        response = self._get(year=2027)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "INVALID_ACCEPTED_YEAR")
        self.search.assert_not_called()


class AcceptedCatalogCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as self.database:
            self.store = PaperDiscoveryStore(self.database.name)
        self.accepted_search = Mock(side_effect=AssertionError("accepted source network must not run"))
        self.service = PaperDiscoverySearchService(
            accepted_source=SimpleNamespace(search=self.accepted_search),
            store=self.store,
        )

    def tearDown(self):
        self.database.close()

    def _get(self, **params):
        with patch.object(routes_paper, "_paper_discovery_enabled", return_value=True), patch.object(
            routes_paper, "_paper_store", return_value=self.store
        ), patch.object(routes_paper, "_paper_search_service", return_value=self.service):
            return self.client.get("/api/papers/conferences/usenix-security/accepted", params=params)

    def test_cache_hit_reads_catalog_and_creates_import_snapshot_without_network(self):
        self.store.upsert_catalog_paper(CatalogPaper(
            "accepted-2025", "usenix-security", 2025, "Cached Accepted Paper", "cached accepted paper",
            authors=["Ada"], abstract="A cached abstract", official_page_url="https://www.usenix.org/paper",
            official_pdf_url="https://www.usenix.org/paper.pdf", publication_stage="accepted",
            metadata_hash="accepted-2025-hash", index_status="pending",
        ))

        response = self._get(year=2025, q="cached", limit=10)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([item["title"] for item in body["candidates"]], ["Cached Accepted Paper"])
        self.assertEqual(len(self.store.get_candidates(body["search_id"])), 1)
        self.accepted_search.assert_not_called()

    def test_cache_miss_returns_stable_not_ready_without_network(self):
        response = self._get(year=2025)

        self.assertEqual(response.status_code, 424)
        self.assertEqual(response.json()["code"], "CATALOG_NOT_READY")
        self.assertTrue(response.json()["retryable"])
        self.accepted_search.assert_not_called()


class PaperSingleImportCatalogJobFallbackTests(unittest.TestCase):
    """Task04 修复一：单篇导入在 search_sessions 为空的 catalog-search 场景下，
    必须回退到 search_jobs 解析，而非误报 SEARCH_NOT_FOUND。"""

    def setUp(self):
        self.client = TestClient(app)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as self.database:
            self.store = PaperDiscoveryStore(self.database.name)
        self.now = datetime.now(timezone.utc)
        self.future = (self.now + timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z")

    def tearDown(self):
        self.database.close()

    def _job(self, search_id, status="partial", expires_at=None):
        return SearchJob(
            search_id, "security", [], [], status, "catalog-search-v1",
            False, None, 1, self.now.isoformat(timespec="seconds").replace("+00:00", "Z"),
            None, None, expires_at or self.future,
            self.now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        )

    def _result(self, search_id, catalog_paper_id):
        snapshot = {
            "catalog_paper_id": catalog_paper_id,
            "candidate_id": catalog_paper_id,
            "title": "A Safe Paper",
            "conference_id": "ccs",
            "conference_name": "CCS",
            "year": 2025,
            "authors": ["Author"],
            "pdf_url": "https://papers.example/paper.pdf",
            "article_url": "https://papers.example/paper.html",
            "source_kind": "dblp",
            "source_page_url": "https://papers.example/paper.html",
            "source_links": [{"kind": "pdf", "url": "https://papers.example/paper.pdf"}],
        }
        return SearchResult(search_id, catalog_paper_id, 1, 0.0, None, 0.0, snapshot, "")

    def _catalog_paper(self, catalog_paper_id):
        ts = self.now.isoformat(timespec="seconds").replace("+00:00", "Z")
        return CatalogPaper(
            catalog_paper_id, "ccs", 2025, "A Safe Paper", "a safe paper",
            ["Author"], None, [], None, None, "published",
            "https://www.usenix.org/paper", "https://www.usenix.org/paper.pdf",
            None, None, "hash-" + catalog_paper_id, "pending", 0, ts, ts,
        )

    def test_single_import_resolves_catalog_job_fallback_and_succeeds(self):
        """无 search_session、只有 search_job 时，单篇导入应回退成功（不再误报 SEARCH_NOT_FOUND）。"""
        self.store.upsert_catalog_paper(self._catalog_paper("cp-1"))
        self.store.create_search_job(self._job("job-1"))
        self.store.save_search_result(self._result("job-1", "cp-1"))
        result = {
            "paper_id": "paper-1", "stored_name": "2025-CCS-A-Safe-Paper.pdf",
            "status": "indexed", "error_code": None, "existing": False,
        }
        with patch.object(routes_paper, "_paper_store", return_value=self.store), patch.object(
            routes_paper, "import_candidate", return_value=result
        ) as importer:
            response = self.client.post(
                "/api/papers/imports",
                json={"search_id": "job-1", "candidate_id": "cp-1"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), result)
        # 候选来自 by_id（dict 快照），而非 get_candidate
        self.assertIsInstance(importer.call_args.args[0], dict)
        self.assertEqual(importer.call_args.args[0]["catalog_paper_id"], "cp-1")
        self.assertEqual(importer.call_args.kwargs["conference_short_name"], "CCS")

    def test_single_import_three_search_context_codes_are_mutually_exclusive(self):
        """同一合法 search_id 在不同检索上下文下一律只命中其一：不存在/未就绪/已过期互斥。"""
        past = (self.now - timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
        cases = [
            ("SEARCH_NOT_FOUND", None, None, 404, "搜索会话不存在"),
            ("SEARCH_NOT_READY", "running", self.future, 400, "搜索结果尚未冻结"),
            ("SEARCH_EXPIRED", "partial", past, 400, "搜索会话已过期"),
        ]
        for code, status, expires_at, status_code, message in cases:
            with self.subTest(code=code):
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as database:
                    store = PaperDiscoveryStore(database.name)
                    if status is not None:
                        store.upsert_catalog_paper(self._catalog_paper("cp-x"))
                        store.create_search_job(self._job("job-x", status=status, expires_at=expires_at))
                        store.save_search_result(self._result("job-x", "cp-x"))
                    try:
                        with patch.object(routes_paper, "_paper_store", return_value=store), patch.object(
                            routes_paper, "import_candidate", side_effect=AssertionError("must not import")
                        ):
                            response = self.client.post(
                                "/api/papers/imports",
                                json={"search_id": "job-x", "candidate_id": "cp-x"},
                            )
                    finally:
                        os.unlink(database.name)
                self.assertEqual(response.status_code, status_code)
                body = response.json()
                self.assertEqual(set(body), {"code", "message", "retryable", "request_id"})
                self.assertEqual(body["code"], code)
                self.assertEqual(body["message"], message)
                self.assertFalse(body["retryable"])


class PaperImportBatchErrorSemanticsTests(unittest.TestCase):
    """Task04 修复二：未预期异常不得伪装成 503 IMPORT_BATCH_UNAVAILABLE，
    须落日志并返回可诊断 424 IMPORT_BATCH_ERROR。"""

    def setUp(self):
        self.client = TestClient(app)

    def _assert_unexpected_exception_returns_424_and_logs(self, response):
        self.assertEqual(response.status_code, 424)
        body = response.json()
        self.assertEqual(set(body), {"code", "message", "retryable", "request_id"})
        self.assertEqual(body["code"], "IMPORT_BATCH_ERROR")
        self.assertFalse(body["retryable"])

    def test_create_batch_unexpected_exception_returns_424_and_logs(self):
        with patch.object(routes_paper, "_paper_server_snapshot", return_value=(SimpleNamespace(), [{}])), patch.object(
            routes_paper, "_paper_batch_service"
        ) as service, self.assertLogs("backend.app.api.routes_paper", level="ERROR") as logs:
            service.return_value.create_batch.side_effect = RuntimeError("boom")
            response = self.client.post(
                "/api/papers/imports",
                json={"search_id": "job-1", "candidate_ids": ["cp-1"]},
            )
        self._assert_unexpected_exception_returns_424_and_logs(response)
        self.assertTrue(any("批量导入未预期异常" in record.getMessage() for record in logs.records))

    def test_import_batches_alias_unexpected_exception_returns_424_and_logs(self):
        with patch.object(routes_paper, "_paper_server_snapshot", return_value=(SimpleNamespace(), [{}])), patch.object(
            routes_paper, "_paper_batch_service"
        ) as service, self.assertLogs("backend.app.api.routes_paper", level="ERROR") as logs:
            service.return_value.create_batch.side_effect = RuntimeError("boom")
            response = self.client.post(
                "/api/papers/import-batches",
                json={"search_id": "job-1", "candidate_ids": ["cp-1"]},
            )
        self._assert_unexpected_exception_returns_424_and_logs(response)
        self.assertTrue(any("批量导入未预期异常" in record.getMessage() for record in logs.records))

    def test_get_batch_unexpected_exception_returns_424_and_logs(self):
        with patch.object(routes_paper, "_paper_batch_service") as service, self.assertLogs(
            "backend.app.api.routes_paper", level="ERROR"
        ) as logs:
            service.return_value.get_status.side_effect = RuntimeError("boom")
            response = self.client.get("/api/papers/imports/does-not-matter")
        self._assert_unexpected_exception_returns_424_and_logs(response)
        self.assertTrue(any("批量导入未预期异常" in record.getMessage() for record in logs.records))

    def test_retry_batch_unexpected_exception_returns_424_and_logs(self):
        service = SimpleNamespace(
            store=SimpleNamespace(
                get_batch=Mock(return_value=SimpleNamespace(search_id="s1", status="running")),
                get_items=Mock(return_value=[SimpleNamespace(candidate_id="c1")]),
            ),
            retry_batch=Mock(side_effect=RuntimeError("boom")),
        )
        with patch.object(routes_paper, "_paper_server_snapshot", return_value=(SimpleNamespace(), [{}])), patch.object(
            routes_paper, "_paper_batch_service", return_value=service
        ), self.assertLogs("backend.app.api.routes_paper", level="ERROR") as logs:
            response = self.client.post("/api/papers/imports/bid/retry")
        self._assert_unexpected_exception_returns_424_and_logs(response)
        self.assertTrue(any("批量导入未预期异常" in record.getMessage() for record in logs.records))

    def test_cancel_batch_unexpected_exception_returns_424_and_logs(self):
        service = SimpleNamespace(
            store=SimpleNamespace(
                get_batch=Mock(return_value=SimpleNamespace(search_id="s1", status="queued")),
            ),
            cancel_batch=Mock(side_effect=RuntimeError("boom")),
        )
        with patch.object(routes_paper, "_paper_batch_service", return_value=service), self.assertLogs(
            "backend.app.api.routes_paper", level="ERROR"
        ) as logs:
            response = self.client.post("/api/papers/import-batches/bid/cancel")
        self._assert_unexpected_exception_returns_424_and_logs(response)
        self.assertTrue(any("批量导入未预期异常" in record.getMessage() for record in logs.records))

    def test_resume_item_unexpected_exception_returns_424_and_logs(self):
        service = SimpleNamespace(
            store=SimpleNamespace(get_item=Mock(side_effect=RuntimeError("boom"))),
        )
        with patch.object(routes_paper, "_paper_batch_service", return_value=service), self.assertLogs(
            "backend.app.api.routes_paper", level="ERROR"
        ) as logs:
            response = self.client.post("/api/papers/import-items/iid/resume")
        self._assert_unexpected_exception_returns_424_and_logs(response)
        self.assertTrue(any("批量导入未预期异常" in record.getMessage() for record in logs.records))

    def test_database_locked_conflict_still_returns_503_retryable(self):
        """确属瞬时冲突（DATABASE_LOCKED）仍走 503 retryable，且不被意外异常分支吞掉。"""
        from backend.app.paper_discovery.application.paper_import_batch_service import PaperImportBatchServiceError
        with patch.object(routes_paper, "_paper_server_snapshot", return_value=(SimpleNamespace(), [{}])), patch.object(
            routes_paper, "_paper_batch_service"
        ) as service:
            service.return_value.create_batch.side_effect = PaperImportBatchServiceError(
                "DATABASE_LOCKED", "批次状态库正忙", retryable=True
            )
            response = self.client.post(
                "/api/papers/imports",
                json={"search_id": "job-1", "candidate_ids": ["cp-1"]},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "DATABASE_LOCKED")
        self.assertTrue(response.json()["retryable"])


if __name__ == "__main__":
    unittest.main()
