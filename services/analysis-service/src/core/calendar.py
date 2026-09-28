"""Рабочий календарь объекта: рабочие дни и рабочие сессии (docs/methodology.md, раздел 2).

Выводы строятся только по рабочим сессиям, а сроки считаются в рабочих днях. Сессии
приходят в UTC, рабочие часы заданы в местном времени календаря, поэтому всё
сравнение идёт через его часовой пояс. «Сегодня» — местная дата `as_of`, а не часы
сервера.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core.inputs import WorkCalendar

ONE_DAY = timedelta(days=1)


class CalendarError(ValueError):
    """Календарь из плана нельзя применить: неизвестный пояс или пустые рабочие часы."""


@dataclass(frozen=True)
class Calendar:
    """Календарь, готовый к расчётам: пояс разобран, списки превращены в множества."""

    tz: ZoneInfo
    weekend_days: frozenset[int]
    holidays: frozenset[date]
    work_start: time
    work_end: time


def calendar_from_plan(source: WorkCalendar) -> Calendar:
    """Календарь из контракта «весь план»."""
    try:
        tz = ZoneInfo(source.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise CalendarError(f"Неизвестный часовой пояс календаря: {source.timezone!r}") from exc
    if source.work_hours.end <= source.work_hours.start:
        # Ночные смены через полночь в MVP не поддерживаются: окно не было бы одним днём.
        raise CalendarError("Конец рабочих часов должен быть позже начала в пределах суток")
    return Calendar(
        tz=tz,
        weekend_days=frozenset(source.weekend_days),
        holidays=frozenset(source.holidays),
        work_start=source.work_hours.start,
        work_end=source.work_hours.end,
    )


def is_working_day(calendar: Calendar, day: date) -> bool:
    """Не выходной по ISO-номеру дня недели и не праздник."""
    return day.isoweekday() not in calendar.weekend_days and day not in calendar.holidays


def local_date(calendar: Calendar, moment: datetime) -> date:
    """Местная дата момента: по ней сессия относится к дню и к активным этапам."""
    return moment.astimezone(calendar.tz).date()


def is_working_session(calendar: Calendar, window_start: datetime, window_end: datetime) -> bool:
    """Окно — рабочая сессия, если целиком лежит в рабочих часах рабочего дня.

    Окно, задевающее границу рабочих часов, рабочим не считается: отклонение по
    сессии, половина которой пришлась на нерабочее время, было бы необоснованным.
    """
    start = window_start.astimezone(calendar.tz)
    end = window_end.astimezone(calendar.tz)
    # Рабочие часы кончаются в пределах суток, поэтому окно через полночь — не рабочее.
    if start.date() != end.date() or not is_working_day(calendar, start.date()):
        return False
    return calendar.work_start <= start.time() and end.time() <= calendar.work_end


def count_working_days(calendar: Calendar, start: date, end: date) -> int:
    """Число рабочих дней в отрезке [start, end], обе даты включительно, как у этапов."""
    days = 0
    current = start
    while current <= end:
        if is_working_day(calendar, current):
            days += 1
        current += ONE_DAY
    return days


def working_days_between(calendar: Calendar, start: date, end: date) -> int:
    """Сколько рабочих дней от `start` до `end`: рабочие дни в (start, end], со знаком.

    Отрицательное значение — `end` раньше `start`. Так считаются отставание старта
    и задержка прогноза относительно плана.
    """
    if end >= start:
        return count_working_days(calendar, start + ONE_DAY, end)
    return -count_working_days(calendar, end + ONE_DAY, start)


def add_working_days(calendar: Calendar, day: date, days: int) -> date:
    """Дата через `days` рабочих дней после `day` (до — при отрицательном значении).

    Обратна `working_days_between`: для рабочего результата
    `working_days_between(day, add_working_days(day, n)) == n`. Ноль возвращает `day`.
    """
    step = ONE_DAY if days >= 0 else -ONE_DAY
    remaining = abs(days)
    current = day
    while remaining:
        current += step
        if is_working_day(calendar, current):
            remaining -= 1
    return current
