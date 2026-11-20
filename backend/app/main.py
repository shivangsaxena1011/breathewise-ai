"""BreatheWise AI — FastAPI application.

Layout: app wiring (clients, store, middleware) first, then the JSON API grouped by feature, then the
optional single-page-app fallback used when the backend also serves the built frontend (Docker).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .schemas import (
    AlertsRequest,
    ChatRequest,
    IndoorRequest,
    Lang,
    MobilityRequest,
    PlanRequest,
    ReportCreate,
    RoutineRequest,
    WhatIfRequest,
)
from .services import air_quality, assistant, emissions, exposure, gemini, indoor, planner, risk
from .services.cache import RateLimiter
from .services.community import RedisReportStore, ReportStore, SQLiteReportStore, StoreError, voter_id

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("breathewise")

JSONDict = dict[str, Any]
Latitude = Annotated[float, Query(ge=-90, le=90)]
Longitude = Annotated[float, Query(ge=-180, le=180)]

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
ON_VERCEL = bool(os.getenv("VERCEL"))
IMAGE_SIGNATURES = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}

general_limiter = RateLimiter(settings.rate_limit_per_minute)
ai_limiter = RateLimiter(settings.ai_rate_limit_per_minute)
AI_PATHS = frozenset({"/api/chat", "/api/plan/family", "/api/reports/analyze", "/api/whatif"})
RATE_LIMITED_GET_PREFIXES = ("/api/air", "/api/geocode")

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
    "connect-src 'self'; font-src 'self'; manifest-src 'self'; worker-src 'self'; object-src 'none'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'self'; upgrade-insecure-requests"
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(self), microphone=(self), geolocation=(self)",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

TOO_MANY_REQUESTS = "Too many requests — please wait a minute."
WHAT_IF_DISCLAIMER = "Estimates from stated assumptions; they do not predict exact changes in your neighbourhood AQI."
PHOTO_NOTE = "AI describes what is visible; it cannot measure air quality from a photo. The photo is not stored."


# ----------------------------------------------------------------------------- shared resources
def get_http(app: FastAPI) -> httpx.AsyncClient:
    """Shared HTTP client, created on first use (serverless platforms may skip lifespan events)."""
    if getattr(app.state, "http", None) is None:
        app.state.http = httpx.AsyncClient(headers={"User-Agent": "BreatheWise/1.0"})
    return app.state.http


def get_store(app: FastAPI) -> ReportStore:
    """Community report store: Upstash Redis when configured (shared across instances), else SQLite."""
    if getattr(app.state, "store", None) is None:
        if settings.redis_url and settings.redis_token:
            app.state.store = RedisReportStore(settings.redis_url, settings.redis_token, get_http(app))
        else:
            app.state.store = SQLiteReportStore(settings.database_path)
    return app.state.store


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the shared client and store at startup and close them on shutdown."""
    get_http(app)
    get_store(app)
    log.info("AI mode: %s", "Gemini " + settings.gemini_model if settings.ai_enabled else "rules only (no GEMINI_API_KEY)")
    yield
    await app.state.http.aclose()
    app.state.http = None
    if getattr(app.state, "store", None) is not None:
        app.state.store.close()
        app.state.store = None


app = FastAPI(
    title="BreatheWise AI",
    version="1.0.0",
    description="Air-quality guidance for families: live AQI, protection plans, indoor air, emissions and community reports.",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept", "Accept-Language"],
)


# ----------------------------------------------------------------------------- middleware
def client_ip(request: Request) -> str:
    """Best-effort client IP. Prefer headers set by the platform edge (Vercel / Cloud Run),
    which a client cannot forge, over the first X-Forwarded-For entry, which it can."""
    if ON_VERCEL:  # Vercel overwrites these, so clients cannot forge them there
        for header in ("x-vercel-forwarded-for", "x-real-ip"):
            if value := request.headers.get(header):
                return value.split(",")[0].strip()
    if fwd := request.headers.get("x-forwarded-for"):
        return fwd.split(",")[-1].strip()  # rightmost entry is appended by the platform's front end
    return request.client.host if request.client else "unknown"


def is_rate_limited(request: Request) -> bool:
    """Count this request against the per-IP limits; True when the caller is over a limit."""
    path = request.url.path
    if not ((path.startswith("/api/") and request.method == "POST") or path.startswith(RATE_LIMITED_GET_PREFIXES)):
        return False
    ip = client_ip(request)
    return not general_limiter.allow(ip) or (path in AI_PATHS and not ai_limiter.allow(ip))


