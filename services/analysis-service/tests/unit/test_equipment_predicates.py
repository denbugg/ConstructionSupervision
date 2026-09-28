"""D3, D4, D5, D6: техника на участках (docs/methodology.md, разделы 6 и 9)."""

from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest
from src.core.context import build_context
from src.core.explain import describe
from src.core.predicates import REGISTRY, evaluate, load_rules
from src.core.rules import RuleParams

from tests.factories import (
    load_facts,
    load_plan,
    make_area,
    make_equipment,
    make_facts,
    make_plan,
    make_session,
    make_stage,
    windows,
)

RULES = {
    r.code: r
    for r in load_rules(Path(__file__).resolve().parents[2] / "data" / "deviation_rules.yaml")
}
D3_D6 = [RULES[c] for c in ("D3", "D4", "D5", "D6")]
PLAN = load_plan()
NAMES = {c.code: c.name_ru for c in PLAN.equipment_classes}
PARAMS = RuleParams(transient_window_sessions=4, min_stage_conf=0.5)
PIT_STAGE, FOUNDATION_STAGE = PLAN.stages[1], PLAN.stages[2]
PIT = "PIT:Котлован"
GATE = "ENTRY_GATE:Въезд"
FOOTPRINT = "BUILDING_FOOTPRINT:Пятно застройки"
DANGER = "DANGER:Опасная зона"
DAY = date(2026, 10, 20)  # активна только «Разработка котлована»


def _findings(facts, enums, plan=PLAN, rules=D3_D6):
    return evaluate(build_context(plan, facts, enums=enums, params=PARAMS), rules)


def _codes(findings):
    return [(f.code, f.area, f.equipment_class, f.occurrences) for f in findings]


def _series(area, cls, n, *, count=1, static=None, day=DAY, first=time(6), blind=False):
    """n подряд окон, в каждом на участке `area` стоит `cls`."""
    return [
        make_session(
            at,
            make_area(
                area,
                make_equipment(cls, count, static=static, at=at),
                cameras_usable=0 if blind else None,
            ),
        )
        for at in windows(day, first, n)
    ]


def _outside(cls, n):
    return [
        make_session(at, make_area(PIT), outside=(make_equipment(cls, at=at),))
        for at in windows(DAY, time(6), n)
    ]


def test_день_2_даёт_d3_с_ключом_будущего_этапа(enums):
    (finding,) = _findings(load_facts("facts_day2.json"), enums)

    assert finding.code == "D3"
    assert finding.stage_id == FOUNDATION_STAGE.id
    assert (finding.area, finding.equipment_class) == (PIT, "concrete_pump")
    assert finding.active and finding.occurrences == 4
    assert finding.facts["template_variant"] == "ahead"
    assert finding.facts["active_stages"] == [PIT_STAGE.name]
    assert finding.rule_ref["stage_rule_id"] == str(FOUNDATION_STAGE.rule.id)


def test_d3_дня_2_читается_как_возможное_опережение(enums):
    (finding,) = _findings(load_facts("facts_day2.json"), enums)

    deviation = describe(finding, RULES["D3"], NAMES)

    assert deviation.title == "Возможное опережение: Автобетононасос для «Фундаментная плита»"
    assert "начинается 21.11.2026" in deviation.message
    assert "(Разработка котлована)" in deviation.message


def test_день_3_даёт_d4_по_экскаватору_у_въезда(enums):
    (finding,) = _findings(load_facts("facts_day3.json"), enums)

    assert (finding.code, finding.area, finding.equipment_class) == ("D4", GATE, "excavator")
    assert finding.stage_id is None
    assert finding.occurrences == 12 and finding.severity == "LOW"
    assert "служебном участке" in finding.facts["state_reason"]


@pytest.mark.parametrize("name", ["facts_normal_day.json", "facts_day1.json"])
def test_в_нормальный_день_и_день_1_техника_на_своих_местах(enums, name):
    assert _findings(load_facts(name), enums) == []


def test_d3_без_будущего_этапа_ключ_без_этапа(enums):
    plan = make_plan(PIT_STAGE)

    (finding,) = _findings(make_facts(*_series(PIT, "concrete_pump", 2)), enums, plan)

    assert (finding.code, finding.stage_id) == ("D3", None)
    assert "template_variant" not in finding.facts
    assert describe(finding, RULES["D3"], NAMES).title == "Техника не по этапу: Автобетононасос"


