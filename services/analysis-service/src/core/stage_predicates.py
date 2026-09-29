"""Предикаты по этапу и видимости: D7, D9, D10 (docs/methodology.md, разделы 7, 8 и 9).

D7 сравнивает уверенную стадию по фото с плановой визуальной стадией. D9 смотрит на
отрезок первых рабочих дней этапа целиком, а не на серию сессий. D10 —
единственный вывод по невидимому: он говорит «проверьте вручную» там, где остальные
предикаты молчат. Модуль регистрирует предикаты при импорте; импортирует его
`core/predicates.py`.
"""

from collections import Counter
from datetime import date
from typing import Any

from src.core.activity import actual_start, rule_checks
from src.core.calendar import add_working_days, is_working_day, local_date
from src.core.context import Context, Streak, find_streaks
from src.core.equipment_state import BLIND
from src.core.inputs import AreaFact, SessionFact, Stage, StageObservation
from src.core.plan_on_date import closed, completion, visual_milestone
from src.core.predicates import (
    DeviationRule,
    Finding,
    evidence_refs,
    held_working_days,
    register,
    severity,
)

# methodology.md, раздел 4.4: камера без снимков в окне — причина NO_IMAGES.
NO_IMAGES = "NO_IMAGES"


def _first_working_days(ctx: Context, start: date, k: int) -> list[date]:
    """Первые `k` рабочих дней с `start` включительно: выходной старт сдвигается вперёд."""
    first = (
        start if is_working_day(ctx.calendar, start) else add_working_days(ctx.calendar, start, 1)
    )
    return [add_working_days(ctx.calendar, first, i) for i in range(k)]


def _stage_facts(stage: Stage) -> dict[str, Any]:
    return {
        "stage_name": stage.name,
        "stage_code": stage.code,
        "zone_type": stage.zone_type,
        "plan_start": stage.plan_start.isoformat(),
        "plan_end": stage.plan_end.isoformat(),
    }


def _stage_mismatch_state(
    ctx: Context, session: SessionFact
) -> tuple[Stage, StageObservation, int] | bool | None:
    """Состояние сессии для D7: (этап, наблюдение, на сколько стадий расходится) или нет.

    Неуверенная стадия — «не наблюдалась»: серию не рвёт и в неё не входит.
    """
    observation = session.stage_observation
    if observation is None or observation.conf < ctx.params.min_stage_conf:
        return None
    stage = visual_milestone(ctx.plan, local_date(ctx.calendar, session.window_start))
    if stage is None:
        return False
    diff = ctx.enums.stage_index(observation.stage_label) - ctx.enums.stage_index(
        stage.visual_stage
    )
    return (stage, observation, diff) if diff else False


def _mismatch_finding(
    ctx: Context, rule: DeviationRule, streak: Streak, min_sessions: int
) -> Finding:
    last_session = streak.sessions[-1]
    stage, observation, diff = streak.payloads[-1]
    held = held_working_days(ctx, streak)
    names = rule.params.get("label_names", {})
    facts = _stage_facts(stage) | {
        "planned_stage": stage.visual_stage,
        "planned_stage_name": names.get(stage.visual_stage, stage.visual_stage),
        "observed_stage": observation.stage_label,
        "observed_stage_name": names.get(observation.stage_label, observation.stage_label),
        "observed_conf": round(observation.conf, 2),
        "min_stage_conf": ctx.params.min_stage_conf,
        "direction": "AHEAD" if diff > 0 else "BEHIND",
        "stages_apart": abs(diff),
        "sessions_checked": len(streak.sessions),
        "min_sessions": min_sessions,
        "first_seen_at": streak.sessions[0].window_start.isoformat(),
        "last_seen_at": last_session.window_end.isoformat(),
        "held_working_days": held,
    }
    if diff > 0:
        facts["template_variant"] = "ahead"
    # Доказательство — сами кадры, по которым классификатор определил стадию.
    images = [i for cam in last_session.cameras if cam.usable for i in cam.image_ids]
    return Finding(
        code=rule.code,
        severity=severity(rule, held),
        stage_id=stage.id,
        area=None,
        equipment_class=None,
        session_id=last_session.session_id,
        first_seen_at=streak.sessions[0].window_start,
        last_seen_at=last_session.window_end,
        occurrences=len(streak.sessions),
        active=streak.active,
        facts=facts,
        evidence=evidence_refs((), images),
        rule_ref={"deviation_rule": rule.code},
    )


