"""
Contract Risk Analyser - FastAPI Backend
Entry point for the FastAPI application.
Priority 4: Production fail-closed, tightened CORS, optional docs.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.routes import upload, analyse, history, export
from api.middleware.auth import validate_security_config_at_startup, DEV_MODE
from pipeline.rag_engine import init_engine


def _get_cors_origins() -> list:
    """
    Determine allowed CORS origins.
    Production uses ALLOWED_ORIGINS env var.
    Dev/local allows localhost:3000.
    """
    allowed = os.getenv("ALLOWED_ORIGINS")
    if allowed:
        origins = [o.strip() for o in allowed.split(",") if o.strip()]
        if origins:
            return origins
    if DEV_MODE:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    # Production default: empty list (no cross-origin allowed unless configured)
    return []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    print("🚀 Starting Contract Risk Analyser backend...")
    # Fail closed in production if required security env vars are missing
    validate_security_config_at_startup()
    # Initialize RAG engine (loads embedding model and ChromaDB)
    init_engine()
    yield
    print("👋 Shutting down...")


# Disable docs/OpenAPI in production unless explicitly enabled
_enable_docs = DEV_MODE or os.getenv("ENABLE_OPENAPI", "false").lower() == "true"

app = FastAPI(
    title="Contract Risk Analyser",
    description="AI-powered legal contract risk analysis",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _enable_docs else None,
    redoc_url="/redoc" if _enable_docs else None,
    openapi_url="/openapi.json" if _enable_docs else None,
)

# CORS middleware
_origins = _get_cors_origins()
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
else:
    # No CORS middleware means same-origin only, which is safe for production
    if DEV_MODE:
        # In dev, add permissive CORS if no origins configured
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

# Include routers
app.include_router(upload.router, prefix="/api/v1", tags=["upload"])
app.include_router(analyse.router, prefix="/api/v1", tags=["analysis"])
app.include_router(history.router, prefix="/api/v1", tags=["history"])
app.include_router(export.router, prefix="/api/v1", tags=["export"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "contract-risk-analyser"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
