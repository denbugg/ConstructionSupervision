"""Конвейер распознавания на настоящей базе: vision, analysis и очередь — заглушки.

Проверяется то, что делает воркер: захват снимка, запись детекций и стадии, пересчёт факта
окна, смещение относительно прошлого окна, возврат в очередь и отказ.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.clients.vision_client import VisionRejected, VisionUnavailable
from src.config import settings
from src.dal.models import (
    AreaVisibility,
    Camera,
    Detection,
    Image,
    ObservationSession,
    SessionFact,
    Zone,
)
from src.services.recognition import Recognition

from tests.conftest import FakeQueue, FakeStorage

OBJECT_ID = UUID("22222222-2222-4222-8222-222222222222")
PIT = [[0, 0], [0.5, 0], [0.5, 1], [0, 1]]
T0 = datetime(2026, 10, 20, 6, 0, tzinfo=UTC)
EXCAVATOR = {"equipment_class": "excavator", "bbox": [0.1, 0.2, 0.3, 0.8], "conf": 0.91}


def vision_result(*detections, brightness=0.5, stage="PIT") -> dict:
    return {
        "model": {"detector": "yolov8s-worldv2", "device": "cpu", "classes_version": "x"},
        "image": {"width": 1920, "height": 1080},
        "detections": list(detections),
        "stage": {"label": stage, "conf": 0.8, "scores": {stage: 0.8, "FRAME": 0.2}},
        "quality": {"brightness": brightness, "blur": 0.1},
        "inference_ms": 50,
    }


class FakeVision:
    def __init__(self) -> None:
        self.result: dict | Exception = vision_result(EXCAVATOR)
        self.urls: list[str] = []

    async def analyze(self, url: str) -> dict:
        self.urls.append(url)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeAnalysis:
    def __init__(self) -> None:
        self.signals: list[UUID] = []

    async def request_run(self, object_id: UUID) -> None:
        self.signals.append(object_id)


@pytest.fixture
async def factory(engine) -> AsyncIterator:
    """Сессии воркера на одном соединении в общей транзакции: commit — точка сохранения."""
    connection = await engine.connect()
    transaction = await connection.begin()

    def make() -> AsyncSession:
        return AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )

    yield make
    await transaction.rollback()
    await connection.close()


@pytest.fixture
def vision() -> FakeVision:
    return FakeVision()


@pytest.fixture
def analysis() -> FakeAnalysis:
    return FakeAnalysis()


@pytest.fixture
def recognition(factory, vision, analysis) -> tuple[Recognition, FakeQueue]:
    queue = FakeQueue()
    return Recognition(factory, FakeStorage(), vision, analysis, queue, settings), queue


@pytest.fixture
async def camera(factory) -> Camera:
    async with factory() as db:
        camera = Camera(object_id=OBJECT_ID, code="cam-north", name="cam-north")
        db.add(camera)
        await db.flush()
        db.add(
            Zone(
                object_id=OBJECT_ID,
                camera_id=camera.id,
                zone_type="PIT",
                name="Котлован",
                polygon=PIT,
            )
        )
        await db.commit()
        return camera


async def add_image(factory, camera: Camera, at: datetime, status="PENDING") -> Image:
    async with factory() as db:
        start = at.replace(minute=(at.minute // 30) * 30)
        window = ObservationSession(
            object_id=OBJECT_ID, window_start=start, window_end=start + timedelta(minutes=30)
        )
        db.add(window)
        await db.flush()
        image = Image(
            object_id=OBJECT_ID,
            camera_id=camera.id,
            captured_at=at,
            captured_at_source="EXIF",
            session_id=window.id,
            storage_key=f"{OBJECT_ID}/{camera.id}/{uuid4()}.jpg",
            checksum=uuid4().hex,
            status=status,
        )
        db.add(image)
        await db.commit()
        return image


async def fetch(factory, query):
    async with factory() as db:
        return list(await db.scalars(query))


async def test_снимок_распознан_и_факт_окна_посчитан(
    recognition, factory, camera, vision, analysis
):
    service, _ = recognition
    image = await add_image(factory, camera, T0)

    assert await service.analyze_image(image.id) == "analyzed"

    [row] = await fetch(factory, select(Image).where(Image.id == image.id))
    assert (row.status, row.usable, row.usable_reason, row.error) == ("ANALYZED", True, None, None)
    assert vision.urls == [f"http://s3:8333/images/{image.storage_key}?X-Amz-Signature=test"]
    [det] = await fetch(factory, select(Detection).where(Detection.image_id == image.id))
    [pit] = await fetch(factory, select(Zone).where(Zone.camera_id == camera.id))
    assert (det.zone_id, det.anchor, det.moved, det.model_version) == (
        pit.id,
        [0.2, 0.8],
        None,
        "yolov8s-worldv2",
    )
    [fact] = await fetch(
        factory, select(SessionFact).where(SessionFact.session_id == row.session_id)
    )
    assert (fact.area, fact.equipment_class, fact.count, fact.static) == (
        "PIT:Котлован",
        "excavator",
        1,
        None,
    )
    assert fact.evidence[0]["detection_id"] == str(det.id)
    [vis] = await fetch(
        factory, select(AreaVisibility).where(AreaVisibility.session_id == row.session_id)
    )
    assert (vis.status, vis.cameras_total, vis.cameras_usable) == ("OK", 1, 1)
    [window] = await fetch(
        factory, select(ObservationSession).where(ObservationSession.id == row.session_id)
    )
    assert (window.stage_label, window.stage_conf) == ("PIT", 0.8)
    assert analysis.signals == [OBJECT_ID]


async def test_смещение_относительно_прошлого_окна_камеры(recognition, factory, camera):
    service, _ = recognition
    first = await add_image(factory, camera, T0)
    second = await add_image(factory, camera, T0 + timedelta(minutes=30))

    await service.analyze_image(first.id)
    await service.analyze_image(second.id)

    [det] = await fetch(factory, select(Detection).where(Detection.image_id == second.id))
    assert (det.moved, det.displacement) == (False, 0.0)
    [fact] = await fetch(
        factory, select(SessionFact).where(SessionFact.session_id == second.session_id)
    )
    assert (fact.count, fact.static) == (1, 1)


async def test_тёмный_кадр_не_даёт_техники_и_делает_участок_слепым(
    recognition, factory, camera, vision
):
    service, _ = recognition
    vision.result = vision_result(EXCAVATOR, brightness=0.05)
    image = await add_image(factory, camera, T0)

    await service.analyze_image(image.id)

    [row] = await fetch(factory, select(Image).where(Image.id == image.id))
    assert (row.status, row.usable, row.usable_reason) == ("ANALYZED", False, "DARK")
    facts = await fetch(
        factory, select(SessionFact).where(SessionFact.session_id == row.session_id)
    )
    assert facts == []
    [vis] = await fetch(
        factory, select(AreaVisibility).where(AreaVisibility.session_id == row.session_id)
    )
    assert (vis.status, vis.reason) == ("BLIND", "DARK")


async def test_повторно_распознанный_снимок_не_удваивает_технику(recognition, factory, camera):
    service, _ = recognition
    image = await add_image(factory, camera, T0)
    await service.analyze_image(image.id)
    async with factory() as db:
        await db.execute(update(Image).where(Image.id == image.id).values(status="PENDING"))
        await db.commit()

    await service.analyze_image(image.id)

    detections = await fetch(factory, select(Detection).where(Detection.image_id == image.id))
    [fact] = await fetch(
        factory, select(SessionFact).where(SessionFact.session_id == image.session_id)
    )
    assert (len(detections), fact.count) == (1, 1)


async def test_распознанный_снимок_второй_раз_не_берётся(recognition, factory, camera, analysis):
    service, _ = recognition
    image = await add_image(factory, camera, T0)
    await service.analyze_image(image.id)

    assert await service.analyze_image(image.id) == "skipped"
    assert len(analysis.signals) == 1


async def test_vision_недоступен_снимок_ждёт_в_pending(recognition, factory, camera, vision):
    service, _ = recognition
    vision.result = VisionUnavailable("Сервис распознавания недоступен")
    image = await add_image(factory, camera, T0)

    assert await service.analyze_image(image.id) == "deferred"

    [row] = await fetch(factory, select(Image).where(Image.id == image.id))
    assert (row.status, row.error) == ("PENDING", "Сервис распознавания недоступен")


async def test_vision_отказал_снимок_failed(recognition, factory, camera, vision, analysis):
    service, _ = recognition
    vision.result = VisionRejected("Изображение не читается", upstream_code="IMAGE_DECODE_FAILED")
    image = await add_image(factory, camera, T0)

    assert await service.analyze_image(image.id) == "failed"

    [row] = await fetch(factory, select(Image).where(Image.id == image.id))
    assert (row.status, row.error) == ("FAILED", "Изображение не читается")
    assert analysis.signals == []


async def test_правка_зон_пересчитывает_факты_без_распознавания(
    recognition, factory, camera, vision, analysis
):
    service, _ = recognition
    # Экскаватор справа — вне котлована: пока разметки справа нет, он OUTSIDE.
    vision.result = vision_result({**EXCAVATOR, "bbox": [0.6, 0.2, 0.8, 0.8]})
    image = await add_image(factory, camera, T0)
    await service.analyze_image(image.id)
    async with factory() as db:
        db.add(
            Zone(
                object_id=OBJECT_ID,
                camera_id=camera.id,
                zone_type="ENTRY_GATE",
                name="Въезд",
                polygon=[[0.5, 0], [1, 0], [1, 1], [0.5, 1]],
            )
        )
        await db.commit()

    assert await service.reapply_zones(OBJECT_ID) == 1

    [det] = await fetch(factory, select(Detection).where(Detection.image_id == image.id))
    [gate] = await fetch(factory, select(Zone).where(Zone.zone_type == "ENTRY_GATE"))
    assert det.zone_id == gate.id
    [fact] = await fetch(
        factory, select(SessionFact).where(SessionFact.session_id == image.session_id)
    )
    assert (fact.area, fact.equipment_class, fact.count) == ("ENTRY_GATE:Въезд", "excavator", 1)
    areas = await fetch(
        factory,
        select(AreaVisibility.area).where(AreaVisibility.session_id == image.session_id),
    )
    assert sorted(areas) == ["ENTRY_GATE:Въезд", "PIT:Котлован"]
    assert len(vision.urls) == 1  # повторного распознавания не было
    assert analysis.signals == [OBJECT_ID, OBJECT_ID]


async def test_проход_по_базе_ставит_ждущие_и_зависшие(recognition, factory, camera):
    service, queue = recognition
    waiting = await add_image(factory, camera, T0)
    stuck = await add_image(factory, camera, T0 + timedelta(hours=1), status="PROCESSING")
    fresh = await add_image(factory, camera, T0 + timedelta(hours=2), status="PROCESSING")
    await add_image(factory, camera, T0 + timedelta(hours=3), status="ANALYZED")
    async with factory() as db:
        await db.execute(
            update(Image)
            .where(Image.id == stuck.id)
            .values(updated_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await db.commit()

    await service.sweep()

    assert set(queue.enqueued) == {waiting.id, stuck.id}
    assert fresh.id not in queue.enqueued
