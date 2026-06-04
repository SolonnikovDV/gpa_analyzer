"""FastAPI application factory."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import api_router


def create_api_app() -> FastAPI:
    app = FastAPI(
        title="GPA Analyzer API",
        version="2.0.0",
        description="Modular API (agent flow factory, governance, jobs)",
    )

    # CORS must be the outermost middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security stack (added last = executed first in Starlette middleware chain)
    from api.middleware import (
        BasicAuthMiddleware,
        RateLimitMiddleware,
        RequestIDMiddleware,
        SecurityHeadersMiddleware,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(BasicAuthMiddleware)
    app.add_middleware(RequestIDMiddleware)

    app.include_router(api_router, prefix="")
    return app
