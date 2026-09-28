"""D7–D10 и инварианты ленты по всем предикатам (docs/methodology.md, разделы 7–9, 12)."""

from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest
from src.core.context import build_context
from src.core.explain import describe
from src.core.inputs import CameraState
from src.core.predicates import REGISTRY, evaluate, load_rules
from src.core.rules import RuleParams

from tests.factories import (
    load_facts,
    load_plan,
    make_area,
    make_camera,
    make_equipment,
    make_facts,
    make_plan,
    make_session,
    windows,
)

RULES = {
    r.code: r
    for r in load_rules(Path(__file__).resolve().parents[2] / "data" / "deviation_rules.yaml")
}
PLAN = load_plan()
NAMES = {c.code: c.name_ru for c in PLAN.equipment_classes}
PARAMS = RuleParams(transient_window_sessions=4, min_stage_conf=0.5)
PREPARATION, PIT_STAGE = PLAN.stages[0], PLAN.stages[1]
PIT = "PIT:Котлован"
STORAGE = "STORAGE:Склад"
GATE = "ENTRY_GATE:Въезд"


def _findings(facts, enums, codes, plan=PLAN, as_of=None):
    ctx = build_context(plan, facts, enums=enums, params=PARAMS, as_of=as_of)
    return evaluate(ctx, [RULES[c] for c in codes])


def _full(at):
    return make_session(
        at,
        make_area(
            PIT,
            make_equipment("excavator", static=0, at=at),
            make_equipment("dump_truck", 2, at=at),
        ),
    )


def _excavator(at):
    return make_session(at, make_area(PIT, make_equipment("excavator", static=0, at=at)))


def _blind(at):
    return make_session(at, make_area(PIT, cameras_usable=0, reason="DARK"))


def _sessions(builder, day, n, first=time(6)):
    return [builder(at) for at in windows(day, first, n)]


# --- D7: стадия по фото не совпадает с планом ---------------------------------------------


def _photo(label, conf=0.8, day=date(2026, 10, 20), n=2, first=time(6)):
    """Сессии с котлованом, где классификатор видит стадию `label`."""
    return [make_session(at, make_area(PIT), stage=(label, conf)) for at in windows(day, first, n)]


def test_d7_опережение_когда_на_фото_фундамент_а_по_плану_котлован(enums):
    (finding,) = _findings(make_facts(*_photo("FOUNDATION")), enums, ["D7"])

    assert (finding.code, finding.stage_id, finding.area) == ("D7", PIT_STAGE.id, None)
    assert finding.facts["direction"] == "AHEAD" and finding.facts["stages_apart"] == 2
    assert finding.severity == "HIGH" and finding.evidence
    assert describe(finding, RULES["D7"], NAMES).title == (
        "Стадия по фото опережает план: «Разработка котлована»"
    )


def test_d7_отставание_когда_по_плану_уже_фундамент(enums):
    # 25.11 активна «Фундаментная плита» с плановой стадией FOUNDATION.
    (finding,) = _findings(make_facts(*_photo("PIT", day=date(2026, 11, 25))), enums, ["D7"])

    assert finding.stage_id == PLAN.stages[2].id
    assert finding.facts["direction"] == "BEHIND"
    deviation = describe(finding, RULES["D7"], NAMES)
    assert deviation.title == "Стадия по фото отстаёт от плана: «Фундаментная плита»"
    assert "объект на фото — котлован (уверенность 0.8)" in deviation.message
    assert "уже должен быть фундамент" in deviation.message


def test_одна_сессия_с_чужой_стадией_это_ещё_не_d7(enums):
    sessions = _photo("FOUNDATION", n=1) + _photo("PIT", n=2, first=time(7))

    assert _findings(make_facts(*sessions), enums, ["D7"]) == []


def test_неуверенная_стадия_серию_d7_не_рвёт_и_в_неё_не_входит(enums):
    at = windows(date(2026, 10, 20), time(6), 3)
    sessions = [
        make_session(at[0], make_area(PIT), stage=("FOUNDATION", 0.8)),
        make_session(at[1], make_area(PIT), stage=("FOUNDATION", 0.3)),
        make_session(at[2], make_area(PIT), stage=("FOUNDATION", 0.8)),
    ]

    (finding,) = _findings(make_facts(*sessions), enums, ["D7"])

    assert finding.occurrences == 2


