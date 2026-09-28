"""Предикаты по технике на участках: D3, D4, D5, D6 (docs/methodology.md, разделы 6 и 9).

В отличие от D1 и D2, здесь ключ — не этап, а пара «участок × класс»: вывод касается
конкретной машины на конкретном месте. Порог серии `min_sessions` лежит в `params`
правила отклонения, а не в правиле этапа.

Модуль регистрирует предикаты при импорте; импортирует его `core/predicates.py`,
поэтому реестр всегда полон.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from src.core.calendar import local_date
from src.core.context import Context, Streak, find_streaks
from src.core.equipment_state import (
    BLIND,
    IDLE,
    OUT_OF_ZONE,
    OUTSIDE,
    PERSON,
    ROLE_SAFETY,
    ROLE_WORK,
    equipment_states,
)
from src.core.inputs import Evidence, SessionFact, Stage
from src.core.plan_on_date import active_stages, closed
from src.core.predicates import (
    DeviationRule,
    Finding,
    evidence_refs,
    held_working_days,
    register,
    severity,
)
from src.core.rules import expected_classes

OUTSIDE_NAME = "вне размеченных зон"

# (этап или None, участок, класс) — ключ отклонения без object_id и кода.
Key = tuple[UUID | None, str, str]


@dataclass(frozen=True)
class Hit:
    """Условие выполнено в сессии: числа, рамки и поля `facts`, свои у каждого кода."""

    count: int
    static: int | None
    evidence: tuple[Evidence, ...]
    extra: dict[str, Any]
    rule_ref: dict[str, Any] = field(default_factory=dict)


Observe = Callable[[Context, SessionFact], dict[Key, Hit]]


def _visible(session: SessionFact) -> set[str]:
    """Где в сессии можно было что-то увидеть: видимые участки и «вне зон», если есть кадр."""
    visible = {a.area for a in session.areas if a.visibility.status != BLIND}
    if any(camera.usable for camera in session.cameras):
        visible.add(OUTSIDE)
    return visible


def _equipment_findings(ctx: Context, rule: DeviationRule, observe: Observe) -> list[Finding]:
    """Серии по каждому ключу: сессия без находки на видимом участке рвёт серию."""
    min_sessions = rule.params.get("min_sessions", 1)
    observed = [(s, observe(ctx, s), _visible(s)) for s in ctx.sessions]
    # Порядок первого появления: результат детерминирован и читается по времени.
    keys = list(dict.fromkeys(key for _, hits, _ in observed for key in hits))
    findings = []
    for key in keys:
        rows = [
            (s, hits[key] if key in hits else (False if key[1] in visible else None))
            for s, hits, visible in observed
        ]
        for streak in find_streaks(rows):
            if len(streak.sessions) >= min_sessions:
                findings.append(_equipment_finding(ctx, rule, key, streak, min_sessions))
    return findings


def _equipment_finding(
    ctx: Context, rule: DeviationRule, key: Key, streak: Streak, min_sessions: int
) -> Finding:
    stage_id, area, cls = key
    last_session, hit = streak.sessions[-1], streak.payloads[-1]
    held = held_working_days(ctx, streak)
    facts = {
        "area": area,
        "equipment_class": cls,
        "equipment_name": ctx.class_names.get(cls, cls),
        "count": hit.count,
        "static": hit.static,
        "sessions_checked": len(streak.sessions),
        "min_sessions": min_sessions,
        "first_seen_at": streak.sessions[0].window_start.isoformat(),
        "last_seen_at": last_session.window_end.isoformat(),
        "held_working_days": held,
        **hit.extra,
    }
    return Finding(
        code=rule.code,
        severity=severity(rule, held),
        stage_id=stage_id,
        area=area,
        equipment_class=cls,
        session_id=last_session.session_id,
        first_seen_at=streak.sessions[0].window_start,
        last_seen_at=last_session.window_end,
        occurrences=len(streak.sessions),
        active=streak.active,
        facts=facts,
        evidence=evidence_refs(hit.evidence),
        rule_ref={"deviation_rule": rule.code, **hit.rule_ref},
    )


def _future_stage(ctx: Context, day: date, zone_type: str, cls: str) -> Stage | None:
    """Ближайший по плану будущий этап того же типа участка, чьё правило ждёт этот класс.

    Этап, уже закрытый отметкой «выполнен», будущим не бывает (раздел 10.3b).
    """
    future = [
        s
        for s in ctx.plan.stages
        if s.plan_start > day
        and not closed(s, day)
        and s.zone_type == zone_type
        and s.rule is not None
        and cls in expected_classes(s.rule)
    ]
    return min(future, key=lambda s: (s.plan_start, s.seq), default=None)


def _unexpected(ctx: Context, session: SessionFact) -> dict[Key, Hit]:
    day = local_date(ctx.calendar, session.window_start)
    active = active_stages(ctx.plan, day)
    hits: dict[Key, Hit] = {}
    for area in session.areas:
        if area.visibility.status == BLIND or ctx.enums.role(area.zone_type) != ROLE_WORK:
            continue
        here = [s for s in active if s.zone_type == area.zone_type]
        # Нет активного этапа типа — это D5, а не D3. Этап без правила не говорит, какая
        # техника ему нужна, и обвинять машину «не по этапу» не на чем.
        if not here or any(s.rule is None for s in here):
            continue
        expected = frozenset().union(*(expected_classes(s.rule) for s in here))
        for item in area.equipment:
            cls = item.equipment_class
            if cls == PERSON or cls in expected:
                continue
            extra: dict[str, Any] = {
                "area_name": area.name,
                "active_stages": [s.name for s in here],
                "expected_classes": sorted(expected),
            }
            rule_ref: dict[str, Any] = {}
            ahead = _future_stage(ctx, day, area.zone_type, cls)
            if ahead is not None:
                extra |= {
                    "template_variant": "ahead",
                    "future_stage_name": ahead.name,
                    "future_stage_code": ahead.code,
                    "future_plan_start": ahead.plan_start.isoformat(),
                }
                rule_ref = {
                    "stage_rule_id": str(ahead.rule.id),
                    "stage_rule_version": ahead.rule.version,
                }
            key = (ahead.id if ahead else None, area.area, cls)
            hits[key] = Hit(item.count, item.static, item.evidence, extra, rule_ref)
    return hits


def _by_state(pick: Callable[[str, str], bool]) -> Observe:
    """Находки по статусу нетранзитной техники (раздел 6): pick(статус, участок)."""

    def observe(ctx: Context, session: SessionFact) -> dict[Key, Hit]:
        day = local_date(ctx.calendar, session.window_start)
        active = active_stages(ctx.plan, day)
        names = {a.area: a.name for a in session.areas}
        statuses = equipment_states(
            session,
            active,
            transient=ctx.transient,
            enums=ctx.enums,
            class_names=ctx.class_names,
            works_in_place=ctx.works_in_place,
        )
        return {
            (None, st.area, st.equipment_class): Hit(
                st.count,
                st.static,
                st.evidence,
                {
                    "area_name": names.get(st.area, OUTSIDE_NAME),
                    "state": st.state,
                    "state_reason": st.reason,
                    "active_stages": [s.name for s in active],
                },
            )
            # Транзитная техника по месту не простаивает: D4 и D5 к ней не применяются.
            for st in statuses
            if st.equipment_class not in ctx.transient and pick(st.state, st.area)
        }

    return observe


def _in_danger(ctx: Context, session: SessionFact) -> dict[Key, Hit]:
    return {
        (None, area.area, item.equipment_class): Hit(
            item.count, item.static, item.evidence, {"area_name": area.name}
        )
        for area in session.areas
        if area.visibility.status != BLIND and ctx.enums.role(area.zone_type) == ROLE_SAFETY
        for item in area.equipment
    }


@register("unexpected_equipment")
def unexpected_equipment(ctx: Context, rule: DeviationRule) -> list[Finding]:
    """D3: класса нет в правилах активных этапов участка; есть у будущего этапа — опережение."""
    return _equipment_findings(ctx, rule, _unexpected)


@register("idle_equipment")
def idle_equipment(ctx: Context, rule: DeviationRule) -> list[Finding]:
    """D4: нетранзитная техника в простое или вне всех зон."""
    return _equipment_findings(
        ctx,
        rule,
        _by_state(lambda state, area: state == IDLE or (state == OUT_OF_ZONE and area == OUTSIDE)),
    )


@register("wrong_zone")
def wrong_zone(ctx: Context, rule: DeviationRule) -> list[Finding]:
    """D5: нетранзитная техника на рабочем участке, где нет активного этапа его типа."""
    return _equipment_findings(
        ctx, rule, _by_state(lambda state, area: state == OUT_OF_ZONE and area != OUTSIDE)
    )


@register("danger_zone")
def danger_zone(ctx: Context, rule: DeviationRule) -> list[Finding]:
    """D6: техника или человек в опасной зоне; порог — одна сессия."""
    return _equipment_findings(ctx, rule, _in_danger)
