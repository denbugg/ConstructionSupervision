"""Выводы по объекту: статус, прогресс этапов, загрузка техники (срезы последнего прогона)."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from src.api.deps import SessionDep
from src.api.schemas.objects import (
    EquipmentDay,
    EquipmentRead,
    ObjectStatusRead,
    ProgressRead,
    StageProgress,
)
from src.services.results import ResultsService

router = APIRouter(prefix="/objects", tags=["Выводы по объекту"])


@router.get(
    "/{object_id}/status",
    response_model=ObjectStatusRead,
    summary="Сводный статус объекта для дашборда",
)
async def get_status(object_id: UUID, session: SessionDep):
    row, deviations = await ResultsService(session).status_counters(object_id)
    return ObjectStatusRead.of(row, deviations)


@router.get(
    "/{object_id}/progress",
    response_model=ProgressRead,
    summary="Прогресс, SPI и прогноз по этапам — данные для Ганта",
)
async def get_progress(object_id: UUID, session: SessionDep):
    status, stages, activity = await ResultsService(session).progress(object_id)
    return ProgressRead(
        object_id=object_id,
        as_of=status.as_of,
        stages=[StageProgress.of(s, activity.get(s.stage_id, [])) for s in stages],
    )


@router.get(
    "/{object_id}/equipment",
    response_model=EquipmentRead,
    summary="Загрузка техники по дням и классам (F10)",
    description="Фильтр по местным датам — полуинтервал `[from, to)`.",
)
async def get_equipment(
    object_id: UUID,
    session: SessionDep,
    day_from: Annotated[date | None, Query(alias="from")] = None,
    day_to: Annotated[date | None, Query(alias="to")] = None,
):
    status, rows = await ResultsService(session).equipment(object_id, day_from, day_to)
    return EquipmentRead(
        object_id=object_id, as_of=status.as_of, items=[EquipmentDay.of(r) for r in rows]
    )
