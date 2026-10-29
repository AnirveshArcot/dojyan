"""FastAPI application composition."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.analysis import router as analysis_router
from .routes.health import router as health_router
from .routes.vintages import router as vintages_router

app = FastAPI(
    title="WindDesk API",
    version="3.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url="/api/redoc",
)
origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET"], allow_headers=["*"])
app.include_router(health_router)
app.include_router(analysis_router)
app.include_router(vintages_router)
