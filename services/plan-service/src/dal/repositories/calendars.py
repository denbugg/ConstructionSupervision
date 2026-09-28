"""Запросы к таблице work_calendar."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dal.models import WorkCalendar


class CalendarRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, calendar_id: UUID) -> WorkCalendar | None:
        return await self._session.get(WorkCalendar, calendar_id)

    async def by_code(self, code: str) -> WorkCalendar | None:
        return await self._session.scalar(select(WorkCalendar).where(WorkCalendar.code == code))

    async def list(self, *, limit: int, offset: int) -> tuple[list[WorkCalendar], int]:
        total = await self._session.scalar(select(func.count()).select_from(WorkCalendar))
        rows = await self._session.scalars(
            select(WorkCalendar).order_by(WorkCalendar.code).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)

    async def add(self, calendar: WorkCalendar) -> WorkCalendar:
        self._session.add(calendar)
        await self._session.flush()
        await self._session.refresh(calendar)
        return calendar

    async def save(self, calendar: WorkCalendar) -> WorkCalendar:
        await self._session.flush()
        # updated_at ставит база (onupdate): перечитываем, чтобы ответ не отставал от строки.
        await self._session.refresh(calendar)
        return calendar
