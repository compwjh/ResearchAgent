import unittest

from backend.app.services.paper_download_security import (
    DOWNLOAD_BLOCKED,
    INVALID_URL,
    URLSecurityError,
    validate_peer_ip,
    validate_redirect_chain,
    validate_redirect_target,
    validate_url,
)

PUBLIC = "93.184.216.34"


def resolver(_host):
    return [PUBLIC]


class PaperDownloadSecurityTests(unittest.TestCase):
    def assert_code(self, code, call, *args, **kwargs):
        with self.assertRaises(URLSecurityError) as raised:
            call(*args, **kwargs)
        self.assertEqual(raised.exception.code, code)

    def test_valid_https_url_and_peer_are_accepted(self):
        target = validate_url("https://papers.example/paper.pdf", allowed_hosts={"papers.example"}, dns_resolver=resolver)
        self.assertEqual(target.port, 443)
        self.assertEqual(target.addresses, (PUBLIC,))
        self.assertEqual(validate_peer_ip(target, PUBLIC), PUBLIC)

    def test_protocol_port_and_allowlist_are_restricted(self):
        self.assert_code(DOWNLOAD_BLOCKED, validate_url, "http://papers.example/paper.pdf", allowed_hosts={"papers.example"}, dns_resolver=resolver)
        self.assert_code(DOWNLOAD_BLOCKED, validate_url, "https://papers.example:8443/paper.pdf", allowed_hosts={"papers.example"}, dns_resolver=resolver)
        self.assert_code(DOWNLOAD_BLOCKED, validate_url, "https://other.example/paper.pdf", allowed_hosts={"papers.example"}, dns_resolver=resolver)

    def test_credentials_fragment_and_auth_query_are_rejected(self):
        options = {"allowed_hosts": {"papers.example"}, "dns_resolver": resolver}
        for url in (
            "https://user:password@papers.example/paper.pdf",
            "https://papers.example/paper.pdf#fragment",
            "https://papers.example/paper.pdf?access_token=secret",
            "https://papers.example/paper.pdf?X-Amz-Signature=secret",
        ):
            with self.assertRaises(URLSecurityError) as raised:
                validate_url(url, **options)
            self.assertEqual(raised.exception.code, DOWNLOAD_BLOCKED)
            self.assertNotIn("password", str(raised.exception).lower())
            self.assertNotIn("secret", str(raised.exception).lower())

    def test_dangerous_and_obfuscated_dns_results_are_blocked(self):
        for value in ("127.0.0.1", "10.0.0.1", "169.254.1.2", "::1", "::ffff:93.184.216.34", "0.0.0.0"):
            self.assert_code(DOWNLOAD_BLOCKED, validate_url, "https://papers.example/paper.pdf", allowed_hosts={"papers.example"}, dns_resolver=lambda _host, value=value: [value])
        for host in ("2130706433", "0177.0.0.1", "127.1", "0x7f000001"):
            self.assert_code(DOWNLOAD_BLOCKED, validate_url, f"https://{host}/paper.pdf", allowed_hosts={host}, dns_resolver=resolver)

    def test_ssrf_matrix_rejects_multicast_reserved_and_more_ipv6(self):
        blocked = ("224.0.0.1", "240.0.0.1", "255.255.255.255", "fc00::1", "fe80::1", "ff02::1", "2001:db8::1", "::")
        for value in blocked:
            self.assert_code(
                DOWNLOAD_BLOCKED,
                validate_url,
                "https://papers.example/paper.pdf",
                allowed_hosts={"papers.example"},
                dns_resolver=lambda _host, value=value: [value],
            )

    def test_ssrf_matrix_rejects_decimal_octal_hex_and_short_hosts(self):
        for host in ("2852039168", "0177.0.0.1", "0x7f.0x0.0x0.0x1", "127.1", "127.0.1"):
            self.assert_code(DOWNLOAD_BLOCKED, validate_url, f"https://{host}/paper.pdf", allowed_hosts={host}, dns_resolver=resolver)

    def test_redirect_targets_reject_cross_protocol_port_and_auth_without_leaks(self):
        target = validate_url("https://papers.example/a", allowed_hosts={"papers.example"}, dns_resolver=resolver)
        for location, secret in (
            ("http://papers.example/b", None),
            ("https://papers.example:8443/b", None),
            ("https://user:password@papers.example/b", "password"),
            ("https://papers.example/b?access_token=TOPSECRET", "TOPSECRET"),
        ):
            with self.assertRaises(URLSecurityError) as raised:
                validate_redirect_target(target, location, allowed_hosts={"papers.example"}, dns_resolver=resolver)
            self.assertEqual(raised.exception.code, DOWNLOAD_BLOCKED)
            if secret:
                self.assertNotIn(secret, str(raised.exception))

    def test_two_hop_loop_is_bounded_and_missing_location_is_stable(self):
        options = {"allowed_hosts": {"papers.example"}, "dns_resolver": resolver}
        final = validate_redirect_chain("https://papers.example/a", ["/b", "/a"], max_redirects=2, **options)
        self.assertEqual(final.url, "https://papers.example/a")
        self.assert_code(DOWNLOAD_BLOCKED, validate_redirect_chain, "https://papers.example/a", ["/b", "/a", "/b"], max_redirects=2, **options)
        self.assert_code(INVALID_URL, validate_redirect_target, final, "", **options)

    def test_dns_is_injected_and_only_public_addresses_are_returned(self):
        calls = []

        def injected(host):
            calls.append(host)
            return ["192.168.1.1", PUBLIC]

        target = validate_url("https://papers.example/paper.pdf", allowed_hosts={"papers.example"}, dns_resolver=injected)
        self.assertEqual(calls, ["papers.example"])
        self.assertEqual(target.addresses, (PUBLIC,))
        self.assert_code(DOWNLOAD_BLOCKED, validate_peer_ip, target, "192.168.1.1")
        self.assert_code(DOWNLOAD_BLOCKED, validate_peer_ip, target, "93.184.216.35")

    def test_redirect_is_manual_and_revalidated_each_hop(self):
        target = validate_url("https://papers.example/a", allowed_hosts={"papers.example"}, dns_resolver=resolver)
        redirected = validate_redirect_target(target, "/b", allowed_hosts={"papers.example"}, dns_resolver=resolver)
        self.assertEqual(redirected.url, "https://papers.example/b")
        self.assert_code(DOWNLOAD_BLOCKED, validate_redirect_target, target, "https://other.example/b", allowed_hosts={"papers.example"}, dns_resolver=resolver)
        self.assert_code(DOWNLOAD_BLOCKED, validate_redirect_chain, "https://papers.example/a", ["/b", "/c"], allowed_hosts={"papers.example"}, dns_resolver=resolver, max_redirects=1)


if __name__ == "__main__":
    unittest.main()
