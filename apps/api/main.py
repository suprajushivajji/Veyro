"""FastAPI application entrypoint for RecoverOS."""

import json
import os
from collections import Counter
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


app = FastAPI(title="RecoverOS API", version="0.1.0")
DATA_DIR = Path(__file__).resolve().parents[2] / "ml" / "dataset"


def _load_records(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as data_file:
        records = json.load(data_file)
    return records if isinstance(records, list) else []


def _database_is_connected() -> bool:
    """Check PostgreSQL only when a database URL is configured."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return False
    try:
        import psycopg2
    except ImportError:
        return False
    try:
        connection = psycopg2.connect(database_url, connect_timeout=1)
        connection.close()
    except (OSError, psycopg2.Error):
        return False
    return True


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/")
def root() -> JSONResponse:
    return JSONResponse(
        {
            "message": "RecoverOS API",
            "version": app.version,
            "endpoints": {
                "health": "/api/health",
                "events_stats": "/api/events/stats",
            },
        }
    )


@app.get("/api/health")
def health() -> JSONResponse:
    events = _load_records("revenue_events.json")
    customers = _load_records("customers.json")
    merchants = _load_records("merchants.json")
    database = "connected" if _database_is_connected() else "disconnected"
    return JSONResponse(
        {
            "status": "ok" if database == "connected" else "degraded",
            "version": app.version,
            "database": database,
            "counts": {
                "events": len(events),
                "customers": len(customers),
                "merchants": len(merchants),
            },
        }
    )


@app.get("/api/events/stats")
def event_stats() -> dict:
    events = _load_records("revenue_events.json")
    pattern_counts = Counter()
    for event in events:
        for pattern in event.get("pattern_flags", {}):
            pattern_counts[pattern] += 1
    return {
        "summary": {
            "total_events": len(events),
            "total_revenue_at_risk_paise": sum(
                int(event.get("amount_paise", 0)) for event in events
            ),
        },
        "by_event_type": dict(Counter(event.get("event_type") for event in events)),
        "by_payment_method": dict(
            Counter(event.get("payment_method") for event in events)
        ),
        "patterns": dict(pattern_counts),
    }
