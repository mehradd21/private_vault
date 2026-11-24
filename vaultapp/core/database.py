"""SQLite metadata store. No password, plaintext key or plaintext path is stored."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name  TEXT    NOT NULL,
    stored_name   TEXT    NOT NULL UNIQUE,
    kind          TEXT    NOT NULL CHECK (kind IN ('image','video')),
    mime          TEXT    NOT NULL,
    original_ext  TEXT    NOT NULL,
    size          INTEGER NOT NULL,
    imported_at   INTEGER NOT NULL,
    hidden        INTEGER NOT NULL DEFAULT 0,
    duration_ms   INTEGER,
    thumb_name    TEXT,
    source_uri    TEXT,
    integrity     TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_kind_hidden ON files(kind, hidden);
CREATE INDEX IF NOT EXISTS idx_files_imported ON files(imported_at DESC);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class VaultDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        with self._lock:
            self._connection.executescript(SCHEMA)
            self._connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                self._connection.execute("BEGIN")
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    # ---------- file records ----------
    def add_file(self, record: dict[str, Any]) -> int:
        columns = (
            "display_name", "stored_name", "kind", "mime", "original_ext",
            "size", "imported_at", "hidden", "duration_ms", "thumb_name",
            "source_uri", "integrity",
        )
        values = [record.get(column) for column in columns]
        with self.transaction() as conn:
            cursor = conn.execute(
                f"INSERT INTO files ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                values,
            )
            return int(cursor.lastrowid)

    def get_file(self, file_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
        return dict(row) if row else None

    def get_by_stored_name(self, stored_name: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM files WHERE stored_name=?", (stored_name,)
            ).fetchone()
        return dict(row) if row else None

    def list_files(
        self,
        kind: str | None = None,
        hidden: bool | None = None,
        query: str = "",
        sort: str = "newest",
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if kind in ("image", "video"):
            clauses.append("kind=?")
            params.append(kind)
        if hidden is not None:
            clauses.append("hidden=?")
            params.append(1 if hidden else 0)
        if query:
            clauses.append("display_name LIKE ?")
            params.append(f"%{query}%")
        order = {
            "newest": "imported_at DESC, id DESC",
            "oldest": "imported_at ASC, id ASC",
            "name": "display_name COLLATE NOCASE ASC",
            "size": "size DESC",
        }.get(sort, "imported_at DESC, id DESC")
        sql = "SELECT * FROM files"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY " + order
        with self._lock:
            rows = self._connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def count_files(self, hidden: bool | None = None) -> dict[str, int]:
        where = " WHERE hidden=?" if hidden is not None else ""
        params = (1 if hidden else 0,) if hidden is not None else ()
        with self._lock:
            rows = self._connection.execute(
                "SELECT kind, COUNT(*) AS c, COALESCE(SUM(size),0) AS s FROM files" + where +
                " GROUP BY kind", params,
            ).fetchall()
        result = {"image": 0, "video": 0, "images": 0, "videos": 0, "bytes": 0, "total": 0}
        for row in rows:
            result[row["kind"]] = row["c"]
            result[row["kind"] + "s"] = row["c"]
            result["bytes"] += row["s"]
        result["total"] = result["image"] + result["video"]
        return result

    def rename(self, file_id: int, new_name: str) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE files SET display_name=? WHERE id=?", (new_name, file_id))

    def set_hidden(self, file_id: int, hidden: bool) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE files SET hidden=? WHERE id=?", (1 if hidden else 0, file_id))

    def set_integrity(self, file_id: int, value: str) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE files SET integrity=? WHERE id=?", (value, file_id))

    def delete_file(self, file_id: int) -> dict[str, Any] | None:
        record = self.get_file(file_id)
        if record is None:
            return None
        with self.transaction() as conn:
            conn.execute("DELETE FROM files WHERE id=?", (file_id,))
        return record

    def restore_file(self, record: dict[str, Any]) -> None:
        """Reinsert an exact record if on-disk cleanup failed after DB deletion."""
        with self.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO files "
                "(id,display_name,stored_name,kind,mime,original_ext,size,imported_at,"
                "hidden,duration_ms,thumb_name,source_uri,integrity) "
                "VALUES (:id,:display_name,:stored_name,:kind,:mime,:original_ext,:size,"
                ":imported_at,:hidden,:duration_ms,:thumb_name,:source_uri,:integrity)",
                record,
            )

    def stored_names(self) -> set[str]:
        with self._lock:
            rows = self._connection.execute("SELECT stored_name, thumb_name FROM files").fetchall()
        names = set()
        for row in rows:
            names.add(row["stored_name"])
            if row["thumb_name"]:
                names.add(row["thumb_name"])
        return names

    # ---------- settings ----------
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def delete_setting(self, key: str) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM settings WHERE key=?", (key,))

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.get_setting(key, str(default)) or default)
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.get_setting(key, str(default)) or default)
        except (TypeError, ValueError):
            return default
