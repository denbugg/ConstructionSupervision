"""Постобработка детектора: промпт → класс техники, нормировка рамок, склейка дублей (F2).

Детектор подавляет пересечения только внутри одного промпта. Одна машина поэтому приходит
несколькими рамками: «excavator» и «digger» одного класса или, на снимках lct-raw, «tipper truck»,
«knuckle boom truck» и «truck» разных классов. Склеиваем любые рамки с IoU выше порога и
оставляем самую уверенную: иначе site-worker насчитает три машины там, где стоит одна.
Человек у экскаватора не теряется: его рамка мала, и IoU с рамкой машины низкий.
"""

from collections.abc import Sequence
from dataclasses import dataclass

# Точность координат и уверенности в ответе: 1e-4 кадра — доля пикселя даже для 4K.
PRECISION = 4


@dataclass(frozen=True)
class RawBox:
    """Рамка в пикселях кадра, как её вернул детектор."""

    x1: float
    y1: float
    x2: float
    y2: float
    conf: float
    prompt_index: int


@dataclass(frozen=True)
class Detection:
    """Рамка с кодом класса; координаты [x1, y1, x2, y2] нормированы 0…1."""

    equipment_class: str
    bbox: tuple[float, float, float, float]
    conf: float


def postprocess(
    boxes: Sequence[RawBox],
    width: int,
    height: int,
    prompt_codes: Sequence[str],
    min_conf: float,
    iou_threshold: float,
) -> list[Detection]:
    """Детекции не ниже порога, по убыванию уверенности, одна рамка на объект."""
    candidates: list[Detection] = []
    for box in boxes:
        if box.conf < min_conf:
            continue
        if not 0 <= box.prompt_index < len(prompt_codes):
            raise ValueError(f"номер промпта {box.prompt_index} вне словаря детектора")
        bbox = _normalize(box, width, height)
        if bbox is None:
            continue
        candidates.append(Detection(prompt_codes[box.prompt_index], bbox, round(box.conf, 4)))

    candidates.sort(key=lambda d: d.conf, reverse=True)
    kept: list[Detection] = []
    for det in candidates:
        if not any(iou(k.bbox, det.bbox) > iou_threshold for k in kept):
            kept.append(det)
    return kept


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    """Отношение площади пересечения рамок к площади объединения."""
    inter_w = min(a[2], b[2]) - max(a[0], b[0])
    inter_h = min(a[3], b[3]) - max(a[1], b[1])
    if inter_w <= 0 or inter_h <= 0:
        return 0.0
    inter = inter_w * inter_h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _normalize(box: RawBox, width: int, height: int) -> tuple[float, float, float, float] | None:
    """Рамка в долях кадра, обрезанная по его краю; вырожденная рамка — None."""
    if width <= 0 or height <= 0:
        raise ValueError("размер кадра должен быть положительным")
    x1, x2 = sorted((_clip(box.x1 / width), _clip(box.x2 / width)))
    y1, y2 = sorted((_clip(box.y1 / height), _clip(box.y2 / height)))
    bbox = tuple(round(v, PRECISION) for v in (x1, y1, x2, y2))
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return bbox  # type: ignore[return-value]


def _clip(value: float) -> float:
    return min(1.0, max(0.0, value))
