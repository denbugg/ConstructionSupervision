"""Факты за период (контракт 2) и окна: форма ответа, видимость, пустой период, ошибки.

Окно собирается прямо в базе, а факт пересчитывается тем же `WindowFacts`, что и в воркере:
проверяется чтение материализованного факта, а не распознавание.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from src.dal.models import (
    Camera,
    Detection,
    Image,
    ObservationSession,
    StageObservation,
    Zone,
)
from src.services.window_facts import WindowFacts

SITE = "/api/v1/site"
OBJECT_ID = UUID("33333333-3333-4333-8333-333333333333")
LEFT = [[0, 0], [0.5, 0], [0.5, 1], [0, 1]]
RIGHT = [[0.5, 0], [1, 0], [1, 1], [0.5, 1]]
IN_LEFT, IN_RIGHT = [0.1, 0.2, 0.3, 0.8], [0.6, 0.2, 0.8, 0.8]
T0 = datetime(2026, 10, 22, 6, 0, tzinfo=UTC)
PERIOD = {"from": "2026-10-22T00:00:00Z", "to": "2026-10-23T00:00:00Z"}

# Поля контракта interservice.md, раздел 2 — ровно те, что читает analysis-service.
TOP = {"object_id", "from", "to", "zones_version", "model_versions", "pending_images", "sessions"}
SESSION = {
    "session_id",
    "window_start",
    "window_end",
    "updated_at",
    "cameras",
    "stage_observation",
    "areas",
    "outside_zones",
}
CAMERA = {"code", "images", "usable", "reason", "image_ids"}
AREA = {"area", "zone_type", "name", "visibility", "equipment"}
VISIBILITY = {"status", "cameras_total", "cameras_usable", "reason"}
EQUIPMENT = {"equipment_class", "count", "static", "evidence"}
EVIDENCE = {"image_id", "detection_id", "camera", "conf"}


async def _camera(session, code: str, *zones: tuple[str, str, list]) -> Camera:
    camera = Camera(object_id=OBJECT_ID, code=code, name=code)
    session.add(camera)
    await session.flush()
    for zone_type, name, polygon in zones:
        session.add(
            Zone(
                object_id=OBJECT_ID,
                camera_id=camera.id,
                zone_type=zone_type,
                name=name,
                polygon=polygon,
            )
        )
    await session.flush()
    return camera


async def _window(session, start: datetime) -> ObservationSession:
    window = ObservationSession(
        object_id=OBJECT_ID, window_start=start, window_end=start + timedelta(minutes=30)
    )
    session.add(window)
    await session.flush()
    return window


async def _image(session, camera, window, *boxes, status="ANALYZED", usable=True, reason=None):
    image = Image(
        object_id=OBJECT_ID,
        camera_id=camera.id,
        captured_at=window.window_start + timedelta(minutes=3),
        captured_at_source="EXIF",
        session_id=window.id,
        storage_key=f"{OBJECT_ID}/{uuid4()}.jpg",
        checksum=uuid4().hex,
        status=status,
        usable=usable if status == "ANALYZED" else None,
        usable_reason=reason,
    )
    session.add(image)
    await session.flush()
    for cls, bbox in boxes:
        session.add(
            Detection(
                image_id=image.id,
                session_id=window.id,
                camera_id=camera.id,
                equipment_class=cls,
                bbox=bbox,
                conf=0.9,
                anchor=[(bbox[0] + bbox[2]) / 2, bbox[3]],
                moved=False,
                model_version="yolov8s-worldv2",
            )
        )
    await session.flush()
    return image


@pytest.fixture
async def day3(session):
    """День 3 из фикстур analysis: экскаватор на въезде, камера въезда тёмная."""
    north = await _camera(
        session, "cam-north", ("PIT", "Котлован", LEFT), ("ENTRY_GATE", "Въезд", RIGHT)
    )
    gate = await _camera(
        session, "cam-gate", ("ENTRY_GATE", "Въезд", LEFT), ("STORAGE", "Склад", RIGHT)
    )
    first = await _window(session, T0)
    seen = await _image(
        session, north, first, ("excavator", IN_RIGHT), ("dump_truck", [0.1, 0.1, 0.2, 0.3])
    )
    dark = await _image(session, gate, first, usable=False, reason="DARK")
    await WindowFacts(session).recompute(first.id, OBJECT_ID)
    # Окно, где снимок ещё не распознан: в факты не попадает, но делает их неполными.
    waiting = await _window(session, T0 + timedelta(minutes=30))
    await _image(session, north, waiting, status="PENDING")
    # Окно за пределами периода.
    await _image(session, north, await _window(session, T0 + timedelta(days=1)))
    return {"window": first, "seen": seen, "dark": dark, "north": north}


async def test_факты_за_период_по_контракту(client, day3):
    response = await client.get(f"{SITE}/objects/{OBJECT_ID}/facts", params=PERIOD)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == TOP
    assert (body["from"], body["to"]) == (PERIOD["from"], PERIOD["to"])
    assert (body["zones_version"], body["model_versions"], body["pending_images"]) == (
        4,
        ["yolov8s-worldv2"],
        1,
    )
    [window] = body["sessions"]
    assert set(window) == SESSION
    assert (window["session_id"], window["window_start"], window["window_end"]) == (
        str(day3["window"].id),
        "2026-10-22T06:00:00Z",
        "2026-10-22T06:30:00Z",
    )

    cameras = {c["code"]: c for c in window["cameras"]}
    assert all(set(c) == CAMERA for c in cameras.values())
    assert cameras["cam-north"] == {
        "code": "cam-north",
        "images": 1,
        "usable": True,
        "reason": None,
        "image_ids": [str(day3["seen"].id)],
    }
    assert (cameras["cam-gate"]["usable"], cameras["cam-gate"]["reason"]) == (False, "DARK")
    assert cameras["cam-gate"]["image_ids"] == [str(day3["dark"].id)]

    areas = {a["area"]: a for a in window["areas"]}
    assert set(areas) == {"PIT:Котлован", "ENTRY_GATE:Въезд", "STORAGE:Склад"}
    assert all(set(a) == AREA and set(a["visibility"]) == VISIBILITY for a in areas.values())
    gate_area = areas["ENTRY_GATE:Въезд"]
    assert gate_area["visibility"] == {
        "status": "PARTIAL",
        "cameras_total": 2,
        "cameras_usable": 1,
        "reason": "DARK",
    }
    [excavator] = gate_area["equipment"]
    assert set(excavator) == EQUIPMENT
    assert (excavator["equipment_class"], excavator["count"], excavator["static"]) == (
        "excavator",
        1,
        1,
    )
    assert set(excavator["evidence"][0]) == EVIDENCE
    assert excavator["evidence"][0]["image_id"] == str(day3["seen"].id)
    assert areas["STORAGE:Склад"]["visibility"]["status"] == "BLIND"
    assert areas["STORAGE:Склад"]["equipment"] == []
    assert [e["equipment_class"] for e in areas["PIT:Котлован"]["equipment"]] == ["dump_truck"]
    assert window["outside_zones"] == []


async def test_техника_вне_зон_и_стадия(client, session):
    camera = await _camera(session, "cam-north", ("PIT", "Котлован", LEFT))
    window = await _window(session, T0)
    image = await _image(session, camera, window, ("truck_crane", IN_RIGHT))
    session.add(
        StageObservation(
            image_id=image.id,
            session_id=window.id,
            stage_label="PIT",
            conf=0.7,
            scores={"PIT": 0.7, "FOUNDATION": 0.2},
        )
    )
    await session.flush()
    await WindowFacts(session).recompute(window.id, OBJECT_ID)

    body = (await client.get(f"{SITE}/objects/{OBJECT_ID}/facts", params=PERIOD)).json()

    [fact] = body["sessions"]
    [outside] = fact["outside_zones"]
    assert (outside["equipment_class"], outside["count"]) == ("truck_crane", 1)
    assert fact["stage_observation"] == {
        "stage_label": "PIT",
        "conf": 0.7,
        "scores": {"FOUNDATION": 0.2, "PIT": 0.7},
    }


async def test_нет_снимков_пустой_список(client):
    response = await client.get(f"{SITE}/objects/{uuid4()}/facts", params=PERIOD)

    assert response.status_code == 200
    body = response.json()
    assert (body["sessions"], body["zones_version"], body["pending_images"]) == ([], 0, 0)


async def test_пустой_период_ошибка(client):
    response = await client.get(
        f"{SITE}/objects/{OBJECT_ID}/facts", params={"from": PERIOD["to"], "to": PERIOD["from"]}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PERIOD"


async def test_окна_список_и_состав(client, day3):
    response = await client.get(f"{SITE}/sessions", params={"object_id": str(OBJECT_ID), **PERIOD})

    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 2
    assert [s["window_start"] for s in page["items"]] == [
        "2026-10-22T06:00:00Z",
        "2026-10-22T06:30:00Z",
    ]

    detail = await client.get(f"{SITE}/sessions/{day3['window'].id}")

    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert {c["code"]: c["camera_id"] for c in body["cameras"]}["cam-north"] == str(
        day3["north"].id
    )
    assert {i["id"] for i in body["images"]} == {str(day3["seen"].id), str(day3["dark"].id)}
    assert len(body["areas"]) == 3


async def test_окно_не_найдено(client):
    response = await client.get(f"{SITE}/sessions/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"
