"""Конвейер распознавания: снимок → vision → детекции и стадия → факт окна → сигнал (F2–F6).

Источник истины — статус снимка в базе, а не очередь (README, раздел 4):
- `PENDING → PROCESSING` одним UPDATE: снимок распознаёт ровно один воркер;
- vision недоступен — снимок возвращается в `PENDING`, и проход по базе поставит его снова;
- vision отказал по самому снимку (битый файл) — `FAILED` с причиной, повтор не поможет.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from lct_common import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.clients.analysis_client import AnalysisClient
from src.clients.queue import RecognitionQueue
from src.clients.storage import ImageStorage, StorageUnavailable
from src.clients.vision_client import VisionClient, VisionRejected, VisionUnavailable
from src.config import Settings
from src.core.aggregation import frame_usability
from src.core.movement import PreviousBox, movement
from src.core.zones import place
from src.dal.models import Detection, Image, StageObservation
from src.dal.repositories.recognition import FAILED, PENDING, RecognitionRepository
from src.dal.repositories.zones import ZoneRepository
from src.reference import enums
from src.services.window_facts import WindowFacts, shape

log = get_logger(__name__)

# Сколько снимков один проход по базе ставит в очередь: остальные возьмёт следующий проход.
SWEEP_BATCH = 500


class Recognition:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        storage: ImageStorage,
        vision: VisionClient,
        analysis: AnalysisClient,
        queue: RecognitionQueue,
        config: Settings,
    ) -> None:
        self._factory = factory
        self._storage = storage
        self._vision = vision
        self._analysis = analysis
        self._queue = queue
        self._config = config

    async def analyze_image(self, image_id: UUID) -> str:
        """Распознать снимок и пересчитать его окно. Ответ — исход для лога задачи."""
        async with self._factory() as session:
            image = await RecognitionRepository(session).claim(image_id, self._stale_before())
            await session.commit()
        if image is None:
            return "skipped"

        try:
            result = await self._vision.analyze(await self._storage.internal_url(image.storage_key))
        except (VisionUnavailable, StorageUnavailable) as exc:
            await self._set_status(image_id, PENDING, exc.message)
            return "deferred"
        except VisionRejected as exc:
            await self._set_status(image_id, FAILED, exc.message)
            return "failed"

        try:
            async with self._factory() as session:
                await self._store(session, image, result)
                await session.commit()
        except Exception as exc:
            # Ошибка в нашем коде не должна оставлять снимок в PROCESSING до таймаута
            # и потом крутиться по кругу: FAILED с причиной видно в GET /images/{id}.
            log.exception("recognition.store_failed", image_id=str(image_id))
            await self._set_status(
                image_id, FAILED, f"Ошибка записи результата: {type(exc).__name__}"
            )
            return "failed"

        await self._analysis.request_run(image.object_id)
        return "analyzed"

    async def reapply_zones(self, object_id: UUID) -> int:
        """После правки зон: новая привязка детекций и факты окон, затем сигнал. Ответ — окна.

        Одна транзакция на объект: analysis не должен прочитать факты, где часть окон
        посчитана по старой разметке, а часть — по новой.
        """
        async with self._factory() as session:
            windows = await WindowFacts(session).reapply(object_id)
            await session.commit()
        await self._analysis.request_run(object_id)
        return windows

    async def sweep(self) -> int:
        """Поставить в очередь всё, что ждёт распознавания или зависло."""
        async with self._factory() as session:
            ids = await RecognitionRepository(session).runnable_ids(
                self._stale_before(), SWEEP_BATCH
            )
        await self._queue.enqueue(ids)
        return len(ids)

    async def _store(self, session: AsyncSession, image: Image, result: dict[str, Any]) -> None:
        repo = RecognitionRepository(session)
        # Замок на окно — первым: пересчёт факта должен увидеть детекции соседних снимков.
        window = await repo.lock_window(image.session_id) if image.session_id else None
        usable, reason = frame_usability(
            result["quality"], self._config.min_brightness, self._config.max_blur
        )
        detections = await self._detections(session, image, result, window)
        stage = result.get("stage")
        await repo.replace_results(
            image.id,
            detections,
            StageObservation(
                image_id=image.id,
                session_id=image.session_id,
                stage_label=stage["label"],
                conf=stage["conf"],
                scores=stage["scores"],
            )
            if stage
            else None,
        )
        await repo.finish(image.id, quality=result["quality"], usable=usable, reason=reason)
        if window is not None:
            await WindowFacts(session).recompute(window.id, image.object_id)

    async def _detections(
        self, session: AsyncSession, image: Image, result: dict[str, Any], window
    ) -> list[Detection]:
        zones = [shape(z) for z in await ZoneRepository(session).active_for_camera(image.camera_id)]
        previous = None
        if window is not None:
            boxes = await RecognitionRepository(session).previous_window_boxes(
                image.camera_id, window.window_start
            )
            previous = None if boxes is None else [PreviousBox(c, b) for c, b in boxes]
        # Рамки нормированы к кадру, который видел vision (уже повёрнутому по EXIF).
        width, height = result["image"]["width"], result["image"]["height"]
        roles = enums().zone_roles
        detections = []
        for det in result["detections"]:
            placement = place(det["bbox"], zones, roles)
            moved = movement(
                det["equipment_class"],
                det["bbox"],
                previous,
                width,
                height,
                self._config.move_threshold,
            )
            detections.append(
                Detection(
                    image_id=image.id,
                    session_id=image.session_id,
                    camera_id=image.camera_id,
                    equipment_class=det["equipment_class"],
                    bbox=det["bbox"],
                    conf=det["conf"],
                    anchor=list(placement.anchor),
                    zone_id=placement.zone.id if placement.zone else None,
                    moved=moved.moved,
                    displacement=moved.displacement,
                    model_version=result["model"]["detector"],
                )
            )
        return detections

    async def _set_status(self, image_id: UUID, status: str, error: str) -> None:
        log.warning("recognition.not_analyzed", image_id=str(image_id), status=status, error=error)
        async with self._factory() as session:
            await RecognitionRepository(session).set_status(image_id, status, error)
            await session.commit()

    def _stale_before(self) -> datetime:
        return datetime.now(UTC) - timedelta(minutes=self._config.stale_processing_minutes)
