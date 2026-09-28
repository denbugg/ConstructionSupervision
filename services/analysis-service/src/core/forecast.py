"""Прогресс, SPI, прогноз окончания и статус объекта (F9, docs/methodology.md, разделы 8, 10).

Прогноз линеен: сохранится средний темп последних рабочих дней. Сдвиг этапа переносится
на зависимые этапы по связям `predecessors`. Каждое число прогноза сохраняется в `facts`,
а при нехватке данных система говорит «не знаю» (`UNKNOWN`, уверенность `LOW`), а не
выдаёт уверенное число по двум снимкам.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from graphlib import CycleError, TopologicalSorter
from typing import Any
from uuid import UUID

from src.core.activity import ActualStart, DailyActivity, actual_start, daily_activity
from src.core.calendar import (
    Calendar,
    add_working_days,
    count_working_days,
    local_date,
    working_days_between,
)
from src.core.context import Context
from src.core.equipment_state import BLIND
from src.core.inputs import Stage
from src.core.plan_on_date import completion

PARTIAL = "PARTIAL"
HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"
NOT_STARTED, IN_PROGRESS, DONE, LATE, AHEAD = "NOT_STARTED", "IN_PROGRESS", "DONE", "LATE", "AHEAD"
ON_TRACK, DELAY, UNKNOWN = "ON_TRACK", "DELAY", "UNKNOWN"
# Откуда прогресс этапа (facts.basis): снимки, план или отметка оператора «выполнен».
OBSERVED, BY_PLAN, OPERATOR = "OBSERVED", "PLAN", "OPERATOR"
# «В основном» — больше половины: это определение слова, а не калибруемый порог.
MOSTLY = 0.5


class ForecastError(ValueError):
    """План нельзя прогнозировать: цикл в связях или ссылка на неизвестный этап."""


@dataclass(frozen=True)
class ForecastParams:
    """Параметры прогноза и уверенности из окружения (docs/methodology.md, раздел 11)."""

    min_activity: float
    forecast_window_days: int
    min_days_for_forecast: int
    on_track_tolerance_days: int
    confidence_high_days: int
    confidence_high_visible: float
    confidence_medium_visible: float
    unknown_blind_share: float


@dataclass(frozen=True)
class VisibilityShare:
    """Сколько пар «сессия × участок» было видно и сколько — лишь частично."""

    pairs: int
    visible: int
    partial: int

    @property
    def share(self) -> float:
        return self.visible / self.pairs if self.pairs else 0.0

    @property
    def partial_share(self) -> float:
        return self.partial / self.visible if self.visible else 0.0


@dataclass(frozen=True)
class StageForecast:
    """Строка stage_fact: факт, прогресс и прогноз этапа на `as_of`."""

    stage_id: UUID
    actual_start: date | None
    last_activity_at: datetime | None
    effective_days: float
    progress: float
    planned_progress: float | None
    spi: float | None
    # Ожидаемые даты с учётом темпа и связей; по ним строится перенос на зависимые этапы.
    expected_start: date
    expected_end: date
    # None — прогноз по темпу не строился: наблюдений меньше MIN_DAYS_FOR_FORECAST.
    forecast_end: date | None
    delay_days: int | None
    status: str
    confidence: str
    facts: dict[str, Any]


@dataclass(frozen=True)
class ObjectForecast:
    """Строка object_status без счётчиков отклонений: их добавляет прогон."""

    status: str
    delay_days: int | None
    spi: float | None
    confidence: str
    stages_at_risk: tuple[dict[str, Any], ...]
    facts: dict[str, Any]


@dataclass(frozen=True)
class Forecast:
    stages: tuple[StageForecast, ...]
    object: ObjectForecast


def last_confident_stage(ctx: Context) -> str | None:
    """Последняя уверенная стадия по фото: неуверенная ничего не ограничивает (раздел 8)."""
    for session in reversed(ctx.sessions):
        observation = session.stage_observation
        if observation is not None and observation.conf >= ctx.params.min_stage_conf:
            return observation.stage_label
    return None


def visibility(
    ctx: Context, zone_type: str | None = None, since: date | None = None
) -> VisibilityShare:
    """Видимость участков (всех или одного типа) по рабочим сессиям с `since`."""
    pairs = visible = partial = 0
    for session in ctx.sessions:
        if since is not None and local_date(ctx.calendar, session.window_start) < since:
            continue
        for area in session.areas:
            if zone_type is not None and area.zone_type != zone_type:
                continue
            pairs += 1
            if area.visibility.status != BLIND:
                visible += 1
                partial += area.visibility.status == PARTIAL
    return VisibilityShare(pairs, visible, partial)


def confidence(
    fp: ForecastParams,
    days: int,
    seen: VisibilityShare,
    *,
    consistent: bool = True,
    floored: bool = False,
) -> str:
    """Уверенность вывода по таблице раздела 10.8.

    `consistent` — стадия по фото не противоречит прогрессу; `floored` — прогноз упёрся
    в MIN_ACTIVITY. Если видимые сессии в основном частичные (PARTIAL), уверенность ниже
    на шаг (раздел 7).
    """
    if floored:
        return LOW
    if days >= fp.confidence_high_days and seen.share > fp.confidence_high_visible and consistent:
        level = HIGH
    elif days >= fp.min_days_for_forecast and seen.share > fp.confidence_medium_visible:
        level = MEDIUM
    else:
        return LOW
    if seen.partial_share > MOSTLY:
        return MEDIUM if level == HIGH else LOW
    return level


def planned_progress(calendar: Calendar, stage: Stage, today: date) -> float | None:
    """Доля рабочих дней этапа, прошедших к `today` включительно (раздел 10.4).

    None — в окне этапа нет ни одного рабочего дня, и доля не определена.
    """
    total = count_working_days(calendar, stage.plan_start, stage.plan_end)
    if total == 0:
        return None
    passed = count_working_days(calendar, stage.plan_start, min(today, stage.plan_end))
    return passed / total


def observation_start(ctx: Context, zone_type: str) -> date | None:
    """Начало наблюдений участка: дата первой рабочей сессии, где он виден (раздел 10.3a)."""
    for session in ctx.sessions:
        for area in session.areas:
            if area.zone_type == zone_type and area.visibility.status != BLIND:
                return local_date(ctx.calendar, session.window_start)
    return None


@dataclass(frozen=True)
class _Observed:
    """Что видно по этапу к `as_of`: старт, эффективные дни, темп."""

    start: ActualStart | None
    rows: tuple[DailyActivity, ...]
    effective_days: float
    progress: float
    restricted: bool
    done_day: date | None
    observed_days: int
    avg_activity: float | None
    # Плановый прогресс за дни до начала наблюдений, в эффективных днях; 0 — не было таких.
    credited_days: float


def _observe(
    ctx: Context,
    fp: ForecastParams,
    stage: Stage,
    today: date,
    last_label: str | None,
    observed_from: date | None,
) -> _Observed:
    start = actual_start(ctx, stage)
    rows = daily_activity(ctx, stage, since=start.day) if start else ()
    # Пока объект на фото не дошёл до стадии этапа, прогресс не засчитывается (раздел 8).
    restricted = (
        stage.visual_stage is not None
        and last_label is not None
        and ctx.enums.stage_index(last_label) < ctx.enums.stage_index(stage.visual_stage)
    )
    credited = 0.0
    if start is not None and observed_from is not None and stage.plan_start < observed_from:
        # Этап шёл по плану, пока его участок не начали наблюдать (раздел 10.3a).
        before = planned_progress(ctx.calendar, stage, observed_from - timedelta(days=1))
        credited = (before or 0.0) * stage.norm_duration_days
    effective, done_day = credited, None
    for row in rows:
        effective += row.activity_index or 0.0
        if done_day is None and not restricted and effective >= stage.norm_duration_days:
            done_day = row.day
    known = {r.day: r.activity_index for r in rows if r.activity_index is not None}
    window = [add_working_days(ctx.calendar, today, -i) for i in range(fp.forecast_window_days)]
    recent = [known[d] for d in window if d in known]
    return _Observed(
        start=start,
        rows=rows,
        effective_days=effective,
        progress=0.0 if restricted else min(effective / stage.norm_duration_days, 1.0),
        restricted=restricted,
        done_day=done_day,
        observed_days=len(known),
        avg_activity=sum(recent) / len(recent) if recent else None,
        credited_days=credited,
    )


def _constraints(
    calendar: Calendar, stage: Stage, dates: dict[UUID, tuple[date, date]]
) -> tuple[date | None, date | None]:
    """Самые ранние начало и конец этапа по связям с ожидаемыми датами предшественников.

    Лаг — в рабочих днях календаря объекта. FS с лагом 0 — следующий рабочий день.
    """
    start_min: date | None = None
    end_min: date | None = None
    for link in stage.predecessors:
        if link.stage_id not in dates:
            raise ForecastError(
                f"Этап {stage.name!r} ссылается на неизвестный этап {link.stage_id}"
            )
        pred_start, pred_end = dates[link.stage_id]
        if link.type == "FS":
            start_min = _later(start_min, add_working_days(calendar, pred_end, 1 + link.lag_days))
        elif link.type == "SS":
            start_min = _later(start_min, add_working_days(calendar, pred_start, link.lag_days))
        elif link.type == "FF":
            end_min = _later(end_min, add_working_days(calendar, pred_end, link.lag_days))
        elif link.type == "SF":
            end_min = _later(end_min, add_working_days(calendar, pred_start, link.lag_days))
        else:
            raise ForecastError(f"Неизвестный тип связи {link.type!r} у этапа {stage.name!r}")
    return start_min, end_min


def _later(current: date | None, candidate: date) -> date:
    return candidate if current is None or candidate > current else current


def _order(stages: tuple[Stage, ...]) -> list[Stage]:
    """Этапы в порядке связей: предшественник раньше последователя."""
    by_id = {s.id: s for s in stages}
    graph = {s.id: {p.stage_id for p in s.predecessors} for s in stages}
    try:
        order = list(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        raise ForecastError(f"Цикл в связях этапов: {exc.args[1]}") from exc
    missing = [i for i in order if i not in by_id]
    if missing:
        raise ForecastError(f"Связь ссылается на неизвестный этап: {missing[0]}")
    return [by_id[i] for i in order]


def _status(fp: ForecastParams, delay: int | None) -> str:
    if delay is None:
        return IN_PROGRESS
    if delay > fp.on_track_tolerance_days:
        return LATE
    if delay < -fp.on_track_tolerance_days:
        return AHEAD
    return IN_PROGRESS


def _unobservable(
    ctx: Context, stage: Stage, today: date, start: date, end: date, reason: str
) -> StageForecast:
    """Этап не проверить по фото: он идёт по плану со сдвигом только по связям."""
    planned = planned_progress(ctx.calendar, stage, today)
    if today < start:
        status = NOT_STARTED
    elif today > end:
        status = DONE
    else:
        status = IN_PROGRESS
    return StageForecast(
        stage_id=stage.id,
        actual_start=None,
        last_activity_at=None,
        effective_days=0.0,
        progress=planned or 0.0,
        planned_progress=planned,
        spi=None,
        expected_start=start,
        expected_end=end,
        forecast_end=end,
        delay_days=working_days_between(ctx.calendar, stage.plan_end, end),
        status=status,
        confidence=LOW,
        facts={"basis": BY_PLAN, "basis_reason": reason},
    )


def _by_mark(
    ctx: Context,
    stage: Stage,
    today: date,
    by_plan_start: date,
    marked: date,
    obs: _Observed | None,
) -> StageForecast:
    """Этап закрыт отметкой оператора (раздел 10.3b): выполнен в дату отметки.

    Отметка сильнее снимков, но старт — только по снимкам: если сигнатура не собралась
    до отметки или этап шёл до начала наблюдений, он неизвестен, а для связей — плановый.
    """
    before_observation = obs is not None and obs.credited_days > 0
    start = obs.start if obs is not None and not before_observation else None
    planned = planned_progress(ctx.calendar, stage, today)
    last_activity = [r.last_working_at for r in obs.rows if r.last_working_at] if obs else []
    return StageForecast(
        stage_id=stage.id,
        actual_start=start.day if start else None,
        last_activity_at=last_activity[-1] if last_activity else None,
        effective_days=round(obs.effective_days, 3) if obs else 0.0,
        progress=1.0,
        planned_progress=round(planned, 4) if planned is not None else None,
        spi=round(1 / planned, 3) if planned else None,
        expected_start=start.day if start else min(by_plan_start, marked),
        expected_end=marked,
        forecast_end=marked,
        delay_days=working_days_between(ctx.calendar, stage.plan_end, marked),
        status=DONE,
        # Окончание подтвердил человек, а не темп по снимкам.
        confidence=HIGH,
        facts={
            "basis": OPERATOR,
            "completed_on": marked.isoformat(),
            "completed_by": stage.completed_by,
            "completion_note": stage.completion_note,
            "norm_duration_days": stage.norm_duration_days,
            "start_deviation_days": start.start_deviation_days if start else None,
            "started_before_observation": before_observation,
        },
    )


def _stage_forecast(
    ctx: Context,
    fp: ForecastParams,
    stage: Stage,
    today: date,
    last_label: str | None,
    dates: dict[UUID, tuple[date, date]],
) -> StageForecast:
    start_min, end_min = _constraints(ctx.calendar, stage, dates)
    duration = max(count_working_days(ctx.calendar, stage.plan_start, stage.plan_end), 1)
    by_plan_start = max(stage.plan_start, start_min or stage.plan_start)
    by_plan_end = max(
        add_working_days(ctx.calendar, by_plan_start, duration - 1), end_min or by_plan_start
    )
    marked = completion(stage, today)
    if marked is not None:
        obs = None
        if stage.rule is not None:
            observed_from = observation_start(ctx, stage.zone_type)
            obs = _observe(ctx, fp, stage, today, last_label, observed_from)
        return _by_mark(ctx, stage, today, by_plan_start, marked, obs)
    if stage.rule is None:
        reason = "у этапа нет правила: по снимкам его не проверить, прогресс — по плану"
        return _unobservable(ctx, stage, today, by_plan_start, by_plan_end, reason)

    observed_from = observation_start(ctx, stage.zone_type)
    obs = _observe(ctx, fp, stage, today, last_label, observed_from)
    # «Не видно» — не «не начато» (раздел 7): участок этапа с его начала ни разу не был виден,
    # и считать его опоздавшим не на чем.
    if obs.start is None and visibility(ctx, stage.zone_type, since=stage.plan_start).visible == 0:
        reason = "участок этапа с плановой даты начала ни разу не был виден — прогресс по плану"
        return _unobservable(ctx, stage, today, by_plan_start, by_plan_end, reason)
    # Всё окно этапа — до начала наблюдений, и после него работ этапа не видно (раздел 10.3a).
    if obs.start is None and observed_from is not None and stage.plan_end < observed_from:
        reason = "плановое окно этапа закончилось до начала наблюдений — выполнен по плану"
        return _unobservable(ctx, stage, today, by_plan_start, by_plan_end, reason)
    # Этап шёл до начала наблюдений: его настоящий старт снимки не застали.
    before_observation = obs.credited_days > 0
    floored = False
    remaining = None
    if obs.done_day is not None:
        start = by_plan_start if before_observation else obs.start.day
        end, forecast_end, status = obs.done_day, obs.done_day, DONE
    elif obs.start is not None:
        start = by_plan_start if before_observation else obs.start.day
        forecast_end = None
        if obs.observed_days >= fp.min_days_for_forecast and obs.avg_activity is not None:
            rate = max(obs.avg_activity, fp.min_activity)
            floored = obs.avg_activity < fp.min_activity
            remaining = (1 - obs.progress) * stage.norm_duration_days / rate
            forecast_end = add_working_days(ctx.calendar, today, math.ceil(remaining))
        # Без прогноза по темпу для связей берём план, но не раньше сегодняшнего дня.
        end = max(forecast_end or max(stage.plan_end, today), end_min or start)
        if forecast_end is not None:
            forecast_end = end
        status = None
    else:
        # Не начат, хотя участок видели: раньше «сегодня» уже не начнётся, раньше
        # предшественников — тоже.
        start = max(by_plan_start, today)
        end = max(add_working_days(ctx.calendar, start, duration - 1), end_min or start)
        forecast_end = end
        status = LATE if today > stage.plan_start else NOT_STARTED

    delay = (
        working_days_between(ctx.calendar, stage.plan_end, forecast_end)
        if forecast_end is not None
        else None
    )
    if status is None:
        status = _status(fp, delay)
    planned = planned_progress(ctx.calendar, stage, today)
    spi = obs.progress / planned if planned else None
    seen = visibility(ctx, stage.zone_type, since=obs.start.day if obs.start else stage.plan_start)
    last_activity = [r.last_working_at for r in obs.rows if r.last_working_at is not None]
    return StageForecast(
        stage_id=stage.id,
        actual_start=obs.start.day if obs.start and not before_observation else None,
        last_activity_at=last_activity[-1] if last_activity else None,
        effective_days=round(obs.effective_days, 3),
        progress=round(obs.progress, 4),
        planned_progress=round(planned, 4) if planned is not None else None,
        spi=round(spi, 3) if spi is not None else None,
        expected_start=start,
        expected_end=end,
        forecast_end=forecast_end,
        delay_days=delay,
        status=status,
        confidence=confidence(
            fp, obs.observed_days, seen, consistent=not obs.restricted, floored=floored
        ),
        facts={
            "basis": OBSERVED,
            "norm_duration_days": stage.norm_duration_days,
            "start_deviation_days": (
                obs.start.start_deviation_days if obs.start and not before_observation else None
            ),
            "started_before_observation": before_observation,
            "observation_start": observed_from.isoformat() if observed_from else None,
            "credited_days": round(obs.credited_days, 3),
            "observed_days": obs.observed_days,
            "avg_activity": round(obs.avg_activity, 3) if obs.avg_activity is not None else None,
            "forecast_window_days": fp.forecast_window_days,
            "min_activity": fp.min_activity,
            "floored_by_min_activity": floored,
            "remaining_days": round(remaining, 2) if remaining is not None else None,
            "progress_raw": round(obs.effective_days / stage.norm_duration_days, 4),
            "progress_limited_by_stage": obs.restricted,
            "last_confident_stage": last_label,
            "visual_stage": stage.visual_stage,
            "visible_share": round(seen.share, 3),
            "shifted_by_predecessors": start_min is not None and start_min > stage.plan_start,
        },
    )


def _object_forecast(
    ctx: Context, fp: ForecastParams, stages: dict[UUID, Stage], results: list[StageForecast]
) -> ObjectForecast:
    """Статус объекта по этапам критического пути (разделы 10.6–10.8)."""
    days = len({local_date(ctx.calendar, s.window_start) for s in ctx.sessions})
    seen = visibility(ctx)
    critical = [
        r for r in results if stages[r.stage_id].total_float_days == 0 and r.delay_days is not None
    ]
    at_risk = tuple(
        {
            "stage_id": str(r.stage_id),
            "name": stages[r.stage_id].name,
            "plan_end": stages[r.stage_id].plan_end.isoformat(),
            "forecast_end": r.forecast_end.isoformat(),
            "delay_days": r.delay_days,
        }
        for r in sorted(critical, key=lambda r: -r.delay_days)
        if r.delay_days > 0 and r.status != DONE
    )
    # Этап по отметке оператора входит в SPI: его освоенный объём подтверждён (раздел 10.3b).
    observable = [
        r for r in results if r.facts["basis"] in (OBSERVED, OPERATOR) and r.planned_progress
    ]
    earned = sum(r.progress * stages[r.stage_id].norm_duration_days for r in observable)
    scheduled = sum(r.planned_progress * stages[r.stage_id].norm_duration_days for r in observable)
    spi = round(earned / scheduled, 3) if scheduled else None
    delay = max((r.delay_days for r in critical), default=None)
    facts = {
        "observation_days": days,
        "visible_share": round(seen.share, 3),
        "min_days_for_forecast": fp.min_days_for_forecast,
        "unknown_blind_share": fp.unknown_blind_share,
        "delay_days_by_critical_path": delay,
        "spi_by_norm_weights": spi,
    }
    blind_share = 1 - seen.share if seen.pairs else 1.0
    if days < fp.min_days_for_forecast or blind_share > fp.unknown_blind_share or delay is None:
        return ObjectForecast(UNKNOWN, None, None, LOW, at_risk, facts)
    if delay > fp.on_track_tolerance_days:
        status = DELAY
    elif delay < -fp.on_track_tolerance_days:
        status = AHEAD
    else:
        status = ON_TRACK
    worst = [r for r in critical if r.delay_days == delay]
    level = confidence(
        fp,
        days,
        seen,
        consistent=not any(r.facts.get("progress_limited_by_stage") for r in results),
        floored=any(r.facts.get("floored_by_min_activity") for r in worst),
    )
    return ObjectForecast(status, delay, spi, level, at_risk, facts)


def forecast(ctx: Context, fp: ForecastParams) -> Forecast:
    """Прогноз всех этапов и статус объекта на `ctx.as_of`."""
    today = local_date(ctx.calendar, ctx.as_of)
    last_label = last_confident_stage(ctx)
    dates: dict[UUID, tuple[date, date]] = {}
    results = []
    for stage in _order(ctx.plan.stages):
        result = _stage_forecast(ctx, fp, stage, today, last_label, dates)
        dates[stage.id] = (result.expected_start, result.expected_end)
        results.append(result)
    by_id = {s.id: s for s in ctx.plan.stages}
    # В ответе — порядок графика, а не порядок обхода связей.
    results.sort(key=lambda r: by_id[r.stage_id].seq)
    return Forecast(tuple(results), _object_forecast(ctx, fp, by_id, results))
