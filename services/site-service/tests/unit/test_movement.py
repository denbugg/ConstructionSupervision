"""Смещение относительно прошлого окна камеры (methodology.md, 4.3)."""

import math

import pytest
from src.core.movement import PreviousBox, displacement, movement

THRESHOLD = 0.01
BOX = (0.40, 0.50, 0.50, 0.60)


def shifted(box, dx=0.0, dy=0.0):
    x1, y1, x2, y2 = box
    return (x1 + dx, y1 + dy, x2 + dx, y2 + dy)


def test_нет_прошлого_окна_сравнивать_не_с_чем():
    result = movement("excavator", BOX, None, 1920, 1080, THRESHOLD)

    assert result.moved is None
    assert result.displacement is None


def test_в_прошлом_окне_нет_этого_класса():
    previous = [PreviousBox("dump_truck", BOX)]

    assert movement("excavator", BOX, previous, 1920, 1080, THRESHOLD).moved is None
    assert movement("excavator", BOX, [], 1920, 1080, THRESHOLD).moved is None


def test_на_месте_неподвижна():
    result = movement("excavator", BOX, [PreviousBox("excavator", BOX)], 1920, 1080, THRESHOLD)

    assert result.moved is False
    assert result.displacement == 0.0


def test_сдвиг_больше_порога_сдвинулась():
    previous = [PreviousBox("excavator", shifted(BOX, dx=0.05))]

    result = movement("excavator", BOX, previous, 1000, 1000, THRESHOLD)

    assert result.moved is True
    assert result.displacement == pytest.approx(0.05 / math.sqrt(2), abs=1e-4)


def test_порог_включительно_сдвинулась():
    other = shifted(BOX, dx=0.02)
    exact = displacement(BOX, other, 1920, 1080)

    assert movement("excavator", BOX, [PreviousBox("excavator", other)], 1920, 1080, exact).moved


def test_берётся_ближайшая_рамка_того_же_класса():
    previous = [
        PreviousBox("excavator", shifted(BOX, dx=0.3)),
        PreviousBox("excavator", shifted(BOX, dx=0.001)),
        PreviousBox("dump_truck", BOX),
    ]

    assert movement("excavator", BOX, previous, 1920, 1080, THRESHOLD).moved is False


def test_смещение_учитывает_пропорции_кадра():
    # Широкий кадр: сдвиг по x в долях ширины длиннее в пикселях, чем тот же по y.
    along_x = displacement(BOX, shifted(BOX, dx=0.1), 1920, 1080)
    along_y = displacement(BOX, shifted(BOX, dy=0.1), 1920, 1080)

    assert along_x == pytest.approx(192 / math.hypot(1920, 1080))
    assert along_x > along_y


def test_размер_кадра_неизвестен_кадр_квадратный():
    assert displacement(BOX, shifted(BOX, dx=0.1), None, None) == pytest.approx(0.1 / math.sqrt(2))
