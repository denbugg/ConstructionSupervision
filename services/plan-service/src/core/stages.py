"""Правка этапа: какие значения этап может принять (docs/data-model.md, раздел 1.4).

Даты этапа — обе включительно, поэтому этап в один день допустим, а конец раньше начала — нет.
Работы этапа идут на рабочем участке: въезд, склад и опасная зона этапом не бывают, иначе
правило этапа искало бы технику там, где она только ждёт. Отметка «этап выполнен» — дата,
автор и комментарий вместе: без автора и даты комментарий ничего не объясняет.
"""

from collections.abc import Mapping
from datetime import date
from typing import Any

# Роль типа зоны, на которой идут работы этапов (enums.yaml: zone_type_role).
WORK_ROLE = "WORK"
COMPLETION_FIELDS = ("completed_on", "completion_note")


class StageError(ValueError):
    """Этап в таком виде не имеет смысла и не сохраняется."""


class StageDatesError(StageError):
    """Плановый конец раньше планового начала."""


class StageZoneError(StageError):
    """Тип участка этапа — не рабочий."""


class StageCompletionError(StageError):
    """Комментарий к отметке «выполнен» без самой отметки."""


def work_zone_types(zone_roles: Mapping[str, str]) -> tuple[str, ...]:
    """Типы зон с ролью WORK — в порядке enums.yaml."""
    return tuple(zone for zone, role in zone_roles.items() if role == WORK_ROLE)


def check_stage(
    plan_start: date, plan_end: date, zone_type: str, zone_roles: Mapping[str, str]
) -> None:
    """Проверка этапа после правки: даты и тип участка."""
    if plan_end < plan_start:
        raise StageDatesError(
            f"Плановое окончание {plan_end.isoformat()} раньше начала {plan_start.isoformat()}"
        )
    if zone_roles.get(zone_type) != WORK_ROLE:
        raise StageZoneError(
            f"На участке типа {zone_type} работы этапов не идут; "
            f"допустимо: {list(work_zone_types(zone_roles))}"
        )


def completion_changes(
    requested: Mapping[str, Any], current_on: date | None, actor: str | None
) -> dict[str, Any]:
    """Поля отметки «этап выполнен» после правки (ADR-0015).

    `requested` — поля отметки из запроса (`completed_on`, `completion_note`), только
    переданные. Новая дата — автор из `X-Actor`; `completed_on: null` снимает отметку вместе с
    автором и комментарием. Комментарий объясняет отметку, поэтому без даты не сохраняется.
    """
    if "completed_on" in requested and requested["completed_on"] is None:
        return {"completed_on": None, "completed_by": None, "completion_note": None}
    changes: dict[str, Any] = {}
    completed_on = requested.get("completed_on", current_on)
    if "completed_on" in requested:
        changes |= {"completed_on": completed_on, "completed_by": actor}
    if "completion_note" in requested:
        note = (requested["completion_note"] or "").strip() or None
        if note is not None and completed_on is None:
            raise StageCompletionError("Комментарий к отметке без даты выполнения этапа")
        changes["completion_note"] = note
    return changes
