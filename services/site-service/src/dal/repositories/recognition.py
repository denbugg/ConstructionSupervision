"""Запросы конвейера распознавания: захват снимка, детекции, стадия, кадры окна."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.dal.models import Detection, Image, ObservationSession, StageObservation

PENDING, PROCESSING, ANALYZED, FAILED = "PENDING", "PROCESSING", "ANALYZED", "FAILED"


class RecognitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _runnable(self, stale_before: datetime):
        """Ждёт распознавания или завис: воркер упал, не сняв PROCESSING."""
        return or_(
            Image.status == PENDING,
            (Image.status == PROCESSING) & (Image.updated_at < stale_before),
        )

    async def claim(self, image_id: UUID, stale_before: datetime) -> Image | None:
        """Забрать снимок в работу. None — его уже взял другой воркер или он готов.

        Проверка и смена статуса — одним UPDATE: два воркера не распознают один снимок.
        """
        return await self._session.scalar(
            update(Image)
            .where(Image.id == image_id, self._runnable(stale_before))
            .values(status=PROCESSING, error=None)
            .returning(Image)
        )

    async def runnable_ids(self, stale_before: datetime, limit: int) -> list[UUID]:
        rows = await self._session.scalars(
            select(Image.id)
            .where(self._runnable(stale_before))
            .order_by(Image.captured_at, Image.id)
            .limit(limit)
        )
        return list(rows)

    async def set_status(self, image_id: UUID, status: str, error: str | None) -> None:
        await self._session.execute(
            update(Image).where(Image.id == image_id).values(status=status, error=error)
        )

    async def finish(
        self, image_id: UUID, *, quality: dict, usable: bool, reason: str | None
    ) -> None:
        """Снимок распознан: качество кадра, пригодность и статус ANALYZED."""
        await self._session.execute(
            update(Image)
            .where(Image.id == image_id)
            .values(
                quality=quality, usable=usable, usable_reason=reason, status=ANALYZED, error=None
            )
        )

    async def lock_window(self, session_id: UUID) -> ObservationSession | None:
        """Окно под замком до конца транзакции: два снимка окна пересчитывают его по очереди.

        Без замка второй воркер не увидел бы незакоммиченные детекции первого, и факт окна
        остался бы без одного из снимков.
        """
        return await self._session.scalar(
            select(ObservationSession).where(ObservationSession.id == session_id).with_for_update()
        )

    async def replace_results(
        self,
        image_id: UUID,
        detections: Sequence[Detection],
        stage: StageObservation | None,
    ) -> None:
        """Результат распознавания снимка заменяет прежний: повтор не удваивает технику."""
        await self._session.execute(delete(Detection).where(Detection.image_id == image_id))
        await self._session.execute(
            delete(StageObservation).where(StageObservation.image_id == image_id)
        )
        self._session.add_all(detections)
        if stage is not None:
            self._session.add(stage)
        await self._session.flush()

    async def previous_window_boxes(
        self, camera_id: UUID, before: datetime
    ) -> list[tuple[str, list[float]]] | None:
        """Рамки прошлого окна камеры: последнего раньше `before`, где у неё есть пригодный кадр.

        None — такого окна нет, сравнивать не с чем.
        """
        previous = await self._session.scalar(
            select(ObservationSession.id)
            .join(Image, Image.session_id == ObservationSession.id)
            .where(
                Image.camera_id == camera_id,
                Image.status == ANALYZED,
                Image.usable.is_(True),
                ObservationSession.window_start < before,
            )
            .order_by(ObservationSession.window_start.desc())
            .limit(1)
        )
        if previous is None:
            return None
        rows = await self._session.execute(
            select(Detection.equipment_class, Detection.bbox)
            .join(Image, Image.id == Detection.image_id)
            .where(
                Image.session_id == previous,
                Image.camera_id == camera_id,
                Image.status == ANALYZED,
                Image.usable.is_(True),
            )
        )
        return [(cls, bbox) for cls, bbox in rows]

    async def window_frames(
        self, session_id: UUID
    ) -> list[tuple[Image, list[Detection], StageObservation | None]]:
        """Распознанные снимки окна с детекциями и стадией."""
        images = list(
            await self._session.scalars(
                select(Image).where(Image.session_id == session_id, Image.status == ANALYZED)
            )
        )
        ids = [i.id for i in images]
        detections: dict[UUID, list[Detection]] = {i: [] for i in ids}
        for det in await self._session.scalars(
            select(Detection).where(Detection.image_id.in_(ids))
        ):
            detections[det.image_id].append(det)
        stages = {
            s.image_id: s
            for s in await self._session.scalars(
                select(StageObservation).where(StageObservation.image_id.in_(ids))
            )
        }
        return [(i, detections[i.id], stages.get(i.id)) for i in images]
