"""Community pollution reports.

Two interchangeable stores with the same async interface:
- SQLiteReportStore: stdlib only, for local runs and tests.
- RedisReportStore: Upstash Redis over its HTTPS REST API, for serverless hosting (Vercel), where the
  local filesystem is per-instance and temporary. Selected automatically when its env vars are set.

Privacy: coordinates are rounded to ~100 m; no names, emails or photos are stored. Each confirmation
is keyed by a salted hash of the visitor's IP, so one person counts once without storing the IP.
Reports show as "unverified" until several different neighbours confirm them.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import math
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Protocol

import httpx

from ..schemas import ReportCreate

BLOCKLIST = {"http://", "https://", "www.", "<script"}
CONFIRMED_AT = 3
RETENTION_DAYS = 30
NEARBY_KM = 25
NEARBY_DAYS = 14


def moderate(text: str) -> bool:
    low = text.lower()
    return not any(bad in low for bad in BLOCKLIST)


def voter_id(ip: str, salt: str) -> str:
    """Stable pseudonym for one visitor: a keyed HMAC of the IP, so the IP itself is never stored."""
    return hmac.new(salt.encode(), ip.encode(), hashlib.sha256).hexdigest()[:20]


def present(d: dict[str, Any]) -> dict[str, Any]:
    out = {
        "id": int(d["id"]),
        "category": d["category"],
        "description": d["description"],
        "lat": float(d["lat"]),
        "lon": float(d["lon"]),
        "created_at": int(d["created_at"]),
        "confirmations": int(d["confirmations"]),
        "ai_assisted": str(d["ai_assisted"]) in ("1", "True", "true"),
    }
    out["status"] = "confirmed" if out["confirmations"] >= CONFIRMED_AT else "unverified"
    return out


class ReportStore(Protocol):
    async def add(self, report: ReportCreate) -> dict[str, Any]: ...
    async def get(self, report_id: int) -> dict[str, Any] | None: ...
    async def confirm(self, report_id: int, voter: str) -> dict[str, Any] | None: ...
    async def nearby(self, lat: float, lon: float) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...


class SQLiteReportStore:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                created_at INTEGER NOT NULL,
                confirmations INTEGER NOT NULL DEFAULT 0,
                ai_assisted INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS confirmations (
                report_id INTEGER NOT NULL,
                voter TEXT NOT NULL,
                PRIMARY KEY (report_id, voter)
            );
            CREATE INDEX IF NOT EXISTS idx_reports_place ON reports (lat, lon, created_at);
        """)
        self._conn.commit()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._conn.close()

    def __del__(self) -> None:
        self.close()

    async def add(self, report: ReportCreate) -> dict[str, Any]:
        if not moderate(report.description):
            raise ValueError("Links and markup are not allowed in reports.")
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO reports (category, description, lat, lon, created_at, ai_assisted) VALUES (?,?,?,?,?,?)",
                (report.category, report.description, round(report.lat, 3), round(report.lon, 3),
                 int(time.time()), int(report.ai_assisted)),
            )
            self._conn.commit()
        created = await self.get(cur.lastrowid or 0)
        if created is None:  # pragma: no cover - SQLite always returns the inserted row
            raise StoreError("Report could not be saved")
        return created

    async def get(self, report_id: int) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        return present(dict(row)) if row else None

    async def confirm(self, report_id: int, voter: str) -> dict[str, Any] | None:
        if await self.get(report_id) is None:
            return None
        with self._lock:
            new = self._conn.execute("INSERT OR IGNORE INTO confirmations (report_id, voter) VALUES (?, ?)",
                                     (report_id, voter)).rowcount
            if new:
                self._conn.execute("UPDATE reports SET confirmations = confirmations + 1 WHERE id = ?", (report_id,))
            self._conn.commit()
        return await self.get(report_id)

    async def nearby(self, lat: float, lon: float) -> list[dict[str, Any]]:
        dlat = NEARBY_KM / 111.0
        dlon = NEARBY_KM / (111.0 * max(0.1, math.cos(math.radians(lat))))
        since = int(time.time()) - NEARBY_DAYS * 86400
        rows = self._conn.execute(
            "SELECT * FROM reports WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 100",
            (lat - dlat, lat + dlat, lon - dlon, lon + dlon, since),
        ).fetchall()
        return [present(dict(r)) for r in rows]


