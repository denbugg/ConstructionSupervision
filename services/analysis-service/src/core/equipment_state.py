"""Статусы техники: работает / простой / вне зоны (F4, docs/methodology.md, раздел 6).

Базовое правило заказчика: на статичном снимке техника работает, если она в рабочей
зоне, где по плану сейчас идут работы. Неподвижность между сессиями только уточняет
его. Транзитная техника по месту не простаивает: движение для неё норма. Техника,
работающая стоя (`works_in_place`), на рабочем участке с активным этапом не простаивает
из-за неподвижности. Класс
`person` статуса не получает, опасная зона проверяется отдельно (D6).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from src.core.enums import Enums
from src.core.inputs import EquipmentFact, Evidence, SessionFact, Stage

WORKING = "WORKING"
IDLE = "IDLE"
OUT_OF_ZONE = "OUT_OF_ZONE"
UNKNOWN = "UNKNOWN"

OUTSIDE = "OUTSIDE"
BLIND = "BLIND"
PERSON = "person"
ROLE_WORK, ROLE_SERVICE, ROLE_SAFETY = "WORK", "SERVICE", "SAFETY"


@dataclass(frozen=True)
class EquipmentStatus:
    """Статус пары «участок × класс» в сессии с обоснованием для `facts`."""

    area: str
    equipment_class: str
    state: str
    reason: str
    count: int
    static: int | None
    evidence: tuple[Evidence, ...]


def _state(
    role: str | None, stage_here: bool, transient: bool, in_place: bool, item: EquipmentFact
) -> tuple[str, str]:
    """Строка таблицы раздела 6: (статус, почему). role=None — вне всех зон."""
    if transient:
        return WORKING, "транзитная техника: заезд, выезд и погрузка — норма"
    if role == ROLE_SERVICE:
        return IDLE, "стоит на служебном участке, а не на рабочем"
    if role is None:
        return OUT_OF_ZONE, "за пределами участков работ этапа не ведутся"
    if not stage_here:
        return OUT_OF_ZONE, "на рабочем участке, где по плану нет активного этапа этого типа"
    if in_place:
        return WORKING, "на участке идёт этап; работает стоя, неподвижность — норма"
    if item.static is not None and item.static == item.count:
        return IDLE, f"на участке идёт этап, но {item.static} из {item.count} не сдвинулись"
    if item.static is None:
        return WORKING, "на участке идёт этап; сравнить с прошлой сессией не с чем"
    return WORKING, f"на участке идёт этап; сдвинулись {item.count - item.static} из {item.count}"


def equipment_states(
    session: SessionFact,
    active: Sequence[Stage],
    *,
    transient: frozenset[str],
    enums: Enums,
    class_names: dict[str, str],
    works_in_place: frozenset[str] = frozenset(),
) -> tuple[EquipmentStatus, ...]:
    """Статусы всей техники сессии; `active` — этапы, активные на местную дату сессии.

    Невидимые участки пропускаются: детекций там нет, и «не видно» — не «стоит».
    """
    active_types = {s.zone_type for s in active}
    placed = [
        (area.area, area.name, enums.role(area.zone_type), area.zone_type, item)
        for area in session.areas
        if area.visibility.status != BLIND
        for item in area.equipment
    ]
    placed += [(OUTSIDE, None, None, None, item) for item in session.outside_zones]

    statuses = []
    for area, name, role, zone_type, item in placed:
        cls = item.equipment_class
        if cls == PERSON or role == ROLE_SAFETY:
            continue
        where = f"на участке «{name}»" if name else "вне размеченных зон"
        label = class_names.get(cls, cls)
        if not active_types:
            state, why = UNKNOWN, "на дату нет ни одного активного этапа"
        else:
            state, why = _state(
                role, zone_type in active_types, cls in transient, cls in works_in_place, item
            )
        statuses.append(
            EquipmentStatus(
                area=area,
                equipment_class=cls,
                state=state,
                reason=f"{label} {where}: {why}",
                count=item.count,
                static=item.static,
                evidence=item.evidence,
            )
        )
    return tuple(statuses)
