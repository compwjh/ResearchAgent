"""Strict schema and integrity checks for the SQLite task ledger."""

import re
import sqlite3
from typing import Sequence, Tuple


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _signature(conn: sqlite3.Connection) -> Tuple[object, object]:
    objects = set()
    for kind, name, owner, sql in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' AND type IN ('table','index','view','trigger')"):
        normalized = re.sub(r"\s+", " ", sql or "").strip().casefold()
        objects.add((kind, name, owner, normalized))
    tables = sorted(row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
    shapes = {}
    for table in tables:
        quoted = _quote(table)
        columns = tuple(tuple(row[:6]) for row in conn.execute(
            "PRAGMA table_info({})".format(quoted)))
        unique = []
        for index in conn.execute("PRAGMA index_list({})".format(quoted)):
            if index[2]:
                indexed = tuple(row[2] for row in conn.execute(
                    "PRAGMA index_info({})".format(_quote(index[1]))))
                unique.append((index[3], index[4], indexed))
        foreign = tuple(tuple(row) for row in conn.execute(
            "PRAGMA foreign_key_list({})".format(quoted)))
        shapes[table] = (columns, tuple(sorted(unique)), foreign)
    return objects, shapes


def validate_schema(conn: sqlite3.Connection, statements: Sequence[str]) -> None:
    """Require the v1 table shape and reject corrupt or FK-invalid databases."""
    try:
        expected = sqlite3.connect(":memory:")
        try:
            for statement in statements:
                expected.execute(statement)
            if _signature(conn) != _signature(expected):
                raise ValueError("schema_mismatch: task ledger schema differs from protocol")
        finally:
            expected.close()
        violations = list(conn.execute("PRAGMA foreign_key_check"))
        if violations:
            raise ValueError("foreign_key_violation: task ledger contains invalid references")
        checks = [row[0] for row in conn.execute("PRAGMA quick_check")]
        if checks != ["ok"]:
            raise ValueError("database_integrity_error: quick_check failed")
    except sqlite3.Error as exc:
        raise ValueError("schema_validation_failed: SQLite check failed") from exc
