"""
BidCheck - Firebase Cloud Functions (2nd gen) Entry Point.

Wraps the FastAPI ASGI app as a Firebase HTTP function using the
firebase-functions Python SDK.

Routing note: Firebase Hosting rewrites /api/** -> this function.
The function strips the /api prefix and passes the request to FastAPI.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Set environment defaults before any app import ───────────────────────────
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:////tmp/bidcheck.db"

if "EXTRACTOR" not in os.environ:
    os.environ["EXTRACTOR"] = "fake"

os.environ.setdefault("ENVIRONMENT", "production")

# ── Add the bundled app code to sys.path ─────────────────────────────────────
# In Cloud Functions, the working dir is the source directory (functions/).
# We bundle the app/ directory inside functions/app/ during deployment.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── Import FastAPI app ────────────────────────────────────────────────────────
from app.api.main import app as fastapi_app  # noqa: E402

# ── Firebase Functions 2nd gen HTTP handler ───────────────────────────────────
from firebase_functions import https_fn
import asyncio


@https_fn.on_request(region="us-central1")
def bidcheckApi(req: https_fn.Request) -> https_fn.Response:
    """
    Firebase Cloud Functions 2nd gen HTTP handler for BidCheck FastAPI.
    Bridges Firebase's WSGI-style request/response to FastAPI's ASGI interface.
    """
    import io
    from flask import make_response  # firebase_functions uses Flask under the hood

    # Build ASGI scope from the incoming Firebase request
    path = req.path
    # The Firebase rewrite maps /api/** -> this function,
    # but the request path still includes /api prefix.
    # FastAPI routes are mounted at root, so strip /api prefix.
    if path.startswith("/api"):
        path = path[4:] or "/"

    query_string = req.query_string if isinstance(req.query_string, bytes) else req.query_string.encode()
    body = req.get_data()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": req.method,
        "path": path,
        "query_string": query_string,
        "root_path": "",
        "headers": [
            (k.lower().encode(), v.encode())
            for k, v in req.headers
        ],
    }

    # Collect ASGI response via coroutine
    response_started = {}
    response_body = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            response_started["status"] = message["status"]
            response_started["headers"] = message.get("headers", [])
        elif message["type"] == "http.response.body":
            response_body.append(message.get("body", b""))

    async def run():
        await fastapi_app(scope, receive, send)

    # Run the ASGI app synchronously
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(run())
    finally:
        loop.close()

    status = response_started.get("status", 500)
    headers = {
        k.decode(): v.decode()
        for k, v in response_started.get("headers", [])
    }
    full_body = b"".join(response_body)

    resp = make_response(full_body, status)
    for k, v in headers.items():
        resp.headers[k] = v
    return resp

