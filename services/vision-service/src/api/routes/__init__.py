"""Сборка роутеров сервиса под общим префиксом.

Префикс /api/v1/vision одинаков снаружи и внутри контейнера: gateway
проксирует без переписывания пути (ADR-0009).
"""

from fastapi import APIRouter, Depends

from src.api.deps import require_api_key
from src.api.routes import analyze

api_router = APIRouter(prefix="/api/v1/vision", dependencies=[Depends(require_api_key)])
api_router.include_router(analyze.router)
