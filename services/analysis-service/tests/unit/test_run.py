"""Прогон целиком на фикстурах демо-дней — рубеж R1 (docs/board.md, T14)."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from src.core.forecast import ForecastParams
from src.core.predicates import load_rules
from src.core.rules import RuleParams
from src.core.run import RunError, analyze

from tests.factories import load_facts, load_plan, make_facts

RULES = load_rules(Path(__file__).resolve().parents[2] / "data" / "deviation_rules.yaml")
PLAN = load_plan()
PARAMS = RuleParams(transient_window_sessions=4, min_stage_conf=0.5)
FP = ForecastParams(
    min_activity=0.1,
    forecast_window_days=5,
    min_days_for_forecast=3,
    on_track_tolerance_days=2,
    confidence_high_days=5,
    confidence_high_visible=0.8,
    confidence_medium_visible=0.5,
    unknown_blind_share=0.5,
)
DAYS = ["facts_normal_day.json", "facts_day1.json", "facts_day2.json", "facts_day3.json"]


def _analyze(facts, enums, as_of=None):
    return analyze(
        PLAN, facts, rules=RULES, enums=enums, params=PARAMS, forecast_params=FP, as_of=as_of
    )


def _all_days():
    return make_facts(*(s for name in DAYS for s in load_facts(name).sessions))


def _codes(result):
    return sorted({d.finding.code for d in result.deviations})


@pytest.mark.parametrize(
    ("name", "codes"),
    [
        ("facts_normal_day.json", []),
        ("facts_day1.json", ["D2"]),
        ("facts_day2.json", ["D3"]),
        ("facts_day3.json", ["D10", "D4"]),
    ],
)
def test_демо_день_даёт_свои_отклонения(enums, name, codes):
    assert _codes(_analyze(load_facts(name), enums)) == codes


def test_день_3_склад_вне_контроля_экскаватор_простаивает_у_въезда(enums):
    result = _analyze(load_facts("facts_day3.json"), enums)

    keys = {(d.finding.code, d.finding.area, d.finding.equipment_class) for d in result.deviations}
    assert keys == {("D4", "ENTRY_GATE:Въезд", "excavator"), ("D10", "STORAGE:Склад", None)}
    assert result.counters["blind_areas"] == 1


def test_повторный_прогон_даёт_тот_же_результат(enums):
    facts = _all_days()

    assert _analyze(facts, enums) == _analyze(facts, enums)


def test_четыре_дня_подряд_история_и_открытые(enums):
    result = _analyze(_all_days(), enums)
    state = {d.finding.code: d.finding.active for d in result.deviations}

    # D2 дня 1 закрылся самосвалами дня 2, бетононасос дня 2 уехал на день 3.
    assert state == {"D2": False, "D3": False, "D4": True, "D10": True}
    assert result.counters["deviations"] == {"INFO": 1, "LOW": 1}
    assert result.stats["deviations_found"] == 4 and result.stats["deviations_active"] == 2
    assert result.as_of == datetime(2026, 10, 22, 12, tzinfo=UTC)


def test_as_of_в_прошлом_не_видит_следующих_дней(enums):
    as_of = datetime(2026, 10, 20, 12, tzinfo=UTC)

    result = _analyze(_all_days(), enums, as_of=as_of)

    assert [(d.finding.code, d.finding.active) for d in result.deviations] == [("D2", True)]
    assert result.stats["sessions_working"] == 24


def test_у_каждого_отклонения_есть_текст_факты_и_доказательства(enums):
    for deviation in _analyze(_all_days(), enums).deviations:
        assert deviation.title and deviation.message
        assert deviation.finding.facts and deviation.finding.evidence


def test_результат_содержит_факт_этапов_агрегаты_и_статус(enums):
    result = _analyze(_all_days(), enums)

    assert [s.stage_id for s in result.stage_facts] == [s.id for s in PLAN.stages]
    assert {r.stage_id for r in result.daily_activity} == {PLAN.stages[1].id}
    assert {e.equipment_class for e in result.daily_equipment} >= {"excavator", "dump_truck"}
    assert result.object_status.status in {"ON_TRACK", "DELAY", "AHEAD", "UNKNOWN"}
    assert result.counters["stages"]["total"] == 3
    assert (result.plan_version, result.zones_version) == (PLAN.plan_version, 4)


def test_один_день_наблюдений_статус_объекта_неизвестен(enums):
    assert _analyze(load_facts("facts_day1.json"), enums).object_status.status == "UNKNOWN"


def test_факты_чужого_объекта_это_ошибка(enums):
    facts = load_facts("facts_day1.json").model_copy(update={"object_id": uuid4()})

    with pytest.raises(RunError):
        _analyze(facts, enums)
