"""Время съёмки снимка (F1; ТЗ, п. 3): EXIF → имя файла → поле формы → иначе NEEDS_TIME.

Время без часового пояса (EXIF без OffsetTimeOriginal, имя файла, поле формы без смещения) —
местное время камеры, пояс которой задан `CAMERA_TIMEZONE`. Явное смещение главнее. Результат
всегда в UTC: так его хранит база и так его сравнивает analysis. Снимок без времени не
теряется: он ждёт ручного ввода и в план-факте не участвует.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import PurePath

EXIF_FORMAT = "%Y:%m:%d %H:%M:%S"
# Дата и время подряд в имени файла: 20261020_090000, IMG_20261020_090000, PXL_20261020_090000123,
# 2026-10-20_09-00-00, 2026-10-20 09.00.00. Разделители между частями — любые из «-_. :T».
FILENAME_PATTERN = re.compile(
    r"(?<!\d)(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})[ _T.-]?(\d{2})[-_.:]?(\d{2})[-_.:]?(\d{2})"
)
OFFSET_PATTERN = re.compile(r"^([+-])(\d{2}):?(\d{2})$")
# Раньше этой даты цифровых камер на стройках нет: число в имени файла — не время съёмки.
EARLIEST = datetime(2000, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class CapturedAt:
    """Время съёмки в UTC и откуда оно взято — чтобы вывод можно было проверить."""

    at: datetime | None
    # Значение timestamp_source из enums.yaml: EXIF, FILENAME, MANUAL, UNKNOWN.
    source: str
    detail: str


def resolve_captured_at(
    exif: Mapping[str, str],
    filename: str,
    form_value: str | None,
    camera_tz: tzinfo,
) -> CapturedAt:
    """Время съёмки по первому источнику, который дал правдоподобное время.

    Правдоподобное — не раньше 2000 года: сброшенные часы камеры дают 1970 или 1980 год.
    Верхней границы нет намеренно: демо-хронология живёт в датах графика, которые могут быть
    позже сегодняшнего дня, а время загрузки со временем съёмки не связано.
    """
    tried = []
    exif_at = parse_exif(exif, camera_tz)
    if exif_at is not None and exif_at >= EARLIEST:
        return CapturedAt(exif_at, "EXIF", _exif_detail(exif))
    if exif_at is not None:
        tried.append(f"EXIF {exif_at.isoformat()} неправдоподобно")
    name_at = parse_filename(filename, camera_tz)
    if name_at is not None and name_at >= EARLIEST:
        return CapturedAt(name_at, "FILENAME", f"имя файла {PurePath(filename).name}")
    form_at = parse_form_value(form_value, camera_tz) if form_value else None
    if form_at is not None and form_at >= EARLIEST:
        return CapturedAt(form_at, "MANUAL", f"поле формы {form_value}")
    if form_value:
        tried.append(f"поле формы {form_value!r} не разобрано или неправдоподобно")
    return CapturedAt(None, "UNKNOWN", "; ".join(tried) or "ни EXIF, ни имени файла со временем")


def parse_exif(exif: Mapping[str, str], camera_tz: tzinfo) -> datetime | None:
    """DateTimeOriginal (или DateTime) со смещением OffsetTimeOriginal, если оно есть."""
    raw = exif.get("DateTimeOriginal") or exif.get("DateTime")
    if not raw:
        return None
    try:
        local = datetime.strptime(raw.strip().rstrip("\x00"), EXIF_FORMAT)
    except ValueError:
        return None  # «0000:00:00 00:00:00» и прочий мусор незаполненного поля
    offset = _offset(exif.get("OffsetTimeOriginal") or exif.get("OffsetTime"))
    return local.replace(tzinfo=offset or camera_tz).astimezone(UTC)


def parse_filename(filename: str, camera_tz: tzinfo) -> datetime | None:
    """Время из имени файла без расширения; подпапка — это камера, а не время."""
    match = FILENAME_PATTERN.search(PurePath(filename).stem)
    if not match:
        return None
    try:
        local = datetime(*(int(part) for part in match.groups()))
    except ValueError:
        return None  # 20261340_990000 — цифры есть, даты нет
    return local.replace(tzinfo=camera_tz).astimezone(UTC)


def parse_form_value(value: str, camera_tz: tzinfo) -> datetime | None:
    """ISO-8601 из поля формы; без смещения — местное время камеры."""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=camera_tz)
    return parsed.astimezone(UTC)


def _offset(value: str | None) -> timezone | None:
    match = OFFSET_PATTERN.match((value or "").strip())
    if not match:
        return None
    sign = -1 if match.group(1) == "-" else 1
    return timezone(sign * timedelta(hours=int(match.group(2)), minutes=int(match.group(3))))


def _exif_detail(exif: Mapping[str, str]) -> str:
    tag = "DateTimeOriginal" if exif.get("DateTimeOriginal") else "DateTime"
    offset = exif.get("OffsetTimeOriginal") or exif.get("OffsetTime")
    return f"EXIF {tag} {exif[tag]}" + (f" {offset}" if offset else "")
