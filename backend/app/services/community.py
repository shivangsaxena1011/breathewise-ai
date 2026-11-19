"""Community pollution reports (SQLite, stdlib only).

Privacy: coordinates are rounded to ~100 m, no names/emails/photos are stored.
Reports are shown as "unverified" until several neighbours confirm them.
"""

from __future__ import annotations

import math
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from ..schemas import ReportCreate

_lock = threading.Lock()
BLOCKLIST = {"http://", "https://", "www.", "<script"}
CONFIRMED_AT = 3


class ReportStore:
    def __init__(self, path: str) -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                created_at INTEGER NOT NULL,
                confirmations INTEGER NOT NULL DEFAULT 0,
                ai_assisted INTEGER NOT NULL DEFAULT 0
            )""")
        self._conn.commit()

    @staticmethod
    def moderate(text: str) -> bool:
        low = text.lower()
        return not any(bad in low for bad in BLOCKLIST)

    def add(self, report: ReportCreate) -> dict[str, Any]:
        if not self.moderate(report.description):
            raise ValueError("Links and markup are not allowed in reports.")
        with _lock:
            cur = self._conn.execute(
                "INSERT INTO reports (category, description, lat, lon, created_at, ai_assisted) VALUES (?,?,?,?,?,?)",
                (report.category, report.description, round(report.lat, 3), round(report.lon, 3),
                 int(time.time()), int(report.ai_assisted)),
            )
            self._conn.commit()
            return self.get(cur.lastrowid)

    def get(self, report_id: int) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        return self._row(row) if row else None

    def confirm(self, report_id: int) -> dict[str, Any] | None:
        with _lock:
            self._conn.execute("UPDATE reports SET confirmations = confirmations + 1 WHERE id = ?", (report_id,))
            self._conn.commit()
        return self.get(report_id)

    def nearby(self, lat: float, lon: float, radius_km: float = 25, days: int = 14, limit: int = 100) -> list[dict[str, Any]]:
        dlat = radius_km / 111.0
        dlon = radius_km / (111.0 * max(0.1, math.cos(math.radians(lat))))
        since = int(time.time()) - days * 86400
        rows = self._conn.execute(
            "SELECT * FROM reports WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT ?",
            (lat - dlat, lat + dlat, lon - dlon, lon + dlon, since, limit),
        ).fetchall()
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["ai_assisted"] = bool(d["ai_assisted"])
        d["status"] = "confirmed" if d["confirmations"] >= CONFIRMED_AT else "unverified"
        return d
