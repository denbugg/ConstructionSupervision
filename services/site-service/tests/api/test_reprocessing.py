"""Пересчёты по API: правка разметки ставит пересчёт фактов, повторное распознавание снимков.

Сам пересчёт фактов проверяется в test_recognition.py (задача воркера); здесь — что API
ставит его ровно тогда, когда разметка действительно поменялась.
"""

from uuid import UUID, uuid4

from sqlalchemy import select
from src.dal.models import Camera, Image, Zone

SITE = "/api/v1/site"
OBJECT_ID = UUID("44444444-4444-4444-8444-444444444444")
LEFT = [[0, 0], [0.5, 0], [0.5, 1], [0, 1]]
SMALLER = [[0, 0], [0.4, 0], [0.4, 1], [0, 1]]


async def _camera_with_zone(session) -> tuple[Camera, Zone]:
    camera = Camera(object_id=OBJECT_ID, code="cam-north", name="cam-north")
    session.add(camera)
    await session.flush()
    zone = Zone(
        object_id=OBJECT_ID, camera_id=camera.id, zone_type="PIT", name="Котлован", polygon=LEFT
    )
    session.add(zone)
    await session.flush()
    return camera, zone


async def test_правка_зоны_ставит_пересчёт_а_пустая_правка_нет(client, session, queue):
    _, zone = await _camera_with_zone(session)

    same = await client.patch(f"{SITE}/zones/{zone.id}", json={"polygon": LEFT})
    assert same.status_code == 200, same.text
    assert queue.reapplied == []

    changed = await client.patch(f"{SITE}/zones/{zone.id}", json={"polygon": SMALLER})
    assert changed.status_code == 200, changed.text
    assert queue.reapplied == [OBJECT_ID]


async def test_новая_зона_и_выключение_камеры_ставят_пересчёт(client, session, queue):
    camera, _ = await _camera_with_zone(session)

    created = await client.post(
        f"{SITE}/zones",
        json={"camera_id": str(camera.id), "zone_type": "STORAGE", "polygon": SMALLER},
    )
    assert created.status_code == 201, created.text
    assert (await client.delete(f"{SITE}/cameras/{camera.id}")).status_code == 204
    assert (await client.delete(f"{SITE}/cameras/{camera.id}")).status_code == 204

    # Повторное выключение уже выключенной камеры ничего не меняет и пересчёт не ставит.
    assert queue.reapplied == [OBJECT_ID, OBJECT_ID]


async def test_повторный_импорт_той_же_разметки_пересчёт_не_ставит(client, queue):
    markup = {
        "object_id": str(OBJECT_ID),
        "cameras": [{"code": "cam-gate", "zones": [{"zone_type": "PIT", "polygon": LEFT}]}],
    }

    assert (await client.post(f"{SITE}/zones/import", json=markup)).status_code == 200
    assert (await client.post(f"{SITE}/zones/import", json=markup)).status_code == 200

    assert queue.reapplied == [OBJECT_ID]


async def test_ручной_пересчёт_и_недоступная_очередь(client, queue):
    response = await client.post(f"{SITE}/zones/reapply", json={"object_id": str(OBJECT_ID)})

    assert response.status_code == 202, response.text
    assert response.json() == {"object_id": str(OBJECT_ID), "queued": True}
    assert queue.reapplied == [OBJECT_ID]

    queue.broken = True
    failed = await client.post(f"{SITE}/zones/reapply", json={"object_id": str(OBJECT_ID)})

    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "QUEUE_UNAVAILABLE"


async def test_повторное_распознавание(client, session, queue):
    camera, _ = await _camera_with_zone(session)
    images = {}
    for status in ("ANALYZED", "FAILED", "PROCESSING", "NEEDS_TIME"):
        image = Image(
            object_id=OBJECT_ID,
            camera_id=camera.id,
            storage_key=f"{OBJECT_ID}/{uuid4()}.jpg",
            checksum=uuid4().hex,
            status=status,
            error="Изображение не читается" if status == "FAILED" else None,
        )
        session.add(image)
        images[status] = image
    await session.flush()

    response = await client.post(f"{SITE}/images/reanalyze", json={"object_id": str(OBJECT_ID)})

    assert response.status_code == 202, response.text
    assert response.json() == {"object_id": str(OBJECT_ID), "images": 2}
    assert set(queue.enqueued) == {images["ANALYZED"].id, images["FAILED"].id}
    rows = {
        i.id: (i.status, i.error)
        for i in await session.scalars(
            select(Image)
            .where(Image.object_id == OBJECT_ID)
            .execution_options(populate_existing=True)
        )
    }
    assert rows[images["ANALYZED"].id] == ("PENDING", None)
    assert rows[images["FAILED"].id] == ("PENDING", None)
    assert rows[images["PROCESSING"].id][0] == "PROCESSING"
    assert rows[images["NEEDS_TIME"].id][0] == "NEEDS_TIME"
