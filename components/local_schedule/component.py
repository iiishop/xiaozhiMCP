from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..base import MCPComponent

VALID_STATUSES = {"未开始", "进行中", "已完成"}


def _parse_datetime(value: str) -> datetime:
    text = (value or "").strip()
    if not text:
        raise ValueError("datetime value is required")

    normalized = text.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _to_iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


class LocalScheduleStore:
    def __init__(self, db_path: str | None = None) -> None:
        default_path = Path(__file__).with_name("local_schedule.sqlite3")
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
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    schedule_type TEXT NOT NULL DEFAULT 'range',
                    status TEXT NOT NULL DEFAULT '未开始',
                    start_ts INTEGER NOT NULL,
                    end_ts INTEGER NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    due_ts INTEGER,
                    due_time TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._ensure_columns(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_schedules_start_end ON schedules(start_ts, end_ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_schedules_type ON schedules(schedule_type)")
            conn.commit()

    def _ensure_columns(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("PRAGMA table_info(schedules)").fetchall()
        existing = {str(row[1]) for row in rows}
        if "schedule_type" not in existing:
            conn.execute("ALTER TABLE schedules ADD COLUMN schedule_type TEXT NOT NULL DEFAULT 'range'")
        if "status" not in existing:
            conn.execute("ALTER TABLE schedules ADD COLUMN status TEXT NOT NULL DEFAULT '未开始'")
        if "due_ts" not in existing:
            conn.execute("ALTER TABLE schedules ADD COLUMN due_ts INTEGER")
        if "due_time" not in existing:
            conn.execute("ALTER TABLE schedules ADD COLUMN due_time TEXT")

    def add_event(
        self,
        title: str,
        schedule_type: str = "range",
        start_time: str = "",
        end_time: str = "",
        due_time: str = "",
        status: str = "未开始",
        description: str = "",
    ) -> dict[str, Any]:
        type_value = (schedule_type or "range").strip().lower()
        if type_value not in {"range", "deadline"}:
            raise ValueError("schedule_type must be 'range' or 'deadline'")

        title_text = (title or "").strip()
        if not title_text:
            raise ValueError("title is required")

        status_text = (status or "未开始").strip()
        if status_text not in VALID_STATUSES:
            raise ValueError("status must be one of: 未开始, 进行中, 已完成")

        due_iso = None
        due_ts = None

        if type_value == "range":
            start_dt = _parse_datetime(start_time)
            end_dt = _parse_datetime(end_time)
            if end_dt <= start_dt:
                raise ValueError("end_time must be later than start_time")
        else:
            due_dt = _parse_datetime(due_time)
            start_dt = due_dt
            end_dt = due_dt
            due_iso = _to_iso(due_dt)
            due_ts = int(due_dt.timestamp())

        start_iso = _to_iso(start_dt)
        end_iso = _to_iso(end_dt)
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())
        created_at = _to_iso(datetime.now(UTC).replace(tzinfo=None))

        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                INSERT INTO schedules (title, description, schedule_type, status, start_ts, end_ts, start_time, end_time, due_ts, due_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title_text,
                    description or "",
                    type_value,
                    status_text,
                    start_ts,
                    end_ts,
                    start_iso,
                    end_iso,
                    due_ts,
                    due_iso,
                    created_at,
                ),
            )
            conn.commit()
            event_id = int(cur.lastrowid)

        return {
            "id": event_id,
            "title": title_text,
            "description": description or "",
            "schedule_type": type_value,
            "status": status_text,
            "start_time": start_iso,
            "end_time": end_iso,
            "due_time": due_iso,
            "created_at": created_at,
        }

    def list_events(self, start_time: str = "", end_time: str = "") -> list[dict[str, Any]]:
        sql = (
            "SELECT id, title, description, schedule_type, status, start_time, end_time, due_time, created_at, start_ts, end_ts "
            "FROM schedules"
        )
        params: list[Any] = []
        where: list[str] = []

        if start_time.strip():
            start_ts = int(_parse_datetime(start_time).timestamp())
            where.append("end_ts > ?")
            params.append(start_ts)
        if end_time.strip():
            end_ts = int(_parse_datetime(end_time).timestamp())
            where.append("start_ts < ?")
            params.append(end_ts)

        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY start_ts ASC"

        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()

        return [self._row_to_event(row) for row in rows]

    def _row_to_event(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "title": str(row["title"]),
            "description": str(row["description"]),
            "schedule_type": str(row["schedule_type"]),
            "status": str(row["status"]),
            "start_time": str(row["start_time"]),
            "end_time": str(row["end_time"]),
            "due_time": str(row["due_time"] or ""),
            "created_at": str(row["created_at"]),
        }

    def update_event(
        self,
        event_id: int,
        title: str = "",
        schedule_type: str = "",
        start_time: str = "",
        end_time: str = "",
        due_time: str = "",
    ) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT id, title, description, schedule_type, start_time, end_time, due_time, created_at
                , status
                FROM schedules
                WHERE id = ?
                """,
                (int(event_id),),
            ).fetchone()

            if row is None:
                return {"updated": False, "event": None}

            current = self._row_to_event(row)
            new_type = (schedule_type or current["schedule_type"]).strip().lower()
            if new_type not in {"range", "deadline"}:
                raise ValueError("schedule_type must be 'range' or 'deadline'")

            new_title = (title or current["title"]).strip()
            if not new_title:
                raise ValueError("title cannot be empty")

            if new_type == "range":
                start_dt = _parse_datetime(start_time or current["start_time"])
                end_dt = _parse_datetime(end_time or current["end_time"])
                if end_dt <= start_dt:
                    raise ValueError("end_time must be later than start_time")
                start_iso = _to_iso(start_dt)
                end_iso = _to_iso(end_dt)
                due_iso = None
                due_ts = None
            else:
                ref_due = due_time or current["due_time"] or current["start_time"]
                due_dt = _parse_datetime(ref_due)
                start_iso = _to_iso(due_dt)
                end_iso = _to_iso(due_dt)
                due_iso = _to_iso(due_dt)
                due_ts = int(due_dt.timestamp())

            start_ts = int(_parse_datetime(start_iso).timestamp())
            end_ts = int(_parse_datetime(end_iso).timestamp())

            conn.execute(
                """
                UPDATE schedules
                SET title = ?, schedule_type = ?, start_ts = ?, end_ts = ?, start_time = ?, end_time = ?, due_ts = ?, due_time = ?
                WHERE id = ?
                """,
                (new_title, new_type, start_ts, end_ts, start_iso, end_iso, due_ts, due_iso, int(event_id)),
            )
            conn.commit()

            updated_row = conn.execute(
                """
                SELECT id, title, description, schedule_type, start_time, end_time, due_time, created_at
                , status
                FROM schedules
                WHERE id = ?
                """,
                (int(event_id),),
            ).fetchone()

        return {"updated": True, "event": self._row_to_event(updated_row)}

    def update_event_status(self, event_id: int, status: str) -> dict[str, Any]:
        status_text = (status or "").strip()
        if status_text not in VALID_STATUSES:
            raise ValueError("status must be one of: 未开始, 进行中, 已完成")

        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE schedules SET status = ? WHERE id = ?",
                (status_text, int(event_id)),
            )
            conn.commit()
            if cur.rowcount <= 0:
                return {"updated": False, "event": None}

            row = conn.execute(
                """
                SELECT id, title, description, schedule_type, status, start_time, end_time, due_time, created_at
                FROM schedules
                WHERE id = ?
                """,
                (int(event_id),),
            ).fetchone()

        return {"updated": True, "event": self._row_to_event(row)}

    def delete_event(self, event_id: int) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.execute("DELETE FROM schedules WHERE id = ?", (int(event_id),))
            conn.commit()
            return cur.rowcount > 0

    def find_free_slots(self, range_start: str, range_end: str, min_minutes: int = 30) -> list[dict[str, Any]]:
        start_dt = _parse_datetime(range_start)
        end_dt = _parse_datetime(range_end)
        if end_dt <= start_dt:
            raise ValueError("range_end must be later than range_start")

        minimum_seconds = max(1, int(min_minutes)) * 60
        range_start_ts = int(start_dt.timestamp())
        range_end_ts = int(end_dt.timestamp())

        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT start_ts, end_ts
                FROM schedules
                WHERE schedule_type = 'range' AND end_ts > ? AND start_ts < ?
                ORDER BY start_ts ASC
                """,
                (range_start_ts, range_end_ts),
            ).fetchall()

        merged: list[tuple[int, int]] = []
        for row in rows:
            busy_start = max(range_start_ts, int(row["start_ts"]))
            busy_end = min(range_end_ts, int(row["end_ts"]))
            if busy_end <= busy_start:
                continue

            if not merged or busy_start > merged[-1][1]:
                merged.append((busy_start, busy_end))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], busy_end))

        free_slots: list[dict[str, Any]] = []
        cursor = range_start_ts
        for busy_start, busy_end in merged:
            if busy_start - cursor >= minimum_seconds:
                free_slots.append(
                    {
                        "start_time": _to_iso(datetime.fromtimestamp(cursor)),
                        "end_time": _to_iso(datetime.fromtimestamp(busy_start)),
                        "minutes": (busy_start - cursor) // 60,
                    }
                )
            cursor = max(cursor, busy_end)

        if range_end_ts - cursor >= minimum_seconds:
            free_slots.append(
                {
                    "start_time": _to_iso(datetime.fromtimestamp(cursor)),
                    "end_time": _to_iso(datetime.fromtimestamp(range_end_ts)),
                    "minutes": (range_end_ts - cursor) // 60,
                }
            )

        return free_slots


