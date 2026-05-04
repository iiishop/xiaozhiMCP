from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ErrorStore:
    def __init__(self, db_path: str | None = None) -> None:
        default_path = Path("runtime_errors.sqlite3")
        self.db_path = Path(db_path) if db_path else default_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS log_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    level TEXT NOT NULL,
                    source TEXT NOT NULL,
                    error_code TEXT NOT NULL,
                    message TEXT NOT NULL,
                    conclusion TEXT NOT NULL,
                    detail TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_log_errors_ts ON log_errors(ts DESC)")
            conn.commit()

    def add_known(self, source: str, error_code: str, message: str, conclusion: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO log_errors (ts, level, source, error_code, message, conclusion, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (_now_text(), "ERROR", source, error_code, message, conclusion, ""),
            )
            conn.commit()

    def add_unknown(self, source: str, message: str, detail: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO log_errors (ts, level, source, error_code, message, conclusion, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (_now_text(), "ERROR", source, "UNHANDLED", message, "No predefined resolution available.", detail),
            )
            conn.commit()

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 500))
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT ts, level, source, error_code, message, conclusion, detail FROM log_errors ORDER BY id DESC LIMIT ?",
                (lim,),
            ).fetchall()
        return [
            {
                "time": str(r["ts"]),
                "level": str(r["level"]),
                "source": str(r["source"]),
                "error_code": str(r["error_code"]),
                "message": str(r["message"]),
                "conclusion": str(r["conclusion"]),
                "detail": str(r["detail"]),
            }
            for r in rows
        ]
