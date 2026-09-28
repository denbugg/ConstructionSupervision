"""Окно наблюдения (сессия): SESSION_WINDOW_MINUTES, выровненное по :00 и :30 UTC.

Технику считают по окну, а не по кадру: одна машина, попавшая в две камеры, иначе была бы
посчитана дважды (methodology.md, раздел 2). Окна выровнены по UTC, а не по местному
времени: все объекты и камеры делят одну сетку, а рабочие часы — забота analysis.
"""

from datetime import UTC, datetime, timedelta

MINUTES_PER_DAY = 24 * 60


class WindowError(ValueError):
    """Длина окна не делит сутки нацело: окна разных дней не совпали бы по сетке."""


def session_window(at: datetime, minutes: int) -> tuple[datetime, datetime]:
    """Окно `[начало, конец)`, в которое попадает момент съёмки."""
    if minutes <= 0 or MINUTES_PER_DAY % minutes:
        raise WindowError(f"Окно {minutes} мин не делит сутки нацело")
    if at.tzinfo is None:
        raise WindowError("Момент съёмки без часового пояса: окно не определить")
    moment = at.astimezone(UTC)
    midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = (moment - midnight) // timedelta(minutes=minutes)
    start = midnight + elapsed * timedelta(minutes=minutes)
    return start, start + timedelta(minutes=minutes)
