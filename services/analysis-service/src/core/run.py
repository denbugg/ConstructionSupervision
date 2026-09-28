"""Прогон методики целиком: план + факты + момент `as_of` → все выводы (F7–F9).

Чистая функция: ни БД, ни сети. Результат зависит только от входа, поэтому повторный
вызов даёт тот же результат, а сервис (T15) может пересчитывать всё с нуля на каждый
сигнал и сверять отклонения с базой по ключу (analysis-service README, раздел 4).
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from src.core.activity import DailyActivity, DailyEquipment, daily_activity, daily_equipment
from src.core.context import Context, build_context
from src.core.enums import Enums
from src.core.equipment_state import BLIND
from src.core.explain import Deviation, describe
from src.core.forecast import ForecastParams, ObjectForecast, StageForecast, forecast
from src.core.inputs import Facts, Plan
from src.core.predicates import DeviationRule, evaluate
from src.core.rules import RuleParams


class RunError(ValueError):
    """Вход прогона несогласован: план и факты относятся к разным объектам."""


@dataclass(frozen=True)
class AnalysisResult:
    """Всё, что прогон записывает в analysisdb: отклонения, факт по этапам, агрегаты, статус."""

    object_id: UUID
    as_of: datetime
    plan_version: int
    zones_version: int
    deviations: tuple[Deviation, ...]
    stage_facts: tuple[StageForecast, ...]
    daily_activity: tuple[DailyActivity, ...]
    daily_equipment: tuple[DailyEquipment, ...]
    object_status: ObjectForecast
    # Счётчики для дашборда: отклонения по серьёзности, слепые участки, этапы по статусам.
    counters: dict[str, Any]
    stats: dict[str, Any]


def _counters(
    ctx: Context, deviations: tuple[Deviation, ...], stages: tuple[StageForecast, ...]
) -> dict[str, Any]:
    """Счётчики object_status: только то, что держится на `as_of`."""
    active = [d.finding for d in deviations if d.finding.active]
    by_status = Counter(s.status for s in stages)
    last = ctx.sessions[-1] if ctx.sessions else None
    return {
        "deviations": dict(sorted(Counter(f.severity for f in active).items())),
        # Слепые на as_of — участки, не видимые в последней рабочей сессии.
        "blind_areas": sum(a.visibility.status == BLIND for a in last.areas) if last else 0,
        "stages": {"total": len(stages)} | {k.lower(): v for k, v in sorted(by_status.items())},
    }


def analyze(
    plan: Plan,
    facts: Facts,
    *,
    rules: tuple[DeviationRule, ...],
    enums: Enums,
    params: RuleParams,
    forecast_params: ForecastParams,
    as_of: datetime | None = None,
) -> AnalysisResult:
    """Прогон по объекту на момент `as_of` (по умолчанию — конец последней сессии с фактами)."""
    if facts.object_id != plan.object.id:
        raise RunError(
            f"Факты объекта {facts.object_id} не относятся к плану объекта {plan.object.id}"
        )
    ctx = build_context(plan, facts, enums=enums, params=params, as_of=as_of)
    by_code = {r.code: r for r in rules}
    findings = sorted(evaluate(ctx, rules), key=lambda f: (f.first_seen_at, f.code, str(f.key)))
    deviations = tuple(describe(f, by_code[f.code], ctx.class_names) for f in findings)
    result = forecast(ctx, forecast_params)
    started = {s.stage_id for s in result.stages if s.actual_start is not None}
    # Не начатый этап после своих плановых дат дал бы только строки «не видно»: это шум,
    # а не факт. Её опоздание и так видно по статусу и прогнозу.
    activity = tuple(
        row
        for stage in plan.stages
        for row in daily_activity(ctx, stage)
        if stage.id in started or row.day <= stage.plan_end
    )
    return AnalysisResult(
        object_id=plan.object.id,
        as_of=ctx.as_of,
        plan_version=plan.plan_version,
        zones_version=facts.zones_version,
        deviations=deviations,
        stage_facts=result.stages,
        daily_activity=activity,
        daily_equipment=daily_equipment(ctx),
        object_status=result.object,
        counters=_counters(ctx, deviations, result.stages),
        stats={
            "sessions": len(facts.sessions),
            "sessions_working": len(ctx.sessions),
            # Больше нуля — часть снимков периода ещё распознаётся, выводы неполные.
            "pending_images": facts.pending_images,
            "deviations_found": len(deviations),
            "deviations_active": sum(d.finding.active for d in deviations),
        },
    )
