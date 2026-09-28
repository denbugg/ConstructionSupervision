"""Прогресс, SPI, прогноз, перенос по связям, статус объекта (docs/methodology.md, 8, 10)."""

from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest
from src.core.calendar import add_working_days, calendar_from_plan, count_working_days
from src.core.context import build_context
from src.core.forecast import (
    ForecastError,
    ForecastParams,
    VisibilityShare,
    confidence,
    forecast,
    planned_progress,
)
from src.core.inputs import Predecessor
from src.core.rules import RuleParams

from tests.factories import (
    load_plan,
    make_area,
    make_equipment,
    make_facts,
    make_plan,
    make_session,
    make_stage,
    windows,
)

PLAN = load_plan()
CALENDAR = calendar_from_plan(PLAN.calendar)
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
PREPARATION, PIT_STAGE, FOUNDATION = PLAN.stages
PIT = "PIT:Котлован"
# Котлован по плану 15.10–20.11: 31 рабочий день. Первые пять — 15, 16, 17, 19, 20 октября.
FIRST_WEEK = [date(2026, 10, d) for d in (15, 16, 17, 19, 20)]


def _session(at, *, excavator_static=0, trucks=True, blind=False, stage=("PIT", 0.78)):
    if blind:
        return make_session(at, make_area(PIT, cameras_usable=0, reason="DARK"), stage=None)
    equipment = [make_equipment("excavator", static=excavator_static, at=at)]
    if trucks:
        equipment.append(make_equipment("dump_truck", 2, at=at))
    return make_session(at, make_area(PIT, *equipment), stage=stage)


def _days(days, per_day=4, **kwargs):
    """По `per_day` одинаковых сессий в каждый из дней."""
    return [_session(at, **kwargs) for day in days for at in windows(day, time(6), per_day)]


def _half_days(days):
    """Полдня техника работает, полдня экскаватор стоит: индекс активности 0.5."""
    sessions = []
    for day in days:
        at = windows(day, time(6), 4)
        sessions += [_session(t) for t in at[:2]] + [
            _session(t, excavator_static=1) for t in at[2:]
        ]
    return sessions


def _run(enums, sessions, plan=PLAN, as_of=None):
    ctx = build_context(plan, make_facts(*sessions), enums=enums, params=PARAMS, as_of=as_of)
    return forecast(ctx, FP)


def _stage(result, stage):
    return next(s for s in result.stages if s.stage_id == stage.id)


def test_полная_работа_в_графике(enums):
    result = _run(enums, _days(FIRST_WEEK))
    pit = _stage(result, PIT_STAGE)

    assert pit.actual_start == date(2026, 10, 15)
    assert pit.effective_days == 5
    assert pit.progress == pit.planned_progress == round(5 / 31, 4)
    assert pit.spi == 1.0
    assert pit.forecast_end == PIT_STAGE.plan_end and pit.delay_days == 0
    assert (pit.status, pit.confidence) == ("IN_PROGRESS", "HIGH")
    assert pit.last_activity_at == datetime(2026, 10, 20, 8, tzinfo=UTC)
    assert result.object.status == "ON_TRACK"
    assert (result.object.delay_days, result.object.spi) == (0, 1.0)
    assert result.object.stages_at_risk == ()


def test_половинный_темп_сдвигает_этап_и_зависимый(enums):
    result = _run(enums, _half_days(FIRST_WEEK))
    pit, foundation = _stage(result, PIT_STAGE), _stage(result, FOUNDATION)

    assert pit.spi == 0.5
    assert pit.facts["avg_activity"] == 0.5
    # (1 − 2.5/31) × 31 / 0.5 = 57 рабочих дней от 20.10 против 26 по плану.
    assert pit.forecast_end == add_working_days(CALENDAR, date(2026, 10, 20), 57)
    assert (pit.delay_days, pit.status) == (31, "LATE")
    # Фундамент связан FS: начнётся на следующий рабочий день после котлована.
    assert foundation.expected_start == add_working_days(CALENDAR, pit.forecast_end, 1)
    assert foundation.delay_days == 31
    assert result.object.status == "DELAY" and result.object.delay_days == 31
    assert [r["name"] for r in result.object.stages_at_risk] == [
        "Разработка котлована",
        "Фундаментная плита",
    ]


def test_полный_простой_упирается_в_min_activity(enums):
    pit = _stage(_run(enums, _days(FIRST_WEEK, excavator_static=1)), PIT_STAGE)

    assert pit.actual_start is not None and pit.progress == 0
    assert pit.facts["floored_by_min_activity"]
    # 31 / 0.1 = 310 рабочих дней, а не бесконечность.
    assert pit.facts["remaining_days"] == 310
    assert pit.confidence == "LOW"


