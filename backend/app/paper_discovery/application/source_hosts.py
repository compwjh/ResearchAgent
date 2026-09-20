"""Application boundary for the source registry's fixed download hosts.

The API layer may select a source allowlist, but it must not import
infrastructure modules directly.  The registry remains the single authority;
this module only exposes its read-only application seam.
"""

from backend.app.paper_discovery.infrastructure.source_registry import builtin_allowed_hosts

__all__ = ["builtin_allowed_hosts"]
