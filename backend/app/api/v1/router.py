from fastapi import APIRouter

from .admin import router as admin_router
from .audio import router as audio_router
from .auth import router as auth_router
from .feedback import router as feedback_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(feedback_router)
api_router.include_router(admin_router)
api_router.include_router(audio_router)
