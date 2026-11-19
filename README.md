<div align="center">

<img src="frontend/public/logo.svg" alt="BreatheWise AI logo" width="96" height="96" />

# BreatheWise AI

**Breathe smarter. Live healthier.**

A GenAI assistant that helps families and communities get through severe winter smog: what the air is doing right now, what each family member should do about it, and how everyday choices reduce both personal exposure and city emissions.

[![CI](https://github.com/shivangsaxena1011/breathewise-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/shivangsaxena1011/breathewise-ai/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.165-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![Gemini](https://img.shields.io/badge/Google-Gemini-4285F4?logo=google&logoColor=white)
![Tests](https://img.shields.io/badge/tests-157%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/backend%20coverage-92%25-brightgreen)

**[Live demo → breathewise-ai-tau.vercel.app](https://breathewise-ai-tau.vercel.app)**

</div>

---

## Contents

1. [About the hackathon](#about-the-hackathon)
2. [Chosen vertical and persona](#chosen-vertical-and-persona)
3. [The problem](#the-problem)
4. [The solution](#the-solution)
5. [How it works](#how-it-works)
6. [Decision logic](#decision-logic)
7. [GenAI approach](#genai-approach)
8. [Evaluation focus areas](#evaluation-focus-areas)
9. [Assumptions](#assumptions)
10. [Tech stack and project structure](#tech-stack-and-project-structure)
11. [Running, testing and deployment](#running-testing-and-deployment)
12. [Limitations and roadmap](#limitations-and-roadmap)

---

## About the hackathon

**PromptWars Virtual** is a weekly "vibe coding" challenge run by Hack2skill. Individual participants build working applications mostly by prompting GenAI tools against a curated problem statement, and document the problem, the prompt strategy and the solution. The programme encourages prompt-driven development, so builders spend their time on ideas and real-world problems rather than boilerplate.

This project is the submission for **Challenge 6: Urban Air Quality Assistant**:

> *Create a GenAI-powered assistant that helps families and communities navigate severe winter smog and urban air pollution. The application should suggest low-emission daily routines, indoor air quality hacks, and sustainable alternatives tailored to their location and lifestyle, while clearly explaining the direct impact of their choices.*

The full write-up of the prompt strategy is in [BLOG.md](BLOG.md).

## Chosen vertical and persona

| | |
| --- | --- |
| **Vertical** | Urban Air Quality Assistant (environment and public health) |
| **Primary persona** | A parent in a North-Indian city (Delhi, Lucknow, Jabalpur…) who looks after children, older relatives and a commuter, and has to decide every winter morning what is safe |
| **Secondary personas** | Outdoor workers, people with asthma or COPD, and neighbourhood groups that want to act on local pollution sources |
| **Languages** | English and Hindi (Hinglish questions are understood) |

## The problem

AQI apps tell people *how bad* the air is. They rarely tell a family *what to do*: whether the children can play outside, when to air the house, whether the morning walk is safe for an older relative, or whether taking the metro makes any difference. Advice that exists is generic, comes without reasoning, and ignores who is actually in the household. Families also have no simple way to see how their own choices (travel, burning leaves, electricity use) feed the smog they breathe.

## The solution

BreatheWise turns live air-quality data and a short household profile into specific, explained actions. The interface has five tabs and an assistant:

| Area | What the user gets |
| --- | --- |
| **🌤️ Today** | An estimated India AQI (CPCB method) with its category and health statement, current pollutants, and a 24-hour PM2.5 forecast. It marks the **cleanest and worst 2-hour windows** and explains *why* smog is building (low wind, shallow mixing layer, fog). A regional 5×5 pollution grid sits alongside the **Proactive Guardian**, which checks a planned activity against the forecast and suggests a cleaner time. |
| **🛡️ Family Shield** | A risk level for **each family member** based on age, health conditions and time outdoors. Every action comes with a "Why?". It also gives a whole-home checklist and an adaptive daily routine built from the forecast windows. |
| **🏠 Indoor Air Doctor** | Whether to open the windows right now, tips room by room, purifier sizing (clean-air delivery rate) for each room, and a low-cost DIY filter option for families without a purifier. |
| **🌱 Travel & Impact** | CO₂ per person for 11 travel modes, with the maths shown. A **What-If simulator** covers switching travel mode, moving exercise to a cleaner hour (inhaled-dose reduction), not burning waste, and saving electricity. An eco tracker adds streaks, a weekly chart and challenges. |
| **📣 Community Watch** | Neighbours report garbage burning, dust or smoke. **Gemini Vision** helps fill the report from a photo, and other people confirm reports. |
| **💬 Ask BreatheWise** | A chat assistant with voice input and spoken replies. Every answer is grounded in the live data and the household profile. |

It also has offline mode (the last reading is shown with its timestamp), dark mode, reduced-motion support and full keyboard use. On phones the five sections move to an app-style bottom navigation bar, with large touch targets and room for iPhone safe areas.

## How it works

```
┌─────────────────────────┐        ┌──────────────────────────────────────────────┐
│  React + TypeScript UI  │  /api  │  FastAPI (Vercel serverless function)        │
│  • 5 tabs + chat        │ ─────► │  • Validation (Pydantic), rate limits, CSP   │
│  • EN / हिं, voice       │        │  • Deterministic engines (AQI, risk, indoor, │
│  • Offline cache        │ ◄───── │    emissions, exposure, alerts, routine)     │
└─────────────────────────┘  JSON  │  • Gemini layer: explain, personalise, triage│
                                   └──────┬──────────────────┬────────────────────┘
                                          │                  │
      Open-Meteo (free, no key)    WAQI stations (CPCB)    Google Gemini API
      • CAMS air-quality model     • nearest live station   • grounded chat
      • weather (wind, mixing)     • measured PM2.5 / AQI   • JSON-schema plans
      • geocoding                                           • vision (photo triage)
```

**Request flow, using the Family Shield as an example**

1. The user picks a city and describes the household (names, ages, conditions, hours outside, commute).
2. The backend fetches hourly air-quality and weather data from the model (cached for 10 minutes for each ~1 km location).
3. Optionally, when a station-data token is configured, the model is calibrated to the nearest monitoring station (see below). The live demo runs on the model alone.
4. Deterministic code computes the AQI, the cleanest and worst windows, and each member's risk score and actions, and records which data was used.
5. Gemini receives that plan as data and rewrites it into warm, personalised guidance in English or Hindi. It may not add numbers or drop safety actions.
6. The UI shows both: the AI summary, and the rule-based actions with their *Why?*. If Gemini is unavailable, the rule-based plan is shown alone.

## Decision logic

All numbers come from transparent, unit-tested code ([`backend/app/services`](backend/app/services)). None of them come from the language model.

| Decision | Logic |
| --- | --- |
| **AQI** | India NAQI (CPCB 2014): a sub-index per pollutant by linear interpolation within the breakpoint band, using 24-hour means for PM2.5, PM10, NO₂ and SO₂ and 8-hour means for O₃ and CO, with at least ⅔ data coverage. AQI is the maximum sub-index, and at least 3 pollutants including PM are required. |
| **Station calibration (optional, off on the demo)** | Use the nearest WAQI station only if it is within 30 km and its reading is under 3 hours old. Convert its US-EPA PM2.5 and PM10 sub-indices back to µg/m³ (2013 EPA breakpoints, the scale WAQI uses). Correction factor = measured ÷ model value for the same hour, limited to between 0.4× and 3×, and skipped if the model reads under 5 µg/m³. The factor scales the 24-hour averages (so the AQI) and the whole hourly forecast, so every feature uses corrected numbers. With no token or no usable station, the model is used alone. |
| **Best and worst time** | The cleanest and dirtiest consecutive 2-hour daytime windows (6:00–21:00) in the next 24 hours, then for each later day. |
| **Smog drivers** | Wind below 6 km/h means pollution isn't dispersing. A mixing layer below 400 m means pollution is trapped near the ground. Humidity above 80% with temperature below 18 °C means fog plus smoke. |
| **Member risk (0–5)** | Today's worst air level, plus 1 for a sensitive age (infant, child, elderly), plus 1 for lung or heart conditions (when the air is Moderate or worse), plus 1 for pregnancy, plus 1 for 4 or more hours outdoors. Capped at 5. Ties go to the person with more sensitivity factors. |
| **Actions** | Rules keyed on risk and profile. Examples: exercise indoors at risk 4+, an N95 at Poor or worse, never a mask for infants, a reliever inhaler for asthma or COPD, and indoor breaks for outdoor workers. |
| **Windows (ventilation)** | Open if the current hour is Good or Satisfactory. Air out briefly if it is Moderate, or if it is clean right now on an otherwise Poor day. Keep closed if it is Poor or worse. |
| **Purifier size** | CADR = room area × height × 5 air changes per hour (given in m³/h and CFM). |
| **Trip CO₂** | Fuel used × fuel carbon content (for example petrol 2.31 kg/L at 15 km/L), electricity × 0.72 kg/kWh Indian grid factor, divided by passengers for shared modes. |
| **Exercise timing** | Inhaled dose = PM2.5 × breathing rate (rest 0.5, light 1.0, moderate 1.6, vigorous 3.0 m³/h) × time. The usual hour is compared with the cleanest hour in the forecast. |
| **Guardian alert** | Average PM2.5 for the activity's duration. Warn at Poor or worse, or at Moderate or worse for sensitive people. Suggest the cleanest *future* daytime hour that day if it is at least 20% cleaner. Activities in the past are flagged. |

## GenAI approach

The core principle is **compute first, then explain**. The model never invents data.

- **Grounding block:** every prompt includes a `CONTEXT` block with the live AQI, pollutants, forecast windows and weather drivers, all computed by the backend.
- **Prompt-injection fencing:** anything the user typed (questions, names, place names) goes inside `<USER_DATA>` tags. Names are JSON-quoted, and the system prompt tells the model to treat that content as data.
- **Structured output:** family plans and photo triage use JSON schemas (`response_json_schema`), so the UI never parses free text.
- **Safety rules in the system prompt:** use only the numbers provided, say that the data is a model estimate, give no medical diagnosis, tell users to seek care for serious symptoms, and always include a low-cost option.
- **Vision guardrails:** the model classifies only what is visible, never estimates AQI from a photo, and never describes people or licence plates.
- **Resilience:** if a model is out of quota or retired, the backend tries the next model in the list (`gemini-3.8-flash`, then `gemini-3.5-flash-lite`, then `gemini-2.5-flash`). If all fail, every feature falls back to rule-based output, so the app never breaks.

## Evaluation focus areas

| Focus area | How BreatheWise addresses it |
| --- | --- |
| **Problem statement alignment** | Every element of the brief maps to a feature. Low-emission daily routines → Daily Routine and Green Mobility. Indoor air quality hacks → Indoor Air Doctor. Sustainable alternatives → What-If and challenges. Tailored to location and lifestyle → live data for the chosen city plus the household profile. Clearly explaining the impact of choices → a *Why?* on every action and assumptions on every number. The app targets families and communities, with English and Hindi support. |
| **Code quality** | Clear layers: routes in `main.py`, pure engines in `services/`, prompts in `assistant.py`, and the AI client in `gemini.py`. Strict TypeScript and typed Pydantic models throughout. The Ruff linter passes with zero issues, and pure logic (`eco.ts`, `aqi.py`) is kept separate from the UI. |
| **Security** | The Gemini key lives only on the server and never reaches the browser. Every input is validated with Pydantic bounds and enums. Requests are rate-limited per IP (stricter for AI endpoints), using headers that can't be forged on Vercel. Uploads are checked by file signature and capped at 4 MB, and photos are never stored. Responses carry CSP, `X-Frame-Options`, `nosniff` and a referrer policy. SQL is parameterised. The UI never injects HTML, and the chat Markdown renderer is tested against XSS. Report locations are rounded to about 100 m, and community reports reject links. |
| **Efficiency** | A 10-minute in-memory cache for each location and a shared HTTP client. Area-grid points are fetched in one batch request. Pages are lazy-loaded (about 80 KB gzipped for the main bundle). Charts and animations are plain CSS and SVG with no chart library, and hashed assets are cached for a year. Gzip is on, and the serverless function starts cold without any startup step. |
| **Testing** | **157 automated tests.** 134 backend tests (pytest, 92%+ coverage) cover AQI breakpoints, risk scoring, every calculator, every API endpoint, validation, rate limiting and spoofing, privacy rounding, upload checks, Gemini fallback with a fake client, prompt fencing, chat-history normalisation, station parsing and calibration, the Redis report store (against a fake Upstash server), Hindi rule text, and the Vercel entry point. 23 frontend tests (Vitest) cover tracker and streak logic, timezone-safe dates, error messages, i18n completeness, XSS-safe Markdown, and city-clock and AQI display helpers. GitHub Actions runs the linter, tests, type check and build on every push. |
| **Accessibility** | Semantic tabs with arrow-key navigation, a skip-to-content control, and labelled inputs. The AQI is shown as a number and a word, never colour alone. Live regions announce results. The chat dialog returns focus when it closes. `prefers-reduced-motion` and dark mode are respected, and every screen works at phone width. The whole interface, voice included, is available in Hindi. |

## Data sources and attribution

- Air-quality model, weather and geocoding: [Open-Meteo](https://open-meteo.com/) (CC BY 4.0), using Copernicus Atmosphere Monitoring Service (CAMS) data.
- Live station readings: the [World Air Quality Index Project](https://waqi.info/), relaying the originating agencies (in India, the Central Pollution Control Board). The app shows these credits with every station reading, as WAQI's terms require. The data is used free of charge, for non-commercial purposes.

## Assumptions

- **Air data** comes from an atmospheric model (CAMS via Open-Meteo, roughly a 10–45 km grid). An optional station-calibration module can correct it with the nearest monitoring station; it is not enabled on the live demo. Busy roads and burning sites can still be worse than both.
- **Calibration** assumes the station's error ratio at the current hour holds for the rest of the forecast. This works well for the next day, when weather patterns are similar, and is an approximation beyond that.
- **The AQI is an estimate** of the CPCB index computed from those concentrations, not an official CPCB value. Station sub-indices are converted using the US-EPA 2013 breakpoints that WAQI reports in.
- **Emission factors** are typical Indian-context values: petrol car 15 km/L, scooter 45 km/L, city bus 30 passengers, grid 0.72 kg CO₂/kWh, open waste burning about 8 g PM2.5 per kg. Each one is shown next to the result.
- **Breathing rates** are typical adult values. Children breathe more air per kg of body weight, which the risk engine reflects qualitatively.
- **Guidance** follows general public-health advice and is **not medical advice**. Serious symptoms always lead to "seek medical care".
- **Privacy by design:** there are no accounts. The household profile and eco tracker stay in the browser. Only the anonymous community reports are stored on the server, and confirmations are keyed by a salted hash of the visitor's IP, never the IP itself. Reports expire after 30 days.

## Tech stack and project structure

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript (strict), Vite, hand-written CSS animations, Web Speech API, service worker |
| Backend | Python 3.12+, FastAPI, Pydantic v2, httpx (async), SQLite or Upstash Redis |
| AI | Google Gemini through the `google-genai` SDK (text, JSON schema, vision) |
| Data | Open-Meteo Air Quality (CAMS), Forecast and Geocoding APIs; World Air Quality Index (WAQI) station feed (relays CPCB stations) |
| Quality | pytest + pytest-cov, Vitest, Ruff, GitHub Actions |
| Hosting | Vercel (static frontend and a Python serverless function) |

```
├── api/index.py              # Vercel entry point → FastAPI app
├── backend/
│   ├── app/
│   │   ├── main.py           # routes, middleware (rate limit, security headers), static serving
│   │   ├── config.py         # settings from environment variables
│   │   ├── schemas.py        # request models with strict bounds
│   │   └── services/
│   │       ├── aqi.py        # CPCB NAQI maths
│   │       ├── air_quality.py# Open-Meteo client, snapshot, forecast windows, smog drivers
│   │       ├── stations.py   # nearest live station + model calibration
│   │       ├── risk.py       # Family Shield risk engine
│   │       ├── indoor.py     # ventilation verdict, room tips, purifier sizing
│   │       ├── emissions.py  # travel / energy / burning estimates
│   │       ├── exposure.py   # inhaled-dose What-If
│   │       ├── planner.py    # Guardian alerts, daily routine
│   │       ├── community.py  # community reports: SQLite locally, Upstash Redis when hosted
│   │       ├── assistant.py  # prompts, grounding, rule-based fallback
│   │       ├── i18n.py       # English / Hindi text for rule-based output
│   │       └── gemini.py     # Gemini client with model fallback
│   └── tests/                # 134 pytest tests
├── frontend/
│   ├── public/               # logo, manifest, service worker
│   └── src/
│       ├── pages/            # Today, Family, HomeAir, Impact, Community
│       ├── Chat.tsx          # assistant with voice
│       ├── eco.ts            # tracker / streak / challenge logic (pure)
│       ├── i18n.ts           # English + Hindi strings
│       └── *.test.ts(x)      # 23 Vitest tests
├── vercel.json               # build, routing, security headers
├── BLOG.md                   # technical blog (problem, prompt strategy, solution)
└── .github/workflows/ci.yml  # lint + tests + build on every push
```

## Running, testing and deployment

**Prerequisites:** Python 3.12+ and Node.js 22+. A Gemini API key is optional: without one, the app runs in rule-based mode.

From the project folder:

```powershell
cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt
```
```powershell
cd frontend; npm install; npm run build
```
```powershell
$env:GEMINI_API_KEY = "<your key>"; cd backend; .venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Then open http://localhost:8000. For frontend hot reload, run `npm run dev` in `frontend/`, which proxies `/api` to port 8000.

**Tests and checks**

```powershell
cd backend; .venv\Scripts\python -m ruff check app tests ..\api; .venv\Scripts\python -m pytest --cov=app
```
```powershell
cd frontend; npx tsc --noEmit; npm test
```

**Configuration** (environment variables, see [.env.example](.env.example)): `GEMINI_API_KEY`, `WAQI_TOKEN` (free, for live station data), `KV_REST_API_URL` and `KV_REST_API_TOKEN` (Upstash Redis, for persistent reports; set automatically by Vercel's Upstash integration), `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS`, `ALLOWED_ORIGINS`, `RATE_LIMIT_PER_MINUTE`, `AI_RATE_LIMIT_PER_MINUTE`, `AIR_CACHE_SECONDS`.

**Deployment:** the app is deployed on **Vercel**. `vercel.json` builds the React app as static files and runs FastAPI as a Python serverless function (`api/index.py`) for every `/api/*` route. The Gemini key is set as a Vercel environment variable. A `Dockerfile` is also included for container platforms such as Google Cloud Run.

## Limitations and roadmap

- **Persistence:** on the live demo, community reports are kept in per-instance SQLite and can reset when Vercel restarts an instance. The code already supports a hosted Redis store (Upstash) for permanent, shared reports; it is not enabled on the demo.
- **Data:** the next step is to combine several nearby stations (inverse-distance weighting) and add a station map layer.
- **Planned features:** push notifications for the Guardian, more Indian languages, and school and neighbourhood dashboards.

---

<div align="center">

**We don't just tell people how polluted their city is. We help them decide what to do next.**

Built for PromptWars Virtual, Challenge 6 by **[Shivang Saxena](https://github.com/shivangsaxena1011)**. *General guidance, not medical advice.*

</div>
