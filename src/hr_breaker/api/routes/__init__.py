"""API routes package."""

from .coach import router as coach_router
from .cvs import router as cvs_router
from .editor import router as editor_router
from .feedback import router as feedback_router
from .optimize import router as optimize_router
from .subscription import router as subscription_router
from .telegram import router as telegram_router
from .transcribe import router as transcribe_router
from .users import router as users_router
from .webhooks import router as webhooks_router

__all__ = [
    "coach_router",
    "cvs_router",
    "editor_router",
    "feedback_router",
    "optimize_router",
    "subscription_router",
    "telegram_router",
    "transcribe_router",
    "users_router",
    "webhooks_router",
]