@pytest.mark.parametrize("name", ["facts_normal_day.json", "facts_day1.json", "facts_day3.json"])
def test_в_демо_дни_стадия_совпадает_с_планом(enums, name):
    assert _findings(load_facts(name), enums, ["D7"]) == []


def test_без_этапа_с_плановой_стадией_d7_нет(enums):
    # 01.10 активна только «Подготовка территории», visual_stage у неё не задан.
    assert _findings(make_facts(*_photo("FRAME", day=date(2026, 10, 1))), enums, ["D7"]) == []


# --- D8: этап затянулся -------------------------------------------------------------------

OVERRUN_PLAN = make_plan(PIT_STAGE.model_copy(update={"plan_end": date(2026, 10, 16)}))


def test_d8_когда_сигнатура_держится_после_plan_end(enums):
    (finding,) = _findings(load_facts("facts_normal_day.json"), enums, ["D8"], OVERRUN_PLAN)

    assert (finding.code, finding.stage_id, finding.area) == ("D8", PIT_STAGE.id, PIT)
    assert finding.occurrences == 12 and finding.severity == "HIGH"
    # 17 и 19 октября; 18-е — воскресенье.
    assert finding.facts["days_after_plan_end"] == 2
    assert finding.facts["signature_observed"] == {"excavator": 1, "dump_truck": 2}


def test_d8_читается_с_числами(enums):
    (finding,) = _findings(load_facts("facts_normal_day.json"), enums, ["D8"], OVERRUN_PLAN)

    message = describe(finding, RULES["D8"], NAMES).message

    assert "закончился 16.10.2026" in message
    assert "экскаватор — 1, самосвал — 2" in message
    assert "2 рабочих дней после плановой даты" in message


def test_одна_сессия_после_plan_end_это_ещё_не_d8(enums):
    later = _sessions(_excavator, date(2026, 10, 19), 3, first=time(9))
    sessions = [_full(datetime(2026, 10, 19, 6, tzinfo=UTC)), *later]

    assert _findings(make_facts(*sessions), enums, ["D8"], OVERRUN_PLAN) == []


def test_в_плановые_даты_d8_нет(enums):
    assert _findings(load_facts("facts_normal_day.json"), enums, ["D8"]) == []


def test_этап_без_правила_d8_не_даёт(enums):
    plan = make_plan(OVERRUN_PLAN.stages[0].model_copy(update={"rule": None}))

    assert _findings(load_facts("facts_normal_day.json"), enums, ["D8"], plan) == []


def test_после_отметки_выполнен_d8_нет(enums):
    """Раздел 10.3b: этап закрыли в плановый срок — техника после него этап не затягивает."""
    marked = OVERRUN_PLAN.stages[0].model_copy(update={"completed_on": date(2026, 10, 16)})

    assert _findings(load_facts("facts_normal_day.json"), enums, ["D8"], make_plan(marked)) == []


# --- D9: не начат в срок ------------------------------------------------------------------

# Котлован начинается 15.10; первые три рабочих дня — 15, 16 и 17 октября.
FIRST_DAYS = [date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 17)]
AFTER = datetime(2026, 10, 19, 12, tzinfo=UTC)


def _first_days(builder, n=2):
    return [s for day in FIRST_DAYS for s in _sessions(builder, day, n)]


def test_d9_если_за_k_дней_старта_нет(enums):
    (finding,) = _findings(make_facts(*_first_days(_excavator)), enums, ["D9"], as_of=AFTER)

    assert (finding.code, finding.stage_id, finding.area) == ("D9", PIT_STAGE.id, PIT)
    assert finding.active and finding.severity == "HIGH"
    assert finding.facts["deadline"] == "2026-10-17"
    assert (finding.facts["sessions_visible"], finding.facts["sessions_total"]) == (6, 6)
    assert finding.facts["actual_start"] is None
    assert finding.evidence