def test_полный_простой_понижает_уверенность_объекта(enums):
    result = _run(enums, _days(FIRST_WEEK, excavator_static=1))

    assert result.object.status == "DELAY" and result.object.confidence == "LOW"


def test_мало_дней_наблюдений_прогноз_не_строится(enums):
    result = _run(enums, _days(FIRST_WEEK[:2]))
    pit = _stage(result, PIT_STAGE)

    assert pit.forecast_end is None and pit.delay_days is None
    assert pit.status == "IN_PROGRESS" and pit.confidence == "LOW"
    assert result.object.status == "UNKNOWN"
    assert (result.object.delay_days, result.object.spi) == (None, None)


def test_слепые_сессии_дают_unknown(enums):
    sessions = []
    for day in FIRST_WEEK:
        at = windows(day, time(6), 4)
        sessions += [_session(at[0]), *[_session(t, blind=True) for t in at[1:]]]

    result = _run(enums, sessions)

    assert result.object.status == "UNKNOWN"
    assert result.object.facts["visible_share"] == 0.25


def test_as_of_в_прошлом_не_видит_будущего(enums):
    sessions = _days(FIRST_WEEK)
    as_of = datetime(2026, 10, 16, 9, tzinfo=UTC)

    pit = _stage(_run(enums, sessions, as_of=as_of), PIT_STAGE)

    assert pit.effective_days == 2
    assert pit.planned_progress == round(2 / 31, 4)
    assert pit.forecast_end is None


def test_as_of_до_плана_spi_не_делится_на_ноль(enums):
    # Ранний старт 14.10: к as_of плановый прогресс котлована равен нулю.
    pit = _stage(_run(enums, _days([date(2026, 10, 14)])), PIT_STAGE)

    assert pit.planned_progress == 0 and pit.spi is None
    assert pit.facts["start_deviation_days"] == -1


def test_плановый_прогресс_без_рабочих_дней_не_определён():
    sunday = make_stage("Воскресенье", date(2026, 10, 18), date(2026, 10, 18))

    assert planned_progress(CALENDAR, sunday, date(2026, 10, 20)) is None


def test_стадия_по_фото_раньше_этапа_обнуляет_прогресс(enums):
    plan = make_plan(
        PIT_STAGE.model_copy(update={"visual_stage": "FOUNDATION", "predecessors": ()})
    )

    pit = _stage(_run(enums, _days(FIRST_WEEK), plan=plan), PIT_STAGE)

    assert pit.progress == 0 and pit.facts["progress_limited_by_stage"]
    assert pit.facts["progress_raw"] == round(5 / 31, 4)
    # Техника работает, но фото противоречит прогрессу — HIGH не бывает.
    assert pit.confidence == "MEDIUM"


def test_неуверенная_стадия_прогресс_не_ограничивает(enums):
    plan = make_plan(
        PIT_STAGE.model_copy(update={"visual_stage": "FOUNDATION", "predecessors": ()})
    )

    pit = _stage(_run(enums, _days(FIRST_WEEK, stage=("PIT", 0.3)), plan=plan), PIT_STAGE)

    assert not pit.facts["progress_limited_by_stage"] and pit.progress > 0


def test_завершённый_этап(enums):
    short = make_stage(
        "Короткая",
        date(2026, 10, 15),
        date(2026, 10, 17),
        norm_duration_days=3,
        rule=PIT_STAGE.rule,
        visual_stage="PIT",
    )

    result = _run(enums, _days(FIRST_WEEK), plan=make_plan(short))
    (stage,) = result.stages

    assert (stage.status, stage.progress) == ("DONE", 1.0)
    assert stage.forecast_end == date(2026, 10, 17) and stage.delay_days == 0
    assert result.object.stages_at_risk == ()


# --- Отметка оператора «этап выполнен» (раздел 10.3b) --------------------------------------


def _marked(stage, day):
    return stage.model_copy(
        update={"completed_on": day, "completed_by": "Петров П. П.", "completion_note": "акт"}
    )


def test_отметка_выполнен_закрывает_этап_раньше_плана(enums):
    marked_day = date(2026, 10, 19)
    plan = make_plan(PREPARATION, _marked(PIT_STAGE, marked_day), FOUNDATION)

    result = _run(enums, _days(FIRST_WEEK), plan=plan)
    pit = _stage(result, PIT_STAGE)

    assert (pit.status, pit.progress, pit.confidence) == ("DONE", 1.0, "HIGH")
    assert pit.forecast_end == pit.expected_end == marked_day
    # Отметка 19.10 при плане по 20.11: с 20.10 по 20.11 — 27 рабочих дней.
    assert pit.delay_days == -27
    assert pit.actual_start == date(2026, 10, 15)
    assert pit.facts["basis"] == "OPERATOR"
    assert pit.facts["completed_on"] == "2026-10-19"
    assert (pit.facts["completed_by"], pit.facts["completion_note"]) == ("Петров П. П.", "акт")
    # Освоенный объём подтверждён: в SPI этап входит с прогрессом 1.
    assert pit.spi == result.object.spi == round(31 / 5, 3)
    assert result.object.stages_at_risk == ()