class LocalScheduleComponent(MCPComponent):
    def __init__(self, db_path: str | None = None) -> None:
        self.store = LocalScheduleStore(db_path=db_path)

    def register(self, mcp: Any) -> None:
        @mcp.tool()
        def schedule_list_events(start_time: str = "", end_time: str = "") -> dict:
            """List local schedule events. Optional start_time/end_time (ISO datetime)."""
            events = self.store.list_events(start_time=start_time, end_time=end_time)
            return {"success": True, "count": len(events), "events": events}

        @mcp.tool()
        def schedule_add_event(
            title: str,
            schedule_type: str = "range",
            start_time: str = "",
            end_time: str = "",
            due_time: str = "",
            status: str = "未开始",
            description: str = "",
        ) -> dict:
            """Add local event. schedule_type=range uses start/end. schedule_type=deadline uses due_time."""
            try:
                event = self.store.add_event(
                    title=title,
                    schedule_type=schedule_type,
                    start_time=start_time,
                    end_time=end_time,
                    due_time=due_time,
                    status=status,
                    description=description,
                )
                return {"success": True, "event": event}
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc)}

        @mcp.tool()
        def schedule_delete_event(event_id: int) -> dict:
            """Delete a local schedule event by event_id."""
            deleted = self.store.delete_event(event_id)
            return {"success": True, "deleted": deleted, "event_id": int(event_id)}

        @mcp.tool()
        def schedule_update_event(
            event_id: int,
            title: str = "",
            schedule_type: str = "",
            start_time: str = "",
            end_time: str = "",
            due_time: str = "",
        ) -> dict:
            """Update local event title and date fields. For range use start/end, for deadline use due_time."""
            try:
                result = self.store.update_event(
                    event_id=event_id,
                    title=title,
                    schedule_type=schedule_type,
                    start_time=start_time,
                    end_time=end_time,
                    due_time=due_time,
                )
                return {"success": True, **result}
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc), "event_id": int(event_id)}

        @mcp.tool()
        def schedule_update_status(event_id: int, status: str) -> dict:
            """Update event status: 未开始 / 进行中 / 已完成."""
            try:
                result = self.store.update_event_status(event_id=event_id, status=status)
                return {"success": True, **result}
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc), "event_id": int(event_id)}

        @mcp.tool()
        def schedule_find_free_slots(range_start: str, range_end: str, min_minutes: int = 30) -> dict:
            """Find free slots in local schedules between range_start and range_end (ISO datetime)."""
            try:
                slots = self.store.find_free_slots(
                    range_start=range_start,
                    range_end=range_end,
                    min_minutes=min_minutes,
                )
                return {"success": True, "count": len(slots), "free_slots": slots}
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc)}

    def export_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "schedule_list_events",
                "description": "List local schedule events with optional time range filter.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                    },
                },
            },
            {
                "name": "schedule_add_event",
                "description": "Add local schedule event, range or deadline type.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "schedule_type": {"type": "string"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                        "due_time": {"type": "string"},
                        "status": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["title"],
                },
            },
            {
                "name": "schedule_update_event",
                "description": "Update event title/type/time fields by event_id.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "integer"},
                        "title": {"type": "string"},
                        "schedule_type": {"type": "string"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                        "due_time": {"type": "string"},
                    },
                    "required": ["event_id"],
                },
            },
            {
                "name": "schedule_update_status",
                "description": "Update event status by event_id.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "integer"},
                        "status": {"type": "string"},
                    },
                    "required": ["event_id", "status"],
                },
            },
            {
                "name": "schedule_delete_event",
                "description": "Delete local schedule event by event_id.",
                "input_schema": {
                    "type": "object",
                    "properties": {"event_id": {"type": "integer"}},
                    "required": ["event_id"],
                },
            },
            {
                "name": "schedule_find_free_slots",
                "description": "Find free slots between range_start and range_end.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "range_start": {"type": "string"},
                        "range_end": {"type": "string"},
                        "min_minutes": {"type": "integer"},
                    },
                    "required": ["range_start", "range_end"],
                },
            },
        ]

    def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        if tool_name == "schedule_list_events":
            events = self.store.list_events(
                start_time=str(arguments.get("start_time", "")),
                end_time=str(arguments.get("end_time", "")),
            )
            return {"success": True, "count": len(events), "events": events}

        if tool_name == "schedule_add_event":
            try:
                event = self.store.add_event(
                    title=str(arguments.get("title", "")),
                    schedule_type=str(arguments.get("schedule_type", "range")),
                    start_time=str(arguments.get("start_time", "")),
                    end_time=str(arguments.get("end_time", "")),
                    due_time=str(arguments.get("due_time", "")),
                    status=str(arguments.get("status", "未开始")),
                    description=str(arguments.get("description", "")),
                )
                return {"success": True, "event": event}
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc)}

        if tool_name == "schedule_update_event":
            event_id = int(arguments.get("event_id", 0))
            try:
                result = self.store.update_event(
                    event_id=event_id,
                    title=str(arguments.get("title", "")),
                    schedule_type=str(arguments.get("schedule_type", "")),
                    start_time=str(arguments.get("start_time", "")),
                    end_time=str(arguments.get("end_time", "")),
                    due_time=str(arguments.get("due_time", "")),
                )
                return {"success": True, **result}
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc), "event_id": event_id}

        if tool_name == "schedule_update_status":
            event_id = int(arguments.get("event_id", 0))
            try:
                result = self.store.update_event_status(
                    event_id=event_id,
                    status=str(arguments.get("status", "")),
                )
                return {"success": True, **result}
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc), "event_id": event_id}

        if tool_name == "schedule_delete_event":
            event_id = int(arguments.get("event_id", 0))
            deleted = self.store.delete_event(event_id)
            return {"success": True, "deleted": deleted, "event_id": event_id}

        if tool_name == "schedule_find_free_slots":
            try:
                slots = self.store.find_free_slots(
                    range_start=str(arguments.get("range_start", "")),
                    range_end=str(arguments.get("range_end", "")),
                    min_minutes=int(arguments.get("min_minutes", 30)),
                )
                return {"success": True, "count": len(slots), "free_slots": slots}
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc)}

        raise RuntimeError(f"unknown tool: {tool_name}")
