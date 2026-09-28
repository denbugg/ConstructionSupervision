"""Реестр предикатов, D1 и D2, инварианты ленты (docs/methodology.md, раздел 9)."""

from dataclasses import replace
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest
from src.core.context import build_context
from src.core.predicates import REGISTRY, PredicateError, evaluate, load_rules
from src.core.rules import RuleParams

from tests.factories import (
    load_facts,
    load_plan,
    make_area,
    make_equipment,
    make_facts,
    make_session,
    windows,
)

RULES = load_rules(Path(__file__).resolve().parents[2] / "data" / "deviation_rules.yaml")
D1_D2 = [r for r in RULES if r.code in ("D1", "D2")]
PLAN = load_plan()
PARAMS = RuleParams(transient_window_sessions=4, min_stage_conf=0.5)
PIT = "PIT:Котлован"
DAY = date(2026, 10, 20)


def _findings(facts, enums, rules=D1_D2):
    return evaluate(build_context(PLAN, facts, enums=enums, params=PARAMS), rules)


def _empty(at):
    return make_session(at, make_area(PIT))


def _full(at):
    return make_session(
        at,
        make_area(PIT, make_equipment("excavator", at=at), make_equipment("dump_truck", 2, at=at)),
    )


def _partial(at):
    return make_session(at, make_area(PIT, make_equipment("excavator", at=at)))


def _blind(at):
    return make_session(at, make_area(PIT, cameras_usable=0, reason="DARK"))


def _day_sessions(builders, day=DAY, first=time(6)):
    return [
        build(at) for build, at in zip(builders, windows(day, first, len(builders)), strict=True)
    ]


def test_день_1_даёт_один_d2_по_котловану(enums):
    (finding,) = _findings(load_facts("facts_day1.json"), enums)

    assert finding.code == "D2"
    assert finding.stage_id == PLAN.stages[1].id
    assert finding.area == PIT
    assert finding.active and finding.occurrences == 12
    assert finding.severity == "MEDIUM"
    assert finding.facts["observed"] == {"excavator": 1, "dump_truck": 0}
    assert finding.facts["groups_failed"] == [{"any_of": ["dump_truck"], "min": 2, "observed": 0}]
    assert finding.rule_ref["stage_rule_version"] == 2


@pytest.mark.parametrize("name", ["facts_normal_day.json", "facts_day2.json", "facts_day3.json"])
def test_в_остальные_дни_комплект_полон_d1_и_d2_нет(enums, name):
    assert _findings(load_facts(name), enums) == []


def test_d1_срабатывает_после_min_sessions_пустых_сессий(enums):
    (finding,) = _findings(make_facts(*_day_sessions([_empty, _empty])), enums)

    assert finding.code == "D1"
    assert finding.facts["observed"] == {"excavator": 0, "dump_truck": 0}
    # Рамок нет — доказательство сам снимок пустого участка.
    assert finding.evidence[0]["detection_ids"] == []


def test_d1_после_дня_отметки_выполнен_не_ищется(enums):
    """Раздел 10.3b: экскаватор уехал после приёмки котлована — это не «нет техники»."""
    pit = PLAN.stages[1].model_copy(update={"completed_on": DAY})
    plan = PLAN.model_copy(update={"stages": (PLAN.stages[0], pit, PLAN.stages[2])})
    sessions = _day_sessions([_empty, _empty]) + _day_sessions(
        [_empty, _empty], day=date(2026, 10, 21)
    )

    ctx = build_context(plan, make_facts(*sessions), enums=enums, params=PARAMS)
    (finding,) = evaluate(ctx, D1_D2)

    # В день отметки работы ещё идут: D1 за 20.10 остаётся, но на 21.10 уже закрыт.
    assert (finding.code, finding.occurrences, finding.active) == ("D1", 2, False)


def test_одна_пустая_сессия_это_ещё_не_d1(enums):
    assert _findings(make_facts(*_day_sessions([_empty, _full])), enums) == []


def test_без_снимков_d1_не_создаётся(enums):
    sessions = [s.model_copy(update={"cameras": ()}) for s in _day_sessions([_empty, _empty])]

    assert _findings(make_facts(*sessions), enums) == []


