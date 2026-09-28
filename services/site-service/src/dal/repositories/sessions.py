"""Чтение окон и их материализованного факта: контракт «факты за период», `/sessions`.

Окна выбираются условием на `session`, а строки окон — соединением с ним, а не списком ID:
период прогона тянется от начала СМР и может содержать тысячи окон.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dal.models import (
    AreaVisibility,
    Detection,
    Image,
    ObservationSession,
    SessionFact,
)

ANALYZED = "ANALYZED"
# Снимки окна, которые ещё будут распознаны: факты периода по ним неполные.
NOT_YET_ANALYZED = ("PENDING", "PROCESSING")

Window = ObservationSession


def in_period(object_id: UUID, start: datetime, end: datetime) -> ColumnElement[bool]:
    """Окна объекта с началом в полуинтервале [start, end)."""
    return and_(
        Window.object_id == object_id, Window.window_start >= start, Window.window_start < end
    )


def one_window(session_id: UUID) -> ColumnElement[bool]:
    return Window.id == session_id


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, session_id: UUID) -> ObservationSession | None:
        return await self._session.get(ObservationSession, session_id)

    async def observed(self, where: ColumnElement[bool]) -> list[ObservationSession]:
        """Окна, где распознан хотя бы один снимок: окно без них — «нет наблюдений»."""
        has_analyzed = exists().where(Image.session_id == Window.id, Image.status == ANALYZED)
        rows = await self._session.scalars(
            select(Window).where(where, has_analyzed).order_by(Window.window_start)
        )
        return list(rows)

    async def analyzed_images(self, where: ColumnElement[bool]) -> list[Image]:
        rows = await self._session.scalars(
            select(Image)
            .join(Window, Window.id == Image.session_id)
            .where(where, Image.status == ANALYZED)
        )
        return list(rows)

    async def window_images(self, session_id: UUID) -> list[Image]:
        """Все снимки окна, в любом статусе: состав окна показывает и ещё не распознанные."""
        rows = await self._session.scalars(
            select(Image)
            .where(Image.session_id == session_id)
            .order_by(Image.captured_at, Image.id)
        )
        return list(rows)

    async def visibility(self, where: ColumnElement[bool]) -> list[AreaVisibility]:
        rows = await self._session.scalars(
            select(AreaVisibility)
            .join(Window, Window.id == AreaVisibility.session_id)
            .where(where)
            .order_by(AreaVisibility.area)
        )
        return list(rows)

    async def facts(self, where: ColumnElement[bool]) -> list[SessionFact]:
        rows = await self._session.scalars(
            select(SessionFact)
            .join(Window, Window.id == SessionFact.session_id)
            .where(where)
            .order_by(SessionFact.area, SessionFact.equipment_class)
        )
        return list(rows)

    async def model_versions(self, where: ColumnElement[bool]) -> list[str]:
        """Версии детектора, чьи детекции есть в окнах: вывод воспроизводим после смены весов."""
        rows = await self._session.scalars(
            select(Detection.model_version)
            .distinct()
            .join(Image, Image.id == Detection.image_id)
            .join(Window, Window.id == Image.session_id)
            .where(where, Image.status == ANALYZED)
            .order_by(Detection.model_version)
        )
        return list(rows)

    async def pending_images(self, where: ColumnElement[bool]) -> int:
        total = await self._session.scalar(
            select(func.count(Image.id))
            .join(Window, Window.id == Image.session_id)
            .where(where, Image.status.in_(NOT_YET_ANALYZED))
        )
        return int(total or 0)

    # Последним: имя метода в теле класса затеняет встроенный list в аннотациях ниже него.
    async def list(
        self,
        *,
        object_id: UUID | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ObservationSession], int]:
        query = select(Window)
        if object_id is not None:
            query = query.where(Window.object_id == object_id)
        if start is not None:
            query = query.where(Window.window_start >= start)
        if end is not None:
            query = query.where(Window.window_start < end)
        total = await self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self._session.scalars(
            query.order_by(Window.window_start, Window.object_id).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)
