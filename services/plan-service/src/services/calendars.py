"""Рабочие календари: выходные, праздники, рабочие часы (ТЗ, п. 8).

Правка календаря меняет план всех объектов на нём: у каждого растёт plan_version и
уходит сигнал «пересчитай».
"""

from datetime import time
from typing import Any
from uuid import UUID

from lct_common import ConflictError, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.calendars import CalendarCreate, CalendarUpdate
from src.clients.analysis_client import AnalysisClient
from src.core.calendar import CalendarError, check_calendar
from src.dal.models import WorkCalendar
from src.dal.repositories.calendars import CalendarRepository
from src.dal.repositories.objects import ObjectRepository
from src.services.critical_path import CalendarNotFound, refresh_critical_path
from src.services.plan_version import PlanVersion


class CalendarAlreadyExists(ConflictError):
    code = "CALENDAR_ALREADY_EXISTS"


class CalendarInvalid(ValidationError):
    code = "CALENDAR_INVALID"


def _check(fields: dict[str, Any]) -> None:
    hours = fields["work_hours"]
    try:
        check_calendar(
            fields["timezone"],
            fields["weekend_days"],
            time.fromisoformat(hours["start"]),
            time.fromisoformat(hours["end"]),
        )
    except CalendarError as exc:
        raise CalendarInvalid(str(exc)) from exc


class CalendarService:
    def __init__(self, session: AsyncSession, signal: AnalysisClient) -> None:
        self._session = session
        self._repo = CalendarRepository(session)
        self._objects = ObjectRepository(session)
        self._plan_version = PlanVersion(session, signal)

    async def get(self, calendar_id: UUID) -> WorkCalendar:
        calendar = await self._repo.get(calendar_id)
        if calendar is None:
            raise CalendarNotFound(calendar_id)
        return calendar

    async def list(self, *, limit: int, offset: int) -> tuple[list[WorkCalendar], int]:
        return await self._repo.list(limit=limit, offset=offset)

    async def create(self, payload: CalendarCreate) -> WorkCalendar:
        fields = payload.model_dump(mode="json")
        _check(fields)
        if await self._repo.by_code(payload.code) is not None:
            raise CalendarAlreadyExists("Календарь с таким кодом уже есть", code=payload.code)
        fields["holidays"] = sorted(set(fields["holidays"]))
        return await self._repo.add(WorkCalendar(**fields))

    async def update(self, calendar_id: UUID, payload: CalendarUpdate) -> WorkCalendar:
        calendar = await self.get(calendar_id)
        # null в частичной правке означает «не менять»: у календаря нет пустых полей.
        changes = {k: v for k, v in payload.model_dump(mode="json").items() if v is not None}
        current = {
            "timezone": calendar.timezone,
            "weekend_days": calendar.weekend_days,
            "work_hours": calendar.work_hours,
        }
        _check(current | changes)
        if "holidays" in changes:
            changes["holidays"] = sorted(set(changes["holidays"]))
        for field, value in changes.items():
            setattr(calendar, field, value)
        calendar = await self._repo.save(calendar)
        # Название на рабочие дни не влияет: план от него не меняется.
        if changes.keys() - {"name"}:
            object_ids = list(await self._objects.ids_with_calendar(calendar_id))
            # Выходные и праздники меняют число рабочих дней, а с ним резервы этапов.
            await refresh_critical_path(self._session, object_ids)
            await self._plan_version.changed(object_ids)
        return calendar
