"""Тесты рабочего календаря.

Тест правила — это зафиксированная договорённость о том, как система понимает
стройку, поэтому сценарии названы по-русски и описывают ситуацию, а не вызов
функции (docs/testing.md, п. 3).
"""

from datetime import date, time

import pytest
from src.core.calendar import (
    CalendarError,
    WorkCalendar,
    add_months,
    add_working_days,
    check_calendar,
    count_working_days,
    next_working_day,
    working_progress,
)

# 2026-10-19 — понедельник, 2026-10-24 — суббота, 2026-10-25 — воскресенье.
MONDAY = date(2026, 10, 19)
FRIDAY = date(2026, 10, 23)
SATURDAY = date(2026, 10, 24)
NEXT_MONDAY = date(2026, 10, 26)

FIVE_DAY = WorkCalendar()
SIX_DAY = WorkCalendar(weekend_days=(7,))
WITH_HOLIDAY = WorkCalendar(holidays=frozenset({date(2026, 10, 21)}))


def test_выходной_не_является_рабочим_днём():
    assert FIVE_DAY.is_working_day(MONDAY)
    assert not FIVE_DAY.is_working_day(SATURDAY)


def test_при_шестидневке_суббота_рабочая():
    assert SIX_DAY.is_working_day(SATURDAY)


def test_праздник_исключается_даже_в_будний_день():
    assert not WITH_HOLIDAY.is_working_day(date(2026, 10, 21))


def test_старт_в_субботу_переносится_на_понедельник():
    """Этап, начинающийся в выходной, фактически стартует в ближайший рабочий день."""
    assert next_working_day(FIVE_DAY, SATURDAY) == NEXT_MONDAY
    assert add_working_days(FIVE_DAY, SATURDAY, 0) == NEXT_MONDAY


def test_прибавление_рабочих_дней_перешагивает_выходные():
    # понедельник + 5 рабочих дней = следующий понедельник, а не суббота
    assert add_working_days(FIVE_DAY, MONDAY, 5) == NEXT_MONDAY


def test_прибавление_учитывает_праздник():
    # среда 21.10 выпала, поэтому те же 5 дней уезжают на день дальше
    assert add_working_days(WITH_HOLIDAY, MONDAY, 5) == date(2026, 10, 27)


def test_отсчёт_назад_для_обратного_прохода_cpm():
    assert add_working_days(FIVE_DAY, NEXT_MONDAY, -1) == FRIDAY


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 9, 21), 1.0, date(2026, 10, 21)),
        (date(2026, 10, 21), 1.5, date(2026, 12, 6)),  # 21.11 + половина 30 дней до 21.12
        (date(2026, 1, 31), 1.0, date(2026, 2, 28)),  # 31 февраля нет — конец месяца
        (date(2026, 12, 6), 4.7, date(2027, 4, 27)),  # 06.04 + 0,7 × 30 дней до 06.05
        (date(2026, 9, 21), 0.0, date(2026, 9, 21)),
    ],
)
def test_месяцы_откладываются_по_обычному_календарю(start, months, expected):
    assert add_months(start, months) == expected


def test_подсчёт_рабочих_дней_в_полуинтервале():
    # [пн, след. пн) — ровно пять рабочих дней, граничный день не удваивается
    assert count_working_days(FIVE_DAY, MONDAY, NEXT_MONDAY) == 5
    assert count_working_days(FIVE_DAY, MONDAY, MONDAY) == 0
    assert count_working_days(FIVE_DAY, NEXT_MONDAY, MONDAY) == 0


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 10, 18), 0.0),  # этап ещё не начался
        (date(2026, 10, 21), 0.4),  # прошло 2 рабочих дня из 5
        (date(2026, 11, 30), 1.0),  # плановое окончание давно позади
    ],
)
def test_плановый_прогресс_ограничен_нулём_и_единицей(today, expected):
    assert working_progress(FIVE_DAY, MONDAY, NEXT_MONDAY, today) == pytest.approx(expected)


def test_этап_нулевой_длительности_не_делит_на_ноль():
    """Этап-точка считается выполненным, как только наступила его дата."""
    assert working_progress(FIVE_DAY, MONDAY, MONDAY, MONDAY) == 1.0
    assert working_progress(FIVE_DAY, MONDAY, MONDAY, date(2026, 10, 1)) == 0.0


def test_московская_шестидневка_проходит_проверку():
    check_calendar("Europe/Moscow", [7], time(7), time(23))


@pytest.mark.parametrize(
    ("timezone", "weekend", "start", "end", "message"),
    [
        ("Moscow/Kremlin", [7], time(7), time(23), "часовой пояс"),
        ("Europe/Moscow", [0], time(7), time(23), "от 1 до 7"),
        ("Europe/Moscow", [7, 7], time(7), time(23), "дважды"),
        ("Europe/Moscow", [1, 2, 3, 4, 5, 6, 7], time(7), time(23), "ни одного рабочего"),
        ("Europe/Moscow", [7], time(23), time(7), "позже начала"),
        ("Europe/Moscow", [7], time(7), time(7), "позже начала"),
    ],
)
def test_бессмысленный_календарь_отклоняется(timezone, weekend, start, end, message):
    with pytest.raises(CalendarError, match=message):
        check_calendar(timezone, weekend, start, end)
