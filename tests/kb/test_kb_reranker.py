import unittest
from dataclasses import dataclass

import httpx

from backend.app.knowledge_base.infrastructure.reranker import clear_negative_cache, rerank_hits


@dataclass(frozen=True)
class Hit:
    text: str


class RerankerClientTests(unittest.TestCase):
    def setUp(self):
        clear_negative_cache()
        self.hits = [Hit("first"), Hit("second"), Hit("third")]

    @staticmethod
    def transport(payload, seen=None, status=200):
        def handler(request):
            if seen is not None:
                seen.append((request, request.read()))
            if isinstance(payload, Exception):
                payload.request = request
                raise payload
            if isinstance(payload, bytes):
                return httpx.Response(status, content=payload)
            return httpx.Response(status, json=payload)
        return httpx.MockTransport(handler)

    def assert_fail(self, result, reason):
        self.assertEqual(result.reason, reason)
        self.assertFalse(result.used)
        self.assertTrue(result.degraded)
        self.assertEqual(result.hits, self.hits)
        self.assertIsNot(result.hits, self.hits)

    def test_one_batch_preserves_documents_and_optional_model(self):
        for model in ("", "reranker-v1"):
            with self.subTest(model=model):
                seen = []
                result = rerank_hits(
                    "question", self.hits, api_model=model,
                    transport=self.transport({"results": [
                        {"index": 0, "relevance_score": 0.1},
                        {"index": 1, "relevance_score": 0.2},
                        {"index": 2, "relevance_score": 0.3},
                    ]}, seen),
                )
                self.assertTrue(result.used)
                self.assertEqual(len(seen), 1)
                body = __import__("json").loads(seen[0][1])
                self.assertEqual(body["documents"], ["first", "second", "third"])
                self.assertEqual(body.get("model", "<missing>"), model or "<missing>")

    def test_unordered_results_map_by_index_and_ties_are_stable(self):
        result = rerank_hits("q", self.hits, transport=self.transport({"results": [
            {"index": 2, "relevance_score": 0.7},
            {"index": 0, "relevance_score": 0.7},
            {"index": 1, "relevance_score": 0.9},
        ]}))
        self.assertEqual(result.hits, [self.hits[1], self.hits[0], self.hits[2]])
        self.assertEqual(result.scores_by_original_index, (0.7, 0.9, 0.7))
        self.assertIsNot(result.hits, self.hits)
        self.assertEqual([hit.text for hit in self.hits], ["first", "second", "third"])

    def test_disabled_and_small_batches_make_no_request(self):
        calls = []
        transport = self.transport({}, calls)
        cases = [
            (self.hits, False, "disabled"),
            ([], True, "too_few_candidates"),
            ([self.hits[0]], True, "too_few_candidates"),
        ]
        for hits, enabled, reason in cases:
            with self.subTest(reason=reason, size=len(hits)):
                result = rerank_hits("q", hits, enabled=enabled, transport=transport)
                self.assertEqual(result.reason, reason)
        self.assertEqual(calls, [])

    def test_network_http_and_protocol_fail_open(self):
        invalid = [
            (httpx.ConnectError("down"), 200, "connection"),
            (httpx.ReadTimeout("slow"), 200, "timeout"),
            ({}, 503, "http_status"),
            (None, 200, "invalid_json"),
            ({}, 200, "invalid_schema"),
            ({"results": "wrong"}, 200, "invalid_schema"),
            ({"results": [1, 2, 3]}, 200, "invalid_schema"),
            ({"results": [{"index": 0, "relevance_score": 1}]}, 200, "invalid_index"),
            ({"results": [{"index": 0, "relevance_score": 1}, {"index": 0, "relevance_score": 2}, {"index": 2, "relevance_score": 3}]}, 200, "invalid_index"),
            ({"results": [{"index": 0, "relevance_score": 1}, {"index": 1, "relevance_score": 2}, {"index": 3, "relevance_score": 3}]}, 200, "invalid_index"),
            ({"results": [{"index": False, "relevance_score": 1}, {"index": 1, "relevance_score": 2}, {"index": 2, "relevance_score": 3}]}, 200, "invalid_index"),
        ]
        for score in ["1", True]:
            invalid.append(({"results": [{"index": 0, "relevance_score": score}, {"index": 1, "relevance_score": 2}, {"index": 2, "relevance_score": 3}]}, 200, "invalid_score"))
        for score in (b"NaN", b"Infinity"):
            invalid.append((b'{"results":[{"index":0,"relevance_score":' + score + b'},{"index":1,"relevance_score":2},{"index":2,"relevance_score":3}]}', 200, "invalid_score"))
        invalid.append((RuntimeError("boom"), 200, "unexpected"))
        for payload, status, reason in invalid:
            with self.subTest(reason=reason, payload=repr(payload)):
                clear_negative_cache()
                if payload is None:
                    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"{"))
                else:
                    transport = self.transport(payload, status=status)
                self.assert_fail(rerank_hits("q", self.hits, transport=transport), reason)

    def test_negative_cache_uses_monotonic_ttl_and_recovers(self):
        now, calls = [100.0], []
        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                raise httpx.ConnectError("down", request=request)
            return httpx.Response(200, json={"results": [
                {"index": i, "relevance_score": i} for i in range(3)]})
        def clock():
            return now[0]
        transport = httpx.MockTransport(handler)
        self.assert_fail(rerank_hits("q", self.hits, transport=transport, clock=clock, negative_ttl=1), "connection")
        now[0] += 29
        self.assert_fail(rerank_hits("q", self.hits, transport=transport, clock=clock), "connection")
        self.assertEqual(len(calls), 1)
        now[0] += 2
        self.assertTrue(rerank_hits("q", self.hits, transport=transport, clock=clock).used)
        self.assertEqual(len(calls), 2)

    def test_rejects_non_loopback_urls_without_request(self):
        calls = []
        transport = self.transport({}, calls)
        urls = ["https://127.0.0.1:11435", "http://example.com:11435", "http://user:pw@localhost:11435", "http://localhost:bad"]
        for url in urls:
            with self.subTest(url=url):
                result = rerank_hits("q", self.hits, base_url=url, transport=transport)
                self.assertEqual(result.reason, "unexpected")
        self.assertEqual(calls, [])

    def test_nonpositive_timeouts_use_defaults(self):
        seen = []
        result = rerank_hits("q", self.hits, connect_timeout=0, read_timeout=-1,
                             transport=self.transport({"results": [
                                 {"index": i, "relevance_score": i} for i in range(3)]}, seen))
        self.assertTrue(result.used)
        self.assertEqual(seen[0][0].extensions["timeout"]["connect"], 2.0)
        self.assertEqual(seen[0][0].extensions["timeout"]["read"], 60.0)


if __name__ == "__main__":
    unittest.main()
