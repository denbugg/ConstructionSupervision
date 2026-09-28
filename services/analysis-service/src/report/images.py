"""Снимки-доказательства для отчёта: карточка снимка от site + файл → вставка в PDF.

Оригиналы камер весят по 1–2 МБ, и дюжина таких раздула бы PDF до десятков мегабайт,
поэтому снимок ужимается до `REPORT_IMAGE_MAX_PX` по длинной стороне и встраивается data
URI. Рамки заданы в долях кадра и от ужатия не зависят (interservice.md, контракт 6).
"""

import base64
import io
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from src.report.context import EvidencePick
from src.report.model import Box, EvidenceImage

# Качество JPEG встроенного снимка: рамки и технику видно, а файл в разы меньше оригинала.
JPEG_QUALITY = 80


class ImageUnreadable(ValueError):
    """Файл снимка не читается как изображение."""


def shrink_to_data_uri(content: bytes, max_px: int) -> tuple[str, int, int]:
    """JPEG data URI и размер ужатого кадра.

    Кадр поворачивается по EXIF, как в vision-service: рамки посчитаны на повёрнутом кадре,
    и без поворота легли бы мимо техники.
    """
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ImageUnreadable(type(exc).__name__) from exc
    image.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}", image.width, image.height


def evidence_image(
    pick: EvidencePick,
    detail: Mapping[str, Any],
    content: bytes,
    class_names: Mapping[str, str],
    max_px: int,
) -> EvidenceImage:
    """Снимок с рамками: выделены рамки из `evidence` вывода, остальные — фоном."""
    data_uri, width, height = shrink_to_data_uri(content, max_px)
    boxes = []
    for detection in detail.get("detections", ()):
        bbox = detection.get("bbox") or ()
        if len(bbox) != 4:
            continue
        highlighted = str(detection.get("id")) in pick.detection_ids
        code = str(detection.get("equipment_class", ""))
        boxes.append(
            Box(
                bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
                label=class_names.get(code, code) if highlighted else "",
                highlighted=highlighted,
            )
        )
    # Выделенные рисуются последними, чтобы фоновый пунктир не перекрывал их.
    boxes.sort(key=lambda b: b.highlighted)
    captured = detail.get("captured_at")
    return EvidenceImage(
        deviation_id=pick.deviation.id,
        image_id=pick.image_id,
        captured_at=datetime.fromisoformat(captured) if isinstance(captured, str) else None,
        data_uri=data_uri,
        width=width,
        height=height,
        boxes=tuple(boxes),
    )


def missing_image(pick: EvidencePick, problem: str) -> EvidenceImage:
    """Снимок, который не удалось вставить, с причиной — её назовёт раздел «Ограничения»."""
    return EvidenceImage(deviation_id=pick.deviation.id, image_id=pick.image_id, problem=problem)
