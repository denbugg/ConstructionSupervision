"""Проверка правила этапа в сессии: группы, транзитное окно, сигнатура, видимость."""

from datetime import date, time, timedelta

import pytest
from src.core.rules import RuleParams, check_rule, expected_classes

from tests.factories import (
    load_facts,
    load_plan,
    make_area,
    make_equipment,
    make_rule,
    make_session,
    make_stage,
    windows,
)

PLAN = load_plan()
PIT_STAGE = PLAN.stages[1]  # «Разработка котлована»: экскаватор ≥ 1, самосвалы ≥ 2
TRANSIENT = frozenset(c.code for c in PLAN.equipment_classes if c.transient)
PARAMS = RuleParams(transient_window_sessions=4, min_stage_conf=0.5)
PIT, GATE = "PIT:Котлован", "ENTRY_GATE:Въезд"
DAY = date(2026, 10, 20)


def _checks(sessions, enums, stage=PIT_STAGE):
    return [
        check_rule(stage, sessions, i, transient=TRANSIENT, enums=enums, params=PARAMS)
        for i in range(len(sessions))
    ]


def _pit_sessions(*per_window, first=time(6, 0), day=DAY):
    """Окна подряд; в каждом — котлован с перечисленной техникой."""
    starts = windows(day, first, len(per_window))
    return [
        make_session(at, make_area(PIT, *(make_equipment(c, n, at=at) for c, n in eq.items())))
        for at, eq in zip(starts, per_window, strict=True)
    ]


def test_нормальный_день_комплект_полон_в_каждой_сессии(enums):
    checks = _checks(load_facts("facts_normal_day.json").sessions, enums)

    assert all(c.complete for c in checks)
    # Самосвалы видны только в каждом четвёртом окне, но окно в 2 часа их удерживает.
    assert {c.observed["dump_truck"].count for c in checks} == {2}


def test_день_1_экскаватор_есть_самосвалов_нет_неполный_комплект(enums):
    checks = _checks(load_facts("facts_day1.json").sessions, enums)

    assert all(c.partial and not c.complete for c in checks)
    assert all(c.groups[1].observed == 0 for c in checks)
    assert not any(c.signature_met for c in checks)


def test_самосвал_держится_ровно_окно_из_четырёх_сессий(enums):
    sessions = _pit_sessions({"excavator": 1, "dump_truck": 2}, *[{"excavator": 1}] * 4)

    checks = _checks(sessions, enums)

    assert [c.complete for c in checks] == [True, True, True, True, False]
    # Число берётся из окна, где самосвалы были видны, — вместе с его доказательствами.
    assert checks[3].observed["dump_truck"].window_start == sessions[0].window_start
    assert len(checks[3].observed["dump_truck"].evidence) == 2


def test_окно_транзитной_техники_не_переходит_через_ночь(enums):
    evening = _pit_sessions({"excavator": 1, "dump_truck": 2}, first=time(19, 30))
    morning = _pit_sessions({"excavator": 1}, first=time(4, 0), day=DAY + timedelta(days=1))

    checks = _checks(evening + morning, enums)

    assert checks[0].complete
    assert not checks[1].complete


def test_нетранзитная_техника_учитывается_только_в_своей_сессии(enums):
    sessions = _pit_sessions({"excavator": 1, "dump_truck": 2}, {"dump_truck": 2})

    checks = _checks(sessions, enums)

    assert checks[0].complete
    assert checks[1].groups[0].observed == 0


def test_группа_любой_из_складывает_единицы_разных_классов(enums):
    rule = make_rule([(("roller", "bulldozer"), 2)])
    stage = make_stage("Дорога", DAY, DAY, rule=rule)
    sessions = _pit_sessions({"roller": 1, "bulldozer": 1}, {"roller": 1})

    checks = _checks(sessions, enums, stage)

    assert [c.complete for c in checks] == [True, False]
    assert checks[1].groups[0].observed == 1


def test_техника_на_участке_другого_типа_не_засчитывается(enums):
    at = windows(DAY, time(6), 1)[0]
    session = make_session(
        at,
        make_area(PIT),
        make_area(GATE, make_equipment("excavator", at=at), cameras_total=2),
    )

    (check,) = _checks([session], enums)

    assert check.areas == (PIT,)
    assert check.nothing_required


def test_слепой_котлован_не_оценивается(enums):
    at = windows(DAY, time(6), 1)[0]
    session = make_session(at, make_area(PIT, cameras_usable=0, reason="DARK"))

    (check,) = _checks([session], enums)

    assert not check.evaluated
    assert check.skip_reason == "BLIND"
    assert not (check.complete or check.partial or check.nothing_required)


def test_неразмеченный_участок_типа_этапа_не_оценивается(enums):
    at = windows(DAY, time(6), 1)[0]
    session = make_session(at, make_area(GATE, cameras_total=2))

    (check,) = _checks([session], enums)

    assert check.skip_reason == "NO_AREA"


def test_частично_видимый_участок_оценивается(enums):
    at = windows(DAY, time(6), 1)[0]
    pit = make_area(
        PIT,
        make_equipment("excavator", at=at),
        make_equipment("dump_truck", 2, at=at),
        cameras_total=2,
        cameras_usable=1,
        reason="DARK",
    )

    (check,) = _checks([make_session(at, pit)], enums)

    assert check.evaluated and check.complete


def test_день_3_экскаватор_у_въезда_не_портит_комплект_котлована(enums):
    checks = _checks(load_facts("facts_day3.json").sessions, enums)

    assert all(c.complete for c in checks)
    assert all(c.observed["excavator"].count == 1 for c in checks)


def test_сигнатура_по_технике_требует_всех_классов(enums):
    sessions = _pit_sessions({"excavator": 1, "dump_truck": 1}, {"excavator": 1})
    sessions += _pit_sessions({"dump_truck": 1}, first=time(10))

    checks = _checks(sessions, enums)

    # Второе окно: самосвал ещё в транзитном окне — сигнатура держится.
    assert [c.signature_met for c in checks] == [True, True, False]


@pytest.mark.parametrize(
    ("label", "conf", "met"),
    [("PIT", 0.9, False), ("FOUNDATION", 0.9, True), ("FRAME", 0.9, True), ("FRAME", 0.3, False)],
)
def test_сигнатура_по_стадии_требует_уверенной_стадии_не_раньше(enums, label, conf, met):
    rule = make_rule({"concrete_pump": 1}, signature_stage="FOUNDATION")
    stage = make_stage("Плита", DAY, DAY, rule=rule)
    at = windows(DAY, time(6), 1)[0]
    session = make_session(at, make_area(PIT), stage=(label, conf))

    (check,) = _checks([session], enums, stage)

    assert check.signature_met is met


def test_пустая_сигнатура_не_выполняется_никогда(enums):
    stage = make_stage("Без сигнатуры", DAY, DAY, rule=make_rule({"excavator": 1}))

    (check,) = _checks(_pit_sessions({"excavator": 1}), enums, stage)

    assert check.complete and not check.signature_met


def test_этап_без_правила_проверять_нельзя(enums):
    stage = make_stage("Без правила", DAY, DAY)

    with pytest.raises(ValueError):
        _checks(_pit_sessions({"excavator": 1}), enums, stage)


def test_ожидаемые_классы_этапа():
    assert expected_classes(PIT_STAGE.rule) == {"excavator", "dump_truck", "bulldozer", "loader"}
