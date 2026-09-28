"""Стадия объекта по фото: промпты меток и выбор метки по сходству (F6).

Метки стадий — `stage_label` из enums.yaml, их промпты для CLIP — data/stage_prompts.yaml.
Набор меток в двух файлах обязан совпадать: стадия, которой нет в enums.yaml, не пройдёт
проверку в site-service, а стадия без промптов никогда не будет предсказана.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.core.vocabulary import ReferenceDataError

PRECISION = 4


@dataclass(frozen=True)
class StagePrompts:
    """Промпты каждой метки стадии; порядок меток — как в enums.yaml."""

    labels: tuple[str, ...]
    prompts: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class Stage:
    label: str
    conf: float
    scores: dict[str, float]


def parse_stage_labels(raw_enums: Any) -> tuple[str, ...]:
    """Метки стадий из enums.yaml."""
    labels = raw_enums.get("stage_label") if isinstance(raw_enums, dict) else None
    if not isinstance(labels, list) or not labels:
        raise ReferenceDataError("enums.yaml: нет перечисления stage_label")
    return tuple(str(v) for v in labels)


def parse_stage_prompts(raw: Any, labels: Sequence[str]) -> StagePrompts:
    """Промпты по меткам; метки файла совпадают с `stage_label` в точности."""
    items = raw.get("stage_prompts") if isinstance(raw, dict) else None
    if not isinstance(items, dict):
        raise ReferenceDataError("stage_prompts.yaml: нет словаря stage_prompts")
    missing = [label for label in labels if label not in items]
    unknown = [str(label) for label in items if label not in labels]
    if missing or unknown:
        raise ReferenceDataError(
            f"stage_prompts.yaml: метки не совпадают с stage_label в enums.yaml; "
            f"нет промптов для {missing}, лишние {unknown}"
        )
    prompts: dict[str, tuple[str, ...]] = {}
    for label in labels:
        values = items[label] if isinstance(items[label], list) else []
        cleaned = tuple(str(p).strip() for p in values if str(p).strip())
        if not cleaned:
            raise ReferenceDataError(f"stage_prompts.yaml: у {label} пустой список промптов")
        prompts[label] = cleaned
    return StagePrompts(tuple(labels), prompts)


def stage_from_logits(labels: Sequence[str], logits: Sequence[float]) -> Stage:
    """Вероятности меток — softmax по логитам сходства; метка — самая вероятная."""
    if len(labels) != len(logits) or not labels:
        raise ValueError("число логитов должно совпадать с числом меток")
    top = max(logits)
    # Вычитаем максимум: exp от логитов CLIP (сходство × 100) иначе переполняется.
    weights = [math.exp(v - top) for v in logits]
    total = sum(weights)
    scores = {label: round(w / total, PRECISION) for label, w in zip(labels, weights, strict=True)}
    best = max(range(len(labels)), key=lambda i: logits[i])
    return Stage(label=labels[best], conf=scores[labels[best]], scores=scores)
