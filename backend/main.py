"""
Contract Risk Analyser - FastAPI Backend
Entry point for the FastAPI application.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.routes import upload, analyse, history, export
from pipeline.rag_engine import init_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    print("🚀 Starting Contract Risk Analyser backend...")
    # Initialize RAG engine (loads embedding model and ChromaDB)
    init_engine()
    yield
    print("👋 Shutting down...")


app = FastAPI(
    title="Contract Risk Analyser",
    description="AI-powered legal contract risk analysis",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with frontend URL in production
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