def test_d9_читается_с_признаком_и_видимостью(enums):
    (finding,) = _findings(make_facts(*_first_days(_excavator)), enums, ["D9"], as_of=AFTER)

    message = describe(finding, RULES["D9"], NAMES).message

    assert "по 17.10.2026" in message
    assert "(экскаватор, самосвал)" in message
    assert "в 6 из 6 рабочих сессий" in message


def test_пока_k_дней_не_прошли_d9_нет(enums):
    as_of = datetime(2026, 10, 17, 19, tzinfo=UTC)

    assert _findings(make_facts(*_first_days(_excavator)), enums, ["D9"], as_of=as_of) == []


def test_старт_в_первые_дни_снимает_d9(enums):
    sessions = _sessions(_excavator, FIRST_DAYS[0], 2) + _sessions(_full, FIRST_DAYS[1], 2)

    assert _findings(make_facts(*sessions), enums, ["D9"], as_of=AFTER) == []


def test_поздний_старт_закрывает_d9(enums):
    late = _sessions(_full, date(2026, 10, 19), 2)

    (finding,) = _findings(make_facts(*_first_days(_excavator), *late), enums, ["D9"])

    assert not finding.active
    assert finding.last_seen_at == late[0].window_start
    assert finding.facts["actual_start"] == "2026-10-19"
    assert finding.facts["start_deviation_days"] == 3


def test_участок_виден_меньше_половины_сессий_d9_нет(enums):
    sessions = [s for day in FIRST_DAYS for s in [_excavator(windows(day, time(6), 1)[0])]]
    sessions += [s for day in FIRST_DAYS for s in _sessions(_blind, day, 2, first=time(7))]

    assert _findings(make_facts(*sessions), enums, ["D9"], as_of=AFTER) == []


def test_без_наблюдений_в_первые_дни_d9_нет(enums):
    later = _sessions(_excavator, date(2026, 10, 20), 3)

    assert _findings(make_facts(*later), enums, ["D9"]) == []


def _marked_pit(day):
    return make_plan(PIT_STAGE.model_copy(update={"completed_on": day}))


def test_отмеченный_до_срока_старта_этап_d9_не_даёт(enums):
    facts = make_facts(*_first_days(_excavator))

    assert _findings(facts, enums, ["D9"], _marked_pit(FIRST_DAYS[1]), as_of=AFTER) == []


def test_отметка_после_срока_закрывает_d9_последней_сессией_дня_отметки(enums):
    marked_day = date(2026, 10, 19)
    later = _sessions(_excavator, marked_day, 2) + _sessions(_excavator, date(2026, 10, 20), 2)

    (finding,) = _findings(
        make_facts(*_first_days(_excavator), *later), enums, ["D9"], _marked_pit(marked_day)
    )

    assert not finding.active
    assert finding.last_seen_at == later[1].window_end
    assert finding.facts["completed_on"] == "2026-10-19"


def test_отметка_позже_момента_анализа_d9_не_закрывает(enums):
    facts = make_facts(*_first_days(_excavator))

    (finding,) = _findings(facts, enums, ["D9"], _marked_pit(date(2026, 10, 22)), as_of=AFTER)

    assert finding.active and finding.facts["completed_on"] is None


# --- D10: вне контроля ИИ -----------------------------------------------------------------


def test_день_3_даёт_d10_по_складу_а_не_по_въезду(enums):
    (finding,) = _findings(load_facts("facts_day3.json"), enums, ["D10"])

    assert (finding.code, finding.area, finding.stage_id) == ("D10", STORAGE, None)
    assert finding.active and finding.occurrences == 12
    assert finding.severity == "INFO"
    assert finding.facts["reason"] == "DARK"
    # Доказательство — тёмные кадры cam-gate.
    assert finding.evidence and all(e["detection_ids"] == [] for e in finding.evidence)
    assert describe(finding, RULES["D10"], NAMES).message.startswith(
        "Участок «Склад» 12 рабочих сессий подряд не виден ни одной камерой: слишком темно."
    )


@pytest.mark.parametrize("name", ["facts_normal_day.json", "facts_day1.json", "facts_day2.json"])
def test_в_остальные_дни_всё_видно(enums, name):
    assert _findings(load_facts(name), enums, ["D10"]) == []


