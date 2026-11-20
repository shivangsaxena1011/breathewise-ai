"""Vercel serverless entry point: exposes the FastAPI app from backend/app.

Vercel serves the built React site (frontend/dist) as static files and routes
every /api/* request here (see vercel.json).
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# Vercel's filesystem is read-only except /tmp.
os.environ.setdefault("DATABASE_PATH", "/tmp/breathewise.db")

from app.main import app  # noqa: F401  (Vercel looks for a module-level `app`)
