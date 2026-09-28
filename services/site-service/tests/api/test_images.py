"""Приём снимков: частичный успех пакета, дубликаты, камера из подпапки, окно, импорт папки."""

import io
from uuid import UUID

import pytest
from PIL import Image
from sqlalchemy import select
from src.config import settings
from src.dal.models import Camera, ObservationSession
from src.dal.models import Image as ImageRow

SITE = "/api/v1/site"
OBJECT_ID = "11111111-1111-4111-8111-111111111111"


def _jpeg(shade: int, taken: str | None = None, kind: str = "JPEG") -> bytes:
    """Кадр с уникальным содержимым: sha256 разных кадров не совпадает."""
    image = Image.new("RGB", (32, 24), (shade, 100, 100))
    exif = Image.Exif()
    if taken:
        exif[0x8769] = {36867: taken}  # DateTimeOriginal во вложенном Exif IFD
    out = io.BytesIO()
    image.save(out, kind, exif=exif) if kind == "JPEG" else image.save(out, kind)
    return out.getvalue()


async def _upload(client, files, **form):
    return await client.post(
        f"{SITE}/images",
        data={"object_id": OBJECT_ID} | form,
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
    )


async def test_пакет_принимается_частично(client, session, storage, queue, monkeypatch):
    monkeypatch.setattr(settings, "max_image_mb", 1)
    good = _jpeg(10, "2026:10:20 12:03:00")
    files = [
        ("IMG_0001.jpg", good),
        ("IMG_0002.jpg", good),  # тот же кадр второй раз
        ("act.pdf", b"%PDF-1.7 not an image"),
        ("IMG_0003.jpg", _jpeg(20)),  # без времени — принимается, ждёт ручного ввода
        ("huge.jpg", b"\xff\xd8" + b"0" * (1024 * 1024 + 1)),
    ]

    response = await _upload(client, files, camera_code="cam-north")

    assert response.status_code == 202, response.text
    body = response.json()
    accepted = {a["file"]: a for a in body["accepted"]}
    rejected = {r["file"]: r for r in body["rejected"]}
    assert set(accepted) == {"IMG_0001.jpg", "IMG_0003.jpg"}
    first = accepted["IMG_0001.jpg"]
    assert (first["captured_at"], first["captured_at_source"], first["status"]) == (
        "2026-10-20T09:03:00Z",
        "EXIF",
        "PENDING",
    )
    assert (accepted["IMG_0003.jpg"]["status"], accepted["IMG_0003.jpg"]["captured_at"]) == (
        "NEEDS_TIME",
        None,
    )
    assert rejected["IMG_0002.jpg"]["code"] == "IMAGE_ALREADY_EXISTS"
    assert rejected["IMG_0002.jpg"]["image_id"] == first["image_id"]
    assert rejected["act.pdf"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert rejected["huge.jpg"]["code"] == "IMAGE_TOO_LARGE"

    camera = await session.scalar(select(Camera).where(Camera.code == "cam-north"))
    assert camera.reference_image_id == UUID(first["image_id"])  # первый снимок — эталон
    assert len(storage.objects) == 2
    key = next(k for k in storage.objects if first["image_id"] in k)
    assert key.startswith(f"{OBJECT_ID}/{camera.id}/2026-10-20/")
    # В очередь распознавания — только снимки со временем: без него нет окна.
    assert [str(i) for i in queue.enqueued] == [first["image_id"]]


async def test_камера_из_подпапки_и_время_из_имени_файла(client):
    response = await _upload(
        client,
        [
            ("cam-gate/20261020_120500.jpg", _jpeg(30)),
            ("20261020_121000.jpg", _jpeg(40)),  # ни подпапки, ни camera_code
        ],
    )

    body = response.json()
    assert [(a["camera_code"], a["captured_at_source"]) for a in body["accepted"]] == [
        ("cam-gate", "FILENAME")
    ]
    assert body["rejected"][0]["code"] == "CAMERA_REQUIRED"


async def test_снимки_одного_окна_с_двух_камер_в_одной_сессии(client, session):
    await _upload(client, [("cam-a/20261020_120100.jpg", _jpeg(50))])
    await _upload(client, [("cam-b/20261020_122900.jpg", _jpeg(60))])
    await _upload(client, [("cam-b/20261020_123000.jpg", _jpeg(70))])  # уже следующее окно

    windows = (
        await session.scalars(select(ObservationSession).order_by(ObservationSession.window_start))
    ).all()

    assert [(w.window_start.isoformat(), w.image_count, w.camera_count) for w in windows] == [
        ("2026-10-20T09:00:00+00:00", 2, 2),
        ("2026-10-20T09:30:00+00:00", 1, 1),
    ]


async def test_недоступное_хранилище_отклоняет_файл_и_ничего_не_пишет(client, session, storage):
    storage.broken = True

    response = await _upload(client, [("cam-a/20261020_120100.jpg", _jpeg(80))])

    assert response.json()["rejected"][0]["code"] == "STORAGE_UNAVAILABLE"
    assert (await session.scalars(select(ImageRow))).all() == []
    # Камера из отклонённого файла тоже не остаётся: точка сохранения откатилась целиком.
    assert (await session.scalars(select(Camera))).all() == []


async def test_слишком_большой_пакет(client, monkeypatch):
    monkeypatch.setattr(settings, "max_files_per_request", 2)

    response = await _upload(client, [(f"cam-a/{n}.jpg", _jpeg(n)) for n in range(3)])

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMAGE_BATCH_TOO_LARGE"


async def test_список_фильтры_и_снимки_без_времени_в_конце(client):
    await _upload(
        client,
        [
            ("cam-a/20261020_130000.jpg", _jpeg(120)),
            ("cam-a/IMG_0001.jpg", _jpeg(121)),  # без времени
            ("cam-b/20261020_120000.jpg", _jpeg(122)),
        ],
    )

    everything = (await client.get(f"{SITE}/images", params={"object_id": OBJECT_ID})).json()
    waiting = (await client.get(f"{SITE}/images", params={"status": "NEEDS_TIME"})).json()
    period = (
        await client.get(
            f"{SITE}/images",
            params={"from": "2026-10-20T09:30:00Z", "to": "2026-10-20T10:30:00Z"},
        )
    ).json()
    wrong = await client.get(
        f"{SITE}/images", params={"from": "2026-10-21T00:00:00Z", "to": "2026-10-20T00:00:00Z"}
    )

    assert [i["captured_at"] for i in everything["items"]] == [
        "2026-10-20T09:00:00Z",
        "2026-10-20T10:00:00Z",
        None,
    ]
    assert (waiting["total"], period["total"]) == (1, 1)
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (400, "INVALID_PERIOD")


async def test_карточка_со_ссылкой_для_браузера(client):
    uploaded = await _upload(client, [("cam-a/20261020_130000.jpg", _jpeg(130))])
    image_id = uploaded.json()["accepted"][0]["image_id"]

    card = (await client.get(f"{SITE}/images/{image_id}")).json()
    missing = await client.get(f"{SITE}/images/{OBJECT_ID}")

    assert card["url"].startswith("http://localhost:8333/images/")
    assert (card["width"], card["height"], card["detections"], card["stage"]) == (32, 24, [], None)
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "IMAGE_NOT_FOUND")


