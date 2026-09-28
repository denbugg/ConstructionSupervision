"""Фактический старт, индекс активности, загрузка техники (docs/methodology.md, 10.1–10.2)."""

from datetime import UTC, date, datetime, time

from src.core.activity import actual_start, daily_activity, daily_equipment
from src.core.context import build_context
from src.core.rules import RuleParams

from tests.factories import (
    load_facts,
    load_plan,
    make_area,
    make_equipment,
    make_facts,
    make_plan,
    make_rule,
    make_session,
    make_stage,
    windows,
)

PLAN = load_plan()
PARAMS = RuleParams(transient_window_sessions=4, min_stage_conf=0.5)
PREPARATION, PIT_STAGE = PLAN.stages[0], PLAN.stages[1]
PIT = "PIT:Котлован"
GATE = "ENTRY_GATE:Въезд"
DANGER = "DANGER:Опасная зона"


def _ctx(facts, enums, plan=PLAN):
    return build_context(plan, facts, enums=enums, params=PARAMS)


def _full(at, static=0):
    return make_session(
        at,
        make_area(
            PIT,
            make_equipment("excavator", static=static, at=at),
            make_equipment("dump_truck", 2, at=at),
        ),
    )


def _excavator(at, static=0):
    return make_session(at, make_area(PIT, make_equipment("excavator", static=static, at=at)))


def _blind(at):
    return make_session(at, make_area(PIT, cameras_usable=0, reason="DARK"))


def _sessions(builder, day, n, first=time(6)):
    return [builder(at) for at in windows(day, first, n)]


def test_старт_котлована_в_нормальный_день(enums):
    start = actual_start(_ctx(load_facts("facts_normal_day.json"), enums), PIT_STAGE)

    assert start.day == date(2026, 10, 19)
    assert start.window_start == datetime(2026, 10, 19, 6, tzinfo=UTC)
    # 16, 17 и 19 октября — рабочие; 18-е — воскресенье.
    assert start.start_deviation_days == 3


def test_без_самосвалов_сигнатура_не_выполнена_и_старта_нет(enums):
    assert actual_start(_ctx(load_facts("facts_day1.json"), enums), PIT_STAGE) is None


def test_одна_сессия_с_сигнатурой_это_ещё_не_старт(enums):
    later = _sessions(_excavator, date(2026, 10, 20), 4, first=time(9))
    sessions = [_full(datetime(2026, 10, 20, 6, tzinfo=UTC)), *later]

    assert actual_start(_ctx(make_facts(*sessions), enums), PIT_STAGE) is None


def test_слепая_сессия_серию_старта_не_рвёт(enums):
    at = windows(date(2026, 10, 20), time(6), 3)
    sessions = [_full(at[0]), _blind(at[1]), _full(at[2])]

    start = actual_start(_ctx(make_facts(*sessions), enums), PIT_STAGE)

    assert start.window_start == at[0] and start.sessions == 2


def test_ранний_старт_даёт_отрицательное_отклонение(enums):
    start = actual_start(
        _ctx(make_facts(*_sessions(_full, date(2026, 10, 14), 2)), enums), PIT_STAGE
    )

    assert start.start_deviation_days == -1


def test_после_отметки_выполнен_старт_не_собирается_и_активность_не_считается(enums):
    """Раздел 10.3b: сигнатура после дня отметки — уже не работы этого этапа."""
    stage = PIT_STAGE.model_copy(update={"completed_on": date(2026, 10, 16)})
    sessions = [
        *_sessions(_excavator, date(2026, 10, 15), 2),
        *_sessions(_excavator, date(2026, 10, 16), 2),
        *_sessions(_full, date(2026, 10, 17), 2),
    ]
    ctx = _ctx(make_facts(*sessions), enums, make_plan(stage))

    assert actual_start(ctx, stage) is None
    rows = daily_activity(ctx, stage)
    assert [r.day for r in rows] == [date(2026, 10, 15), date(2026, 10, 16)]


def test_у_этапа_без_правила_нет_ни_старта_ни_активности(enums):
    stage = PIT_STAGE.model_copy(update={"rule": None})
    ctx = _ctx(load_facts("facts_normal_day.json"), enums, make_plan(stage))

    assert actual_start(ctx, stage) is None
    assert daily_activity(ctx, stage) == ()


def test_активность_нормального_дня_полная(enums):
    (row,) = daily_activity(_ctx(load_facts("facts_normal_day.json"), enums), PIT_STAGE)

    assert (row.day, row.sessions_total, row.sessions_working) == (date(2026, 10, 19), 12, 12)
    assert row.activity_index == 1.0 and row.blind_sessions == 0


def test_без_комплекта_активность_ноль(enums):
    (row,) = daily_activity(_ctx(load_facts("facts_day1.json"), enums), PIT_STAGE)

    assert (row.sessions_total, row.sessions_working, row.activity_index) == (12, 0, 0.0)


