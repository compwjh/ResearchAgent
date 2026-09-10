"""SQLite persistence and compare-and-set state machine for paper imports."""

from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from backend.app.platform.config import BASE_DIR
from backend.app.paper_discovery.domain.paper_import_batch import (
    BATCH_CANCELLED,
    BATCH_COMPLETED,
    BATCH_FAILED,
    BATCH_PARTIAL_SUCCESS,
    BATCH_QUEUED,
    BATCH_RUNNING,
    BATCH_STATES,
    BATCH_WAITING_LOGIN,
    ITEM_CANCELLED,
    ITEM_COMPLETED,
    ITEM_DOWNLOADING,
    ITEM_FAILED,
    ITEM_INDEXING,
    ITEM_QUEUED,
    ITEM_STATES,
    ITEM_TRANSITIONS,
    ITEM_VALIDATING,
    ITEM_WAITING_LOGIN,
    PaperImportBatch,
    PaperImportItem,
)

SCHEMA_VERSION = 2
MAX_BATCH_ITEMS = 20
DEFAULT_LEASE_SECONDS = 15 * 60
MIN_LEASE_RENEW_SECONDS = 5 * 60
IMPORT_INTERRUPTED = "IMPORT_INTERRUPTED"
INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
BATCH_NOT_FOUND = "BATCH_NOT_FOUND"
ITEM_NOT_FOUND = "ITEM_NOT_FOUND"
BATCH_LIMIT_EXCEEDED = "BATCH_LIMIT_EXCEEDED"
DATABASE_LOCKED = "DATABASE_LOCKED"

ACTIVE_LEASE_STATES = (ITEM_DOWNLOADING, ITEM_VALIDATING, ITEM_INDEXING)
TITLE_YEAR_NULL = -2147483648


class PaperImportBatchStoreError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.error_code = code
        super().__init__(message)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _timestamp(value: Optional[str | datetime] = None) -> str:
    if value is None:
        return _utcnow()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return str(value)


def _plus_seconds(value: str, seconds: int) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed + timedelta(seconds=seconds)).isoformat(timespec="seconds").replace("+00:00", "Z")