@app.middleware("http")
async def rate_limit(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Reject callers over their per-minute budget before any upstream or AI work happens."""
    if is_rate_limited(request):
        return JSONResponse({"detail": TOO_MANY_REQUESTS}, status_code=429)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Add hardening headers to every response, including 429s (registered last, so it runs outermost)."""
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    if not request.url.path.startswith("/api/docs"):  # Swagger UI loads its own scripts
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    return response


# ----------------------------------------------------------------------------- error handling
@app.exception_handler(air_quality.UpstreamError)
async def upstream_unavailable(_request: Request, exc: air_quality.UpstreamError) -> JSONResponse:
    """The air-quality provider failed: a gateway error, with a message that never leaks internals."""
    return JSONResponse({"detail": str(exc)}, status_code=502)


@app.exception_handler(StoreError)
async def store_unavailable(_request: Request, _exc: StoreError) -> JSONResponse:
    """The report store failed: ask the user to retry rather than exposing the cause."""
    return JSONResponse({"detail": "Community reports are temporarily unavailable. Please try again."}, status_code=503)


async def snapshot(request: Request, lat: float, lon: float) -> JSONDict:
    """Air-quality snapshot for a point; UpstreamError becomes a 502 via the handler above."""
    return await air_quality.get_snapshot(get_http(request.app), lat, lon)


async def snapshot_or_none(request: Request, lat: float | None, lon: float | None) -> JSONDict | None:
    """Snapshot when a location is given and the provider answers; None lets a feature degrade gracefully."""
    if lat is None or lon is None:
        return None
    try:
        return await snapshot(request, lat, lon)
    except air_quality.UpstreamError:
        return None


# ----------------------------------------------------------------------------- meta & data
@app.get("/api/health", tags=["meta"])
async def health() -> JSONDict:
    """Liveness plus which optional features (AI, stations, shared storage) are active."""
    return {
        "status": "ok",
        "ai": gemini.enabled(),
        "stations": bool(settings.waqi_token),
        "reports_storage": "redis" if settings.redis_url and settings.redis_token else "sqlite",
        "model": (gemini.active_model() or settings.gemini_model) if gemini.enabled() else None,
    }


@app.get("/api/geocode", tags=["air"])
async def geocode(request: Request, q: str = Query(min_length=2, max_length=80), lang: Lang = "en") -> JSONDict:
    """Search places by name."""
    return {"results": await air_quality.geocode(get_http(request.app), q, lang)}


@app.get("/api/air", tags=["air"])
async def air(request: Request, lat: Latitude, lon: Longitude) -> JSONDict:
    """Estimated India AQI, pollutants, weather drivers, 3-day hourly forecast and cleanest windows."""
    return await snapshot(request, lat, lon)


@app.get("/api/air/grid", tags=["air"])
async def air_grid(request: Request, lat: Latitude, lon: Longitude) -> JSONDict:
    """Regional PM2.5 on a 5x5 model grid around a point."""
    return await air_quality.get_area_grid(get_http(request.app), lat, lon)


# ----------------------------------------------------------------------------- family & daily life
@app.post("/api/plan/family", tags=["family"])
async def family_plan(req: PlanRequest, request: Request) -> JSONDict:
    """Per-member risk and actions for today, optionally rewritten warmly by Gemini."""
    snap = await snapshot(request, req.lat, req.lon)
    plan = risk.build_plan(req.household, snap, req.lang)
    plan["ai"] = await assistant.personalise_plan(plan, req.lang)
    return plan


@app.post("/api/indoor", tags=["family"])
async def indoor_doctor(req: IndoorRequest, request: Request) -> JSONDict:
    """Ventilation verdict, room-by-room tips and purifier sizing."""
    snap = await snapshot(request, req.lat, req.lon)
    return indoor.diagnose(req.home, req.rooms, snap, req.lang)


@app.post("/api/routine", tags=["family"])
async def daily_routine(req: RoutineRequest, request: Request) -> JSONDict:
    """A timed daily routine (exercise, commute, ventilation) around today's forecast."""
    snap = await snapshot(request, req.lat, req.lon)
    commute = req.commute_mode or next((m.commute_mode for m in req.household.members if m.commute_mode), None)
    return planner.routine(req.household, snap, commute, req.lang)


@app.post("/api/alerts", tags=["family"])
async def guardian_alerts(req: AlertsRequest, request: Request) -> JSONDict:
    """Forecast check for planned activities, with a cleaner time when one exists."""
    snap = await snapshot(request, req.lat, req.lon)
    return planner.alerts(req.activities, snap, req.household, req.lang)


# ----------------------------------------------------------------------------- emissions & what-if
@app.post("/api/mobility", tags=["impact"])
async def mobility(req: MobilityRequest) -> JSONDict:
    """Per-person CO2 of one trip across travel modes."""
    return emissions.compare_trip(req.distance_km, req.occupants, req.modes)


@app.post("/api/whatif", tags=["impact"])
async def what_if(req: WhatIfRequest, request: Request) -> JSONDict:
    """Estimate the effect of habit changes; each requested scenario is computed independently."""
    results: JSONDict = {}
    if shift := req.mode_shift:
        results["mode_shift"] = emissions.mode_shift(
            shift.from_mode, shift.to_mode, shift.distance_km_one_way, shift.days_per_week, shift.occupants
        )
    if req.energy_saving:
        results["energy_saving"] = emissions.energy_saving(req.energy_saving.kwh_per_month)
    if req.waste_burning:
        results["waste_burning"] = emissions.waste_burning(req.waste_burning.kg_per_week)
    if exercise := req.exercise_shift:
        if req.lat is None or req.lon is None:
            raise HTTPException(status_code=422, detail="Location is needed for the exercise-timing scenario.")
        snap = await snapshot_or_none(request, req.lat, req.lon)
        results["exercise_shift"] = (
            exposure.exercise_shift(snap, exercise.current_hour, exercise.duration_min, exercise.intensity)
            if snap is not None
            else {"available": False, "reason": "Forecast unavailable right now."}
        )
    if not results:
        raise HTTPException(status_code=422, detail="Pick at least one scenario.")
    explanation = await assistant.explain_what_if(results, req.lang) if req.explain else None
    return {"results": results, "explanation": explanation, "disclaimer": WHAT_IF_DISCLAIMER}


# ----------------------------------------------------------------------------- AI assistant
@app.post("/api/chat", tags=["assistant"])
async def chat(req: ChatRequest, request: Request) -> JSONDict:
    """Grounded chat answer; without live data it still answers, but never states an AQI."""
    snap = await snapshot_or_none(request, req.lat, req.lon)
    history = [m.model_dump() for m in req.history]
    return await assistant.chat(req.message, history, snap, req.place, req.household, req.lang)


# ----------------------------------------------------------------------------- community
@app.get("/api/reports", tags=["community"])
async def list_reports(request: Request, lat: Latitude, lon: Longitude) -> JSONDict:
    """Recent community reports near a point."""
    return {"reports": await get_store(request.app).nearby(lat, lon)}


@app.post("/api/reports", status_code=201, tags=["community"])
async def create_report(report: ReportCreate, request: Request) -> JSONDict:
    """Add a moderated, anonymous pollution report."""
    try:
        return await get_store(request.app).add(report)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/reports/{report_id}/confirm", tags=["community"])
async def confirm_report(report_id: int, request: Request) -> JSONDict:
    """Confirm a report; each person counts once (a salted IP hash is stored, never the IP)."""
    result = await get_store(request.app).confirm(report_id, voter_id(client_ip(request), settings.voter_salt))
    if result is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return result


def sniff_image(data: bytes) -> str | None:
    """MIME type from the file's magic bytes (never trust the client's Content-Type), or None if unsupported."""
    for signature, mime in IMAGE_SIGNATURES.items():
        if data.startswith(signature):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@app.post("/api/reports/analyze", tags=["community"])
async def analyze_photo(photo: UploadFile = File(...), lang: Lang = Form("en")) -> JSONDict:
    """Classify a photo of a possible pollution source; the image is analysed in memory and never stored."""
    data = await photo.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Photo too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")
    mime = sniff_image(data)
    if mime is None:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG or WebP images are supported.")
    if not gemini.enabled():
        raise HTTPException(status_code=503, detail="AI photo analysis is not configured; please fill the form manually.")
    result = await assistant.analyse_photo(data, mime, lang)
    if result is None:
        raise HTTPException(status_code=503, detail="AI analysis is unavailable right now; please fill the form manually.")
    result["note"] = PHOTO_NOTE
    return result


# ----------------------------------------------------------------------------- frontend (SPA)
def mount_spa(target: FastAPI, static_dir: Path) -> bool:
    """Serve the built React app from ``static_dir`` (Docker); on Vercel the platform serves it instead.

    Returns False when there is no build to serve. Paths are resolved and must stay inside
    ``static_dir``, so ``../`` tricks fall back to index.html instead of reading other files.
    """
    if not (static_dir / "index.html").exists():
        return False
    if (static_dir / "assets").is_dir():
        target.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
    static_root = static_dir.resolve()

    @target.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """Serve a built file if it exists inside the static dir, else index.html (client-side routing)."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (static_root / full_path).resolve()
        if full_path and candidate.is_file() and static_root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(static_root / "index.html", headers={"Cache-Control": "no-cache"})

    return True


mount_spa(app, Path(settings.static_dir))