async def test_карточка_для_сервиса_со_ссылкой_во_внутреннюю_сеть(client):
    """Контракт 6: отчёт analysis скачивает снимок из сети Docker, localhost:8333 там не открыть."""
    uploaded = await _upload(client, [("cam-a/20261020_130000.jpg", _jpeg(130))])
    image_id = uploaded.json()["accepted"][0]["image_id"]

    card = (await client.get(f"{SITE}/images/{image_id}", params={"link": "internal"})).json()
    wrong = await client.get(f"{SITE}/images/{image_id}", params={"link": "s3"})

    assert card["url"].startswith("http://s3:8333/images/")
    assert (card["width"], card["height"]) == (32, 24)
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (422, "SCHEMA_VALIDATION_FAILED")


async def test_ручное_время_для_needs_time(client, session, queue):
    uploaded = await _upload(client, [("cam-a/IMG_0001.jpg", _jpeg(140))])
    image_id = uploaded.json()["accepted"][0]["image_id"]
    assert queue.enqueued == []
    url = f"{SITE}/images/{image_id}"

    garbage = await client.patch(url, json={"captured_at": "вчера"})
    manual = await client.patch(url, json={"captured_at": "2026-10-20T12:03:00"})
    again = await client.patch(url, json={"captured_at": "2026-10-20T13:00:00"})

    assert (garbage.status_code, garbage.json()["error"]["code"]) == (400, "INVALID_CAPTURED_AT")
    body = manual.json()
    assert (body["captured_at"], body["captured_at_source"], body["status"]) == (
        "2026-10-20T09:03:00Z",
        "MANUAL",
        "PENDING",
    )
    window = await session.get(ObservationSession, UUID(body["session_id"]))
    assert (window.window_start.isoformat(), window.image_count) == ("2026-10-20T09:00:00+00:00", 1)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "IMAGE_TIME_ALREADY_SET")
    assert [str(i) for i in queue.enqueued] == [image_id]


