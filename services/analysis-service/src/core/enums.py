"""Канонические перечисления из packages/contracts/enums.yaml.

Списки значений в коде не дублируются (AGENTS.md, раздел 7): методика узнаёт роль
типа зоны и порядок стадий по фото только отсюда. Новый тип зоны — строка в
enums.yaml, без правки кода.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ENUMS_FILE = "enums.yaml"


class EnumsError(ValueError):
    """enums.yaml не содержит того, без чего методика не работает."""


@dataclass(frozen=True)
class Enums:
    """Перечисления, которые нужны методике."""

    # Тип зоны → роль: WORK, SERVICE или SAFETY (docs/methodology.md, раздел 2).
    zone_type_role: dict[str, str]
    # Порядок стадий на фото: «раньше» и «позже» сравниваются по индексу.
    stage_labels: tuple[str, ...]
    # Все списки файла как есть — для проверки значений во входных данных.
    values: dict[str, tuple[str, ...]]

    def role(self, zone_type: str) -> str:
        """Роль типа зоны; неизвестный тип — ошибка данных, а не молчаливый ноль."""
        try:
            return self.zone_type_role[zone_type]
        except KeyError:
            raise EnumsError(f"Тип зоны {zone_type!r} не описан в zone_type_role") from None

    def stage_index(self, label: str) -> int:
        """Позиция стадии по фото в порядке строительства."""
        try:
            return self.stage_labels.index(label)
        except ValueError:
            raise EnumsError(f"Стадия {label!r} не описана в stage_label") from None


def parse_enums(raw: dict[str, Any]) -> Enums:
    """Разобранный YAML → Enums. Отдельно от чтения файла, чтобы тестировать без диска."""
    try:
        roles = {str(k): str(v) for k, v in raw["zone_type_role"].items()}
        labels = tuple(str(v) for v in raw["stage_label"])
    except (KeyError, AttributeError, TypeError) as exc:
        raise EnumsError(f"В enums.yaml нет zone_type_role или stage_label: {exc}") from exc

    values = {k: tuple(str(x) for x in v) for k, v in raw.items() if isinstance(v, list)}
    missing = set(values.get("zone_type", ())) - roles.keys()
    if missing:
        raise EnumsError(f"У типов зон нет роли в zone_type_role: {sorted(missing)}")
    return Enums(zone_type_role=roles, stage_labels=labels, values=values)


def load_enums(contracts_dir: str | Path) -> Enums:
    """Читает enums.yaml из каталога контрактов (CONTRACTS_DIR)."""
    path = Path(contracts_dir) / ENUMS_FILE
    with path.open(encoding="utf-8") as file:
        return parse_enums(yaml.safe_load(file))
