"""Фактический старт этапа, индекс активности по дням, загрузка техники (F9, F10).

docs/methodology.md, разделы 10.1–10.2. Здесь только факт: что и когда наблюдалось.
Прогресс, SPI и прогноз строятся на этих числах в `core/forecast.py`.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from src.core.calendar import local_date, working_days_between
from src.core.context import Context, find_streaks
from src.core.equipment_state import PERSON, ROLE_SAFETY, WORKING, equipment_states
from src.core.inputs import SessionFact, Stage
from src.core.plan_on_date import active_stages, closed
from src.core.rules import RuleCheck, check_rule


@dataclass(frozen=True)
class ActualStart:
    """Первая сессия серии, в которой сигнатура этапа держится `min_sessions` подряд."""

    stage_id: UUID
    day: date
    session_id: UUID
    window_start: datetime
    sessions: int
    # actual_start − plan_start в рабочих днях: плюс — опоздание, минус — ранний старт.
    start_deviation_days: int


@dataclass(frozen=True)
class DailyActivity:
    """Строка daily_activity: активность этапа за местный день."""

    stage_id: UUID
    day: date
    sessions_total: int
    sessions_working: int
    # None — участок этапа за день ни разу не был виден: «не знаем», а не ноль.
    activity_index: float | None
    blind_sessions: int
    # Конец последней сессии дня, где комплект был и работал; None — такой не было.
    last_working_at: datetime | None = None


@dataclass(frozen=True)
class DailyEquipment:
    """Строка daily_equipment: класс техники на площадке за местный день."""

    day: date
    equipment_class: str
    sessions_seen: int
    max_count: int


def rule_checks(ctx: Context, stage: Stage) -> list[RuleCheck]:
    """Проверка правила этапа в каждой рабочей сессии контекста, по порядку сессий."""
    return [
        check_rule(
            stage, ctx.sessions, i, transient=ctx.transient, enums=ctx.enums, params=ctx.params
        )
        for i in range(len(ctx.sessions))
    ]


def actual_start(
    ctx: Context, stage: Stage, checks: Sequence[RuleCheck] | None = None
) -> ActualStart | None:
    """Фактический старт (раздел 10.1); None — сигнатура ещё не держалась серией.

    Сессии, где участок этапа не виден, серию не рвут и в неё не входят. `checks` —
    готовые проверки из `rule_checks`, чтобы не проверять правило дважды. Старт
    собирается только до отметки «выполнен» включительно (раздел 10.3b).
    """
    if stage.rule is None:
        return None
    checks = rule_checks(ctx, stage) if checks is None else checks
    rows = [
        (s, None if not c.evaluated else (c if c.signature_met else False))
        for s, c in zip(ctx.sessions, checks, strict=True)
        if not closed(stage, local_date(ctx.calendar, s.window_start))
    ]
    for streak in find_streaks(rows):
        if len(streak.sessions) >= stage.rule.min_sessions:
            first = streak.sessions[0]
            day = local_date(ctx.calendar, first.window_start)
            return ActualStart(
                stage_id=stage.id,
                day=day,
                session_id=first.session_id,
                window_start=first.window_start,
                sessions=len(streak.sessions),
                start_deviation_days=working_days_between(ctx.calendar, stage.plan_start, day),
            )
    return None


def _working(ctx: Context, stage: Stage, session: SessionFact, check: RuleCheck) -> bool:
    """Хотя бы одна нетранзитная единица из `required` на участке этапа работает.

    Этап считается активным в своих сессиях и вне плановых дат: иначе по таблице
    раздела 6 техника затянувшегося этапа была бы «вне зоны», и этап не набирал бы
    прогресс ровно тогда, когда его доделывают.
    """
    required = {c for g in stage.rule.required for c in g.any_of} - ctx.transient
    # Только транзитные классы в required — достаточно присутствия комплекта (раздел 10.2).
    if not required:
        return True
    day = local_date(ctx.calendar, session.window_start)
    active = active_stages(ctx.plan, day)
    if stage not in active:
        active = (*active, stage)
    statuses = equipment_states(
        session,
        active,
        transient=ctx.transient,
        enums=ctx.enums,
        class_names=ctx.class_names,
        works_in_place=ctx.works_in_place,
    )
    return any(
        st.state == WORKING and st.area in check.areas and st.equipment_class in required
        for st in statuses
    )


def daily_activity(
    ctx: Context, stage: Stage, since: date | None = None
) -> tuple[DailyActivity, ...]:
    """Индекс активности этапа по местным дням с `since` (раздел 10.2).

    `since` по умолчанию — раньшее из `plan_start` и фактического старта. У этапа без
    правила или без групп `required` комплекта нет, и индекс не считается. После дня
    отметки «выполнен» — тоже: работы этапа кончились (раздел 10.3b).
    """
    if stage.rule is None or not stage.rule.required:
        return ()
    checks = rule_checks(ctx, stage)
    if since is None:
        start = actual_start(ctx, stage, checks)
        since = min(stage.plan_start, start.day) if start else stage.plan_start
    days: dict[date, list[int]] = {}
    last_working: dict[date, datetime] = {}
    for session, check in zip(ctx.sessions, checks, strict=True):
        day = local_date(ctx.calendar, session.window_start)
        if day < since or closed(stage, day):
            continue
        total_working_blind = days.setdefault(day, [0, 0, 0])
        if not check.evaluated:
            # Невидимая сессия не штрафует индекс, а снижает уверенность (раздел 10.2).
            total_working_blind[2] += 1
            continue
        total_working_blind[0] += 1
        if check.complete and _working(ctx, stage, session, check):
            total_working_blind[1] += 1
            last_working[day] = session.window_end
    return tuple(
        DailyActivity(
            stage_id=stage.id,
            day=day,
            sessions_total=total,
            sessions_working=working,
            activity_index=working / total if total else None,
            blind_sessions=blind,
            last_working_at=last_working.get(day),
        )
        for day, (total, working, blind) in days.items()
    )


def daily_equipment(ctx: Context) -> tuple[DailyEquipment, ...]:
    """Загрузка техники по дням и классам (F10): в скольких сессиях и сколько за раз.

    Число за сессию — сумма по участкам и «вне зон»: участки — разные места площадки.
    Опасные зоны накладываются поверх остальных и в сумму не входят, иначе машина в
    опасной зоне котлована посчиталась бы дважды. Человек — не техника.
    """
    seen: dict[tuple[date, str], list[int]] = {}
    for session in ctx.sessions:
        day = local_date(ctx.calendar, session.window_start)
        totals: dict[str, int] = {}
        items = [
            item
            for area in session.areas
            if ctx.enums.role(area.zone_type) != ROLE_SAFETY
            for item in area.equipment
        ]
        for item in (*items, *session.outside_zones):
            totals[item.equipment_class] = totals.get(item.equipment_class, 0) + item.count
        for cls, count in totals.items():
            if cls == PERSON:
                continue
            sessions_max = seen.setdefault((day, cls), [0, 0])
            sessions_max[0] += 1
            sessions_max[1] = max(sessions_max[1], count)
    return tuple(
        DailyEquipment(day=day, equipment_class=cls, sessions_seen=n, max_count=peak)
        for (day, cls), (n, peak) in sorted(seen.items())
    )
