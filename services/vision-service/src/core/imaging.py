"""Декодирование снимка и подготовка кадра к метрикам качества.

Байты → RGB-кадр с учётом ориентации из EXIF: камера, снятая «на боку», иначе дала бы рамки,
повёрнутые относительно полигонов зон, размеченных на том же, но правильно повёрнутом кадре.
"""

import io

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

# Форматы, которые принимает site-service при загрузке снимков (api-guidelines.md, раздел 7).
SUPPORTED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


class ImageDecodeError(ValueError):
    """Байты не удалось прочитать как изображение: битый или обрезанный файл."""


class UnsupportedImageFormat(ValueError):
    """Изображение прочитано, но его формат не поддерживается."""


def decode_image(content: bytes) -> Image.Image:
    """RGB-кадр, повёрнутый по EXIF; ошибки чтения — доменные, а не голые OSError."""
    try:
        image = Image.open(io.BytesIO(content))
    except UnidentifiedImageError as exc:
        raise ImageDecodeError("файл не распознан как изображение") from exc
    except (OSError, Image.DecompressionBombError) as exc:
        raise ImageDecodeError(f"изображение не читается: {type(exc).__name__}") from exc

    if image.format not in SUPPORTED_FORMATS:
        raise UnsupportedImageFormat(f"формат {image.format} не поддерживается")
    try:
        # Заголовок читается при open, а сами пиксели — только здесь: обрезанный JPEG
        # падает именно на load.
        image.load()
        return ImageOps.exif_transpose(image).convert("RGB")
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise ImageDecodeError(f"изображение не читается: {type(exc).__name__}") from exc


def gray_for_quality(image: Image.Image, side: int) -> np.ndarray:
    """Кадр в оттенках серого, длинная сторона не больше `side` пикселей.

    Метрика размытости зависит от разрешения, поэтому все снимки приводятся к одному размеру.
    """
    small = image.copy()
    small.thumbnail((side, side), Image.Resampling.BILINEAR)
    return np.asarray(small.convert("L"), dtype=np.float64)
