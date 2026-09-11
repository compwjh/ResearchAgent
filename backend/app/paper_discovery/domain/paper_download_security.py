"""Compatibility exports for the shared server-side URL security boundary.

Paper-discovery callers historically imported these symbols from this domain
module.  The implementation lives in ``backend.app.core.url_security`` so
other bounded contexts can reuse the same checks without importing paper
discovery internals.
"""

from backend.app.core.url_security import (
    DEFAULT_MAX_REDIRECTS,
    DOWNLOAD_BLOCKED,
    INVALID_URL,
    DNSResolver,
    URLSecurityError,
    ValidatedURL,
    validate_peer_ip,
    validate_redirect_chain,
    validate_redirect_target,
    validate_url,
)

__all__ = [
    "DEFAULT_MAX_REDIRECTS",
    "DOWNLOAD_BLOCKED",
    "INVALID_URL",
    "DNSResolver",
    "URLSecurityError",
    "ValidatedURL",
    "validate_peer_ip",
    "validate_redirect_chain",
    "validate_redirect_target",
    "validate_url",
]