def test_одна_слепая_сессия_это_ещё_не_d10(enums):
    at = windows(date(2026, 10, 20), time(6), 3)
    sessions = [_blind(at[0]), _excavator(at[1]), _blind(at[2])]

    assert _findings(make_facts(*sessions), enums, ["D10"]) == []


def test_участок_без_единого_кадра_это_d10_без_снимков(enums):
    sessions = [
        make_session(at, make_area(PIT), make_area(STORAGE, cameras_usable=0, reason="NO_IMAGES"))
        for at in windows(date(2026, 10, 20), time(6), 2)
    ]

    (finding,) = _findings(make_facts(*sessions), enums, ["D10"])

    assert finding.area == STORAGE and finding.evidence == ()
    assert finding.facts["evidence_absent_reason"]


def test_тёмные_кадры_без_ссылок_d10_не_дают(enums):
    # Кадры были (DARK), но в фактах их нет: без доказательств отклонение не создаётся.
    dark = CameraState(code="cam-gate", images=1, usable=False, reason="DARK")
    sessions = [
        make_session(
            at,
            make_area(PIT),
            make_area(STORAGE, cameras_usable=0, reason="DARK"),
            cameras=(dark,),
        )
        for at in windows(date(2026, 10, 20), time(6), 3)
    ]

    assert _findings(make_facts(*sessions), enums, ["D10"]) == []


def test_d10_по_этапу_без_размеченного_участка(enums):
    # 01.10 активна «Подготовка территории» (пятно застройки), размечен только котлован.
    sessions = _sessions(_excavator, date(2026, 10, 1), 2)

    (finding,) = _findings(make_facts(*sessions), enums, ["D10"])

    assert (finding.stage_id, finding.area) == (PREPARATION.id, None)
    assert finding.evidence == ()
    deviation = describe(finding, RULES["D10"], NAMES)
    assert deviation.title == "Вне контроля ИИ: «Подготовка территории»"
    assert "(BUILDING_FOOTPRINT) не размечен" in deviation.message


def test_у_закрытого_отметкой_этапа_без_участка_d10_нет(enums):
    marked = PREPARATION.model_copy(update={"completed_on": date(2026, 9, 30)})
    sessions = _sessions(_excavator, date(2026, 10, 1), 2)

    assert _findings(make_facts(*sessions), enums, ["D10"], make_plan(marked, PIT_STAGE)) == []


def test_вне_рабочего_времени_d10_нет(enums):
    night = _sessions(_blind, date(2026, 10, 20), 4, first=time(21))
    sunday = _sessions(_blind, date(2026, 10, 25), 4)

    assert _findings(make_facts(*night, *sunday), enums, ["D10"]) == []


# --- Инварианты ленты по всем готовым предикатам -------------------------------------------

READY = [c for c in RULES if RULES[c].predicate in REGISTRY]


def test_готовы_все_предикаты():
    assert list(RULES) == READY


def test_по_слепому_участку_ничего_кроме_d10(enums):
    sessions = [
        make_session(
            at,
            make_area(PIT, cameras_usable=0, reason="DARK"),
            make_area(GATE, cameras_usable=0, reason="DARK"),
            cameras=(make_camera("cam-north", at, reason="DARK"),),
        )
        for day in [*FIRST_DAYS, date(2026, 10, 19)]
        for at in windows(day, time(6), 3)
    ]

    findings = _findings(make_facts(*sessions), enums, READY)

    assert {f.code for f in findings} == {"D10"}


def test_без_снимков_бывает_только_d10(enums):
    facts = [load_facts(n) for n in ("facts_day1.json", "facts_day2.json", "facts_day3.json")]
    sessions = [s for f in facts for s in f.sessions] + _sessions(_excavator, date(2026, 10, 1), 2)

    findings = _findings(make_facts(*sessions), enums, READY)

    assert {"D2", "D3", "D4", "D10"} <= {f.code for f in findings}
    for finding in findings:
        assert finding.facts
        if not finding.evidence:
            assert finding.code == "D10" and finding.facts["evidence_absent_reason"]
        assert describe(finding, RULES[finding.code], NAMES).message