def test_поздняя_отметка_сдвигает_последователя(enums):
    first = _marked(
        make_stage(
            "Котлован",
            date(2026, 10, 15),
            date(2026, 10, 16),
            norm_duration_days=2,
            rule=PIT_STAGE.rule,
        ),
        date(2026, 10, 20),
    )
    second = make_stage("Плита", date(2026, 10, 17), date(2026, 10, 22), seq=2).model_copy(
        update={"predecessors": (Predecessor(stage_id=first.id, type="FS"),)}
    )

    result = _run(enums, _days(FIRST_WEEK), plan=make_plan(first, second))
    done, after = _stage(result, first), _stage(result, second)

    # Закончили 20.10 вместо 16.10: 17, 19 и 20 октября.
    assert (done.status, done.delay_days) == ("DONE", 3)
    # FS от даты отметки: плита — с 21.10, пять рабочих дней, по 26.10 (25-е — воскресенье).
    assert (after.expected_start, after.expected_end) == (date(2026, 10, 21), date(2026, 10, 26))
    assert after.delay_days == 3


def test_отметка_без_наблюдённого_старта(enums):
    marked_day = date(2026, 10, 19)
    plan = make_plan(PREPARATION, _marked(PIT_STAGE, marked_day), FOUNDATION)

    pit = _stage(_run(enums, _days(FIRST_WEEK, trucks=False), plan=plan), PIT_STAGE)

    assert (pit.status, pit.forecast_end) == ("DONE", marked_day)
    # Старт по снимкам не собрался — он неизвестен, для связей берётся плановый.
    assert pit.actual_start is None and pit.facts["start_deviation_days"] is None
    assert pit.expected_start == PIT_STAGE.plan_start


def test_отметка_у_этапа_без_правила(enums):
    stage = _marked(
        make_stage("Без правила", date(2026, 10, 15), date(2026, 10, 30)), FIRST_WEEK[-1]
    )

    (result,) = _run(enums, _days(FIRST_WEEK), plan=make_plan(stage)).stages

    assert (result.status, result.facts["basis"]) == ("DONE", "OPERATOR")
    assert result.actual_start is None and result.effective_days == 0


def test_отметка_позже_момента_анализа_не_действует(enums):
    plan = make_plan(PREPARATION, _marked(PIT_STAGE, date(2026, 10, 22)), FOUNDATION)

    pit = _stage(_run(enums, _days(FIRST_WEEK), plan=plan), PIT_STAGE)

    assert pit.facts["basis"] == "OBSERVED" and pit.status == "IN_PROGRESS"


def test_не_начатый_при_видимом_участке_этап_опаздывает(enums):
    # Экскаватор без самосвалов: сигнатура «экскаватор + самосвал» не выполнена.
    pit = _stage(_run(enums, _days(FIRST_WEEK, trucks=False)), PIT_STAGE)

    assert pit.actual_start is None and pit.status == "LATE"
    assert pit.expected_start == date(2026, 10, 20)
    # Старт сегодня плюс 31 рабочий день плановой длительности — на 4 дня позже плана.
    assert pit.delay_days == 4


def test_невидимый_этап_идёт_по_плану(enums):
    # Подготовка территории: пятно застройки не размечено, наблюдать нечего.
    prep = _stage(_run(enums, _days(FIRST_WEEK)), PREPARATION)

    assert prep.facts["basis"] == "PLAN"
    assert (prep.status, prep.delay_days, prep.confidence) == ("DONE", 0, "LOW")


def test_этап_до_начала_наблюдений_выполнен_по_плану(enums):
    """Раздел 10.3a: наблюдения с 15.10, окно этапа 01–10.10, его сигнатуры после не видно."""
    early = make_stage("Ранняя", date(2026, 10, 1), date(2026, 10, 10), rule=PIT_STAGE.rule)

    (stage,) = _run(enums, _days(FIRST_WEEK, trucks=False), plan=make_plan(early)).stages

    assert stage.facts["basis"] == "PLAN"
    assert "до начала наблюдений" in stage.facts["basis_reason"]
    assert (stage.status, stage.delay_days) == ("DONE", 0)


