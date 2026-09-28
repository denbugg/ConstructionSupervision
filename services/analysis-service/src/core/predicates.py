"""Реестр предикатов отклонений D1–D10 (docs/methodology.md, раздел 9).

Предикат — чистая функция «контекст прогона + настройка правила → находки». Какой
предикат стоит за кодом, его пороги и тексты лежат в данных (deviation_rule, начальные
значения — data/deviation_rules.yaml). Новый тип отклонения с новой логикой — функция
здесь и её регистрация, около 30 строк.

Общие правила для всех предикатов:
- выводы строятся только по рабочим сессиям — `build_context` отбрасывает остальные;
- «подряд» считается по наблюдаемым сессиям: сессия, где участок не виден, серию не
  рвёт и в неё не входит — «не видно» не значит ни «есть», ни «нет»;
- находка без `facts` и `evidence` не создаётся. Исключение — D10, когда снимков нет по
  определению: тогда причина записана в `facts.evidence_absent_reason` (раздел 12).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from src.core.calendar import local_date, working_days_between
from src.core.context import Context, Streak, find_streaks
from src.core.inputs import Evidence, Stage
from src.core.plan_on_date import closed
from src.core.rules import RuleCheck, check_rule


class PredicateError(ValueError):
    """Настройка правила ссылается на предикат, которого нет в реестре, или испорчена."""


@dataclass(frozen=True)
class DeviationRule:
    """Настройка кода отклонения: строка таблицы deviation_rule."""

    code: str
    predicate: str
    enabled: bool
    severity: str
    params: dict[str, Any]
    title_template: str
    message_template: str


def parse_rules(raw: dict[str, Any]) -> tuple[DeviationRule, ...]:
    """Разобранный YAML → настройки. Отдельно от чтения файла, чтобы тестировать без диска."""
    try:
        return tuple(
            DeviationRule(
                code=code,
                predicate=body["predicate"],
                enabled=body.get("enabled", True),
                severity=body["severity"],
                params=dict(body.get("params") or {}),
                title_template=body["title_template"],
                message_template=body["message_template"],
            )
            for code, body in raw["rules"].items()
        )
    except (KeyError, TypeError, AttributeError) as exc:
        raise PredicateError(f"Испорчена настройка правил отклонений: {exc}") from exc


def load_rules(path: str | Path) -> tuple[DeviationRule, ...]:
    with Path(path).open(encoding="utf-8") as file:
        return parse_rules(yaml.safe_load(file))


@dataclass(frozen=True)
class Finding:
    """Отклонение до оформления текстом: ключ, серьёзность, числа и доказательства."""

    code: str
    severity: str
    stage_id: UUID | None
    area: str | None
    equipment_class: str | None
    # Последняя сессия серии, в которой условие выполнялось.
    session_id: UUID
    first_seen_at: datetime
    last_seen_at: datetime
    occurrences: int
    # Серия дошла до последней наблюдаемой сессии: условие держится на момент as_of.
    active: bool
    facts: dict[str, Any]
    evidence: tuple[dict[str, Any], ...]
    rule_ref: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple:
        """Ключ ленты (methodology.md, раздел 9): повтор обновляет строку, а не плодит дубль."""
        return (self.stage_id, self.area, self.code, self.equipment_class)


Predicate = Callable[[Context, DeviationRule], list[Finding]]
REGISTRY: dict[str, Predicate] = {}


def register(name: str) -> Callable[[Predicate], Predicate]:
    """Регистрирует предикат под именем, на которое ссылается deviation_rule.predicate."""

    def decorator(fn: Predicate) -> Predicate:
        REGISTRY[name] = fn
        return fn

    return decorator


def evaluate(ctx: Context, rules: Iterable[DeviationRule]) -> list[Finding]:
    """Все находки по включённым правилам."""
    findings: list[Finding] = []
    for rule in rules:
        if not rule.enabled:
            continue
        predicate = REGISTRY.get(rule.predicate)
        if predicate is None:
            raise PredicateError(f"{rule.code}: предикат {rule.predicate!r} не зарегистрирован")
        findings.extend(f for f in predicate(ctx, rule) if _explained(f))
    return findings


def _explained(finding: Finding) -> bool:
    """Инвариант раздела 12: есть числа и есть снимки — или сказано, почему снимков нет."""
    return bool(finding.facts) and bool(
        finding.evidence or finding.facts.get("evidence_absent_reason")
    )


def held_working_days(ctx: Context, streak: Streak) -> int:
    """Сколько рабочих дней держится серия: 0 — в пределах одного дня."""
    first = local_date(ctx.calendar, streak.sessions[0].window_start)
    last = local_date(ctx.calendar, streak.sessions[-1].window_start)
    return working_days_between(ctx.calendar, first, last)


def severity(rule: DeviationRule, held_days: int) -> str:
    """Базовая серьёзность или повышенная, если условие держится дольше порога."""
    after = rule.params.get("escalate_after_days")
    if after is not None and held_days >= after:
        return rule.params.get("escalate_to", rule.severity)
    return rule.severity


def evidence_refs(
    detections: Iterable[Evidence], image_ids: Iterable[UUID] = ()
) -> tuple[dict[str, Any], ...]:
    """Доказательства в формате отклонения: снимок и рамки на нём."""
    by_image: dict[UUID, list[str]] = {}
    for ev in detections:
        by_image.setdefault(ev.image_id, []).append(str(ev.detection_id))
    for image_id in image_ids:
        by_image.setdefault(image_id, [])
    return tuple({"image_id": str(i), "detection_ids": ids} for i, ids in by_image.items())


def _planned(stage: Stage, day: date) -> bool:
    """Этап активен по плану: даты включительно."""
    return stage.plan_start <= day <= stage.plan_end


def _stage_findings(
    ctx: Context,
    rule: DeviationRule,
    condition: Callable[[RuleCheck], bool],
    *,
    when: Callable[[Stage, date], bool] = _planned,
) -> list[Finding]:
    """D1, D2, D8: серии сессий в дни `when`, где правило этапа в состоянии `condition`.

    Со следующего дня после отметки «выполнен» этап не проверяется (раздел 10.3b).
    """
    findings = []
    for stage in ctx.plan.stages:
        if stage.rule is None:
            continue
        rows = []
        for i, session in enumerate(ctx.sessions):
            day = local_date(ctx.calendar, session.window_start)
            if not when(stage, day) or closed(stage, day):
                rows.append((session, False))
                continue
            check = check_rule(
                stage,
                ctx.sessions,
                i,
                transient=ctx.transient,
                enums=ctx.enums,
                params=ctx.params,
            )
            if not check.evaluated:
                rows.append((session, None))
            else:
                rows.append((session, check if condition(check) else False))
        for streak in find_streaks(rows):
            if len(streak.sessions) >= stage.rule.min_sessions:
                findings.append(_stage_finding(ctx, rule, stage, streak))
    return findings


def _stage_finding(ctx: Context, rule: DeviationRule, stage: Stage, streak: Streak) -> Finding:
    last_session, check = streak.sessions[-1], streak.payloads[-1]
    names = {a.area: a.name for a in last_session.areas}
    held = held_working_days(ctx, streak)
    required_classes = [c for g in stage.rule.required for c in g.any_of]
    signature_classes = list(stage.rule.signature.equipment)
    groups = [
        {"any_of": list(g.group.any_of), "min": g.group.min, "observed": g.observed}
        for g in check.groups
    ]
    facts = {
        "stage_name": stage.name,
        "stage_code": stage.code,
        "plan_start": stage.plan_start.isoformat(),
        "plan_end": stage.plan_end.isoformat(),
        "area": " + ".join(check.areas),
        "area_name": " + ".join(names[a] for a in check.areas),
        "sessions_checked": len(streak.sessions),
        "first_seen_at": streak.sessions[0].window_start.isoformat(),
        "last_seen_at": last_session.window_end.isoformat(),
        "held_working_days": held,
        "transient_window_sessions": ctx.params.transient_window_sessions,
        "stage_rule_id": str(stage.rule.id),
        "stage_rule_version": stage.rule.version,
        "required": [{"any_of": list(g.any_of), "min": g.min} for g in stage.rule.required],
        "observed": {
            c: (check.observed[c].count if c in check.observed else 0) for c in required_classes
        },
        "groups": groups,
        "groups_failed": [g for g in groups if g["observed"] < g["min"]],
        "signature": signature_classes,
        "signature_stage_label": stage.rule.signature.stage_label,
        "signature_observed": {
            c: (check.observed[c].count if c in check.observed else 0) for c in signature_classes
        },
    }
    detections = [
        ev
        for c in dict.fromkeys(required_classes + signature_classes)
        if c in check.observed
        for ev in check.observed[c].evidence
    ]
    # Рамок нет (пустой участок) — доказательство сам снимок: на нём видно, что пусто.
    images = (
        []
        if detections
        else [i for cam in last_session.cameras if cam.usable for i in cam.image_ids]
    )
    return Finding(
        code=rule.code,
        severity=severity(rule, held),
        stage_id=stage.id,
        area=facts["area"],
        equipment_class=None,
        session_id=last_session.session_id,
        first_seen_at=streak.sessions[0].window_start,
        last_seen_at=last_session.window_end,
        occurrences=len(streak.sessions),
        active=streak.active,
        facts=facts,
        evidence=evidence_refs(detections, images),
        rule_ref={
            "deviation_rule": rule.code,
            "stage_rule_id": str(stage.rule.id),
            "stage_rule_version": stage.rule.version,
        },
    )


@register("missing_required")
def missing_required(ctx: Context, rule: DeviationRule) -> list[Finding]:
    """D1: этап активен, но ни в одной группе `required` нет ни одной единицы."""
    return _stage_findings(ctx, rule, lambda check: check.nothing_required)


@register("incomplete_set")
def incomplete_set(ctx: Context, rule: DeviationRule) -> list[Finding]:
    """D2: часть групп `required` выполнена, часть — нет."""
    return _stage_findings(ctx, rule, lambda check: check.partial)


@register("stage_overrun")
def stage_overrun(ctx: Context, rule: DeviationRule) -> list[Finding]:
    """D8: сигнатура этапа держится после `plan_end` — этап затянулся."""
    findings = _stage_findings(
        ctx, rule, lambda check: check.signature_met, when=lambda s, day: day > s.plan_end
    )
    # Рабочая сессия лежит в одних местных сутках, поэтому дата конца окна — дата сессии.
    return [
        replace(
            f,
            facts=f.facts
            | {
                "days_after_plan_end": working_days_between(
                    ctx.calendar,
                    date.fromisoformat(f.facts["plan_end"]),
                    local_date(ctx.calendar, f.last_seen_at),
                )
            },
        )
        for f in findings
    ]


# Предикаты по технике и по срокам и видимости живут в своих модулях, чтобы этот не
# разрастался. Импорт в конце файла регистрирует их вместе с реестром: кто бы ни
# импортировал реестр, D3–D10 в нём есть.
from src.core import equipment_predicates, stage_predicates  # noqa: E402, F401
