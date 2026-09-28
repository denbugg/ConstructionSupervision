"""Справочные файлы контрактов: классы техники и перечисления (ADR-0014).

Классы техники живут в одном файле `equipment_classes.yaml`, перечисления — в `enums.yaml`.
Здесь только разбор и проверка уже прочитанного YAML: файл, который пройдёт проверку,
одинаково поймут plan, vision и ml. Испорченный файл — ошибка старта сервиса, а не
тихий пустой список.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# Код класса совпадает с меткой детектора и ключами правил этапов (api-guidelines.md, раздел 3).
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
# Перечисления, без которых plan-service не может проверить свой вход.
REQUIRED_ENUMS = (
    "object_type",
    "object_lifecycle",
    "construction_phase",
    "zone_type",
    "equipment_group",
    "stage_label",
    "stage_source",
    "dependency_type",
)


class ReferenceDataError(ValueError):
    """Справочный файл испорчен: сервис с ним не стартует."""


@dataclass(frozen=True)
class EquipmentClass:
    code: str
    name_ru: str
    group: str
    # Приезжает и уезжает рейсами: присутствие считается за окно сессий (методика, раздел 5).
    transient: bool
    prompts: tuple[str, ...]
    aliases: tuple[str, ...]
    # Работает, не сдвигаясь с места: неподвижность на рабочем участке не простой (раздел 6).
    works_in_place: bool = False


def parse_enums(raw: Any) -> dict[str, tuple[str, ...]]:
    """Списки значений из enums.yaml; словари (роли типов зон) здесь не нужны."""
    if not isinstance(raw, dict):
        raise ReferenceDataError("enums.yaml: ожидался словарь перечислений")
    values = {
        k: tuple(str(v) for v in items) for k, items in raw.items() if isinstance(items, list)
    }
    missing = [name for name in REQUIRED_ENUMS if not values.get(name)]
    if missing:
        raise ReferenceDataError(f"enums.yaml: нет перечислений {missing}")
    return values


def parse_zone_roles(raw: Any, zone_types: Iterable[str]) -> dict[str, str]:
    """Роли типов зон из enums.yaml: у каждого типа зоны должна быть роль."""
    roles = raw.get("zone_type_role") if isinstance(raw, dict) else None
    if not isinstance(roles, dict):
        raise ReferenceDataError("enums.yaml: нет словаря zone_type_role")
    missing = [z for z in zone_types if z not in roles]
    if missing:
        raise ReferenceDataError(f"enums.yaml: у типов зон нет роли в zone_type_role: {missing}")
    return {str(zone): str(role) for zone, role in roles.items()}


def parse_equipment_classes(raw: Any, groups: Iterable[str]) -> tuple[EquipmentClass, ...]:
    """Классы техники с проверкой: код, уникальность, группа из enums.yaml, признак транзита."""
    try:
        items = raw["equipment_classes"]
    except (KeyError, TypeError) as exc:
        raise ReferenceDataError("equipment_classes.yaml: нет списка equipment_classes") from exc
    allowed_groups = set(groups)
    classes: list[EquipmentClass] = []
    seen: set[str] = set()
    for number, item in enumerate(items or (), start=1):
        where = f"equipment_classes.yaml, запись {number}"
        try:
            cls = EquipmentClass(
                code=str(item["code"]),
                name_ru=str(item["name_ru"]).strip(),
                group=str(item["group"]),
                transient=item["transient"],
                prompts=tuple(str(p) for p in item.get("prompts") or ()),
                aliases=tuple(str(a) for a in item.get("aliases") or ()),
                works_in_place=item.get("works_in_place", False),
            )
        except (KeyError, TypeError, AttributeError) as exc:
            raise ReferenceDataError(f"{where}: нет обязательного поля {exc}") from exc
        if not CODE_PATTERN.match(cls.code):
            raise ReferenceDataError(f"{where}: код {cls.code!r} не в lower_snake_case")
        if cls.code in seen:
            raise ReferenceDataError(f"{where}: код {cls.code!r} повторяется")
        if not cls.name_ru:
            raise ReferenceDataError(f"{where}: пустое название")
        if cls.group not in allowed_groups:
            raise ReferenceDataError(f"{where}: группы {cls.group!r} нет в equipment_group")
        if not isinstance(cls.transient, bool):
            raise ReferenceDataError(f"{where}: transient — true или false")
        if not isinstance(cls.works_in_place, bool):
            raise ReferenceDataError(f"{where}: works_in_place — true или false")
        seen.add(cls.code)
        classes.append(cls)
    if not classes:
        raise ReferenceDataError("equipment_classes.yaml: ни одного класса")
    return tuple(classes)


def unknown_codes(codes: Iterable[str], classes: Iterable[EquipmentClass]) -> list[str]:
    """Коды, которых нет в справочнике классов, — по порядку первого упоминания, без повторов."""
    known = {c.code for c in classes}
    return list(dict.fromkeys(c for c in codes if c not in known))