@register("stage_mismatch")
def stage_mismatch(ctx: Context, rule: DeviationRule) -> list[Finding]:
    """D7: уверенная стадия по фото раньше или позже плановой визуальной стадии."""
    min_sessions = rule.params.get("min_sessions", 1)
    states = [(s, _stage_mismatch_state(ctx, s)) for s in ctx.sessions]
    # Ключ — этап, задающий плановую стадию: смена этапа в плане начинает новую серию.
    keys = dict.fromkeys(state[0].id for _, state in states if isinstance(state, tuple))
    findings = []
    for key in keys:
        rows = [
            (s, state if not isinstance(state, tuple) or state[0].id == key else False)
            for s, state in states
        ]
        findings += [
            _mismatch_finding(ctx, rule, streak, min_sessions)
            for streak in find_streaks(rows)
            if len(streak.sessions) >= min_sessions
        ]
    return findings


def _signature_names(ctx: Context, stage: Stage) -> list[str]:
    signature = stage.rule.signature
    names = [ctx.class_names.get(c, c).lower() for c in signature.equipment]
    if signature.stage_label is not None:
        names.append(f"стадия по фото не раньше {signature.stage_label}")
    return names


@register("late_start")
def late_start(ctx: Context, rule: DeviationRule) -> list[Finding]:
    """D9: за `k_days` рабочих дней с `plan_start` сигнатура не собралась в фактический старт.

    Проверяется, только когда эти дни прошли к `as_of` и участок этапа был виден хотя бы
    в доле `min_visible_share` рабочих сессий этих дней: не видели — не обвиняем. Этап,
    отмеченный выполненным не позже срока, выполнили — D9 по нему нет (раздел 10.3b).
    """
    k, min_share = rule.params["k_days"], rule.params["min_visible_share"]
    today = local_date(ctx.calendar, ctx.as_of)
    findings = []
    for stage in ctx.plan.stages:
        if stage.rule is None:
            continue
        days = _first_working_days(ctx, stage.plan_start, k)
        marked = completion(stage, today)
        if today <= days[-1] or (marked is not None and marked <= days[-1]):
            continue
        checks = rule_checks(ctx, stage)
        start = actual_start(ctx, stage, checks)
        if start is not None and start.day <= days[-1]:
            continue
        window = [
            (s, c)
            for s, c in zip(ctx.sessions, checks, strict=True)
            if local_date(ctx.calendar, s.window_start) in days
        ]
        visible = [(s, c) for s, c in window if c.evaluated]
        if not window or len(visible) / len(window) < min_share:
            continue
        last, check = visible[-1]
        names = {a.area: a.name for a in last.areas}
        facts = _stage_facts(stage) | {
            "area": " + ".join(check.areas),
            "area_name": " + ".join(names[a] for a in check.areas),
            "k_days": k,
            "deadline": days[-1].isoformat(),
            "sessions_total": len(window),
            "sessions_visible": len(visible),
            "min_visible_share": min_share,
            "signature": list(stage.rule.signature.equipment),
            "signature_stage_label": stage.rule.signature.stage_label,
            "signature_names": _signature_names(ctx, stage),
            "actual_start": start.day.isoformat() if start else None,
            "start_deviation_days": start.start_deviation_days if start else None,
            "completed_on": marked.isoformat() if marked else None,
            "stage_rule_id": str(stage.rule.id),
            "stage_rule_version": stage.rule.version,
        }
        detections = [
            ev
            for c in stage.rule.signature.equipment
            if c in check.observed
            for ev in check.observed[c].evidence
        ]
        # Рамок сигнатуры нет — доказательство сами снимки участка: на них видно, что пусто.
        images = [i for cam in last.cameras if cam.usable for i in cam.image_ids]
        # Старт так и не собрался — условие держится до последней сессии; собрался с
        # опозданием — отклонение закрылось в момент старта; этап закрыли отметкой без
        # наблюдённого старта — последней сессией дня отметки.
        if start is not None:
            ended_at = start.window_start
        elif marked is not None:
            ended_at = [
                s for s in ctx.sessions if local_date(ctx.calendar, s.window_start) <= marked
            ][-1].window_end
        else:
            ended_at = ctx.sessions[-1].window_end
        findings.append(
            Finding(
                code=rule.code,
                severity=rule.severity,
                stage_id=stage.id,
                area=facts["area"],
                equipment_class=None,
                session_id=last.session_id,
                first_seen_at=window[0][0].window_start,
                last_seen_at=ended_at,
                occurrences=len(visible),
                active=start is None and marked is None,
                facts=facts,
                evidence=evidence_refs(detections, images),
                rule_ref={
                    "deviation_rule": rule.code,
                    "stage_rule_id": str(stage.rule.id),
                    "stage_rule_version": stage.rule.version,
                },
            )
        )
    return findings


def _blind_evidence(streak: Streak) -> tuple[dict[str, Any], ...]:
    """Кадры непригодных камер с конца серии: на них видно, почему участок слепой."""
    for session in reversed(streak.sessions):
        images = [i for cam in session.cameras if not cam.usable for i in cam.image_ids]
        if images:
            return evidence_refs((), images)
    return ()


