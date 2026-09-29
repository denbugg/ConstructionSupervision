"""Перечисления из packages/contracts/enums.yaml, нужные site-service.

Разбор и проверка уже прочитанного YAML: списков значений в коде нет (CONTRIBUTING.md, раздел 7).
Испорченный файл — ошибка старта сервиса, а не тихий пустой список. Тот же разбор есть в
plan-service: код сервисов не общий (CONTRIBUTING.md, раздел 6), а 30 строк дешевле общей
библиотеки.
"""

from dataclasses import dataclass
from typing import Any

# Перечисления, без которых site-service не может проверить свой вход и выход.
REQUIRED_ENUMS = (
    "zone_type",
    "visibility_status",
    "visibility_reason",
    "stage_label",
    "image_status",
)


class ReferenceDataError(ValueError):
    """Справочный файл испорчен: сервис с ним не стартует."""


@dataclass(frozen=True)
class Enums:
    values: dict[str, tuple[str, ...]]
    # Роль типа зоны: WORK, SERVICE или SAFETY (methodology.md, раздел 2).
    zone_roles: dict[str, str]
    # Русское название типа — название участка по умолчанию (data-model.md, 2.2).
    zone_names: dict[str, str]

    @property
    def zone_types(self) -> tuple[str, ...]:
        return self.values["zone_type"]


def parse_enums(raw: Any) -> Enums:
    """Списки значений и роли типов зон; у каждого типа зоны должна быть роль."""
    if not isinstance(raw, dict):
        raise ReferenceDataError("enums.yaml: ожидался словарь перечислений")
    values = {
        str(k): tuple(str(v) for v in items) for k, items in raw.items() if isinstance(items, list)
    }
    missing = [name for name in REQUIRED_ENUMS if not values.get(name)]
    if missing:
        raise ReferenceDataError(f"enums.yaml: нет перечислений {missing}")
    roles = _zone_dict(raw, "zone_type_role", values["zone_type"], "роли")
    names = _zone_dict(raw, "zone_type_name", values["zone_type"], "названия")
    return Enums(values, roles, names)


def _zone_dict(raw: dict, key: str, zone_types: tuple[str, ...], what: str) -> dict[str, str]:
    """Словарь «тип зоны → значение», где значение есть у каждого типа."""
    items = raw.get(key)
    if not isinstance(items, dict):
        raise ReferenceDataError(f"enums.yaml: нет словаря {key}")
    missing = [z for z in zone_types if not str(items.get(z) or "").strip()]
    if missing:
        raise ReferenceDataError(f"enums.yaml: у типов зон нет {what} в {key}: {missing}")
    return {str(zone): str(value).strip() for zone, value in items.items()}