def test_неподвижный_экскаватор_не_работает(enums):
    at = windows(date(2026, 10, 20), time(6), 4)
    sessions = [_full(at[0]), _full(at[1], static=1), _full(at[2], static=1), _full(at[3])]

    (row,) = daily_activity(_ctx(make_facts(*sessions), enums), PIT_STAGE)

    assert (row.sessions_total, row.sessions_working) == (4, 2)
    assert row.activity_index == 0.5


def test_слепые_сессии_не_штрафуют_индекс(enums):
    at = windows(date(2026, 10, 20), time(6), 4)
    sessions = [_full(at[0]), _blind(at[1]), _blind(at[2]), _full(at[3])]

    (row,) = daily_activity(_ctx(make_facts(*sessions), enums), PIT_STAGE)

    assert (row.sessions_total, row.blind_sessions, row.activity_index) == (2, 2, 1.0)


def test_день_без_видимости_это_неизвестно_а_не_ноль(enums):
    (row,) = daily_activity(
        _ctx(make_facts(*_sessions(_blind, date(2026, 10, 20), 3)), enums), PIT_STAGE
    )

    assert (row.sessions_total, row.blind_sessions, row.activity_index) == (0, 3, None)


def test_только_транзитные_в_required_достаточно_комплекта(enums):
    stage = make_stage(
        "Вывоз грунта",
        date(2026, 10, 15),
        date(2026, 11, 20),
        rule=make_rule({"dump_truck": 1}),
    )
    sessions = [
        make_session(at, make_area(PIT, make_equipment("dump_truck", static=1, at=at)))
        for at in windows(date(2026, 10, 20), time(6), 2)
    ]

    (row,) = daily_activity(_ctx(make_facts(*sessions), enums, make_plan(stage)), stage)

    assert row.activity_index == 1.0


def test_затянувшийся_этап_продолжает_набирать_активность(enums):
    # План закончился 16.10, техника этапа работает 20.10: по таблице раздела 6 она была
    # бы «вне зоны», но для индекса активности этап активен в своих сессиях.
    stage = PIT_STAGE.model_copy(update={"plan_end": date(2026, 10, 16)})

    (row,) = daily_activity(
        _ctx(make_facts(*_sessions(_full, date(2026, 10, 20), 3)), enums, make_plan(stage)),
        stage,
    )

    assert row.activity_index == 1.0


def test_дни_до_плана_и_до_старта_не_считаются(enums):
    before = _sessions(_excavator, date(2026, 10, 14), 2)
    during = _sessions(_excavator, date(2026, 10, 20), 2)
    ctx = _ctx(make_facts(*before, *during), enums)

    assert [r.day for r in daily_activity(ctx, PIT_STAGE)] == [date(2026, 10, 20)]
    assert [r.day for r in daily_activity(ctx, PIT_STAGE, since=date(2026, 10, 1))] == [
        date(2026, 10, 14),
        date(2026, 10, 20),
    ]


def test_ранний_старт_начинает_активность_раньше_плана(enums):
    early = _sessions(_full, date(2026, 10, 14), 2)

    rows = daily_activity(_ctx(make_facts(*early), enums), PIT_STAGE)

    assert [r.day for r in rows] == [date(2026, 10, 14)]


def test_загрузка_техники_нормального_дня(enums):
    rows = daily_equipment(_ctx(load_facts("facts_normal_day.json"), enums))

    assert [(r.equipment_class, r.sessions_seen, r.max_count) for r in rows] == [
        ("dump_truck", 3, 2),
        ("excavator", 12, 1),
    ]


def test_загрузка_складывает_участки_и_вне_зон(enums):
    # День 3: экскаватор в котловане и второй — у въезда.
    rows = daily_equipment(_ctx(load_facts("facts_day3.json"), enums))

    assert {r.equipment_class: r.max_count for r in rows}["excavator"] == 2


def test_опасная_зона_и_человек_не_попадают_в_загрузку(enums):
    at = datetime(2026, 10, 20, 6, tzinfo=UTC)
    session = make_session(
        at,
        make_area(PIT, make_equipment("excavator", at=at), make_equipment("person", 3, at=at)),
        make_area(DANGER, make_equipment("excavator", at=at)),
        outside=(make_equipment("loader", at=at),),
    )

    rows = daily_equipment(_ctx(make_facts(session), enums))

    assert [(r.equipment_class, r.max_count) for r in rows] == [("excavator", 1), ("loader", 1)]


def test_вне_рабочего_времени_загрузки_нет(enums):
    night = _sessions(_full, date(2026, 10, 20), 2, first=time(21))

    assert daily_equipment(_ctx(make_facts(*night), enums)) == ()
