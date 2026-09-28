"""Факты за период (межсервисный контракт 2) и окна наблюдения (F4)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from lct_common import Page, PageParams

from src.api.deps import SessionDep
from src.api.schemas.facts import PeriodFacts, SessionDetail, SessionRead
from src.services.facts import FactsService

router = APIRouter(tags=["Факты и окна"])

PERIOD_NOTE = "Полуинтервал `[from, to)` по началу окна, ISO-8601 UTC."


@router.get(
    "/objects/{object_id}/facts",
    response_model=PeriodFacts,
    summary="Факты за период",
    description="Межсервисный контракт (interservice.md, раздел 2): окна с распознанными "
    "снимками, участки × классы техники (максимум по камерам), видимость участков, стадия по "
    f"фото. {PERIOD_NOTE} Нет снимков — `sessions: []`; `from >= to` — `INVALID_PERIOD`.",
)
async def get_facts(
    object_id: UUID,
    session: SessionDep,
    start: Annotated[datetime, Query(alias="from")],
    end: Annotated[datetime, Query(alias="to")],
):
    return await FactsService(session).period(object_id, start, end)


@router.get(
    "/sessions",
    response_model=Page[SessionRead],
    summary="Окна наблюдения",
    description=f"Сколько снимков и камер в окне, стадия по фото. {PERIOD_NOTE}",
)
async def list_sessions(
    session: SessionDep,
    params: Annotated[PageParams, Depends()],
    object_id: UUID | None = None,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
):
    items, total = await FactsService(session).list(
        object_id=object_id, start=start, end=end, limit=params.limit, offset=params.offset
    )
    return Page[SessionRead].of([SessionRead.model_validate(s) for s in items], total, params)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetail,
    summary="Окно наблюдения",
    description="Камеры окна и пригодность их кадров, факт окна в форме контракта, все снимки "
    "окна в любом статусе.",
)
async def get_session(session_id: UUID, session: SessionDep):
    return await FactsService(session).detail(session_id)
