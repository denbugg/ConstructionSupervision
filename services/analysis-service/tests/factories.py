"""Конструкторы входа методики для тестов: план, окна, участки, техника.

Идентификаторы детерминированы (uuid5 от смысла), поэтому фикстуры, собранные
этими функциями, не меняются от запуска к запуску, а доказательства в выводах
можно сравнивать с ожидаемыми.
"""

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from uuid import UUID, uuid5

from src.core.inputs import (
    AreaFact,
    CameraState,
    EquipmentFact,
    Evidence,
    Facts,
    Plan,
    RequiredGroup,
    SessionFact,
    Signature,
    Stage,
    StageObservation,
    StageRule,
    Visibility,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NAMESPACE = UUID("3b9f1d52-6c0e-4a7b-8f24-d15e9a0c7b63")
WINDOW = timedelta(minutes=30)


def stable_id(*parts: object) -> UUID:
    """Один и тот же смысл → один и тот же UUID."""
    return uuid5(NAMESPACE, "/".join(str(p) for p in parts))


def load_plan(name: str = "plan.json") -> Plan:
    return Plan.model_validate(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def load_facts(name: str) -> Facts:
    return Facts.model_validate(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def make_rule(
    required: dict[str, int] | list[tuple[tuple[str, ...], int]],
    *,
    allowed: tuple[str, ...] = (),
    signature: tuple[str, ...] = (),
    signature_stage: str | None = None,
    min_sessions: int = 2,
    version: int = 1,
) -> StageRule:
    """Правило этапа. `{"excavator": 1}` — по группе на класс; список — группы «любой из»."""
    groups = (
        [((cls,), n) for cls, n in required.items()] if isinstance(required, dict) else required
    )
    return StageRule(
        id=stable_id("rule", tuple(groups), allowed, signature),
        version=version,
        required=tuple(RequiredGroup(any_of=any_of, min=n) for any_of, n in groups),
        allowed=allowed,
        signature=Signature(equipment=signature, stage_label=signature_stage),
        min_sessions=min_sessions,
    )


def make_stage(
    name: str,
    plan_start: date,
    plan_end: date,
    *,
    seq: int = 1,
    zone_type: str = "PIT",
    visual_stage: str | None = None,
    norm_duration_days: int = 10,
    rule: StageRule | None = None,
    phase: str = "SUBSTRUCTURE",
) -> Stage:
    return Stage(
        id=stable_id("stage", name),
        code=f"S{seq}",
        name=name,
        phase=phase,
        seq=seq,
        zone_type=zone_type,
        visual_stage=visual_stage,
        plan_start=plan_start,
        plan_end=plan_end,
        norm_duration_days=norm_duration_days,
        rule=rule,
    )


def make_plan(*stages: Stage, base: Plan | None = None) -> Plan:
    """План фикстуры с подменёнными этапами: календарь и классы техники — как в plan.json."""
    return (base or load_plan()).model_copy(update={"stages": stages})


def make_equipment(
    equipment_class: str,
    count: int = 1,
    *,
    static: int | None = None,
    camera: str = "cam-north",
    at: datetime | None = None,
) -> EquipmentFact:
    """Класс на участке; по рамке-доказательству на каждую единицу."""
    image_id = stable_id("image", at, camera)
    return EquipmentFact(
        equipment_class=equipment_class,
        count=count,
        static=static,
        evidence=tuple(
            Evidence(
                image_id=image_id,
                detection_id=stable_id("detection", at, camera, equipment_class, i),
                camera=camera,
                conf=0.9,
            )
            for i in range(count)
        ),
    )


def make_camera(code: str, at: datetime | None, *, reason: str | None = None) -> CameraState:
    """Камера в окне с одним снимком; `reason` — причина непригодности кадра."""
    return CameraState(
        code=code,
        images=1,
        usable=reason is None,
        reason=reason,
        image_ids=(stable_id("image", at, code),),
    )


def make_area(
    area: str,
    *equipment: EquipmentFact,
    cameras_total: int = 1,
    cameras_usable: int | None = None,
    reason: str | None = None,
) -> AreaFact:
    """Участок `ТИП:Название`; статус видимости выводится из числа пригодных камер."""
    zone_type, name = area.split(":", 1)
    # Один класс на двух участках одного снимка — это разные рамки: ID рамки зависит
    # от участка, иначе доказательства двух выводов слились бы в одно.
    equipment = tuple(
        item.model_copy(
            update={
                "evidence": tuple(
                    ev.model_copy(update={"detection_id": stable_id(ev.detection_id, area)})
                    for ev in item.evidence
                )
            }
        )
        for item in equipment
    )
    usable = cameras_total if cameras_usable is None else cameras_usable
    if usable == cameras_total:
        status = "OK"
    elif usable == 0:
        status = "BLIND"
    else:
        status = "PARTIAL"
    return AreaFact(
        area=area,
        zone_type=zone_type,
        name=name,
        visibility=Visibility(
            status=status, cameras_total=cameras_total, cameras_usable=usable, reason=reason
        ),
        equipment=equipment,
    )


def make_session(
    window_start: datetime,
    *areas: AreaFact,
    cameras: tuple[CameraState, ...] | None = None,
    stage: tuple[str, float] | None = ("PIT", 0.78),
    outside: tuple[EquipmentFact, ...] = (),
) -> SessionFact:
    """Окно 30 минут; по умолчанию одна пригодная камера `cam-north` со снимком.

    Стадия по фото — (метка, уверенность) или None.
    """
    if cameras is None:
        cameras = (make_camera("cam-north", window_start),)
    observation = None
    if stage is not None:
        label, conf = stage
        observation = StageObservation(stage_label=label, conf=conf, scores={label: conf})
    return SessionFact(
        session_id=stable_id("session", window_start),
        window_start=window_start,
        window_end=window_start + WINDOW,
        updated_at=window_start + WINDOW + timedelta(minutes=5),
        cameras=cameras,
        stage_observation=observation,
        areas=areas,
        outside_zones=outside,
    )


def make_facts(
    *sessions: SessionFact,
    object_id: UUID | None = None,
    period_from: datetime | None = None,
    period_to: datetime | None = None,
    zones_version: int = 4,
) -> Facts:
    """Факты за период; границы по умолчанию — от первого до конца последнего окна."""
    starts = [s.window_start for s in sessions] or [datetime(2026, 10, 20, tzinfo=UTC)]
    return Facts(
        object_id=object_id or load_plan().object.id,
        period_from=period_from or min(starts),
        period_to=period_to or max(starts) + WINDOW,
        zones_version=zones_version,
        model_versions=("yolov8s-worldv2",),
        sessions=sessions,
    )


def windows(day: date, first: time, count: int) -> list[datetime]:
    """Подряд идущие окна дня в UTC, начиная с `first`."""
    start = datetime.combine(day, first, tzinfo=UTC)
    return [start + i * WINDOW for i in range(count)]
