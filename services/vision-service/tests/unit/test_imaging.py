"""Декодирование снимка: форматы, битые файлы, ориентация по EXIF."""

import io

import pytest
from PIL import Image
from src.core.imaging import ImageDecodeError, UnsupportedImageFormat, decode_image

from tests.conftest import image_bytes


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_поддерживаемые_форматы(fmt):
    image = decode_image(image_bytes((40, 30), fmt))

    assert image.size == (40, 30)
    assert image.mode == "RGB"


def test_gif_не_поддерживается():
    with pytest.raises(UnsupportedImageFormat, match="GIF"):
        decode_image(image_bytes(fmt="GIF"))


def test_не_изображение():
    with pytest.raises(ImageDecodeError, match="не распознан"):
        decode_image(b"%PDF-1.7 definitely not a photo")


def test_обрезанный_jpeg():
    content = image_bytes((400, 300))

    with pytest.raises(ImageDecodeError, match="не читается"):
        decode_image(content[: len(content) // 2])


def test_ориентация_из_exif_применяется():
    # Кадр 40×20, записанный с EXIF Orientation=6 («повернуть на 90°»): камера держалась боком.
    buffer = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", (40, 20)).save(buffer, format="JPEG", exif=exif)

    assert decode_image(buffer.getvalue()).size == (20, 40)
