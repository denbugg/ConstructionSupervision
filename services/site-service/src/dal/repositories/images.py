"""Запросы к таблицам image и session."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.dal.models import Detection, Image, ObservationSession, StageObservation


class ImageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, image_id: UUID) -> Image | None:
        return await self._session.get(Image, image_id)

    async def list(
        self,
        *,
        object_id: UUID | None,
        camera_id: UUID | None,
        start: datetime | None,
        end: datetime | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Image], int]:
        """Снимки по времени съёмки; без времени — в конце, по времени получения."""
        query = select(Image)
        if object_id is not None:
            query = query.where(Image.object_id == object_id)
        if camera_id is not None:
            query = query.where(Image.camera_id == camera_id)
        if start is not None:
            query = query.where(Image.captured_at >= start)
        if end is not None:
            query = query.where(Image.captured_at < end)
        if status is not None:
            query = query.where(Image.status == status)
        total = await self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self._session.scalars(
            query.order_by(Image.captured_at.asc().nulls_last(), Image.received_at, Image.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def detections(self, image_id: UUID) -> Sequence[Detection]:
        rows = await self._session.scalars(
            select(Detection)
            .where(Detection.image_id == image_id)
            .order_by(Detection.conf.desc(), Detection.id)
        )
        return rows.all()

    async def stage(self, image_id: UUID) -> StageObservation | None:
        return await self._session.scalar(
            select(StageObservation)
            .where(StageObservation.image_id == image_id)
            .order_by(StageObservation.created_at.desc())
            .limit(1)
        )

    async def save(self, image: Image) -> Image:
        await self._session.flush()
        await self._session.refresh(image)
        return image

    async def by_checksum(self, object_id: UUID, checksum: str) -> Image | None:
        return await self._session.scalar(
            select(Image).where(Image.object_id == object_id, Image.checksum == checksum)
        )

    async def add(self, image: Image) -> Image:
        self._session.add(image)
        await self._session.flush()
        return image

    async def session_for_window(self, object_id: UUID, start: datetime, end: datetime) -> UUID:
        """Окно объекта; нет — заводится. Два снимка одного окна не создают два окна."""
        await self._session.execute(
            insert(ObservationSession)
            .values(object_id=object_id, window_start=start, window_end=end)
            .on_conflict_do_nothing(constraint="uq_session_object_window")
        )
        return await self._session.scalar(
            select(ObservationSession.id).where(
                ObservationSession.object_id == object_id,
                ObservationSession.window_start == start,
            )
        )

    async def reset_for_reanalysis(self, object_id: UUID, camera_id: UUID | None) -> Sequence[UUID]:
        """Распознанные и отказные снимки — снова в PENDING одним UPDATE; ответ — их ID.

        Снимки в работе не трогаются: воркер допишет их сам. Прежние детекции остаются до
        нового результата — тот заменит их целиком.
        """
        query = update(Image).where(
            Image.object_id == object_id, Image.status.in_(("ANALYZED", "FAILED"))
        )
        if camera_id is not None:
            query = query.where(Image.camera_id == camera_id)
        rows = await self._session.scalars(
            query.values(status="PENDING", error=None).returning(Image.id)
        )
        return rows.all()

    async def recount_session(self, session_id: UUID) -> None:
        """Сколько снимков и камер в окне — пересчётом, а не +1: поздний снимок не собьёт счёт."""
        counts = (
            select(
                func.count(Image.id).label("images"),
                func.count(func.distinct(Image.camera_id)).label("cameras"),
            )
            .where(Image.session_id == session_id)
            .subquery()
        )
        await self._session.execute(
            update(ObservationSession)
            .where(ObservationSession.id == session_id)
            .values(
                image_count=select(counts.c.images).scalar_subquery(),
                camera_count=select(counts.c.cameras).scalar_subquery(),
            )
        )
