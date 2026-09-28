"""Статус техники по таблице docs/methodology.md, раздел 6: строка за строкой."""

from datetime import UTC, date, datetime

import pytest
from src.core.equipment_state import equipment_states
from src.core.plan_on_date import active_stages

from tests.factories import load_facts, load_plan, make_area, make_equipment, make_session

PLAN = load_plan()
TRANSIENT = frozenset(c.code for c in PLAN.equipment_classes if c.transient)
IN_PLACE = frozenset(c.code for c in PLAN.equipment_classes if c.works_in_place)
NAMES = {c.code: c.name_ru for c in PLAN.equipment_classes}
AT = datetime(2026, 10, 20, 6, 0, tzinfo=UTC)
ACTIVE = active_stages(PLAN, date(2026, 10, 20))  # котлован: этап типа PIT
AREAS = {
    "PIT": "PIT:Котлован",
    "FOOTPRINT": "BUILDING_FOOTPRINT:Пятно застройки",
    "GATE": "ENTRY_GATE:Въезд",
    "DANGER": "DANGER:Опасная зона",
}


def _states(session, enums, active=ACTIVE):
    return equipment_states(
        session,
        active,
        transient=TRANSIENT,
        enums=enums,
        class_names=NAMES,
        works_in_place=IN_PLACE,
    )


def _one(where, cls, enums, *, count=1, static=None, active=ACTIVE):
    item = make_equipment(cls, count, static=static, at=AT)
    if where == "OUTSIDE":
        session = make_session(AT, outside=(item,))
    else:
        session = make_session(AT, make_area(AREAS[where], item))
    (status,) = _states(session, enums, active)
    return status


@pytest.mark.parametrize(
    ("where", "cls", "count", "static", "state"),
    [
        # Рабочий участок, где активен этап его типа.
        ("PIT", "excavator", 1, 0, "WORKING"),
        ("PIT", "excavator", 1, None, "WORKING"),
        ("PIT", "excavator", 2, 1, "WORKING"),
        ("PIT", "excavator", 1, 1, "IDLE"),
        ("PIT", "dump_truck", 2, 2, "WORKING"),
        ("PIT", "concrete_pump", 1, 1, "WORKING"),  # работает стоя
        # Рабочий участок без активного этапа его типа.
        ("FOOTPRINT", "excavator", 1, 0, "OUT_OF_ZONE"),
        ("FOOTPRINT", "dump_truck", 1, 1, "WORKING"),
        ("FOOTPRINT", "concrete_pump", 1, 1, "OUT_OF_ZONE"),
        # Служебный участок.
        ("GATE", "excavator", 1, 0, "IDLE"),
        ("GATE", "dump_truck", 1, 1, "WORKING"),
        ("GATE", "concrete_pump", 1, 1, "IDLE"),
        # Вне всех зон.
        ("OUTSIDE", "excavator", 1, None, "OUT_OF_ZONE"),
        ("OUTSIDE", "dump_truck", 1, None, "WORKING"),
        ("OUTSIDE", "concrete_pump", 1, None, "OUT_OF_ZONE"),
    ],
)
def test_строка_таблицы_статусов(enums, where, cls, count, static, state):
    assert _one(where, cls, enums, count=count, static=static).state == state


@pytest.mark.parametrize("cls", ["excavator", "dump_truck"])
def test_без_активных_этапов_статус_неизвестен(enums, cls):
    assert _one("PIT", cls, enums, active=()).state == "UNKNOWN"


def test_человек_статуса_не_получает(enums):
    session = make_session(AT, make_area(AREAS["PIT"], make_equipment("person", 3, at=AT)))

    assert _states(session, enums) == ()


def test_опасная_зона_не_даёт_статуса_её_проверяет_d6(enums):
    session = make_session(AT, make_area(AREAS["DANGER"], make_equipment("excavator", at=AT)))

    assert _states(session, enums) == ()


def test_слепой_участок_пропускается(enums):
    blind = make_area(AREAS["PIT"], make_equipment("excavator", at=AT), cameras_usable=0)

    assert _states(make_session(AT, blind), enums) == ()


def test_обоснование_называет_технику_участок_и_числа(enums):
    status = _one("PIT", "excavator", enums, count=2, static=2)

    assert status.reason.startswith("Экскаватор на участке «Котлован»")
    assert "2 из 2 не сдвинулись" in status.reason
    assert status.evidence and status.count == 2


def test_работающий_стоя_объясняет_почему_неподвижность_не_простой(enums):
    status = _one("PIT", "tower_crane", enums, count=1, static=1)

    assert status.state == "WORKING"
    assert "работает стоя" in status.reason


def test_день_3_экскаватор_у_въезда_простаивает_а_в_котловане_работает(enums):
    for session in load_facts("facts_day3.json").sessions:
        states = {(s.area, s.equipment_class): s.state for s in _states(session, enums)}

        assert states[(AREAS["GATE"], "excavator")] == "IDLE"
        assert states[(AREAS["PIT"], "excavator")] == "WORKING"
