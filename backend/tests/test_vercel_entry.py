"""The Vercel entry point must work even when the platform skips ASGI lifespan events."""

import importlib.util
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from tests.conftest import mock_transport

ENTRY = Path(__file__).resolve().parents[2] / "api" / "index.py"


def test_vercel_entry_exposes_app_and_works_without_lifespan():
    spec = importlib.util.spec_from_file_location("vercel_entry", ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    from app import main
    from app.services import air_quality

    assert module.app is main.app
    air_quality.clear_cache()
    main.general_limiter.reset()
    main.app.state.http = httpx.AsyncClient(transport=mock_transport())
    main.app.state.store = None  # forces lazy creation, as on a cold serverless start
    try:
        client = TestClient(main.app)  # no `with` block → lifespan never runs
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/air", params={"lat": 28.6, "lon": 77.2}).json()["aqi"]["value"] > 0
        r = client.post("/api/reports", json={"category": "other", "description": "Dust from road works",
                                              "lat": 28.6, "lon": 77.2})
        assert r.status_code == 201
    finally:
        if main.app.state.store is not None:
            main.app.state.store.close()
        main.app.state.http = None
        main.app.state.store = None
