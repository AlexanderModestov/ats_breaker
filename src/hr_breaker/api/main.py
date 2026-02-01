"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hr_breaker.api.routes import (
    cvs_router,
    optimize_router,
    subscription_router,
    users_router,
    webhooks_router,
)
from hr_breaker.api.schemas import HealthResponse
from hr_breaker.config import get_settings

settings = get_settings()

app = FastAPI(
    title="HR-Breaker API",
    description="Resume optimization API for job postings",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(users_router, prefix="/api", tags=["users"])
app.include_router(cvs_router, prefix="/api/cvs", tags=["cvs"])
app.include_router(optimize_router, prefix="/api/optimize", tags=["optimize"])
app.include_router(subscription_router, prefix="/api/subscription", tags=["subscription"])
app.include_router(webhooks_router, prefix="/api/webhooks", tags=["webhooks"])


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()