def test_закрытый_отметкой_этап_не_бывает_будущим_для_d3(enums):
    """Раздел 10.3b: этап уже закрыли — насос на котловане не «опережение» по нему."""
    done = FOUNDATION_STAGE.model_copy(update={"completed_on": date(2026, 10, 19)})

    (finding,) = _findings(
        make_facts(*_series(PIT, "concrete_pump", 2)), enums, make_plan(PIT_STAGE, done)
    )

    assert (finding.code, finding.stage_id) == ("D3", None)


def test_после_отметки_техника_на_участке_этапа_не_по_его_правилу(enums):
    """Раздел 10.3b: правило закрытого этапа не участвует в D3 и D5 — экскаватор уже не нужен."""
    done = PIT_STAGE.model_copy(update={"completed_on": date(2026, 10, 19)})
    # Параллельно идёт этап на другом участке: без единого активного этапа статус — UNKNOWN.
    frame = make_stage(
        "Каркас", date(2026, 10, 1), date(2026, 10, 31), seq=3, zone_type="BUILDING_FOOTPRINT"
    )

    (finding,) = _findings(
        make_facts(*_series(PIT, "excavator", 2, static=0)), enums, make_plan(done, frame)
    )

    assert (finding.code, finding.area, finding.equipment_class) == ("D5", PIT, "excavator")
    assert finding.facts["active_stages"] == ["Каркас"]


def test_одна_сессия_с_чужой_техникой_это_ещё_не_d3(enums):
    assert _findings(make_facts(*_series(PIT, "concrete_pump", 1)), enums) == []


def test_допустимая_техника_не_даёт_d3(enums):
    assert _findings(make_facts(*_series(PIT, "bulldozer", 4, static=0)), enums) == []


def test_транзитный_класс_даёт_d3(enums):
    (finding,) = _findings(make_facts(*_series(PIT, "concrete_mixer", 2)), enums)

    assert (finding.code, finding.stage_id) == ("D3", FOUNDATION_STAGE.id)


def test_этап_без_правила_d3_не_даёт(enums):
    plan = make_plan(PIT_STAGE.model_copy(update={"rule": None}))

    assert _findings(make_facts(*_series(PIT, "concrete_pump", 3)), enums, plan) == []


def test_человек_на_рабочем_участке_не_техника_не_по_этапу(enums):
    assert _findings(make_facts(*_series(PIT, "person", 3, count=2)), enums) == []


def test_рабочий_участок_без_активного_этапа_это_d5_а_не_d3(enums):
    (finding,) = _findings(make_facts(*_series(FOOTPRINT, "excavator", 2, static=0)), enums)

    assert (finding.code, finding.area, finding.equipment_class) == ("D5", FOOTPRINT, "excavator")
    assert finding.facts["active_stages"] == [PIT_STAGE.name]
    assert "нет активного этапа этого типа" in finding.facts["state_reason"]


def test_одна_сессия_не_в_той_зоне_это_ещё_не_d5(enums):
    assert _findings(make_facts(*_series(FOOTPRINT, "excavator", 1)), enums) == []


@pytest.mark.parametrize(("n", "expected"), [(2, []), (3, [("D4", GATE, "excavator", 3)])])
def test_d4_после_трёх_сессий_простоя(enums, n, expected):
    assert _codes(_findings(make_facts(*_series(GATE, "excavator", n)), enums)) == expected


def test_d4_повышается_до_medium_если_держится_рабочий_день(enums):
    sessions = _series(GATE, "excavator", 2) + _series(GATE, "excavator", 1, day=date(2026, 10, 21))

    (finding,) = _findings(make_facts(*sessions), enums)

    assert finding.facts["held_working_days"] == 1
    assert finding.severity == "MEDIUM"


def test_неподвижный_экскаватор_в_котловане_простаивает(enums):
    (finding,) = _findings(make_facts(*_series(PIT, "excavator", 3, static=1)), enums)

    assert (finding.code, finding.area) == ("D4", PIT)
    assert finding.facts["static"] == 1


