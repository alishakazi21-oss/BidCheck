"""
BidCheck - Vercel serverless entry point.

Vercel serverless functions run in a read-only filesystem (except /tmp).
This module sets DATABASE_URL to /tmp before any other import so that
SQLAlchemy always writes to the writable temp partition.

NOTE: /tmp is ephemeral per cold-start. For production use, switch
DATABASE_URL to a persistent Postgres or PlanetScale URL via Vercel env vars.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Ensure /tmp is used for SQLite on Vercel (read-only fs everywhere else) ──
# Set before any app imports so config.py picks it up at module load time.
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:////tmp/bidcheck.db"

# Force fake extractor — no PDFs available in serverless context
if "EXTRACTOR" not in os.environ:
    os.environ["EXTRACTOR"] = "fake"

# ── Add project root to sys.path ─────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Import the FastAPI app ───────────────────────────────────────────────────
from app.api.main import app  # noqa: E402  (import after sys.path patch)

# ── Vercel ASGI handler ──────────────────────────────────────────────────────
# Vercel calls `handler` as the ASGI entry point.
handler = app
