"""Календарь объекта: рабочие дни, рабочие сессии, арифметика в рабочих днях.

Календарь — из фикстуры плана: Москва, шестидневка (выходной — воскресенье),
праздник 4 ноября 2026, рабочие часы 07:00–23:00 МСК = 04:00–20:00 UTC.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from src.core.calendar import (
    CalendarError,
    add_working_days,
    calendar_from_plan,
    count_working_days,
    is_working_day,
    is_working_session,
    local_date,
    working_days_between,
)

from tests.factories import load_plan

CAL = calendar_from_plan(load_plan().calendar)
WINDOW = timedelta(minutes=30)


def _utc(day: int, hour: int, minute: int = 0, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


def _session(start: datetime) -> bool:
    return is_working_session(CAL, start, start + WINDOW)


def test_воскресенье_выходной_суббота_рабочая_в_шестидневке():
    assert not is_working_day(CAL, date(2026, 10, 25))
    assert is_working_day(CAL, date(2026, 10, 24))


def test_праздник_4_ноября_не_рабочий_хотя_это_среда():
    assert date(2026, 11, 4).isoweekday() == 3
    assert not is_working_day(CAL, date(2026, 11, 4))


def test_первое_рабочее_окно_начинается_в_07_00_мск():
    assert not _session(_utc(20, 3, 30))
    assert _session(_utc(20, 4, 0))


def test_последнее_рабочее_окно_кончается_в_23_00_мск():
    assert _session(_utc(20, 19, 30))
    assert not _session(_utc(20, 20, 0))


def test_окно_задевшее_границу_рабочих_часов_не_рабочее():
    assert not is_working_session(CAL, _utc(20, 3, 45), _utc(20, 4, 15))


def test_окно_в_рабочие_часы_выходного_дня_не_рабочее():
    assert not _session(_utc(25, 9))
    assert not _session(_utc(4, 9, month=11))


def test_местная_дата_меняется_в_полночь_по_москве_а_не_по_utc():
    assert local_date(CAL, _utc(21, 20, 59)) == date(2026, 10, 21)
    assert local_date(CAL, _utc(21, 21, 0)) == date(2026, 10, 22)


def test_окно_через_местную_полночь_не_рабочее():
    assert not is_working_session(CAL, _utc(21, 20, 45), _utc(21, 21, 15))


def test_даты_этапа_включительно():
    # Пн 19.10 — Сб 24.10: шесть рабочих дней шестидневки.
    assert count_working_days(CAL, date(2026, 10, 19), date(2026, 10, 24)) == 6
    assert count_working_days(CAL, date(2026, 10, 19), date(2026, 10, 19)) == 1
    assert count_working_days(CAL, date(2026, 10, 20), date(2026, 10, 19)) == 0


def test_выходные_и_праздник_не_считаются_рабочими_днями():
    # Пн 02.11 — Вс 08.11: без воскресенья и без 4 ноября.
    assert count_working_days(CAL, date(2026, 11, 2), date(2026, 11, 8)) == 5


def test_разница_в_рабочих_днях_со_знаком():
    assert working_days_between(CAL, date(2026, 10, 24), date(2026, 10, 26)) == 1
    assert working_days_between(CAL, date(2026, 10, 26), date(2026, 10, 24)) == -1
    assert working_days_between(CAL, date(2026, 10, 20), date(2026, 10, 20)) == 0


def test_прибавление_рабочих_дней_перешагивает_выходной_и_праздник():
    assert add_working_days(CAL, date(2026, 10, 24), 1) == date(2026, 10, 26)
    assert add_working_days(CAL, date(2026, 11, 3), 1) == date(2026, 11, 5)
    assert add_working_days(CAL, date(2026, 10, 26), -1) == date(2026, 10, 24)
    assert add_working_days(CAL, date(2026, 10, 20), 0) == date(2026, 10, 20)


@pytest.mark.parametrize("days", [1, 5, 13, 30])
def test_прибавление_обратно_разнице(days):
    start = date(2026, 10, 30)

    assert working_days_between(CAL, start, add_working_days(CAL, start, days)) == days


def test_неизвестный_часовой_пояс_это_ошибка_календаря():
    source = load_plan().calendar.model_copy(update={"timezone": "Mars/Olympus"})

    with pytest.raises(CalendarError):
        calendar_from_plan(source)


def test_рабочие_часы_через_полночь_не_поддерживаются():
    plan_calendar = load_plan().calendar
    hours = plan_calendar.work_hours.model_copy(
        update={"start": plan_calendar.work_hours.end, "end": plan_calendar.work_hours.start}
    )

    with pytest.raises(CalendarError):
        calendar_from_plan(plan_calendar.model_copy(update={"work_hours": hours}))
