"""Stable errors shared by the literature-map application boundary."""

from __future__ import annotations


class LiteratureMapStoreError(RuntimeError):
    """A recoverable map persistence failure with a stable error contract."""