def test_по_слепому_участку_d1_и_d2_нет(enums):
    assert _findings(make_facts(*_day_sessions([_blind] * 4)), enums) == []


def test_слепая_сессия_серию_не_рвёт_и_в_неё_не_входит(enums):
    (finding,) = _findings(make_facts(*_day_sessions([_empty, _blind, _empty])), enums)

    assert finding.occurrences == 2


def test_появившаяся_техника_рвёт_серию_и_закрывает_отклонение(enums):
    sessions = _day_sessions([_empty, _empty, _partial, _empty, _empty])

    findings = _findings(make_facts(*sessions), enums)

    # Одиночная сессия с экскаватором короче min_sessions — D2 из неё не вырастает.
    assert [(f.code, f.active) for f in findings] == [("D1", False), ("D1", True)]
    assert findings[0].key == findings[1].key


def test_самосвалы_в_транзитном_окне_превращают_пустой_котлован_в_d2(enums):
    # После заезда самосвалов 2 часа котлован без экскаватора — неполный комплект, а не D1.
    findings = _findings(make_facts(*_day_sessions([_full, _empty, _empty])), enums)

    assert [(f.code, f.occurrences) for f in findings] == [("D2", 2)]


def test_вне_рабочего_времени_отклонений_нет(enums):
    # 21:00 UTC — полночь по Москве; 25.10 — воскресенье.
    night = _day_sessions([_empty] * 4, first=time(21))
    sunday = _day_sessions([_empty] * 4, day=date(2026, 10, 25))

    assert _findings(make_facts(*night, *sunday), enums) == []


def test_вне_дат_этапа_отклонений_нет(enums):
    after_plan = _day_sessions([_empty] * 3, day=date(2027, 1, 15))

    assert _findings(make_facts(*after_plan), enums) == []


def test_без_размеченного_участка_типа_этапа_d1_нет(enums):
    # 01.10 активна «Подготовка территории» (пятно застройки), а размечен только котлован.
    sessions = _day_sessions([_empty] * 3, day=date(2026, 10, 1))

    assert _findings(make_facts(*sessions), enums) == []


def test_d1_повышается_до_high_если_держится_рабочий_день(enums):
    sessions = [_empty(datetime(2026, 10, d, 6, tzinfo=UTC)) for d in (20, 21)]

    (finding,) = _findings(make_facts(*sessions), enums)

    assert finding.facts["held_working_days"] == 1
    assert finding.severity == "HIGH"


@pytest.mark.parametrize(
    ("days", "severity"), [((20, 21, 22), "MEDIUM"), ((20, 21, 22, 23), "HIGH")]
)
def test_d2_повышается_после_трёх_рабочих_дней(enums, days, severity):
    sessions = [_partial(datetime(2026, 10, d, 6, tzinfo=UTC)) for d in days]

    (finding,) = _findings(make_facts(*sessions), enums)

    assert finding.severity == severity


def test_у_каждой_находки_есть_факты_и_доказательства(enums):
    facts = make_facts(*_day_sessions([_empty, _empty, _partial, _partial, _full]))

    findings = _findings(facts, enums)

    assert {f.code for f in findings} == {"D1", "D2"}
    assert all(f.facts and f.evidence for f in findings)


def test_выключенное_правило_не_проверяется(enums):
    rules = [replace(r, enabled=False) for r in D1_D2]

    assert _findings(load_facts("facts_day1.json"), enums, rules) == []


def test_незарегистрированный_предикат_это_ошибка_настройки(enums):
    rules = [replace(D1_D2[0], predicate="no_such_predicate")]

    with pytest.raises(PredicateError):
        _findings(load_facts("facts_day1.json"), enums, rules)


def test_справочник_правил_покрывает_все_коды(enums):
    assert [r.code for r in RULES] == list(enums.values["deviation_code"])
    assert {r.severity for r in RULES} <= set(enums.values["severity"])
    assert {r.params.get("escalate_to") for r in RULES} - {None} <= set(enums.values["severity"])


def test_предикаты_d1_и_d2_зарегистрированы():
    assert {r.predicate for r in D1_D2} <= set(REGISTRY)