def _blind_finding(ctx: Context, rule: DeviationRule, streak: Streak, min_sessions: int) -> Finding:
    last_session, area = streak.sessions[-1], streak.payloads[-1]
    held = held_working_days(ctx, streak)
    reasons = Counter(a.visibility.reason or NO_IMAGES for a in streak.payloads)
    reason = reasons.most_common(1)[0][0]
    evidence = _blind_evidence(streak)
    facts: dict[str, Any] = {
        "area": area.area,
        "area_name": area.name,
        "zone_type": area.zone_type,
        "sessions_checked": len(streak.sessions),
        "min_sessions": min_sessions,
        "reason": reason,
        "reason_name": rule.params.get("reason_names", {}).get(reason, reason),
        "cameras_total": area.visibility.cameras_total,
        "cameras_usable": area.visibility.cameras_usable,
        "first_seen_at": streak.sessions[0].window_start.isoformat(),
        "last_seen_at": last_session.window_end.isoformat(),
        "held_working_days": held,
    }
    # Камеры участка не прислали ни кадра — показать нечего, и это сказано прямо (раздел 12).
    # Если кадры были, но их нет в фактах, отклонение без доказательств не создаётся.
    if not evidence and reason == NO_IMAGES:
        facts["evidence_absent_reason"] = "камеры участка не прислали ни одного кадра"
    return Finding(
        code=rule.code,
        severity=severity(rule, held),
        stage_id=None,
        area=area.area,
        equipment_class=None,
        session_id=last_session.session_id,
        first_seen_at=streak.sessions[0].window_start,
        last_seen_at=last_session.window_end,
        occurrences=len(streak.sessions),
        active=streak.active,
        facts=facts,
        evidence=evidence,
        rule_ref={"deviation_rule": rule.code},
    )


def _area_state(session: SessionFact, key: str) -> AreaFact | bool | None:
    """Состояние участка для серии D10: слепой — данные, видимый — False, нет в окне — None."""
    area = next((a for a in session.areas if a.area == key), None)
    if area is None:
        return None
    return area if area.visibility.status == BLIND else False


def _blind_areas(ctx: Context, rule: DeviationRule, min_sessions: int) -> list[Finding]:
    keys = dict.fromkeys(a.area for s in ctx.sessions for a in s.areas)
    return [
        _blind_finding(ctx, rule, streak, min_sessions)
        for key in keys
        for streak in find_streaks([(s, _area_state(s, key)) for s in ctx.sessions])
        if len(streak.sessions) >= min_sessions
    ]


def _unmarked_finding(
    ctx: Context, rule: DeviationRule, stage: Stage, streak: Streak, min_sessions: int
) -> Finding:
    last_session = streak.sessions[-1]
    held = held_working_days(ctx, streak)
    facts = _stage_facts(stage) | {
        "template_variant": "no_area",
        "sessions_checked": len(streak.sessions),
        "min_sessions": min_sessions,
        "first_seen_at": streak.sessions[0].window_start.isoformat(),
        "last_seen_at": last_session.window_end.isoformat(),
        "held_working_days": held,
        "evidence_absent_reason": "у этапа нет размеченного участка его типа — снимков по нему нет",
    }
    return Finding(
        code=rule.code,
        severity=severity(rule, held),
        stage_id=stage.id,
        area=None,
        equipment_class=None,
        session_id=last_session.session_id,
        first_seen_at=streak.sessions[0].window_start,
        last_seen_at=last_session.window_end,
        occurrences=len(streak.sessions),
        active=streak.active,
        facts=facts,
        evidence=(),
        rule_ref={"deviation_rule": rule.code},
    )


def _unmarked_stages(ctx: Context, rule: DeviationRule, min_sessions: int) -> list[Finding]:
    """Активный этап, у которого в сессии нет ни одного участка его типа (раздел 7)."""
    findings = []
    for stage in ctx.plan.stages:
        rows = []
        for session in ctx.sessions:
            day = local_date(ctx.calendar, session.window_start)
            planned = stage.plan_start <= day <= stage.plan_end and not closed(stage, day)
            marked = any(a.zone_type == stage.zone_type for a in session.areas)
            rows.append((session, planned and not marked))
        findings += [
            _unmarked_finding(ctx, rule, stage, streak, min_sessions)
            for streak in find_streaks(rows)
            if len(streak.sessions) >= min_sessions
        ]
    return findings


@register("blind_area")
def blind_area(ctx: Context, rule: DeviationRule) -> list[Finding]:
    """D10: участок слепой `min_sessions` рабочих сессий подряд или у этапа в работе нет участка."""
    min_sessions = rule.params.get("min_sessions", 1)
    return _blind_areas(ctx, rule, min_sessions) + _unmarked_stages(ctx, rule, min_sessions)
