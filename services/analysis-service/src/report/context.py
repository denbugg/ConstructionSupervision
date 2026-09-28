"""Контекст PDF-отчёта: восемь разделов из готовых выводов (README, раздел 5).

Отчёт оформляет выводы, а не делает новые: каждое число здесь — поле статуса, этапы,
загрузки техники, отклонения или фактов периода. Считаются только суммы и доли для таблиц
(прогресс фазы — средний по нормативным длительностям, как SPI объекта в методике, 10.6).
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from src.core.calendar import calendar_from_plan, is_working_session, local_date
from src.report.charts import equipment_svg, gantt_svg
from src.report.model import DeviationSnapshot, ReportInput

# Вердикт, при котором отклонение в доказательства отчёта не идёт: оператор назвал его ложным.
REJECTED = "REJECTED"
# Код отклонения «участок вне контроля ИИ» — его эпизоды перечисляются в «Ограничениях».
BLIND_CODE = "D10"
# Этап закрыт отметкой оператора (stage_fact.facts.basis, methodology.md, 10.3b).
OPERATOR = "OPERATOR"


@dataclass(frozen=True)
class EvidencePick:
    """Какой снимок какого отклонения показать и какие рамки на нём выделить."""

    deviation: DeviationSnapshot
    image_id: UUID
    detection_ids: frozenset[str]


def period_bounds(inp: ReportInput) -> tuple[datetime, datetime]:
    """Период отчёта — местные сутки [period_from, period_to] включительно, в UTC."""
    tz = calendar_from_plan(inp.plan.calendar).tz
    start = datetime.combine(inp.period_from, time(0), tzinfo=tz)
    end = datetime.combine(inp.period_to + timedelta(days=1), time(0), tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def deviations_in_period(inp: ReportInput) -> list[DeviationSnapshot]:
    """Эпизоды, пересекающиеся с периодом: сначала серьёзные, внутри — по началу."""
    start, end = period_bounds(inp)
    rank = {s: i for i, s in enumerate(inp.severity_order)}
    found = [d for d in inp.deviations if d.last_seen_at > start and d.first_seen_at < end]
    return sorted(found, key=lambda d: (-rank.get(d.severity, -1), d.first_seen_at, d.code))


def pick_evidence(
    deviations: Sequence[DeviationSnapshot], severity_order: Sequence[str], limit: int
) -> list[EvidencePick]:
    """По снимку на отклонение, от серьёзных к лёгким, без признанных ложными."""
    rank = {s: i for i, s in enumerate(severity_order)}
    candidates = [
        d
        for d in deviations
        if d.evidence and REJECTED not in (d.status, d.verdict) and d.evidence[0].get("image_id")
    ]
    candidates.sort(key=lambda d: (-rank.get(d.severity, -1), -d.last_seen_at.timestamp()))
    return [
        EvidencePick(
            deviation=d,
            image_id=UUID(str(d.evidence[0]["image_id"])),
            detection_ids=frozenset(str(i) for i in d.evidence[0].get("detection_ids", ())),
        )
        for d in candidates[:limit]
    ]


def build_context(inp: ReportInput) -> dict[str, Any]:
    """Всё, что нужно шаблону: по ключу на раздел."""
    cal = calendar_from_plan(inp.plan.calendar)
    as_of = local_date(cal, inp.status.as_of)
    stages = {s.id: s for s in inp.plan.stages}
    facts = {f.stage_id: f for f in inp.stages}
    deviations = deviations_in_period(inp)
    days = [
        inp.period_from + timedelta(days=i)
        for i in range((inp.period_to - inp.period_from).days + 1)
    ]
    names = {c.code: c.name_ru for c in inp.plan.equipment_classes}
    equipment = [e for e in inp.equipment if inp.period_from <= e.day <= inp.period_to]
    return {
        "title": _title(inp, as_of, cal.tz),
        "summary": _summary(inp, facts),
        "gantt": gantt_svg(inp.plan.stages, facts, as_of) if inp.plan.stages else None,
        "equipment": equipment_svg(equipment, days, names) if equipment else None,
        "deviations": [_deviation_row(inp, d, stages, cal.tz) for d in deviations],
        "evidence": _evidence(inp, stages, cal.tz),
        "limitations": limitations(inp, deviations),
        "counts": {
            "deviations": len(deviations),
            "open": sum(d.status in ("NEW", "CONFIRMED") for d in deviations),
            "by_code": sorted(Counter(d.code for d in deviations).items()),
        },
    }


def _title(inp: ReportInput, as_of: date, tz) -> dict[str, Any]:
    status = inp.status
    return {
        "object": inp.plan.object.name,
        "period": f"{inp.period_from:%d.%m.%Y} — {inp.period_to:%d.%m.%Y}",
        "generated_at": f"{inp.generated_at.astimezone(tz):%d.%m.%Y %H:%M}",
        "as_of": f"{inp.status.as_of.astimezone(tz):%d.%m.%Y %H:%M}",
        "as_of_day": as_of,
        "status": inp.labels.of("object_status", status.status),
        "status_code": status.status,
        "delay": _signed(status.delay_days),
        "spi": _spi(status.spi),
        "confidence": inp.labels.of("confidence", status.confidence),
        "plan_version": inp.plan.plan_version,
    }


def _summary(inp: ReportInput, facts: dict) -> dict[str, Any]:
    """SPI, прогресс по фазам (веса — нормативные длительности), этапы в риске."""
    phases: dict[str, dict[str, float]] = {}
    for stage in inp.plan.stages:
        fact = facts.get(stage.id)
        if fact is None:
            continue
        row = phases.setdefault(stage.phase, {"stages": 0, "norm": 0, "plan": 0.0, "fact": 0.0})
        row["stages"] += 1
        row["norm"] += stage.norm_duration_days
        row["plan"] += fact.planned_progress * stage.norm_duration_days
        row["fact"] += fact.progress * stage.norm_duration_days
    return {
        "spi": _spi(inp.status.spi),
        "observation": inp.status.facts,
        "phases": [
            {
                "phase": inp.labels.of("construction_phase", phase),
                "stages": int(row["stages"]),
                "plan": _percent(row["plan"] / row["norm"]),
                "fact": _percent(row["fact"] / row["norm"]),
            }
            for phase, row in phases.items()
            if row["norm"]
        ],
        "at_risk": [
            {
                "name": str(r.get("name", "—")),
                "plan_end": _date(r.get("plan_end")),
                "forecast_end": _date(r.get("forecast_end")),
                "delay": _signed(r.get("delay_days")),
            }
            for r in inp.status.stages_at_risk
        ],
        "stage_statuses": sorted(
            Counter(inp.labels.of("stage_fact_status", f.status) for f in inp.stages).items()
        ),
    }


def _deviation_row(inp: ReportInput, d: DeviationSnapshot, stages: dict, tz) -> dict[str, str]:
    stage = stages.get(d.stage_id)
    status = inp.labels.of("deviation_status", d.status)
    if d.verdict and d.verdict != d.status:
        status += f", {inp.labels.of('verdict', d.verdict)}"
    return {
        "id": str(d.id)[:8],
        "code": d.code,
        "severity": inp.labels.of("severity", d.severity),
        "severity_code": d.severity,
        "stage": f"{stage.code} {stage.name}" if stage else "—",
        "area": area_name(inp, d.area),
        "title": d.title,
        "message": d.message,
        "period": f"{d.first_seen_at.astimezone(tz):%d.%m %H:%M} — "
        f"{d.last_seen_at.astimezone(tz):%d.%m %H:%M}",
        "status": status,
    }


def _evidence(inp: ReportInput, stages: dict, tz) -> list[dict[str, Any]]:
    out = []
    by_id = {d.id: d for d in inp.deviations}
    for image in inp.evidence:
        d = by_id.get(image.deviation_id)
        if d is None:
            continue
        out.append(
            {
                "deviation": _deviation_row(inp, d, stages, tz),
                "image": image,
                "captured_at": (
                    f"{image.captured_at.astimezone(tz):%d.%m.%Y %H:%M}"
                    if image.captured_at
                    else "—"
                ),
            }
        )
    return out


def limitations(inp: ReportInput, deviations: Sequence[DeviationSnapshot]) -> list[str]:
    """Раздел 8: чего система за период не видела и насколько можно верить выводам.

    Обязательный раздел (README, раздел 5): отчёт, умалчивающий о слепых зонах,
    недобросовестен. Пустым он не бывает — уверенность выводов есть всегда.
    """
    out: list[str] = []
    status = inp.status
    days = status.facts.get("observation_days")
    share = status.facts.get("visible_share")
    confidence = inp.labels.of("confidence", status.confidence)
    basis = f"дней наблюдений: {days if days is not None else '—'}"
    if isinstance(share, int | float):
        basis += f", доля сессий с видимыми участками: {_percent(share)}"
    out.append(f"Уверенность выводов — {confidence} ({basis}).")

    out.extend(_blind_areas(inp))

    blind = [d for d in deviations if d.code == BLIND_CODE]
    if blind:
        out.append(
            f"Отклонений «{inp.labels.of('deviation_code', BLIND_CODE)}» за период: {len(blind)} — "
            + "; ".join(sorted({area_name(inp, d.area) for d in blind}))
            + "."
        )

    by_plan = [f for f in inp.stages if f.basis == "PLAN"]
    if by_plan:
        out.append(
            f"Этапов, прогресс которых взят по плану, а не по наблюдениям: {len(by_plan)} — они "
            "прошли до начала наблюдений или их участки не были видны; снимками они не проверены."
        )
    out.extend(_marked_stages(inp))

    if inp.images_without_time is None:
        out.append("Число снимков без времени съёмки неизвестно: site-service не ответил.")
    elif inp.images_without_time:
        out.append(
            f"Снимков без времени съёмки: {inp.images_without_time} — они не отнесены ни к одной "
            "сессии и в анализ не вошли, пока время не введут вручную."
        )
    else:
        out.append("Снимков без времени съёмки нет.")

    if inp.facts is not None and inp.facts.pending_images:
        out.append(
            f"Нераспознанных снимков в периоде: {inp.facts.pending_images} — факты периода "
            "неполные."
        )

    _, end = period_bounds(inp)
    if status.as_of < end - timedelta(days=1):
        local = status.as_of.astimezone(calendar_from_plan(inp.plan.calendar).tz)
        out.append(
            f"Анализ посчитан на {local:%d.%m.%Y %H:%M}: более поздние дни периода в выводах "
            "не учтены."
        )

    missing = [e for e in inp.evidence if e.problem]
    if missing:
        out.append(
            f"Снимков-доказательств не удалось вставить: {len(missing)} ("
            + "; ".join(sorted({e.problem for e in missing if e.problem}))
            + ")."
        )
    out.append(
        "Прогноз окончания — при сохранении текущего темпа; техника распознаётся по снимкам "
        "раз в 30 минут, машины между снимками не видны."
    )
    return out


def _marked_stages(inp: ReportInput) -> list[str]:
    """Этапы, закрытые отметкой оператора: отметка сильнее снимков, поэтому видно, кем и когда."""
    plan = {s.id: s for s in inp.plan.stages}
    marked = [
        plan[f.stage_id]
        for f in inp.stages
        if f.basis == OPERATOR and f.stage_id in plan and plan[f.stage_id].completed_on
    ]
    if not marked:
        return []
    items = [
        f"«{s.name}» — {s.completed_on:%d.%m.%Y}"
        + (f", {s.completed_by}" if s.completed_by else "")
        for s in marked
    ]
    return [
        f"Этапов, закрытых отметкой оператора «выполнен»: {len(marked)} ({'; '.join(items)}). "
        "Их окончание подтвердил человек, а не снимки; со следующего дня после отметки "
        "отклонения по ним не ищутся."
    ]


def _blind_areas(inp: ReportInput) -> list[str]:
    """Слепые участки за период по фактам: сколько рабочих сессий участок не был виден."""
    if inp.facts is None:
        return ["Факты периода не получены (site-service не ответил): слепые участки не оценены."]
    cal = calendar_from_plan(inp.plan.calendar)
    working = [
        s for s in inp.facts.sessions if is_working_session(cal, s.window_start, s.window_end)
    ]
    if not working:
        return ["За период нет рабочих сессий с распознанными снимками: объект не наблюдался."]
    blind: Counter[str] = Counter()
    reasons: dict[str, Counter[str]] = {}
    for session in working:
        for area in session.areas:
            if area.visibility.status == "BLIND":
                blind[area.area] += 1
                reason = inp.labels.of("visibility_reason", area.visibility.reason)
                reasons.setdefault(area.area, Counter())[reason] += 1
    if not blind:
        return [f"Все участки были видны во всех {len(working)} рабочих сессиях периода."]
    lines = [
        f"«{area_name(inp, area)}» не виден в {count} из {len(working)} рабочих сессий "
        f"({', '.join(r for r, _ in reasons[area].most_common())}) — участок вне контроля ИИ, "
        "проверить вручную."
        for area, count in blind.most_common()
    ]
    return lines


def area_name(inp: ReportInput, area: str | None) -> str:
    """`ТИП:Название` → «Название»; составной ключ D1/D2 — через « + »; без участка — «—»."""
    if not area:
        return "—"
    if area == "OUTSIDE":
        return "вне зон"
    parts = []
    for key in area.split(" + "):
        zone_type, _, name = key.partition(":")
        parts.append(name or inp.labels.zone_types.get(zone_type, zone_type))
    return " + ".join(parts)


def _signed(value: Any) -> str:
    if not isinstance(value, int):
        return "—"
    return f"+{value}" if value > 0 else (f"−{abs(value)}" if value < 0 else "0")


def _spi(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _percent(value: float) -> str:
    return f"{round(value * 100)} %"


def _date(value: Any) -> str:
    if isinstance(value, date):
        return f"{value:%d.%m.%Y}"
    if isinstance(value, str) and value:
        try:
            return f"{date.fromisoformat(value):%d.%m.%Y}"
        except ValueError:
            return value
    return "—"
