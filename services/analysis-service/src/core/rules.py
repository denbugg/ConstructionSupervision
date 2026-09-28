"""Проверка правила «этап → техника» в одной рабочей сессии (docs/methodology.md, раздел 5).

Правило проверяется только на видимых участках типа этапа. Если все такие участки
слепые или их нет вовсе, этап в сессии не оценивается: «не видно» — не «пусто».
Серии сессий (`min_sessions`) и выводы D1–D10 здесь не делаются: это вход для
предикатов.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.core.enums import Enums
from src.core.inputs import Evidence, RequiredGroup, SessionFact, Stage, StageRule

BLIND = "BLIND"


@dataclass(frozen=True)
class RuleParams:
    """Параметры методики из окружения (TRANSIENT_WINDOW_SESSIONS, MIN_STAGE_CONF)."""

    transient_window_sessions: int
    min_stage_conf: float


@dataclass(frozen=True)
class Observed:
    """Сколько единиц класса учтено и на каких рамках это число стоит."""

    count: int
    evidence: tuple[Evidence, ...]
    # Окно, из которого взято число: для транзитного класса это может быть прошлое окно.
    window_start: datetime


@dataclass(frozen=True)
class GroupResult:
    group: RequiredGroup
    observed: int
    satisfied: bool


@dataclass(frozen=True)
class RuleCheck:
    """Результат проверки правила этапа в сессии — все числа для `facts` отклонения."""

    stage_id: UUID
    session_id: UUID
    # False — участки типа этапа не видны или не размечены; остальные поля пустые.
    evaluated: bool
    # Почему не оценивалась: NO_AREA — нет размеченного участка типа, BLIND — все слепые.
    skip_reason: str | None
    areas: tuple[str, ...]
    observed: dict[str, Observed]
    groups: tuple[GroupResult, ...]
    signature_met: bool

    @property
    def complete(self) -> bool:
        """Комплект этапа присутствует: выполнены все группы `required`."""
        return self.evaluated and all(g.satisfied for g in self.groups)

    @property
    def nothing_required(self) -> bool:
        """Ни в одной группе нет ни одной единицы — условие D1."""
        return self.evaluated and bool(self.groups) and all(g.observed == 0 for g in self.groups)

    @property
    def partial(self) -> bool:
        """Хотя бы одна группа выполнена, но не все — условие D2."""
        satisfied = [g.satisfied for g in self.groups]
        return self.evaluated and any(satisfied) and not all(satisfied)


def expected_classes(rule: StageRule) -> frozenset[str]:
    """Классы, чьё присутствие на участке этапа ожидаемо: обязательные, допустимые, сигнатура."""
    required = {c for group in rule.required for c in group.any_of}
    return frozenset(required | set(rule.allowed) | set(rule.signature.equipment))


def stage_counts(
    session: SessionFact, zone_type: str
) -> tuple[tuple[str, ...], dict[str, Observed]]:
    """Видимые участки типа в сессии и число единиц по классам на них.

    Участков одного типа обычно один; если их несколько, единицы складываются:
    это разные места площадки, а не разные камеры одного места.
    """
    visible = [
        a for a in session.areas if a.zone_type == zone_type and a.visibility.status != BLIND
    ]
    counts: dict[str, Observed] = {}
    for area in visible:
        for item in area.equipment:
            prev = counts.get(item.equipment_class)
            count = item.count + (prev.count if prev else 0)
            evidence = (prev.evidence if prev else ()) + item.evidence
            counts[item.equipment_class] = Observed(count, evidence, session.window_start)
    return tuple(a.area for a in visible), counts


def _skip_reason(session: SessionFact, zone_type: str) -> str | None:
    of_type = [a for a in session.areas if a.zone_type == zone_type]
    if not of_type:
        return "NO_AREA"
    if all(a.visibility.status == BLIND for a in of_type):
        return BLIND
    return None


def _windowed(
    sessions: Sequence[SessionFact], index: int, zone_type: str, window_sessions: int
) -> dict[str, Observed]:
    """Максимум по классам за окно из `window_sessions` сессий, включая текущую.

    Окно отмеряется по времени (N окон по 30 минут назад), а не по номеру в списке:
    так ночной перерыв или пропуск окон не переносит вчерашний самосвал в сегодня.
    """
    current = sessions[index]
    span = (current.window_end - current.window_start) * (window_sessions - 1)
    best: dict[str, Observed] = {}
    # Идём назад от текущей сессии и останавливаемся на границе окна: прогон по месяцу
    # снимков не должен становиться квадратичным.
    for session in reversed(sessions[: index + 1]):
        if session.window_start < current.window_start - span:
            break
        for cls, observed in stage_counts(session, zone_type)[1].items():
            if cls not in best or observed.count > best[cls].count:
                best[cls] = observed
    return best


def _signature_met(
    rule: StageRule,
    session: SessionFact,
    observed: dict[str, Observed],
    enums: Enums,
    params: RuleParams,
) -> bool:
    signature = rule.signature
    if not signature.equipment and signature.stage_label is None:
        return False
    if any(observed.get(cls) is None for cls in signature.equipment):
        return False
    if signature.stage_label is None:
        return True
    stage = session.stage_observation
    # Неуверенная стадия считается неизвестной: она ничего не подтверждает.
    if stage is None or stage.conf < params.min_stage_conf:
        return False
    return enums.stage_index(stage.stage_label) >= enums.stage_index(signature.stage_label)


def check_rule(
    stage: Stage,
    sessions: Sequence[SessionFact],
    index: int,
    *,
    transient: frozenset[str],
    enums: Enums,
    params: RuleParams,
) -> RuleCheck:
    """Проверяет правило этапа в сессии `sessions[index]`.

    `sessions` — рабочие сессии по возрастанию времени; прошлые нужны для окна
    транзитной техники. `transient` — коды классов с `transient: true`.
    """
    if stage.rule is None:
        raise ValueError(f"У этапа {stage.name!r} нет правила: проверять нечего")
    rule = stage.rule
    session = sessions[index]
    skip = _skip_reason(session, stage.zone_type)
    if skip is not None:
        return RuleCheck(stage.id, session.session_id, False, skip, (), {}, (), False)

    areas, current = stage_counts(session, stage.zone_type)
    windowed = _windowed(sessions, index, stage.zone_type, params.transient_window_sessions)
    # Транзитный класс присутствует, если был в окне; остальные — только в текущей сессии.
    observed = {c: o for c, o in current.items() if c not in transient}
    observed |= {c: o for c, o in windowed.items() if c in transient}

    groups = []
    for group in rule.required:
        # «Любой из»: единицы классов группы складываются.
        total = sum(observed[c].count for c in group.any_of if c in observed)
        groups.append(GroupResult(group, total, total >= group.min))
    signature = _signature_met(rule, session, observed, enums, params)
    return RuleCheck(
        stage.id, session.session_id, True, None, areas, observed, tuple(groups), signature
    )
