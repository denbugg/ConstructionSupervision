"""Отчёт в PDF (T34c): ужатие снимка, рамки доказательства, ключ файла, вёрстка WeasyPrint."""

import base64
import io
from dataclasses import replace
from datetime import UTC, date, datetime, time
from uuid import UUID

import pytest
from PIL import Image
from src.report.context import EvidencePick, build_context
from src.report.html import render_html, template_summary
from src.report.images import ImageUnreadable, evidence_image, shrink_to_data_uri
from src.report.pdf import ReportKey, parse_report_key, render_pdf

from tests.factories import stable_id
from tests.unit.test_report import report_input  # noqa: F401 — фикстура входа отчёта

OBJECT_ID = UUID("0f3a6c1e-8d4b-4c2a-9e71-5b0d2f6a8c31")


def _jpeg(width: int, height: int, orientation: int | None = None) -> bytes:
    buffer = io.BytesIO()
    exif = Image.Exif()
    if orientation is not None:
        exif[0x0112] = orientation
    Image.new("RGB", (width, height), (90, 90, 90)).save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def _decoded_size(data_uri: str) -> tuple[int, int]:
    raw = base64.b64decode(data_uri.split(",", 1)[1])
    with Image.open(io.BytesIO(raw)) as image:
        return image.size


def test_снимок_ужимается_по_длинной_стороне_и_поворачивается_по_exif():
    uri, width, height = shrink_to_data_uri(_jpeg(4000, 3000), max_px=1280)
    assert (width, height) == (1280, 960) == _decoded_size(uri)

    # Ориентация 6 — кадр снят «на боку»: vision считал рамки на повёрнутом кадре.
    _, width, height = shrink_to_data_uri(_jpeg(400, 300, orientation=6), max_px=1280)
    assert (width, height) == (300, 400)


def test_битый_файл_снимка_доменная_ошибка():
    with pytest.raises(ImageUnreadable):
        shrink_to_data_uri(b"not an image", max_px=1280)


def test_выделены_только_рамки_из_доказательства(report_input):  # noqa: F811
    deviation = report_input.deviations[0]
    pick = EvidencePick(deviation, stable_id("img", 1), frozenset({"d-2"}))
    detail = {
        "captured_at": "2026-10-20T09:00:00Z",
        "detections": [
            {"id": "d-2", "equipment_class": "excavator", "bbox": [0.1, 0.2, 0.3, 0.4]},
            {"id": "d-1", "equipment_class": "dump_truck", "bbox": [0.5, 0.5, 0.6, 0.6]},
            {"id": "d-3", "equipment_class": "dump_truck", "bbox": []},
        ],
    }

    image = evidence_image(pick, detail, _jpeg(64, 48), {"excavator": "Экскаватор"}, 1280)

    assert [(b.highlighted, b.label) for b in image.boxes] == [(False, ""), (True, "Экскаватор")]
    assert image.captured_at == datetime(2026, 10, 20, 9, tzinfo=UTC)
    assert (image.width, image.height) == (64, 48)


def test_ключ_отчёта_туда_и_обратно():
    key = ReportKey(
        OBJECT_ID, date(2026, 9, 26), date(2026, 10, 16), date(2026, 10, 22), time(20, 15, 7)
    )

    assert str(key) == f"{OBJECT_ID}/2026-09-26T201507-2026-10-16_2026-10-22.pdf"
    assert parse_report_key(str(key)) == key
    assert parse_report_key(f"{OBJECT_ID}/notes.txt") is None
    assert parse_report_key(f"{OBJECT_ID}/2026-13-40-2026-10-16_2026-10-22.pdf") is None
    assert parse_report_key(f"{OBJECT_ID}/2026-09-26T256000-2026-10-16_2026-10-22.pdf") is None


def test_старый_ключ_без_времени_читается():
    """Отчёты до 27.09 лежат в бакете с ключом без времени и должны остаться в списке."""
    old = f"{OBJECT_ID}/2026-09-26-2026-10-16_2026-10-22.pdf"

    key = parse_report_key(old)

    assert key == ReportKey(OBJECT_ID, date(2026, 9, 26), date(2026, 10, 16), date(2026, 10, 22))
    assert str(key) == old


def test_pdf_по_демо_дням_со_снимком(report_input):  # noqa: F811
    deviation = report_input.deviations[0]
    pick = EvidencePick(deviation, stable_id("img", 1), frozenset({"d-1"}))
    detail = {"detections": [{"id": "d-1", "equipment_class": "excavator", "bbox": [0, 0, 1, 1]}]}
    image = evidence_image(pick, detail, _jpeg(640, 480), {}, 1280)
    context = build_context(replace(report_input, evidence=[image]))

    pdf = render_pdf(render_html(context, template_summary(context)))

    assert pdf.startswith(b"%PDF") and pdf.rstrip().endswith(b"%%EOF")
