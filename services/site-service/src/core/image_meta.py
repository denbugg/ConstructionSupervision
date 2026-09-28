"""Метаданные кадра из байтов файла: формат, размер, EXIF. Без диска и сети.

Формат определяется по содержимому, а не по расширению: переименованный PDF не должен
попасть в распознавание.
"""

import io
from dataclasses import dataclass, field

from PIL import ExifTags, Image, UnidentifiedImageError

# Форматы, которые принимает vision-service и показывает браузер.
SUPPORTED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
# Теги EXIF, нужные для времени съёмки и для объяснения, откуда оно взято.
EXIF_TAGS = ("DateTimeOriginal", "DateTime", "OffsetTimeOriginal", "OffsetTime", "Make", "Model")


class UnsupportedImage(ValueError):
    """Файл — не снимок поддерживаемого формата."""


@dataclass(frozen=True)
class ImageMeta:
    format: str
    content_type: str
    width: int
    height: int
    exif: dict[str, str] = field(default_factory=dict)


def read_image_meta(content: bytes) -> ImageMeta:
    try:
        with Image.open(io.BytesIO(content)) as image:
            kind = image.format or ""
            if kind not in SUPPORTED_FORMATS:
                raise UnsupportedImage(
                    f"Формат {kind or 'не распознан'}; принимаются {', '.join(SUPPORTED_FORMATS)}"
                )
            return ImageMeta(kind, SUPPORTED_FORMATS[kind], image.width, image.height, _exif(image))
    except (UnidentifiedImageError, OSError) as exc:
        raise UnsupportedImage("Файл не читается как изображение") from exc


def _exif(image: Image.Image) -> dict[str, str]:
    """Нужные теги из IFD0 и Exif IFD: DateTimeOriginal лежит во втором."""
    raw = image.getexif()
    merged = dict(raw.items())
    merged.update(raw.get_ifd(ExifTags.IFD.Exif).items())
    result = {}
    for tag_id, value in merged.items():
        name = ExifTags.TAGS.get(tag_id)
        if name in EXIF_TAGS and value is not None:
            text = value.decode(errors="ignore") if isinstance(value, bytes) else str(value)
            if text.strip("\x00 "):
                result[name] = text.strip("\x00 ")
    return result
