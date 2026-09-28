"""Контекст прогона методики и серии сессий подряд (docs/methodology.md, разделы 2 и 9).

Общий вход предикатов отклонений и расчёта активности. Живёт отдельно от реестра
предикатов, чтобы `core/activity.py` и предикаты, которым нужен фактический старт,
не импортировали друг друга по кругу.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.core.calendar import Calendar, calendar_from_plan, is_working_session
from src.core.enums import Enums
from src.core.inputs import Facts, Plan, SessionFact
from src.core.rules import RuleParams


@dataclass(frozen=True)
class Context:
    """Всё, что нужно методике: план, рабочие сессии по времени, параметры, момент расчёта."""

    plan: Plan
    calendar: Calendar
    sessions: tuple[SessionFact, ...]
    enums: Enums
    params: RuleParams
    transient: frozenset[str]
    works_in_place: frozenset[str]
    class_names: dict[str, str]
    # «Сегодня» методики: местная дата as_of, а не часы сервера.
    as_of: datetime


def build_context(
    plan: Plan,
    facts: Facts,
    *,
    enums: Enums,
    params: RuleParams,
    as_of: datetime | None = None,
) -> Context:
    """Контекст прогона. Сессии вне рабочего времени отбрасываются здесь, один раз для всех.

    `as_of` по умолчанию — конец последней сессии с фактами; сессии, закончившиеся
    позже `as_of`, в расчёт не входят: прогон «на прошлую дату» не должен видеть будущее.
    """
    if as_of is None:
        ends = [s.window_end for s in facts.sessions]
        as_of = max(ends) if ends else facts.period_to
    calendar = calendar_from_plan(plan.calendar)
    working = sorted(
        (
            s
            for s in facts.sessions
            if s.window_end <= as_of and is_working_session(calendar, s.window_start, s.window_end)
        ),
        key=lambda s: s.window_start,
    )
    return Context(
        plan=plan,
        calendar=calendar,
        sessions=tuple(working),
        enums=enums,
        params=params,
        transient=frozenset(c.code for c in plan.equipment_classes if c.transient),
        works_in_place=frozenset(c.code for c in plan.equipment_classes if c.works_in_place),
        class_names={c.code: c.name_ru for c in plan.equipment_classes},
        as_of=as_of,
    )


@dataclass(frozen=True)
class Streak:
    """Серия подряд идущих наблюдаемых сессий, где условие выполнялось."""

    sessions: tuple[SessionFact, ...]
    payloads: tuple[Any, ...]
    active: bool


def find_streaks(rows: Sequence[tuple[SessionFact, Any]]) -> list[Streak]:
    """Серии по строкам (сессия, состояние).

    Состояние: None — сессия не наблюдалась (пропускается, серию не рвёт), False —
    условие не выполнено (рвёт серию), иное — условие выполнено, это данные сессии.
    """
    result: list[Streak] = []
    current: list[tuple[SessionFact, Any]] = []
    for session, state in rows:
        if state is None:
            continue
        if state is False:
            if current:
                result.append(_streak(current, active=False))
                current = []
            continue
        current.append((session, state))
    if current:
        result.append(_streak(current, active=True))
    return result


def _streak(items: list[tuple[SessionFact, Any]], *, active: bool) -> Streak:
    return Streak(tuple(s for s, _ in items), tuple(p for _, p in items), active)