class PaperImportBatchStore:
    """Own the durable batch/item state; counters are always query aggregates."""

    def __init__(self, database_path: Optional[Path] = None, *, max_items: int = MAX_BATCH_ITEMS) -> None:
        self.database_path = Path(database_path or BASE_DIR / "data" / "paper_search" / "state.sqlite3")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_items = max(0, min(MAX_BATCH_ITEMS, int(max_items)))
        with self._write_transaction() as connection:
            self._init_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @staticmethod
    def _is_locked(error: sqlite3.OperationalError) -> bool:
        return "database is locked" in str(error).lower() or "database table is locked" in str(error).lower()

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        """Open a serializable write transaction and expose a stable lock error."""
        try:
            connection = self._connect()
        except sqlite3.OperationalError as error:
            if self._is_locked(error):
                raise PaperImportBatchStoreError(DATABASE_LOCKED, "批次状态库正忙，请稍后重试") from error
            raise
        try:
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as error:
                if self._is_locked(error):
                    raise PaperImportBatchStoreError(DATABASE_LOCKED, "批次状态库正忙，请稍后重试") from error
                raise
            try:
                yield connection
            except sqlite3.OperationalError as error:
                if self._is_locked(error):
                    raise PaperImportBatchStoreError(DATABASE_LOCKED, "批次状态库正忙，请稍后重试") from error
                raise
            except Exception:
                connection.rollback()
                raise
            else:
                try:
                    connection.commit()
                except sqlite3.OperationalError as error:
                    if self._is_locked(error):
                        raise PaperImportBatchStoreError(DATABASE_LOCKED, "批次状态库正忙，请稍后重试") from error
                    raise
        finally:
            connection.close()

    @staticmethod
    def _init_schema(connection: sqlite3.Connection) -> None:
        # This metadata is deliberately namespaced: PaperDiscoveryStore owns
        # the legacy shared ``schema_meta`` table in the same SQLite file.
        connection.execute("CREATE TABLE IF NOT EXISTS paper_import_schema_meta(version INTEGER NOT NULL)")
        columns = connection.execute("PRAGMA table_info(paper_import_schema_meta)").fetchall()
        if len(columns) != 1 or columns[0][1] != "version" or str(columns[0][2]).upper() != "INTEGER" or not columns[0][3]:
            raise RuntimeError("Invalid paper import schema metadata: malformed paper_import_schema_meta table")
        rows = connection.execute("SELECT version, typeof(version) AS value_type FROM paper_import_schema_meta").fetchall()
        if len(rows) > 1:
            raise RuntimeError("Invalid paper import schema metadata: expected exactly one row")
        if not rows:
            connection.execute("INSERT INTO paper_import_schema_meta(version) VALUES(?)", (SCHEMA_VERSION,))
        else:
            if rows[0][1] != "integer" or rows[0][0] not in (1, SCHEMA_VERSION):
                raise RuntimeError(f"Unsupported or corrupt paper import schema version: {rows[0][0]!r}")
            # v1 -> v2：释放已终态（completed）条目占用的论文唯一身份，仅保留活跃态占位
            # （spec-021 Task06）。索引重建在下方统一执行，这里只推进版本记录，保证幂等。
            if rows[0][0] != SCHEMA_VERSION:
                connection.execute("UPDATE paper_import_schema_meta SET version=?", (SCHEMA_VERSION,))
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS paper_import_schema_meta_singleton ON paper_import_schema_meta((1))")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS paper_import_batches(
                batch_id TEXT PRIMARY KEY,
                search_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('queued','running','waiting_login','partial_success','completed','failed','cancelled')),
                idempotency_key TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS paper_import_items(
                item_id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES paper_import_batches(batch_id) ON DELETE RESTRICT,
                candidate_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('queued','downloading','waiting_login','validating','indexing','completed','failed','cancelled')),
                stored_name TEXT,
                paper_id TEXT,
                error_code TEXT,
                error_message TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
                lease_owner TEXT,
                lease_expires_at TEXT,
                lease_renewed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                doi TEXT,
                dblp_key TEXT,
                normalized_title TEXT,
                year INTEGER,
                conference_id TEXT,
                idempotency_key TEXT,
                UNIQUE(batch_id, candidate_id)
            )"""
        )
        required_batches = {"batch_id", "search_id", "state", "idempotency_key", "created_at", "updated_at"}
        required_items = {
            "item_id", "batch_id", "candidate_id", "state", "stored_name", "paper_id", "error_code",
            "error_message", "attempt_count", "lease_owner", "lease_expires_at", "lease_renewed_at",
            "created_at", "updated_at", "doi", "dblp_key", "normalized_title", "year", "conference_id",
            "idempotency_key",
        }
        for table, required in (("paper_import_batches", required_batches), ("paper_import_items", required_items)):
            actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
            missing = sorted(required - actual)
            if missing:
                raise RuntimeError(f"Invalid paper import schema: {table} missing columns: {', '.join(missing)}")

        PaperImportBatchStore._validate_schema_contract(connection)

        # These identities are global so two searches cannot enqueue the same
        # knowledge-base paper concurrently. All terminal states (completed /
        # failed / cancelled) are intentionally excluded, allowing a legal
        # re-import or retry; duplicate papers are then caught by the knowledge
        # base's own ``find_existing``. COALESCE turns NULL title components
        # into an explicit identity sentinel.
        for index in ("import_item_doi", "import_item_dblp", "import_item_title", "import_item_idempotency", "import_item_paper_id"):
            connection.execute(f"DROP INDEX IF EXISTS {index}")
        connection.execute("DROP INDEX IF EXISTS paper_import_batch_idempotency")
        # spec-021 Task06：论文身份（doi/dblp/title/idempotency/paper_id）只由**活跃态**
        # 占位。completed/failed/cancelled 均为终态 → 一律释放，使同论文可重新导入或重试；
        # 去重改由知识库既有的 find_existing 负责（PAPER_ALREADY_EXISTS / existing）。
        active_sql = "state IN ('queued','downloading','waiting_login','validating','indexing')"
        # Release identities left behind by pre-v1 stores that did not clear
        # terminal batch keys. This is idempotent and also makes re-opened
        # databases follow the same effective-state policy as new ones.
        connection.execute(
            "UPDATE paper_import_batches SET idempotency_key=NULL "
            "WHERE state IN ('failed','cancelled','partial_success')"
        )
        try:
            connection.execute(f"CREATE UNIQUE INDEX import_item_doi ON paper_import_items(doi) WHERE doi IS NOT NULL AND {active_sql}")
            connection.execute(f"CREATE UNIQUE INDEX import_item_dblp ON paper_import_items(dblp_key) WHERE dblp_key IS NOT NULL AND {active_sql}")
            connection.execute(
                "CREATE UNIQUE INDEX import_item_title ON paper_import_items(normalized_title, "
                f"COALESCE(year, {TITLE_YEAR_NULL}), COALESCE(conference_id, X'00')) "
                f"WHERE normalized_title IS NOT NULL AND {active_sql}"
            )
            connection.execute(f"CREATE UNIQUE INDEX import_item_idempotency ON paper_import_items(idempotency_key) WHERE idempotency_key IS NOT NULL AND {active_sql}")
            connection.execute(f"CREATE UNIQUE INDEX import_item_paper_id ON paper_import_items(paper_id) WHERE paper_id IS NOT NULL AND {active_sql}")
            connection.execute(
                "CREATE UNIQUE INDEX paper_import_batch_idempotency ON paper_import_batches(idempotency_key) "
                "WHERE idempotency_key IS NOT NULL AND state IN ('queued','running','waiting_login','partial_success','completed')"
            )
        except sqlite3.IntegrityError as error:
            raise RuntimeError("Invalid paper import schema: duplicate active paper identity") from error
        connection.execute("CREATE INDEX IF NOT EXISTS import_item_leases ON paper_import_items(state, lease_expires_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS import_item_batch ON paper_import_items(batch_id, state)")

    @staticmethod
    def _validate_schema_contract(connection: sqlite3.Connection) -> None:
        """Reject incompatible pre-existing tables before mutating their data.

        ``CREATE TABLE IF NOT EXISTS`` does not repair a table with the right
        column names but the wrong constraints.  Validate the durable state
        contract explicitly so an accidental/old database fails at startup,
        while allowing harmless extra columns and index names from older
        versions.
        """
        batch_columns = {row[1]: row for row in connection.execute("PRAGMA table_info(paper_import_batches)")}
        item_columns = {row[1]: row for row in connection.execute("PRAGMA table_info(paper_import_items)")}

        def require_column(columns: dict[str, sqlite3.Row], table: str, name: str, *, type_name: str, notnull: Optional[int] = None, pk: Optional[int] = None) -> None:
            column = columns[name]
            if str(column[2]).upper() != type_name or (notnull is not None and column[3] != notnull) or (pk is not None and column[5] != pk):
                raise RuntimeError(f"Invalid paper import schema: {table}.{name} has incompatible definition")

        require_column(batch_columns, "paper_import_batches", "batch_id", type_name="TEXT", pk=1)
        for name in ("search_id", "state", "created_at", "updated_at"):
            require_column(batch_columns, "paper_import_batches", name, type_name="TEXT", notnull=1)
        require_column(item_columns, "paper_import_items", "item_id", type_name="TEXT", pk=1)
        for name in ("batch_id", "candidate_id", "state", "created_at", "updated_at"):
            require_column(item_columns, "paper_import_items", name, type_name="TEXT", notnull=1)
        require_column(item_columns, "paper_import_items", "attempt_count", type_name="INTEGER", notnull=1)

        def check_state_values(table: str, column: str, allowed: frozenset[str]) -> None:
            sql_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            sql = str(sql_row[0] or "") if sql_row else ""
            match = re.search(rf"check\s*\(\s*{column}\s+in\s*\(([^)]*)\)", sql, re.IGNORECASE)
            if match is None:
                raise RuntimeError(f"Invalid paper import schema: {table}.{column} CHECK constraint missing")
            values = {token.strip().strip("'\\\"").lower() for token in match.group(1).split(",")}
            if values != set(allowed):
                raise RuntimeError(f"Invalid paper import schema: {table}.{column} CHECK constraint incompatible")
            invalid = sorted({row[0] for row in connection.execute(f"SELECT DISTINCT {column} FROM {table}") if row[0] not in allowed})
            if invalid:
                raise RuntimeError(f"Invalid paper import schema: {table} contains invalid state values: {invalid}")

        check_state_values("paper_import_batches", "state", BATCH_STATES)
        check_state_values("paper_import_items", "state", ITEM_STATES)

        attempt_sql_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='paper_import_items'"
        ).fetchone()
        attempt_sql = "".join(str(attempt_sql_row[0] or "").lower().split()) if attempt_sql_row else ""
        if "check(attempt_count>=0)" not in attempt_sql:
            raise RuntimeError("Invalid paper import schema: paper_import_items.attempt_count CHECK constraint missing")

        unique_pair = False
        for index in connection.execute("PRAGMA index_list(paper_import_items)"):
            if not index[2]:
                continue
            index_columns = [row[2] for row in connection.execute(f"PRAGMA index_info({index[1]!r})")]
            if index_columns == ["batch_id", "candidate_id"]:
                unique_pair = True
                break
        if not unique_pair:
            raise RuntimeError("Invalid paper import schema: paper_import_items UNIQUE(batch_id, candidate_id) missing")

        foreign_keys = connection.execute("PRAGMA foreign_key_list(paper_import_items)").fetchall()
        if not any(
            row[2] == "paper_import_batches"
            and row[3] == "batch_id"
            and row[4] == "batch_id"
            and str(row[6]).upper() == "RESTRICT"
            for row in foreign_keys
        ):
            raise RuntimeError("Invalid paper import schema: paper_import_items batch_id FK missing")

    @staticmethod
    def _candidate_value(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    def create_batch(
        self,
        batch: PaperImportBatch | str,
        items: Optional[Iterable[PaperImportItem | str | dict[str, Any]]] = None,
        *,
        search_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> PaperImportBatch:
        if isinstance(batch, PaperImportBatch):
            batch_obj = batch
            item_values = list(items or [])
            search = batch_obj.search_id
            key = batch_obj.idempotency_key or idempotency_key
        else:
            search = search_id or str(batch)
            batch_obj = PaperImportBatch(str(uuid.uuid4()), search, idempotency_key=idempotency_key)
            item_values = list(items or [])
            key = idempotency_key
        if not search:
            raise PaperImportBatchStoreError("INVALID_SEARCH_ID", "search_id 不能为空")
        if len(item_values) == 0:
            raise PaperImportBatchStoreError("EMPTY_BATCH", "批次至少需要一个条目")
        # Deduplicate client retries before insert; the database remains the final guard.
        unique_values: list[Any] = []
        seen: set[str] = set()
        for value in item_values:
            candidate_id = value if isinstance(value, str) else self._candidate_value(value, "candidate_id")
            if not candidate_id:
                raise PaperImportBatchStoreError("INVALID_CANDIDATE_ID", "candidate_id 不能为空")
            if str(candidate_id) not in seen:
                unique_values.append(value)
                seen.add(str(candidate_id))
        if len(unique_values) > self.max_items:
            raise PaperImportBatchStoreError(BATCH_LIMIT_EXCEEDED, f"单批最多 {self.max_items} 项")
        now = _utcnow()
        try:
            with self._write_transaction() as connection:
                connection.execute(
                    "INSERT INTO paper_import_batches(batch_id,search_id,state,idempotency_key,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (batch_obj.batch_id, search, BATCH_QUEUED, key, batch_obj.created_at or now, now),
                )
                for value in unique_values:
                    if isinstance(value, str):
                        candidate_id = value
                        fields: dict[str, Any] = {}
                    else:
                        candidate_id = str(self._candidate_value(value, "candidate_id"))
                        fields = {name: self._candidate_value(value, name) for name in (
                            "doi", "dblp_key", "normalized_title", "year", "conference_id", "idempotency_key", "stored_name"
                        )}
                    item_id = self._candidate_value(value, "item_id") or str(uuid.uuid4())
                    connection.execute(
                        """INSERT INTO paper_import_items(
                           item_id,batch_id,candidate_id,state,stored_name,created_at,updated_at,
                           doi,dblp_key,normalized_title,year,conference_id,idempotency_key)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (item_id, batch_obj.batch_id, candidate_id, ITEM_QUEUED, fields.get("stored_name"), now, now,
                         fields.get("doi"), fields.get("dblp_key"), fields.get("normalized_title"), fields.get("year"),
                         fields.get("conference_id"), fields.get("idempotency_key")),
                    )
                return self._batch_from_row(connection.execute("SELECT * FROM paper_import_batches WHERE batch_id=?", (batch_obj.batch_id,)).fetchone(), connection)
        except sqlite3.IntegrityError:
            if key:
                existing = self.get_batch_by_idempotency_key(key)
                if existing is not None:
                    return existing
            raise

    @staticmethod
    def _batch_from_row(row: sqlite3.Row, connection: sqlite3.Connection) -> PaperImportBatch:
        counts = connection.execute(
            "SELECT COUNT(*) total, SUM(state='completed') completed, SUM(state='failed') failed, "
            "SUM(state='waiting_login') waiting, SUM(state='cancelled') cancelled FROM paper_import_items WHERE batch_id=?",
            (row["batch_id"],),
        ).fetchone()
        return PaperImportBatch(
            row["batch_id"], row["search_id"], row["state"], row["created_at"], row["updated_at"],
            int(counts["total"] or 0), int(counts["completed"] or 0), int(counts["failed"] or 0),
            int(counts["waiting"] or 0), int(counts["cancelled"] or 0), row["idempotency_key"],
        )

    @staticmethod
    def _item_from_row(row: sqlite3.Row) -> PaperImportItem:
        names = PaperImportItem.__dataclass_fields__
        values = {name: row[name] for name in names if name in row.keys()}
        if "status" not in values and "state" in row.keys():
            values["status"] = row["state"]
        return PaperImportItem(**values)

    def get_batch(self, batch_id: str) -> Optional[PaperImportBatch]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM paper_import_batches WHERE batch_id=?", (batch_id,)).fetchone()
            return self._batch_from_row(row, connection) if row else None

    def get_batch_by_idempotency_key(self, key: str) -> Optional[PaperImportBatch]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM paper_import_batches WHERE idempotency_key=?", (key,)).fetchone()
            return self._batch_from_row(row, connection) if row else None

    def get_items(self, batch_id: str) -> list[PaperImportItem]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM paper_import_items WHERE batch_id=? ORDER BY rowid", (batch_id,)).fetchall()
        return [self._item_from_row(row) for row in rows]

    list_items = get_items

    def get_item(self, item_id: str) -> Optional[PaperImportItem]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM paper_import_items WHERE item_id=?", (item_id,)).fetchone()
        return self._item_from_row(row) if row else None

    def _require_item(self, connection: sqlite3.Connection, item_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM paper_import_items WHERE item_id=?", (item_id,)).fetchone()
        if row is None:
            raise PaperImportBatchStoreError(ITEM_NOT_FOUND, "导入条目不存在")
        return row

    @staticmethod
    def _refresh_batch(connection: sqlite3.Connection, batch_id: str, now: str) -> None:
        batch = connection.execute("SELECT batch_id FROM paper_import_batches WHERE batch_id=?", (batch_id,)).fetchone()
        if batch is None:
            raise PaperImportBatchStoreError(BATCH_NOT_FOUND, "导入批次不存在")
        rows = connection.execute("SELECT state, COUNT(*) AS count FROM paper_import_items WHERE batch_id=? GROUP BY state", (batch_id,)).fetchall()
        counts = {row["state"]: int(row["count"]) for row in rows}
        total = sum(counts.values())
        active = sum(counts.get(state, 0) for state in (ITEM_DOWNLOADING, ITEM_VALIDATING, ITEM_INDEXING))
        if total == 0 or counts.get(ITEM_QUEUED, 0) == total:
            state = BATCH_QUEUED
        elif counts.get(ITEM_WAITING_LOGIN, 0):
            state = BATCH_WAITING_LOGIN
        elif active:
            state = BATCH_RUNNING
        elif counts.get(ITEM_COMPLETED, 0) == total:
            state = BATCH_COMPLETED
        elif counts.get(ITEM_COMPLETED, 0) and not (counts.get(ITEM_QUEUED, 0) or counts.get(ITEM_WAITING_LOGIN, 0) or active):
            state = BATCH_PARTIAL_SUCCESS
        elif counts.get(ITEM_FAILED, 0) and not (counts.get(ITEM_QUEUED, 0) or counts.get(ITEM_WAITING_LOGIN, 0) or active):
            state = BATCH_FAILED
        elif counts.get(ITEM_CANCELLED, 0) == total:
            state = BATCH_CANCELLED
        else:
            state = BATCH_RUNNING
        # A failed/cancelled/partial batch no longer owns its idempotency
        # identity. Completed batches retain it to prevent duplicate imports.
        idempotency_sql = ",idempotency_key=NULL" if state in {BATCH_FAILED, BATCH_CANCELLED, BATCH_PARTIAL_SUCCESS} else ""
        connection.execute(f"UPDATE paper_import_batches SET state=?,updated_at=?{idempotency_sql} WHERE batch_id=?", (state, now, batch_id))

    def transition_item(
        self, item_id: str, to_state: str, maybe_to_state: Optional[str] = None, *, expected_state: Optional[str] = None,
        lease_owner: Optional[str] = None, paper_id: Optional[str] = None, stored_name: Optional[str] = None,
        error_code: Optional[str] = None, error_message: Optional[str] = None, now: Optional[str | datetime] = None,
    ) -> bool:
        # Also accept the natural positional form ``(item_id, from, to)``;
        # the keyword form is kept for callers that only know the target.
        if maybe_to_state is not None:
            if expected_state is not None:
                raise TypeError("expected_state cannot be combined with positional target")
            expected_state, to_state = to_state, maybe_to_state
        if to_state not in ITEM_STATES:
            raise PaperImportBatchStoreError(INVALID_STATE_TRANSITION, f"未知条目状态: {to_state}")
        timestamp = _timestamp(now)
        with self._write_transaction() as connection:
            current = self._require_item(connection, item_id)
            source = expected_state or current["state"]
            if to_state not in ITEM_TRANSITIONS.get(source, frozenset()):
                raise PaperImportBatchStoreError(INVALID_STATE_TRANSITION, f"不允许 {source} → {to_state}")
            if source in ACTIVE_LEASE_STATES:
                if not lease_owner:
                    raise PaperImportBatchStoreError(INVALID_STATE_TRANSITION, "活动条目必须提供租约所有者")
                condition = "item_id=? AND state=? AND lease_owner=? AND lease_expires_at>?"
                args: list[Any] = [item_id, source, lease_owner, timestamp]
            else:
                condition = "item_id=? AND state=?"
                args = [item_id, source]
            if lease_owner is not None and source not in ACTIVE_LEASE_STATES:
                condition += " AND lease_owner=?"
                args.append(lease_owner)
            updates = ["state=?", "updated_at=?"]
            values: list[Any] = [to_state, timestamp]
            if to_state in {ITEM_WAITING_LOGIN, ITEM_FAILED, ITEM_COMPLETED, ITEM_QUEUED}:
                updates.extend(["lease_owner=NULL", "lease_expires_at=NULL", "lease_renewed_at=NULL"])
            if paper_id is not None:
                updates.append("paper_id=?"); values.append(paper_id)
            if stored_name is not None:
                updates.append("stored_name=?"); values.append(stored_name)
            if error_code is not None or to_state == ITEM_QUEUED:
                updates.append("error_code=?"); values.append(error_code)
                updates.append("error_message=?"); values.append(error_message)
            result = connection.execute(f"UPDATE paper_import_items SET {','.join(updates)} WHERE {condition}", (*values, *args))
            if result.rowcount != 1:
                raise PaperImportBatchStoreError(INVALID_STATE_TRANSITION, "条目状态已被其他执行者更新")
            self._refresh_batch(connection, current["batch_id"], timestamp)
        return True

    transition_item_state = transition_item
    update_item_state = transition_item
    transition = transition_item

    def claim_item(self, item_id: str, lease_owner: str, *, now: Optional[str | datetime] = None, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> bool:
        timestamp = _timestamp(now)
        expires = _plus_seconds(timestamp, lease_seconds)
        with self._write_transaction() as connection:
            row = self._require_item(connection, item_id)
            result = connection.execute(
                "UPDATE paper_import_items SET state=?,attempt_count=attempt_count+1,lease_owner=?,lease_expires_at=?,lease_renewed_at=?,updated_at=? "
                "WHERE item_id=? AND state=?",
                (ITEM_DOWNLOADING, lease_owner, expires, timestamp, timestamp, item_id, ITEM_QUEUED),
            )
            if result.rowcount != 1:
                raise PaperImportBatchStoreError(INVALID_STATE_TRANSITION, "条目不可领取")
            self._refresh_batch(connection, row["batch_id"], timestamp)
        return True

    def resume_item(self, item_id: str, lease_owner: str, *, now: Optional[str | datetime] = None, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> bool:
        timestamp = _timestamp(now)
        expires = _plus_seconds(timestamp, lease_seconds)
        with self._write_transaction() as connection:
            row = self._require_item(connection, item_id)
            result = connection.execute(
                "UPDATE paper_import_items SET state=?,attempt_count=attempt_count+1,lease_owner=?,lease_expires_at=?,lease_renewed_at=?,updated_at=? "
                "WHERE item_id=? AND state=?",
                (ITEM_DOWNLOADING, lease_owner, expires, timestamp, timestamp, item_id, ITEM_WAITING_LOGIN),
            )
            if result.rowcount != 1:
                raise PaperImportBatchStoreError(INVALID_STATE_TRANSITION, "条目不在等待登录状态")
            self._refresh_batch(connection, row["batch_id"], timestamp)
        return True

    def renew_lease(self, item_id: str, lease_owner: str, *, now: Optional[str | datetime] = None, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> bool:
        timestamp = _timestamp(now)
        expires = _plus_seconds(timestamp, lease_seconds)
        not_before = _plus_seconds(timestamp, -MIN_LEASE_RENEW_SECONDS)
        with self._write_transaction() as connection:
            row = self._require_item(connection, item_id)
            result = connection.execute(
                "UPDATE paper_import_items SET lease_expires_at=?,lease_renewed_at=?,updated_at=? WHERE item_id=? "
                "AND state IN (?,?,?) AND lease_owner=? AND lease_expires_at>? AND (lease_renewed_at IS NULL OR lease_renewed_at<=?)",
                (expires, timestamp, timestamp, item_id, ITEM_DOWNLOADING, ITEM_VALIDATING, ITEM_INDEXING, lease_owner, timestamp, not_before),
            )
            if result.rowcount != 1:
                return False
            self._refresh_batch(connection, row["batch_id"], timestamp)
            return True

    def mark_failed(
        self, item_id: str, error_code: str, error_message: Optional[str] = None, *,
        lease_owner: Optional[str] = None, now: Optional[str | datetime] = None,
    ) -> bool:
        timestamp = _timestamp(now)
        with self._write_transaction() as connection:
            row = self._require_item(connection, item_id)
            if row["state"] in ACTIVE_LEASE_STATES:
                if not lease_owner:
                    raise PaperImportBatchStoreError(INVALID_STATE_TRANSITION, "活动条目标记失败必须提供租约所有者")
                condition = "item_id=? AND state IN (?,?,?) AND lease_owner=? AND lease_expires_at>?"
                args: tuple[Any, ...] = (item_id, ITEM_DOWNLOADING, ITEM_VALIDATING, ITEM_INDEXING, lease_owner, timestamp)
            else:
                condition = "item_id=? AND state IN (?,?)"
                args = (item_id, ITEM_QUEUED, ITEM_WAITING_LOGIN)
            result = connection.execute(
                "UPDATE paper_import_items SET state=?,error_code=?,error_message=?,lease_owner=NULL,lease_expires_at=NULL,lease_renewed_at=NULL,updated_at=? WHERE " + condition,
                (ITEM_FAILED, error_code, error_message, timestamp, *args),
            )
            if result.rowcount != 1:
                raise PaperImportBatchStoreError(INVALID_STATE_TRANSITION, "条目不可标记失败")
            self._refresh_batch(connection, row["batch_id"], timestamp)
        return True

    def retry_item(self, item_id: str, *, now: Optional[str | datetime] = None) -> bool:
        return self.transition_item(item_id, ITEM_QUEUED, expected_state=ITEM_FAILED, now=now)

    def retry_batch(self, batch_id: str, *, now: Optional[str | datetime] = None) -> int:
        timestamp = _timestamp(now)
        with self._write_transaction() as connection:
            self._ensure_batch(connection, batch_id)
            result = connection.execute(
                "UPDATE paper_import_items SET state=?,error_code=NULL,error_message=NULL,lease_owner=NULL,lease_expires_at=NULL,lease_renewed_at=NULL,updated_at=? "
                "WHERE batch_id=? AND state IN (?,?)",
                (ITEM_QUEUED, timestamp, batch_id, ITEM_FAILED, ITEM_WAITING_LOGIN),
            )
            self._refresh_batch(connection, batch_id, timestamp)
            return result.rowcount

    def cancel_item(self, item_id: str, *, now: Optional[str | datetime] = None) -> bool:
        timestamp = _timestamp(now)
        with self._write_transaction() as connection:
            row = self._require_item(connection, item_id)
            result = connection.execute(
                "UPDATE paper_import_items SET state=?,lease_owner=NULL,lease_expires_at=NULL,lease_renewed_at=NULL,updated_at=? "
                "WHERE item_id=? AND state IN (?,?,?)",
                (ITEM_CANCELLED, timestamp, item_id, ITEM_QUEUED, ITEM_WAITING_LOGIN, ITEM_FAILED),
            )
            if result.rowcount != 1:
                raise PaperImportBatchStoreError(INVALID_STATE_TRANSITION, "条目不可取消")
            self._refresh_batch(connection, row["batch_id"], timestamp)
        return True

    cancel = cancel_item

    def cancel_batch(self, batch_id: str, *, now: Optional[str | datetime] = None) -> int:
        timestamp = _timestamp(now)
        with self._write_transaction() as connection:
            self._ensure_batch(connection, batch_id)
            result = connection.execute(
                "UPDATE paper_import_items SET state=?,lease_owner=NULL,lease_expires_at=NULL,lease_renewed_at=NULL,updated_at=? "
                "WHERE batch_id=? AND state IN (?,?,?)",
                (ITEM_CANCELLED, timestamp, batch_id, ITEM_QUEUED, ITEM_WAITING_LOGIN, ITEM_FAILED),
            )
            self._refresh_batch(connection, batch_id, timestamp)
            return result.rowcount

    def recover_expired_leases(self, *, now: Optional[str | datetime] = None) -> int:
        timestamp = _timestamp(now)
        with self._write_transaction() as connection:
            rows = connection.execute(
                "SELECT item_id,batch_id FROM paper_import_items WHERE state IN (?,?,?) AND lease_expires_at IS NOT NULL AND lease_expires_at<=?",
                (ITEM_DOWNLOADING, ITEM_VALIDATING, ITEM_INDEXING, timestamp),
            ).fetchall()
            if not rows:
                return 0
            result = connection.execute(
                "UPDATE paper_import_items SET state=?,error_code=?,error_message=?,lease_owner=NULL,lease_expires_at=NULL,lease_renewed_at=NULL,updated_at=? "
                "WHERE state IN (?,?,?) AND lease_expires_at IS NOT NULL AND lease_expires_at<=?",
                (ITEM_FAILED, IMPORT_INTERRUPTED, "任务在服务重启时中断", timestamp, ITEM_DOWNLOADING, ITEM_VALIDATING, ITEM_INDEXING, timestamp),
            )
            for batch_id in {row["batch_id"] for row in rows}:
                self._refresh_batch(connection, batch_id, timestamp)
            return result.rowcount

    recover_expired = recover_expired_leases

    def list_expired_items(self, *, now: Optional[str | datetime] = None) -> list[PaperImportItem]:
        timestamp = _timestamp(now)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM paper_import_items WHERE state IN (?,?,?) AND lease_expires_at IS NOT NULL AND lease_expires_at<=? ORDER BY lease_expires_at,item_id",
                (ITEM_DOWNLOADING, ITEM_VALIDATING, ITEM_INDEXING, timestamp),
            ).fetchall()
        return [self._item_from_row(row) for row in rows]

    def _ensure_batch(self, connection: sqlite3.Connection, batch_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM paper_import_batches WHERE batch_id=?", (batch_id,)).fetchone()
        if row is None:
            raise PaperImportBatchStoreError(BATCH_NOT_FOUND, "导入批次不存在")
        return row
