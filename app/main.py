"""
Swais Saraswathi — Faculty Backend
FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from saraswati_tenant import SchoolMiddleware

from app.core.config import settings
from app.api.v1.router import api_router

app = FastAPI(
    title="Swais Saraswathi — Faculty API",
    description="Backend for the teacher-facing faculty module",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Which school is this request for? ────────────────────────────────────────
# Reads the Host header once and binds that school for the rest of the request.
# An unregistered host is a 404 and a suspended school a 403, both before any
# router runs.
#
# Registered *before* CORS on purpose. add_middleware prepends, so the last one
# added is the outermost and runs first. CORS has to answer the browser's
# preflight OPTIONS itself — if the school were resolved first, a preflight to
# an unregistered host would come back as a bare 404 with no CORS headers, and
# the browser would report it as a CORS failure rather than an unknown school.
app.add_middleware(SchoolMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "service": "swais-saraswathi-backend"}
