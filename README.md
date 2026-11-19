# BreatheWise AI 🍃

**Breathe smarter. Live healthier.** A GenAI assistant that helps families and communities get through winter smog and urban air pollution. It shows the air right now, builds a protection plan for every family member, fixes indoor air, compares low-emission choices, and explains the impact of each choice.

*PromptWars Virtual: Challenge 6, Urban Air Quality Assistant.*

## Features

| Tab | What it does |
| --- | --- |
| **Today** | Live estimated AQI (India NAQI, CPCB method), pollutants, 24-hour PM2.5 forecast, cleanest and worst hours, why smog is building (wind, mixing height, fog), a 5×5 area grid, and the **Proactive Guardian**, which checks a planned activity against the forecast and suggests a cleaner time |
| **Family** | **Family Shield**: a risk level for each person (age, conditions, time outdoors) with actions and a *Why?* for each, a whole-home checklist, and an adaptive **daily routine**. Gemini personalises the wording without changing the safety rules |
| **Home Air** | **Indoor Air Doctor**: whether to open the windows now, tips room by room, purifier sizing (CADR = room volume × 5 air changes/hour), and a low-cost DIY filter option |
| **Impact** | **Green Mobility** (CO₂ for 11 travel modes, maths shown), the **What-If simulator** (switching travel mode, moving exercise time to cut inhaled dose, not burning waste, saving electricity) with an optional AI explanation, an **Eco tracker** with streaks and a weekly chart, and **challenges** |
| **Community** | Report burning, dust or smoke. **Gemini Vision** triages a photo (it never estimates AQI from a photo). Neighbours confirm reports. Locations are rounded to about 100 m and photos are not stored |
| **💬 Chat** | Ask BreatheWise, in English or Hindi (understands Hinglish), with **voice input and spoken replies**. Every answer is grounded in the live data and the household profile |

Also included: an EN/हिं interface, offline mode (the service worker serves the last reading with its timestamp), dark mode, reduced-motion support, and keyboard and screen-reader labels.

## Trust and safety

- The AI never invents numbers. Deterministic code computes the AQI, risk scores, emissions and inhaled dose, and Gemini only explains and personalises them. If the AI is unavailable or out of quota, every feature still works with rule-based output.
- Air data is labelled everywhere as a **model estimate** (CAMS via Open-Meteo), not a station reading.
- Every recommendation shows its reasoning, and every calculation shows its assumptions.
- No medical diagnosis. The assistant tells users to seek care for serious symptoms.
- Security: the API key stays on the server, all inputs are validated with Pydantic, requests are rate-limited (stricter for AI), uploads are checked by file signature and capped at 4 MB, responses carry CSP and other security headers, and user text is wrapped as data to resist prompt injection.

## Architecture

```
React (Vite, TS) ──/api──► FastAPI ──► Open-Meteo air quality + weather + geocoding (free, no key)
                                  └──► Google Gemini (google-genai SDK: text, JSON schema, vision)
                                  └──► SQLite (community reports)
```

Backend modules (`backend/app/services`): `aqi` (CPCB maths), `air_quality` (fetching, caching, forecast windows), `risk` (Family Shield), `indoor`, `emissions`, `exposure`, `planner` (alerts and routine), `community`, `assistant` (prompts) and `gemini` (client with model fallback).

## Run locally

```powershell
cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt
```
```powershell
cd frontend; npm install; npm run build
```
```powershell
cd backend; .venv\Scripts\python -m uvicorn app.main:app --port 8000
```
Open http://localhost:8000. Set `GEMINI_API_KEY` in your environment to turn on the AI (see `.env.example`).

For frontend hot reload, run `npm run dev` in `frontend/` (it proxies `/api` to port 8000).

## Tests

```powershell
cd backend; .venv\Scripts\python -m pytest -q
```
```powershell
cd frontend; npm test
```
There are 61 backend tests (AQI breakpoints, risk engine, calculators, every API endpoint, validation, rate limiting, privacy rounding, upload checks) and 7 frontend tests (i18n completeness, formatting).

## Deploy on Vercel (free Hobby plan)

FastAPI runs as a Vercel Python serverless function (`api/index.py`) and the React build is served as static files. `vercel.json` routes `/api/*` to FastAPI.

```powershell
npx vercel --prod
```
Or import the GitHub repo at https://vercel.com/new. Then add your Gemini key under **Project → Settings → Environment Variables** as `GEMINI_API_KEY`, and redeploy. The key is optional: without it the app runs in rule-based mode.

On Vercel, community reports are kept in SQLite under `/tmp`, so they can reset when a function instance restarts. Connect a database (for example Vercel Postgres or Neon) for permanent storage.

## Alternative: Google Cloud Run (Docker, needs a billing account)

```powershell
gcloud run deploy breathewise --source . --region asia-south1 --allow-unauthenticated --set-env-vars GEMINI_API_KEY=YOUR_KEY
```
The single `Dockerfile` builds the frontend and serves it from FastAPI on `$PORT`. Community reports live in `/tmp` (SQLite), so they reset when the container restarts. Use Firestore or Cloud SQL for persistent storage.
