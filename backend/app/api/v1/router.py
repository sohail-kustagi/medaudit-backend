from fastapi import APIRouter
from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.presign import router as presign_router
from backend.app.api.v1.documents import router as documents_router
from backend.app.api.v1.disputes import router as disputes_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(presign_router)
api_router.include_router(documents_router)
api_router.include_router(disputes_router)
