"""Compatibility import for the frozen literature-map SQLite store seam."""

from .store import LiteratureMapStore, LiteratureMapStoreError, default_database_path

__all__ = ["LiteratureMapStore", "LiteratureMapStoreError", "default_database_path"]