class StoreError(RuntimeError):
    """The hosted database could not be reached."""


class RedisReportStore:
    """Upstash Redis via its REST API (POST /pipeline with a list of commands)."""

    PREFIX = "bw"

    def __init__(self, url: str, token: str, http: httpx.AsyncClient) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self.http = http

    def close(self) -> None:  # the shared HTTP client is owned by the app
        pass

    def _k(self, *parts: Any) -> str:
        return ":".join([self.PREFIX, *map(str, parts)])

    async def _pipeline(self, *commands: list[Any]) -> list[Any]:
        try:
            resp = await self.http.post(f"{self.url}/pipeline", json=[[str(c) for c in cmd] for cmd in commands],
                                        headers={"Authorization": f"Bearer {self.token}"}, timeout=8.0)
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StoreError(f"Report database unavailable ({type(exc).__name__})") from exc
        if not isinstance(body, list) or any(isinstance(r, dict) and "error" in r for r in body):
            raise StoreError("Report database rejected the request")
        return [r.get("result") if isinstance(r, dict) else None for r in body]

    @staticmethod
    def _hash(flat: list[Any] | None) -> dict[str, Any] | None:
        if not flat:
            return None
        return dict(zip(flat[0::2], flat[1::2], strict=False))

    async def add(self, report: ReportCreate) -> dict[str, Any]:
        if not moderate(report.description):
            raise ValueError("Links and markup are not allowed in reports.")
        (new_id,) = await self._pipeline(["INCR", self._k("reports", "seq")])
        lat, lon, ttl = round(report.lat, 3), round(report.lon, 3), RETENTION_DAYS * 86400
        data = {"id": new_id, "category": report.category, "description": report.description, "lat": lat, "lon": lon,
                "created_at": int(time.time()), "confirmations": 0, "ai_assisted": int(report.ai_assisted)}
        fields = [x for kv in data.items() for x in kv]
        await self._pipeline(
            ["HSET", self._k("report", new_id), *fields],
            ["EXPIRE", self._k("report", new_id), ttl],
            ["GEOADD", self._k("reports", "geo"), lon, lat, new_id],
        )
        return present(data)

    async def get(self, report_id: int) -> dict[str, Any] | None:
        (flat,) = await self._pipeline(["HGETALL", self._k("report", report_id)])
        found = self._hash(flat)
        return present(found) if found else None

    async def confirm(self, report_id: int, voter: str) -> dict[str, Any] | None:
        if await self.get(report_id) is None:
            return None
        voters = self._k("report", report_id, "voters")
        added, _ = await self._pipeline(["SADD", voters, voter], ["EXPIRE", voters, RETENTION_DAYS * 86400])
        if added:
            await self._pipeline(["HINCRBY", self._k("report", report_id), "confirmations", 1])
        return await self.get(report_id)

    async def nearby(self, lat: float, lon: float) -> list[dict[str, Any]]:
        geo = self._k("reports", "geo")
        (ids,) = await self._pipeline(["GEOSEARCH", geo, "FROMLONLAT", lon, lat, "BYRADIUS", NEARBY_KM, "km",
                                       "ASC", "COUNT", 200])
        ids = ids or []
        if not ids:
            return []
        rows = await self._pipeline(*[["HGETALL", self._k("report", i)] for i in ids])
        since = int(time.time()) - NEARBY_DAYS * 86400
        expired = [i for i, flat in zip(ids, rows, strict=False) if not flat]
        if expired:  # report hashes expire on their own; tidy the geo index lazily
            await self._pipeline(["ZREM", geo, *expired])
        found = [present(h) for h in (self._hash(f) for f in rows) if h]
        found = [r for r in found if r["created_at"] >= since]
        return sorted(found, key=lambda r: r["created_at"], reverse=True)[:100]