@pytest.fixture
def import_dir(tmp_path, monkeypatch):
    (tmp_path / "day1" / "cam-a").mkdir(parents=True)
    (tmp_path / "day1" / "cam-b" / "2026-10-20").mkdir(parents=True)
    (tmp_path / "day1" / "cam-a" / "20261020_120000.jpg").write_bytes(_jpeg(90))
    (tmp_path / "day1" / "cam-b" / "2026-10-20" / "20261020_120500.png").write_bytes(
        _jpeg(100, kind="PNG")
    )
    (tmp_path / "day1" / "cam-a" / ".gitkeep").write_bytes(b"")
    (tmp_path / "day1" / "loose.jpg").write_bytes(_jpeg(110))
    monkeypatch.setattr(settings, "import_dir", str(tmp_path))
    return tmp_path


async def test_импорт_папки_подпапка_это_камера(client, session, import_dir):
    first = await client.post(
        f"{SITE}/images/import", json={"object_id": OBJECT_ID, "path": "day1"}
    )
    again = await client.post(
        f"{SITE}/images/import", json={"object_id": OBJECT_ID, "path": "day1"}
    )

    assert first.status_code == 202, first.text
    body = first.json()
    assert sorted((a["file"], a["camera_code"]) for a in body["accepted"]) == [
        ("cam-a/20261020_120000.jpg", "cam-a"),
        ("cam-b/2026-10-20/20261020_120500.png", "cam-b"),
    ]
    assert [(r["file"], r["code"]) for r in body["rejected"]] == [("loose.jpg", "CAMERA_REQUIRED")]
    sources = (await session.scalars(select(ImageRow.source))).all()
    assert set(sources) == {"FOLDER_IMPORT"}
    assert {r["code"] for r in again.json()["rejected"]} == {
        "IMAGE_ALREADY_EXISTS",
        "CAMERA_REQUIRED",
    }


async def test_импорт_вне_каталога_импорта_запрещён(client, import_dir):
    outside = await client.post(
        f"{SITE}/images/import", json={"object_id": OBJECT_ID, "path": "../"}
    )
    missing = await client.post(
        f"{SITE}/images/import", json={"object_id": OBJECT_ID, "path": "day9"}
    )

    assert outside.status_code == missing.status_code == 404
    assert outside.json()["error"]["code"] == "IMPORT_DIR_NOT_FOUND"