def test_этап_начатый_до_наблюдений_получает_плановый_прогресс(enums):
    """Раздел 10.3a: этап идёт с 01.10, участок видим с 15.10, дальше работа в полную силу."""
    start, end = date(2026, 10, 1), date(2026, 11, 20)
    norm = count_working_days(CALENDAR, start, end)
    running = make_stage("Идущая", start, end, norm_duration_days=norm, rule=PIT_STAGE.rule)

    (stage,) = _run(enums, _days(FIRST_WEEK), plan=make_plan(running)).stages

    credited = count_working_days(CALENDAR, start, date(2026, 10, 14))
    assert stage.facts["started_before_observation"] is True
    assert stage.facts["observation_start"] == "2026-10-15"
    assert stage.facts["credited_days"] == credited
    # Фактический старт снимки не застали: он неизвестен, а не «15.10 с опозданием».
    assert stage.actual_start is None and stage.facts["start_deviation_days"] is None
    assert stage.effective_days == credited + 5
    assert stage.spi == 1.0 and stage.delay_days == 0
    assert stage.expected_start == start


def test_этап_начатый_до_наблюдений_без_сигнатуры_опаздывает(enums):
    start, end = date(2026, 10, 1), date(2026, 11, 20)
    running = make_stage("Идущая", start, end, rule=PIT_STAGE.rule)

    (stage,) = _run(enums, _days(FIRST_WEEK, trucks=False), plan=make_plan(running)).stages

    assert stage.facts["basis"] == "OBSERVED" and stage.status == "LATE"
    assert stage.facts["credited_days"] == 0


def _linked(pred_type, lag):
    first = make_stage("Первая", date(2026, 12, 1), date(2026, 12, 5), seq=1)
    second = make_stage("Вторая", date(2026, 12, 1), date(2026, 12, 3), seq=2)
    second = second.model_copy(
        update={"predecessors": (Predecessor(stage_id=first.id, type=pred_type, lag_days=lag),)}
    )
    return make_plan(first, second), second


@pytest.mark.parametrize(
    ("pred_type", "lag", "start", "end"),
    [
        # 01–05.12 — вторник–суббота; 06.12 — воскресенье.
        ("FS", 0, date(2026, 12, 7), date(2026, 12, 9)),
        ("SS", 2, date(2026, 12, 3), date(2026, 12, 5)),
        ("FF", 1, date(2026, 12, 1), date(2026, 12, 7)),
        ("SF", 0, date(2026, 12, 1), date(2026, 12, 3)),
    ],
)
def test_перенос_по_типам_связей(enums, pred_type, lag, start, end):
    plan, second = _linked(pred_type, lag)

    result = _stage(_run(enums, _days(FIRST_WEEK), plan=plan), second)

    assert (result.expected_start, result.expected_end) == (start, end)


def test_цикл_в_связях_это_ошибка(enums):
    plan, second = _linked("FS", 0)
    first = plan.stages[0].model_copy(
        update={"predecessors": (Predecessor(stage_id=second.id, type="FS"),)}
    )

    with pytest.raises(ForecastError):
        _run(enums, _days(FIRST_WEEK), plan=make_plan(first, second))


def test_неизвестный_предшественник_это_ошибка(enums):
    orphan = PIT_STAGE.model_copy(
        update={"predecessors": (Predecessor(stage_id=FOUNDATION.id, type="FS"),)}
    )

    with pytest.raises(ForecastError):
        _run(enums, _days(FIRST_WEEK), plan=make_plan(orphan))


@pytest.mark.parametrize(
    ("days", "seen", "kwargs", "expected"),
    [
        (5, VisibilityShare(10, 9, 0), {}, "HIGH"),
        (5, VisibilityShare(10, 8, 0), {}, "MEDIUM"),
        (5, VisibilityShare(10, 9, 0), {"consistent": False}, "MEDIUM"),
        (3, VisibilityShare(10, 6, 0), {}, "MEDIUM"),
        (3, VisibilityShare(10, 5, 0), {}, "LOW"),
        (2, VisibilityShare(10, 10, 0), {}, "LOW"),
        (9, VisibilityShare(10, 10, 0), {"floored": True}, "LOW"),
        # Видимые сессии в основном частичные — на шаг ниже.
        (5, VisibilityShare(10, 10, 6), {}, "MEDIUM"),
        (3, VisibilityShare(10, 10, 6), {}, "LOW"),
    ],
)
def test_уверенность_по_таблице(days, seen, kwargs, expected):
    assert confidence(FP, days, seen, **kwargs) == expected


def test_параметры_прогноза_берутся_из_данных(enums):
    strict = replace(FP, on_track_tolerance_days=0)
    ctx = build_context(PLAN, make_facts(*_days(FIRST_WEEK)), enums=enums, params=PARAMS)

    assert forecast(ctx, strict).object.status == "ON_TRACK"
    assert forecast(ctx, replace(FP, min_days_for_forecast=6)).object.status == "UNKNOWN"
