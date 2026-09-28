"""Рабочие календари: выходные, праздники, рабочие часы."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from lct_common import Page, PageParams

from src.api.deps import AnalysisDep, SessionDep
from src.api.schemas.calendars import CalendarCreate, CalendarRead, CalendarUpdate
from src.services.calendars import CalendarService

router = APIRouter(prefix="/calendars", tags=["Календари"])


@router.get("", response_model=Page[CalendarRead], summary="Рабочие календари")
async def list_calendars(
    session: SessionDep, signal: AnalysisDep, params: Annotated[PageParams, Depends()]
):
    items, total = await CalendarService(session, signal).list(
        limit=params.limit, offset=params.offset
    )
    return Page[CalendarRead].of([CalendarRead.model_validate(c) for c in items], total, params)


@router.post(
    "",
    response_model=CalendarRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать календарь",
)
async def create_calendar(
    payload: CalendarCreate, session: SessionDep, signal: AnalysisDep, response: Response
):
    calendar = await CalendarService(session, signal).create(payload)
    response.headers["Location"] = f"/api/v1/plan/calendars/{calendar.id}"
    return calendar


@router.get("/{calendar_id}", response_model=CalendarRead, summary="Календарь")
async def get_calendar(calendar_id: UUID, session: SessionDep, signal: AnalysisDep):
    return await CalendarService(session, signal).get(calendar_id)


@router.patch(
    "/{calendar_id}",
    response_model=CalendarRead,
    summary="Изменить календарь",
    description="Выходные, праздники, рабочие часы или часовой пояс: у всех объектов на "
    "календаре растёт `plan_version`, и в analysis уходит сигнал «пересчитай».",
)
async def update_calendar(
    calendar_id: UUID, payload: CalendarUpdate, session: SessionDep, signal: AnalysisDep
):
    return await CalendarService(session, signal).update(calendar_id, payload)
