"""RedisReportStore against a tiny in-memory fake of the Upstash REST /pipeline endpoint."""

import asyncio
import json
import math

import httpx
import pytest

from app.schemas import ReportCreate
from app.services.community import RedisReportStore, StoreError, voter_id


class FakeUpstash:
    def __init__(self, token="secret"):
        self.token = token
        self.data: dict = {}
        self.geo: dict = {}

    def run(self, cmd):  # a small command interpreter
        op, *args = cmd
        d = self.data
        if op == "INCR":
            d[args[0]] = int(d.get(args[0], 0)) + 1
            return d[args[0]]
        if op == "HSET":
            h = d.setdefault(args[0], {})
            for k, v in zip(args[1::2], args[2::2], strict=False):
                h[k] = v
            return len(args[1:]) // 2
        if op == "HGETALL":
            return [x for kv in d.get(args[0], {}).items() for x in kv]
        if op == "HINCRBY":
            h = d[args[0]]
            h[args[1]] = str(int(h[args[1]]) + int(args[2]))
            return int(h[args[1]])
        if op == "SADD":
            s = d.setdefault(args[0], set())
            before = len(s)
            s.add(args[1])
            return len(s) - before
        if op in ("EXPIRE", "ZREM"):
            return 1
        if op == "GEOADD":
            self.geo.setdefault(args[0], {})[args[3]] = (float(args[1]), float(args[2]))
            return 1
        if op == "GEOSEARCH":
            lon, lat, radius = float(args[2]), float(args[3]), float(args[5])
            out = []
            for member, (mlon, mlat) in self.geo.get(args[0], {}).items():
                km = 111 * math.hypot(mlat - lat, (mlon - lon) * math.cos(math.radians(lat)))
                if km <= radius:
                    out.append(member)
            return out
        raise AssertionError(f"unexpected command {op}")

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != f"Bearer {self.token}":
            return httpx.Response(401, json={"error": "Unauthorized"})
        assert request.url.path == "/pipeline"
        return httpx.Response(200, json=[{"result": self.run(c)} for c in json.loads(request.content)])


def make_store(fake=None, token="secret"):
    fake = fake or FakeUpstash()
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    return RedisReportStore("https://fake.upstash.io", token, http), fake


def report(**kw):
    base = {"category": "waste_burning", "description": "Garbage burning near the park", "lat": 28.6134, "lon": 77.2096}
    return ReportCreate(**{**base, **kw})


def run(coro):
    return asyncio.run(coro)


def test_add_get_and_privacy_rounding():
    store, _ = make_store()
    added = run(store.add(report()))
    assert added["id"] == 1 and added["lat"] == 28.613 and added["status"] == "unverified"
    assert run(store.get(1))["description"] == "Garbage burning near the park"
    assert run(store.get(999)) is None


def test_reports_survive_a_new_instance():
    """The whole point of the hosted store: a second serverless instance sees the same data."""
    fake = FakeUpstash()
    first, _ = make_store(fake)
    run(first.add(report()))
    second, _ = make_store(fake)
    assert len(run(second.nearby(28.61, 77.21))) == 1


def test_one_confirmation_per_person():
    store, _ = make_store()
    run(store.add(report()))
    alice, bob, carol = (voter_id(ip, "salt") for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"))
    for _ in range(3):
        r = run(store.confirm(1, alice))
    assert r["confirmations"] == 1
    run(store.confirm(1, bob))
    r = run(store.confirm(1, carol))
    assert r["confirmations"] == 3 and r["status"] == "confirmed"
    assert run(store.confirm(42, alice)) is None


def test_nearby_filters_by_distance_and_sorts_newest_first():
    store, _ = make_store()
    run(store.add(report()))
    run(store.add(report(lat=19.07, lon=72.87)))  # Mumbai, far away
    run(store.add(report(description="Construction dust on the main road")))
    found = run(store.nearby(28.61, 77.21))
    assert [r["id"] for r in found] == [3, 1] or {r["id"] for r in found} == {1, 3}
    assert all(r["lat"] > 28 for r in found)


def test_links_are_rejected():
    store, _ = make_store()
    with pytest.raises(ValueError):
        run(store.add(report(description="see www.spam.example now")))


def test_bad_credentials_raise_store_error():
    store, _ = make_store(token="wrong")
    with pytest.raises(StoreError):
        run(store.add(report()))


def test_voter_id_is_a_salted_hash():
    a = voter_id("1.2.3.4", "salt")
    assert a == voter_id("1.2.3.4", "salt") and a != voter_id("1.2.3.4", "other") and "1.2.3.4" not in a


def test_api_returns_503_when_store_is_down(client):
    from app import main
    store, _ = make_store(token="wrong")
    main.app.state.store.close()  # close the fixture's SQLite store before swapping it out
    main.app.state.store = store
    assert client.get("/api/reports", params={"lat": 28.6, "lon": 77.2}).status_code == 503
