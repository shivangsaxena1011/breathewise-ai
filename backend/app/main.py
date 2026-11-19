"""BreatheWise AI — FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .schemas import (AlertsRequest, ChatRequest, IndoorRequest, Lang, MobilityRequest, PlanRequest, ReportCreate,
                      RoutineRequest, WhatIfRequest)
from .services import air_quality, assistant, emissions, exposure, gemini, indoor, planner, risk
from .services.cache import RateLimiter
from .services.community import ReportStore

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("breathewise")

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
IMAGE_SIGNATURES = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}

general_limiter = RateLimiter(settings.rate_limit_per_minute)
ai_limiter = RateLimiter(settings.ai_rate_limit_per_minute)
AI_PATHS = {"/api/chat", "/api/plan/family", "/api/reports/analyze", "/api/whatif"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "http"):
        app.state.http = httpx.AsyncClient(headers={"User-Agent": "BreatheWise/1.0"})
    if not hasattr(app.state, "store"):
        app.state.store = ReportStore(settings.database_path)
    log.info("AI mode: %s", "Gemini " + settings.gemini_model if settings.ai_enabled else "rules only (no GEMINI_API_KEY)")
    yield
    await app.state.http.aclose()


app = FastAPI(title="BreatheWise AI", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins,
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if (path.startswith("/api/") and request.method == "POST") or path.startswith(("/api/air", "/api/geocode")):
        ip = client_ip(request)
        if not general_limiter.allow(ip) or (path in AI_PATHS and not ai_limiter.allow(ip)):
            return JSONResponse({"detail": "Too many requests — please wait a minute."}, status_code=429)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=(self)"
    if not path.startswith("/api/docs"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob: https://*.tile.openstreetmap.org; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
            "font-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
    return response


async def snapshot_or_502(request: Request, lat: float, lon: float) -> dict[str, Any]:
    try:
        return await air_quality.get_snapshot(request.app.state.http, lat, lon)
    except air_quality.UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ----------------------------------------------------------------------------- meta & data
@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "ai": gemini.enabled(), "model": settings.gemini_model if gemini.enabled() else None}


@app.get("/api/geocode")
async def geocode(request: Request, q: str = Query(min_length=2, max_length=80), lang: Lang = "en"):
    try:
        return {"results": await air_quality.geocode(request.app.state.http, q, lang)}
    except air_quality.UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/air")
async def air(request: Request, lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)):
    return await snapshot_or_502(request, lat, lon)


@app.get("/api/air/grid")
async def air_grid(request: Request, lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)):
    try:
        return await air_quality.get_area_grid(request.app.state.http, lat, lon)
    except air_quality.UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ----------------------------------------------------------------------------- family & daily life
@app.post("/api/plan/family")
async def family_plan(req: PlanRequest, request: Request):
    snap = await snapshot_or_502(request, req.lat, req.lon)
    plan = risk.build_plan(req.household, snap)
    plan["ai"] = await assistant.personalise_plan(plan, req.household, req.lang)
    return plan


@app.post("/api/indoor")
async def indoor_doctor(req: IndoorRequest, request: Request):
    snap = await snapshot_or_502(request, req.lat, req.lon)
    return indoor.diagnose(req.home, req.rooms, snap)


@app.post("/api/routine")
async def daily_routine(req: RoutineRequest, request: Request):
    snap = await snapshot_or_502(request, req.lat, req.lon)
    return planner.routine(req.household, snap, req.commute_mode)


@app.post("/api/alerts")
async def guardian_alerts(req: AlertsRequest, request: Request):
    snap = await snapshot_or_502(request, req.lat, req.lon)
    return planner.alerts(req.activities, snap, req.household)


@app.post("/api/mobility")
async def mobility(req: MobilityRequest):
    return emissions.compare_trip(req.distance_km, req.occupants, req.modes)


@app.post("/api/whatif")
async def what_if(req: WhatIfRequest, request: Request):
    results: dict[str, Any] = {}
    if req.mode_shift:
        s = req.mode_shift
        results["mode_shift"] = emissions.mode_shift(s.from_mode, s.to_mode, s.distance_km_one_way, s.days_per_week, s.occupants)
    if req.energy_saving:
        results["energy_saving"] = emissions.energy_saving(req.energy_saving.kwh_per_month)
    if req.waste_burning:
        results["waste_burning"] = emissions.waste_burning(req.waste_burning.kg_per_week)
    if req.exercise_shift:
        if req.lat is None or req.lon is None:
            raise HTTPException(status_code=422, detail="Location is needed for the exercise-timing scenario.")
        snap = await snapshot_or_502(request, req.lat, req.lon)
        e = req.exercise_shift
        results["exercise_shift"] = exposure.exercise_shift(snap, e.current_hour, e.duration_min, e.intensity)
    if not results:
        raise HTTPException(status_code=422, detail="Pick at least one scenario.")
    explanation = await assistant.explain_what_if(results, req.lang) if req.explain else None
    return {"results": results, "explanation": explanation,
            "disclaimer": "Estimates from stated assumptions; they do not predict exact changes in your neighbourhood AQI."}


# ----------------------------------------------------------------------------- AI assistant
@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    snap = None
    if req.lat is not None and req.lon is not None:
        try:
            snap = await air_quality.get_snapshot(request.app.state.http, req.lat, req.lon)
        except air_quality.UpstreamError:
            snap = None  # still answer, but without numbers
    history = [m.model_dump() for m in req.history]
    return await assistant.chat(req.message, history, snap, req.place, req.household, req.lang)


# ----------------------------------------------------------------------------- community
@app.get("/api/reports")
async def list_reports(request: Request, lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)):
    return {"reports": request.app.state.store.nearby(lat, lon)}


@app.post("/api/reports", status_code=201)
async def create_report(report: ReportCreate, request: Request):
    try:
        return request.app.state.store.add(report)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/reports/{report_id}/confirm")
async def confirm_report(report_id: int, request: Request):
    result = request.app.state.store.confirm(report_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return result


def sniff_image(data: bytes) -> str | None:
    for sig, mime in IMAGE_SIGNATURES.items():
        if data.startswith(sig):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@app.post("/api/reports/analyze")
async def analyze_photo(photo: UploadFile = File(...), lang: Lang = Form("en")):
    data = await photo.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Photo too large (max 4 MB).")
    mime = sniff_image(data)
    if mime is None:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG or WebP images are supported.")
    if not gemini.enabled():
        raise HTTPException(status_code=503, detail="AI photo analysis is not configured; please fill the form manually.")
    result = await assistant.analyse_photo(data, mime, lang)
    if result is None:
        raise HTTPException(status_code=503, detail="AI analysis is unavailable right now; please fill the form manually.")
    result["note"] = "AI describes what is visible; it cannot measure air quality from a photo. The photo is not stored."
    return result


# ----------------------------------------------------------------------------- frontend (SPA)
static_dir = Path(settings.static_dir)
if (static_dir / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (static_dir / full_path).resolve()
        if full_path and candidate.is_file() and static_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-cache"})
