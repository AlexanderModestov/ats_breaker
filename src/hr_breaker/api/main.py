"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hr_breaker.services.supabase import SupabaseError
from hr_breaker.api.routes import (
    coach_router,
    cvs_router,
    editor_router,
    feedback_router,
    optimize_router,
    subscription_router,
    telegram_router,
    users_router,
    webhooks_router,
)
from hr_breaker.api.schemas import HealthResponse
from hr_breaker.config import get_settings
from hr_breaker.llm import validate_llm_config

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_llm_config()
    yield


app = FastAPI(
    title="HR-Breaker API",
    description="Resume optimization API for job postings",
    version="0.1.0",
    lifespan=lifespan,
)

@app.exception_handler(SupabaseError)
async def supabase_error_handler(request: Request, exc: SupabaseError) -> JSONResponse:
    """Surface any uncaught Supabase failure as a 500 with its message."""
    return JSONResponse(status_code=500, content={"detail": str(exc)})


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
app.include_router(editor_router, prefix="/api/optimize", tags=["editor"])
app.include_router(subscription_router, prefix="/api/subscription", tags=["subscription"])
app.include_router(feedback_router, prefix="/api/feedback", tags=["feedback"])
app.include_router(webhooks_router, prefix="/api/webhooks", tags=["webhooks"])
app.include_router(coach_router, prefix="/api/coach", tags=["coach"])
app.include_router(telegram_router, prefix="/api/auth/telegram", tags=["telegram"])


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()