def test_без_сравнения_с_прошлой_сессией_экскаватор_в_котловане_работает(enums):
    assert _findings(make_facts(*_series(PIT, "excavator", 4)), enums) == []


def test_d4_вне_всех_зон(enums):
    (finding,) = _findings(make_facts(*_outside("excavator", 3)), enums)

    assert (finding.code, finding.area) == ("D4", "OUTSIDE")
    assert finding.facts["area_name"] == "вне размеченных зон"


@pytest.mark.parametrize(
    "sessions",
    [
        _series(GATE, "dump_truck", 6),
        _series(FOOTPRINT, "concrete_mixer", 4),
        _outside("truck", 4),
    ],
    ids=["въезд", "чужой_рабочий_участок", "вне_зон"],
)
def test_транзитные_классы_не_дают_d4_и_d5(enums, sessions):
    assert _findings(make_facts(*sessions), enums) == []


def test_слепая_сессия_серию_d4_не_рвёт_и_в_неё_не_входит(enums):
    sessions = (
        _series(GATE, "excavator", 2)
        + _series(GATE, "excavator", 1, first=time(7), blind=True)
        + _series(GATE, "excavator", 1, first=time(7, 30))
    )

    assert _codes(_findings(make_facts(*sessions), enums)) == [("D4", GATE, "excavator", 3)]


def test_d6_с_первой_же_сессии_и_для_человека(enums):
    (finding,) = _findings(make_facts(*_series(DANGER, "person", 1, count=2)), enums)

    assert (finding.code, finding.area, finding.equipment_class) == ("D6", DANGER, "person")
    assert finding.severity == "HIGH"
    assert describe(finding, RULES["D6"], NAMES).message == (
        "В опасной зоне «Опасная зона» замечено: Человек, 2 ед. Рабочих сессий подряд: 1."
    )


def test_d6_для_транзитной_техники(enums):
    (finding,) = _findings(make_facts(*_series(DANGER, "dump_truck", 1)), enums)

    assert finding.code == "D6"


@pytest.mark.parametrize(
    ("area", "cls"),
    [(PIT, "concrete_pump"), (GATE, "excavator"), (FOOTPRINT, "excavator"), (DANGER, "person")],
)
def test_по_слепому_участку_ничего(enums, area, cls):
    assert _findings(make_facts(*_series(area, cls, 4, blind=True)), enums) == []


@pytest.mark.parametrize(
    ("area", "cls"),
    [(PIT, "concrete_pump"), (GATE, "excavator"), (FOOTPRINT, "excavator"), (DANGER, "person")],
)
def test_вне_рабочего_времени_ничего(enums, area, cls):
    # 21:00 UTC — полночь по Москве; 25.10 — воскресенье.
    night = _series(area, cls, 4, first=time(21))
    sunday = _series(area, cls, 4, day=date(2026, 10, 25))

    assert _findings(make_facts(*night, *sunday), enums) == []


def test_без_активных_этапов_статуса_нет_и_d4_d5_нет(enums):
    # 15.01.2027 — после всех этапов плана.
    sessions = _series(GATE, "excavator", 3, day=date(2027, 1, 15))

    assert _findings(make_facts(*sessions), enums) == []


def test_каждая_находка_с_фактами_доказательствами_и_текстом(enums):
    at = datetime(2026, 10, 20, 6, tzinfo=UTC)
    sessions = [
        make_session(
            t,
            make_area(PIT, make_equipment("concrete_pump", at=t)),
            make_area(GATE, make_equipment("excavator", at=t)),
            make_area(FOOTPRINT, make_equipment("loader", at=t)),
            make_area(DANGER, make_equipment("person", at=t)),
        )
        for t in windows(at.date(), at.time(), 3)
    ]

    findings = _findings(make_facts(*sessions), enums)

    assert {f.code for f in findings} == {"D3", "D4", "D5", "D6"}
    for finding in findings:
        assert finding.facts and finding.evidence
        assert describe(finding, RULES[finding.code], NAMES).message


def test_предикаты_d3_d6_зарегистрированы():
    assert {r.predicate for r in D3_D6} <= set(REGISTRY)
