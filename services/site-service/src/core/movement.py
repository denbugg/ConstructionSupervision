"""Неподвижность: смещение рамки относительно прошлого окна той же камеры (methodology.md, 4.3).

Это не трекинг машин. Рамка сравнивается с ближайшей рамкой того же класса у той же камеры в
прошлом окне — этого хватает для одного наблюдения «с прошлой сессии ничего не сдвинулось».
Вывод «простой» из него делает analysis-service (ADR-0012).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

Box = Sequence[float]

PRECISION = 4


@dataclass(frozen=True)
class PreviousBox:
    """Рамка прошлого окна той же камеры."""

    equipment_class: str
    bbox: Box


@dataclass(frozen=True)
class Movement:
    """`moved` и `displacement` — null, если сравнивать не с чем."""

    moved: bool | None
    displacement: float | None


UNKNOWN = Movement(moved=None, displacement=None)


def movement(
    equipment_class: str,
    bbox: Box,
    previous: Sequence[PreviousBox] | None,
    width: int | None,
    height: int | None,
    threshold: float,
) -> Movement:
    """Смещение до ближайшей рамки того же класса в прошлом окне камеры.

    `previous = None` — у камеры не было прошлого окна; пустой список или ни одной рамки
    этого класса — тоже «сравнивать не с чем».
    """
    candidates = [p.bbox for p in previous or () if p.equipment_class == equipment_class]
    if not candidates:
        return UNKNOWN
    shift = min(displacement(bbox, other, width, height) for other in candidates)
    return Movement(moved=shift >= threshold, displacement=round(shift, PRECISION))


def displacement(a: Box, b: Box, width: int | None, height: int | None) -> float:
    """Расстояние между центрами рамок в долях диагонали кадра.

    Координаты нормированы по ширине и высоте отдельно, поэтому без пропорций кадра
    расстояние исказилось бы; размер неизвестен — считаем кадр квадратным.
    """
    w, h = (width, height) if width and height else (1, 1)
    dx = (_center(a)[0] - _center(b)[0]) * w
    dy = (_center(a)[1] - _center(b)[1]) * h
    return math.hypot(dx, dy) / math.hypot(w, h)


def _center(box: Box) -> tuple[float, float]:
    x1, y1, x2, y2 = (float(v) for v in box)
    return (x1 + x2) / 2, (y1 + y2) / 2
