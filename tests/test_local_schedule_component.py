from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from components.local_schedule import LocalScheduleStore


class LocalScheduleStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "schedule.sqlite3"
        self.store = LocalScheduleStore(str(self.db_path))

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_add_and_list_events(self) -> None:
        event = self.store.add_event(
            title="Daily Standup",
            schedule_type="range",
            start_time="2026-04-26T09:00:00",
            end_time="2026-04-26T09:30:00",
            description="Team sync",
        )

        events = self.store.list_events("2026-04-26T00:00:00", "2026-04-27T00:00:00")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], event["id"])
        self.assertEqual(events[0]["title"], "Daily Standup")
        self.assertEqual(events[0]["schedule_type"], "range")
        self.assertEqual(events[0]["status"], "未开始")

    def test_add_deadline_and_list(self) -> None:
        deadline = self.store.add_event(
            title="Submit report",
            schedule_type="deadline",
            due_time="2026-04-26T17:20:49",
            description="Q2 report",
        )

        events = self.store.list_events("2026-04-26T00:00:00", "2026-04-27T00:00:00")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], deadline["id"])
        self.assertEqual(events[0]["schedule_type"], "deadline")
        self.assertEqual(events[0]["due_time"], "2026-04-26T17:20:49")

    def test_delete_event(self) -> None:
        event = self.store.add_event(
            title="Doctor",
            schedule_type="range",
            start_time="2026-04-26T10:00:00",
            end_time="2026-04-26T11:00:00",
            description="",
        )

        deleted = self.store.delete_event(event["id"])
        self.assertTrue(deleted)
        self.assertEqual(self.store.list_events(), [])

    def test_find_free_slots(self) -> None:
        self.store.add_event(
            title="Busy-1",
            schedule_type="range",
            start_time="2026-04-26T09:00:00",
            end_time="2026-04-26T10:00:00",
            description="",
        )
        self.store.add_event(
            title="Busy-2",
            schedule_type="range",
            start_time="2026-04-26T11:00:00",
            end_time="2026-04-26T12:00:00",
            description="",
        )
        self.store.add_event(
            title="DDL only",
            schedule_type="deadline",
            due_time="2026-04-26T10:20:49",
            description="No blocking",
        )

        slots = self.store.find_free_slots(
            range_start="2026-04-26T08:00:00",
            range_end="2026-04-26T13:00:00",
            min_minutes=30,
        )
        self.assertEqual(
            slots,
            [
                {"start_time": "2026-04-26T08:00:00", "end_time": "2026-04-26T09:00:00", "minutes": 60},
                {"start_time": "2026-04-26T10:00:00", "end_time": "2026-04-26T11:00:00", "minutes": 60},
                {"start_time": "2026-04-26T12:00:00", "end_time": "2026-04-26T13:00:00", "minutes": 60},
            ],
        )

    def test_reject_invalid_payload_by_type(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_event(
                title="Invalid range",
                schedule_type="range",
                start_time="2026-04-26T10:00:00",
                description="missing end",
            )

        with self.assertRaises(ValueError):
            self.store.add_event(
                title="Invalid deadline",
                schedule_type="deadline",
                start_time="2026-04-26T10:00:00",
                end_time="2026-04-26T11:00:00",
                description="wrong fields",
            )

    def test_update_event_title_and_time(self) -> None:
        event = self.store.add_event(
            title="Old name",
            schedule_type="deadline",
            due_time="2026-04-30T12:00:00",
            description="",
        )

        updated = self.store.update_event(
            event_id=event["id"],
            title="New name",
            due_time="2026-05-01T18:30:00",
        )

        self.assertTrue(updated["updated"])
        self.assertEqual(updated["event"]["title"], "New name")
        self.assertEqual(updated["event"]["due_time"], "2026-05-01T18:30:00")

    def test_update_event_status(self) -> None:
        event = self.store.add_event(
            title="Status test",
            schedule_type="deadline",
            due_time="2026-05-02T10:00:00",
            description="",
        )

        out = self.store.update_event_status(event_id=event["id"], status="进行中")
        self.assertTrue(out["updated"])
        self.assertEqual(out["event"]["status"], "进行中")

        with self.assertRaises(ValueError):
            self.store.update_event_status(event_id=event["id"], status="未知")

    def test_migrates_old_schema_without_schedule_type_column(self) -> None:
        legacy_db = Path(self.tmp_dir.name) / "legacy.sqlite3"
        conn = sqlite3.connect(legacy_db)
        conn.execute(
            """
            CREATE TABLE schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                start_ts INTEGER NOT NULL,
                end_ts INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

        migrated = LocalScheduleStore(str(legacy_db))
        event = migrated.add_event(
            title="After migration",
            schedule_type="deadline",
            due_time="2026-04-26T20:20:49",
            description="ok",
        )
        self.assertEqual(event["schedule_type"], "deadline")


if __name__ == "__main__":
    unittest.main()
