"""Качество кадра: яркость и размытость на синтетических кадрах."""

import numpy as np
import pytest
from PIL import Image, ImageFilter
from src.core.imaging import gray_for_quality
from src.core.quality import blur_score, frame_quality, laplacian_variance

REF = 100.0


def checkerboard(size=64, cell=4) -> np.ndarray:
    y, x = np.indices((size, size))
    return (((x // cell + y // cell) % 2) * 255).astype(np.float64)


def test_яркость_чёрного_белого_серого():
    assert frame_quality(np.zeros((10, 10)), REF).brightness == 0.0
    assert frame_quality(np.full((10, 10), 255.0), REF).brightness == 1.0
    assert frame_quality(np.full((10, 10), 51.0), REF).brightness == 0.2


def test_однотонный_кадр_максимально_размыт():
    assert frame_quality(np.full((50, 50), 128.0), REF).blur == 1.0


def test_резкий_кадр_почти_не_размыт():
    assert frame_quality(checkerboard(), REF).blur < 0.01


def test_размытие_увеличивает_размытость():
    sharp = Image.fromarray(checkerboard(256, 8).astype(np.uint8))
    soft = sharp.filter(ImageFilter.GaussianBlur(3))

    sharp_blur = frame_quality(np.asarray(sharp, dtype=np.float64), REF).blur
    soft_blur = frame_quality(np.asarray(soft, dtype=np.float64), REF).blur

    assert soft_blur > sharp_blur


def test_шкала_размытости_половина_при_эталонной_дисперсии():
    assert blur_score(REF, REF) == 0.5
    assert blur_score(0.0, REF) == 1.0
    assert blur_score(3 * REF, REF) == 0.25


def test_лапласиан_крошечного_кадра_ноль():
    assert laplacian_variance(np.ones((2, 5))) == 0.0


def test_цветной_кадр_не_принимается():
    with pytest.raises(ValueError, match="оттенках серого"):
        frame_quality(np.zeros((10, 10, 3)), REF)


def test_кадр_приводится_к_одному_размеру_для_метрик():
    big = Image.new("RGB", (4000, 2000), "white")
    small = Image.new("RGB", (300, 200), "white")

    assert gray_for_quality(big, 512).shape == (256, 512)
    assert gray_for_quality(small, 512).shape == (200, 300)
