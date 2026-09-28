"""Сборка роутеров сервиса под общим префиксом.

Префикс /api/v1/plan одинаков снаружи и внутри контейнера: gateway проксирует
без переписывания пути (ADR-0009).
"""

from fastapi import APIRouter, Depends

from src.api.deps import require_api_key
from src.api.routes import calendars, equipment_classes, objects, plan, rules, stages, work_types

api_router = APIRouter(prefix="/api/v1/plan", dependencies=[Depends(require_api_key)])
api_router.include_router(objects.router)
api_router.include_router(plan.router)
api_router.include_router(stages.router)
api_router.include_router(rules.router)
api_router.include_router(calendars.router)
api_router.include_router(equipment_classes.router)
api_router.include_router(work_types.router)
