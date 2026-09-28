"""Рабочий календарь: арифметика в рабочих днях (ТЗ, п. 8).

Чистые функции: ни БД, ни сети, ни FastAPI. Именно так выглядит всё, что лежит
в core/ — это то, что покрывается тестами и что мы показываем жюри.

Все плановые длительности считаются в рабочих днях, а не в календарных:
нормативы МРР заданы для рабочих дней, и срок, посчитанный по календарным,
завысил бы выработку примерно на четверть.
"""

import math
from calendar import monthrange
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_WEEKEND_DAYS = (6, 7)  # суббота и воскресенье, нумерация ISO: понедельник = 1
ISO_WEEKDAYS = range(1, 8)


class CalendarError(ValueError):
    """Настройка календаря не имеет смысла: такой календарь не сохраняется."""


def check_calendar(
    timezone: str, weekend_days: Sequence[int], work_start: time, work_end: time
) -> None:
    """Проверка календаря до записи: ошибку лучше показать оператору, чем получить в прогоне.

    Условия совпадают с тем, что analysis-service требует от календаря в «весь план»:
    известный часовой пояс и рабочие часы в пределах одних суток.
    """
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise CalendarError(f"Неизвестный часовой пояс: {timezone!r}") from exc
    wrong = sorted({d for d in weekend_days if d not in ISO_WEEKDAYS})
    if wrong:
        raise CalendarError(f"Выходные — номера дней по ISO от 1 до 7, а не {wrong}")
    if len(set(weekend_days)) != len(weekend_days):
        raise CalendarError("Выходной день указан дважды")
    if len(weekend_days) == len(ISO_WEEKDAYS):
        raise CalendarError("В календаре нет ни одного рабочего дня недели")
    if work_end <= work_start:
        # Смена через полночь не поддерживается: сессия относится к одному местному дню.
        raise CalendarError("Конец рабочих часов должен быть позже начала в пределах суток")


@dataclass(frozen=True)
class WorkCalendar:
    """Календарь объекта: какие дни считаются рабочими."""

    weekend_days: tuple[int, ...] = DEFAULT_WEEKEND_DAYS
    holidays: frozenset[date] = frozenset()

    def is_working_day(self, day: date) -> bool:
        return day.isoweekday() not in self.weekend_days and day not in self.holidays


def next_working_day(calendar: WorkCalendar, day: date) -> date:
    """Ближайший рабочий день, начиная с указанного включительно."""
    current = day
    while not calendar.is_working_day(current):
        current += timedelta(days=1)
    return current


def add_working_days(calendar: WorkCalendar, start: date, days: int) -> date:
    """Дата через `days` рабочих дней от `start`.

    Ноль означает «сам день начала, сдвинутый вперёд до рабочего»: этап,
    начинающийся в субботу, фактически стартует в понедельник.

    Отрицательное значение отсчитывает назад — это нужно для обратного прохода
    при расчёте поздних сроков (CPM).
    """
    current = next_working_day(calendar, start) if days >= 0 else start
    step = timedelta(days=1 if days >= 0 else -1)
    remaining = abs(days)

    while remaining:
        current += step
        if calendar.is_working_day(current):
            remaining -= 1
    return current


def add_months(start: date, months: float) -> date:
    """Дата через `months` календарных месяцев: 21.09 + 1 мес. = 21.10.

    Сроки МРР даны в месяцах, поэтому они откладываются по обычному календарю. Число месяца,
    которого нет в целевом месяце, прижимается к его концу (31.01 + 1 мес. = 28.02). Дробная
    часть — доля следующего месяца в днях, с округлением половины вверх: 21.10 + 0,5 мес. =
    21.10 + 16 дн. (между 21.10 и 21.11 — 31 день).
    """
    whole = math.floor(months)
    begin = _shift_months(start, whole)
    following = _shift_months(start, whole + 1)
    return begin + timedelta(days=math.floor((months - whole) * (following - begin).days + 0.5))


def _shift_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, monthrange(year, month + 1)[1]))


def count_working_days(calendar: WorkCalendar, start: date, end: date) -> int:
    """Число рабочих дней в полуинтервале [start, end).

    Полуинтервал, а не отрезок: так длительности складываются без двойного
    учёта граничного дня, а `end` совпадает с началом следующего этапа.
    """
    if end <= start:
        return 0

    days = 0
    current = start
    while current < end:
        if calendar.is_working_day(current):
            days += 1
        current += timedelta(days=1)
    return days


def working_progress(calendar: WorkCalendar, start: date, end: date, today: date) -> float:
    """Плановая доля выполнения на сегодня, 0…1 — знаменатель SPI.

    До начала этапа — 0, после планового окончания — 1. Этап нулевой
    длительности считается выполненным, как только наступила его дата:
    иначе SPI делился бы на ноль (docs/methodology.md, п. 9.4).
    """
    total = count_working_days(calendar, start, end)
    if total == 0:
        return 1.0 if today >= start else 0.0

    elapsed = count_working_days(calendar, start, min(today, end))
    return max(0.0, min(1.0, elapsed / total))
