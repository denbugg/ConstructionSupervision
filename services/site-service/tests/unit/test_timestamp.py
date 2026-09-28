"""Время снимка: порядок источников, нестандартные имена файлов, EXIF со смещением, мусор."""

import io
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from PIL import Image
from src.core.image_meta import UnsupportedImage, read_image_meta
from src.core.sessions import WindowError, session_window
from src.core.timestamp import parse_filename, resolve_captured_at

MSK = ZoneInfo("Europe/Moscow")
EXIF_TIME = {"DateTimeOriginal": "2026:10:20 12:03:00"}


def _resolve(exif=None, filename="IMG_0042.jpg", form=None):
    return resolve_captured_at(exif or {}, filename, form, MSK)


def test_exif_главнее_имени_файла_и_формы():
    result = _resolve(EXIF_TIME, "cam-north/20261020_150000.jpg", "2026-10-20T16:00:00")

    assert (result.at, result.source) == (datetime(2026, 10, 20, 9, 3, tzinfo=UTC), "EXIF")
    assert "DateTimeOriginal 2026:10:20 12:03:00" in result.detail


def test_смещение_из_exif_главнее_пояса_камеры():
    exif = EXIF_TIME | {"OffsetTimeOriginal": "+05:00"}

    assert _resolve(exif).at == datetime(2026, 10, 20, 7, 3, tzinfo=UTC)


@pytest.mark.parametrize(
    "filename",
    [
        "cam-north/20261020_120000.jpg",
        "IMG_20261020_120000.jpg",
        "PXL_20261020_120000123.jpg",
        "2026-10-20_12-00-00.png",
        "2026-10-20 12.00.00.jpg",
        "snapshot-20261020T120000.jpeg",
    ],
)
def test_время_из_нестандартных_имён_файлов(filename):
    assert parse_filename(filename, MSK) == datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def test_имя_файла_без_времени_и_с_невозможной_датой():
    assert parse_filename("IMG_0042.jpg", MSK) is None
    assert parse_filename("20261340_990000.jpg", MSK) is None
    # Время в подпапке — не время снимка: подпапка означает камеру.
    assert parse_filename("20261020_120000/IMG_0042.jpg", MSK) is None


def test_поле_формы_если_больше_неоткуда():
    local = _resolve(form="2026-10-20T12:30:00")
    utc = _resolve(form="2026-10-20T09:30:00Z")

    assert (local.at, local.source) == (datetime(2026, 10, 20, 9, 30, tzinfo=UTC), "MANUAL")
    assert utc.at == local.at


def test_без_времени_снимок_ждёт_ручного_ввода():
    result = _resolve(form="вчера")

    assert (result.at, result.source) == (None, "UNKNOWN")
    assert "вчера" in result.detail


def test_пустой_и_сброшенный_exif_пропускается():
    zeros = _resolve({"DateTimeOriginal": "0000:00:00 00:00:00"}, "20261020_120000.jpg")
    reset_clock = _resolve({"DateTimeOriginal": "1980:01:01 00:00:00"}, "20261020_120000.jpg")
    only_reset = _resolve({"DateTimeOriginal": "1970:01:01 00:00:00"})

    assert zeros.source == reset_clock.source == "FILENAME"
    assert (only_reset.source, only_reset.at) == ("UNKNOWN", None)
    assert "неправдоподобно" in only_reset.detail


def test_дата_позже_сегодняшней_принимается():
    """Демо-хронология живёт в датах графика — они бывают позже дня загрузки."""
    later = _resolve({"DateTimeOriginal": "2031:01:01 00:00:00"})

    assert (later.source, later.at) == ("EXIF", datetime(2030, 12, 31, 21, 0, tzinfo=UTC))


def _jpeg(**exif_tags) -> bytes:
    image = Image.new("RGB", (64, 48), "gray")
    exif = Image.Exif()
    # Вложенный Exif IFD — словарём по тегу 0x8769: так его пишут и Pillow 11, и Pillow 12.
    tags = {"DateTimeOriginal": 36867, "OffsetTimeOriginal": 36881}
    exif[0x8769] = {tags[name]: value for name, value in exif_tags.items()}
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_метаданные_кадра_и_exif_из_байтов():
    meta = read_image_meta(
        _jpeg(DateTimeOriginal="2026:10:20 12:03:00", OffsetTimeOriginal="+03:00")
    )

    assert (meta.format, meta.content_type, meta.width, meta.height) == (
        "JPEG",
        "image/jpeg",
        64,
        48,
    )
    assert meta.exif == {"DateTimeOriginal": "2026:10:20 12:03:00", "OffsetTimeOriginal": "+03:00"}


def test_не_изображение_и_неподдерживаемый_формат():
    gif = io.BytesIO()
    Image.new("P", (4, 4)).save(gif, "GIF")

    with pytest.raises(UnsupportedImage, match="не читается"):
        read_image_meta(b"%PDF-1.7")
    with pytest.raises(UnsupportedImage, match="GIF"):
        read_image_meta(gif.getvalue())


@pytest.mark.parametrize(
    ("at", "start"),
    [
        (datetime(2026, 10, 20, 9, 3, tzinfo=UTC), datetime(2026, 10, 20, 9, 0, tzinfo=UTC)),
        (datetime(2026, 10, 20, 9, 30, tzinfo=UTC), datetime(2026, 10, 20, 9, 30, tzinfo=UTC)),
        (datetime(2026, 10, 20, 9, 59, 59, tzinfo=UTC), datetime(2026, 10, 20, 9, 30, tzinfo=UTC)),
        # 12:03 МСК — то же окно, что 09:03 UTC.
        (datetime(2026, 10, 20, 12, 3, tzinfo=MSK), datetime(2026, 10, 20, 9, 0, tzinfo=UTC)),
    ],
)
def test_окно_сессии_по_00_и_30_utc(at, start):
    window = session_window(at, 30)

    assert window[0] == start
    assert (window[1] - window[0]).total_seconds() == 30 * 60


def test_окно_не_делящее_сутки_и_время_без_пояса():
    with pytest.raises(WindowError):
        session_window(datetime(2026, 10, 20, 9, 0, tzinfo=UTC), 7)
    with pytest.raises(WindowError):
        session_window(datetime(2026, 10, 20, 9, 0), 30)
