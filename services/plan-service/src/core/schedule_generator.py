"""Генератор синтетического графика по МРР-3.2.81-12 (ТЗ, п. 8; ADR-0011).

Черновик графика, к которому можно привязывать снимки: сроки периодов — из таблицы норм,
раскладка на этапы — по долям шаблона, даты — по рабочему календарю объекта и связям шаблона.
Дальше оператор правит даты сам: нормы предельно допустимые (МРР, п. 4.1).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from src.core.calendar import (
    WorkCalendar,
    add_months,
    add_working_days,
    count_working_days,
    next_working_day,
)
from src.core.cpm import CpmStage, Link, order_stages
from src.core.mrr_norms import (
    Norms,
    NormsError,
    NormsNotAvailable,
    Params,
    period_months,
    piles_working_days,
)
from src.core.templates import TemplateLink, TemplateStage


@dataclass(frozen=True)
class Period:
    """Период таблицы норм в календаре объекта: месяцы МРР, отложенные по обычному календарю."""

    column: str
    title: str
    months: float
    start: date
    # Первый день после периода: с него начинается следующий.
    end: date
    working_days: int


@dataclass(frozen=True)
class GeneratedStage:
    seq: int
    code: str
    name: str
    phase: str
    zone_type: str
    visual_stage: str | None
    plan_start: date
    plan_end: date
    norm_duration_days: int
    work_codes: tuple[str, ...]
    predecessors: tuple[TemplateLink, ...]
    rule: dict[str, Any] | None
    basis: str


@dataclass(frozen=True)
class GeneratedSchedule:
    stages: tuple[GeneratedStage, ...]
    periods: tuple[Period, ...]
    # Общий срок по нормам с коэффициентами, мес., и откуда он.
    total_months: float
    basis: str


def generate_schedule(
    templates: Sequence[TemplateStage],
    norms: Norms,
    params: Params,
    start: date,
    calendar: WorkCalendar,
) -> GeneratedSchedule:
    """График от даты начала: этапы в порядке шаблона с датами, длительностью и основанием."""
    table = period_months(norms, params.floors, params.area)
    shift = norms.shift_coefficients[params.shifts]
    periods = _periods(norms, table.months, shift, start, calendar)
    basis = (
        f"{_cite(norms.table_source)}: {table.basis}; сменность {_num(float(params.shifts))} — "
        f"коэффициент {_num(shift)} ({_cite(norms.shifts_source)})"
    )
    stages = _without_piles(templates) if params.piles == 0 else list(templates)
    durations = {s.code: _duration(s, norms, params, periods, basis) for s in stages}
    dates = _forward_pass(stages, {c: d for c, (d, _) in durations.items()})
    first = next_working_day(calendar, start)
    generated = tuple(
        GeneratedStage(
            seq=seq,
            code=s.code,
            name=s.name,
            phase=s.phase,
            zone_type=s.zone_type,
            visual_stage=s.visual_stage,
            plan_start=add_working_days(calendar, first, dates[s.code][0]),
            plan_end=add_working_days(calendar, first, dates[s.code][1]),
            norm_duration_days=durations[s.code][0],
            work_codes=s.work_codes,
            predecessors=s.predecessors,
            rule=s.rule,
            basis=durations[s.code][1],
        )
        for seq, s in enumerate(stages, start=1)
    )
    total = table.months["total"] * shift
    return GeneratedSchedule(generated, tuple(periods.values()), total, basis)


def check_generator_template(
    object_type: str, templates: Sequence[TemplateStage], norms: Norms
) -> None:
    """Проверка при старте: у типа с нормами есть шаблон, и каждому этапу хватает данных.

    Иначе ошибка всплыла бы только при первой генерации, на демо.
    """
    where = f"mrr_norms.json и wbs_templates.json, {object_type}"
    if not templates:
        raise NormsError(f"{where}: нормы есть, а шаблона этапов нет")
    for stage in templates:
        if stage.piles:
            continue
        if stage.share is None:
            raise NormsError(f"{where}: у этапа {stage.code} нет доли share")
        if stage.phase not in norms.phase_columns:
            raise NormsError(f"{where}: фазе {stage.phase} этапа {stage.code} не задан период")


def _periods(
    norms: Norms,
    months: dict[str, float],
    shift: float,
    start: date,
    calendar: WorkCalendar,
) -> dict[str, Period]:
    """Периоды идут подряд от даты начала; рабочие дни каждого — по календарю объекта."""
    result = {}
    current = next_working_day(calendar, start)
    for column in norms.periods:
        value = months[column] * shift
        end = add_months(current, value)
        working = max(count_working_days(calendar, current, end), 1)
        result[column] = Period(column, norms.titles[column], value, current, end, working)
        current = end
    return result


def _duration(
    stage: TemplateStage,
    norms: Norms,
    params: Params,
    periods: dict[str, Period],
    basis: str,
) -> tuple[int, str]:
    """Длительность этапа в рабочих днях и её обоснование."""
    if stage.piles:
        days, piles_basis = piles_working_days(norms, params.piles, params.sections)
        return max(days, 1), f"{_cite(norms.piles_source)}: {piles_basis}"
    column = norms.phase_columns.get(stage.phase)
    if column is None or stage.share is None:
        raise NormsNotAvailable(
            f"Этап {stage.code}: для фазы {stage.phase} нет периода норм или доли в шаблоне"
        )
    period = periods[column]
    days = max(math.floor(stage.share * period.working_days + 0.5), 1)
    return days, (
        f"{basis}. {period.title.capitalize()} {_num(period.months)} мес.: периоды подряд от "
        f"начала, этот — с {period.start:%d.%m.%Y} по {period.end - timedelta(days=1):%d.%m.%Y}, "
        f"{period.working_days} раб. дн. по календарю объекта; доля этапа "
        f"{_num(stage.share)} (шаблон) = {days} раб. дн."
    )


def _without_piles(templates: Sequence[TemplateStage]) -> list[TemplateStage]:
    """Без свай этап свай выпадает, а его последователи наследуют его предшественников."""
    piles = {s.code: s.predecessors for s in templates if s.piles}
    result = []
    for stage in templates:
        if stage.piles:
            continue
        links: list[TemplateLink] = []
        for link in stage.predecessors:
            inherited = piles.get(link.code)
            for new in inherited if inherited is not None else (link,):
                if all(new.code != known.code for known in links):
                    links.append(new)
        result.append(replace(stage, predecessors=tuple(links)))
    return result


def _forward_pass(
    stages: Sequence[TemplateStage], durations: dict[str, int]
) -> dict[str, tuple[int, int]]:
    """Ранние сроки: номер рабочего дня начала и конца (включительно) от первого рабочего дня.

    Семантика связей — та же, что в core/cpm.py: FS с лагом 0 — следующий рабочий день.
    """
    ids = {s.code: uuid5(NAMESPACE_URL, s.code) for s in stages}
    codes = {v: k for k, v in ids.items()}
    by_code = {s.code: s for s in stages}
    ordered = order_stages(
        [
            CpmStage(
                ids[s.code],
                date.min,
                date.min,
                tuple(Link(ids[p.code], p.type, p.lag_days) for p in s.predecessors),
            )
            for s in stages
        ]
    )
    dates: dict[str, tuple[int, int]] = {}
    for item in ordered:
        stage = by_code[codes[item.id]]
        length = durations[stage.code]
        begin = 0
        for link in stage.predecessors:
            before_start, before_end = dates[link.code]
            begin = max(begin, _earliest_start(link, before_start, before_end, length))
        dates[stage.code] = (begin, begin + length - 1)
    return dates


def _earliest_start(link: TemplateLink, start: int, end: int, length: int) -> int:
    if link.type == "FS":
        return end + 1 + link.lag_days
    if link.type == "SS":
        return start + link.lag_days
    if link.type == "FF":
        return end + link.lag_days - length + 1
    return start + link.lag_days - length + 1  # SF: конец не раньше начала + лаг


def _cite(source: str) -> str:
    """Ссылка из поля source без пояснения: всё до первого «:» или «;»."""
    return source.split(":")[0].split(";")[0].strip()


def _num(value: float) -> str:
    """Число для человека: запятая вместо точки, без лишних нулей."""
    return f"{round(value, 2):g}".replace(".", ",")
