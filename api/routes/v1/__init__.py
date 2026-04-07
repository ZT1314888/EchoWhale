from fastapi import APIRouter

from api.routes.v1.auth import router as auth_router
from api.routes.v1.deepgram import router as deepgram_router
from api.routes.v1.history import router as history_router
from api.routes.v1.media import router as media_router
from api.routes.v1.sessions import router as sessions_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(deepgram_router)
router.include_router(history_router)
router.include_router(media_router)
router.include_router(sessions_router)
