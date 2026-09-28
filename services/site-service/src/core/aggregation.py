"""Факт окна: участки × классы, видимость участков, стадия по фото (methodology.md, раздел 4).

Только наблюдения: сколько единиц класса видно на участке, сколько из них не сдвинулись,
видит ли участок хоть одна камера. Работает ли техника и есть ли отклонение, решает
analysis-service (ADR-0012). Факт окна пересчитывается целиком по всем его кадрам, поэтому
поздний снимок и правка зон дают тот же результат, что и обработка «с нуля».
"""

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from src.core.zones import ZoneShape, place

# Значения visibility_status и visibility_reason из enums.yaml, на которых стоит логика раздела 4.4.
OK, PARTIAL, BLIND = "OK", "PARTIAL", "BLIND"
DARK, BLURRED, NO_IMAGES = "DARK", "BLURRED", "NO_IMAGES"
PRECISION = 4


@dataclass(frozen=True)
class FrameDetection:
    detection_id: UUID
    equipment_class: str
    bbox: tuple[float, float, float, float]
    conf: float
    # Сдвинулась ли единица с прошлого окна камеры; None — сравнивать не с чем.
    moved: bool | None


@dataclass(frozen=True)
class Frame:
    """Распознанный снимок окна."""

    image_id: UUID
    camera_id: UUID
    usable: bool
    reason: str | None
    detections: tuple[FrameDetection, ...] = ()
    # Вероятности меток стадии по снимку; None — стадия не определялась.
    stage_scores: Mapping[str, float] | None = None


@dataclass(frozen=True)
class CameraZones:
    """Активная камера объекта и её активные зоны."""

    id: UUID
    code: str
    zones: tuple[ZoneShape, ...]


@dataclass(frozen=True)
class EquipmentFact:
    area: str
    equipment_class: str
    count: int
    static: int | None
    evidence: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class AreaVisibility:
    area: str
    zone_type: str
    name: str
    cameras_total: int
    cameras_usable: int
    status: str
    reason: str | None


@dataclass(frozen=True)
class WindowStage:
    label: str
    conf: float
    # Сумма вероятностей каждой метки по пригодным кадрам (data-model.md, 2.4).
    scores: dict[str, float]


@dataclass(frozen=True)
class WindowFact:
    equipment: tuple[EquipmentFact, ...]
    visibility: tuple[AreaVisibility, ...]
    stage: WindowStage | None


@dataclass(frozen=True)
class CameraState:
    """Что камера дала окну: распознанные снимки и пригоден ли хоть один."""

    camera_id: UUID
    code: str
    images: int
    usable: bool
    reason: str | None
    image_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class _Seen:
    """Рамки класса на участке в одном кадре одной камеры."""

    image_id: UUID
    camera: str
    detections: tuple[FrameDetection, ...]


def frame_usability(
    quality: Mapping[str, float], min_brightness: float, max_blur: float
) -> tuple[bool, str | None]:
    """Пригоден ли кадр и почему нет (methodology.md, 4.1).

    Темнота проверяется первой: тёмный кадр почти всегда и «размыт» — перепадов яркости
    в нём нет, а причина для человека одна — ночь или закрытый объектив.
    """
    if float(quality.get("brightness", 1.0)) < min_brightness:
        return False, DARK
    if float(quality.get("blur", 0.0)) > max_blur:
        return False, BLURRED
    return True, None


def aggregate_window(
    frames: Sequence[Frame], cameras: Sequence[CameraZones], roles: Mapping[str, str]
) -> WindowFact:
    """Факт окна по всем его распознанным кадрам и текущей разметке зон.

    Кадры неактивных камер не учитываются: их зоны деактивированы вместе с камерой.
    """
    active = {c.id: c for c in cameras}
    frames = sorted((f for f in frames if f.camera_id in active), key=lambda f: str(f.image_id))
    usable = [f for f in frames if f.usable]
    return WindowFact(
        equipment=_equipment(usable, active, roles),
        visibility=_visibility(frames, cameras),
        stage=_stage(usable),
    )


def _equipment(
    usable: Sequence[Frame], cameras: Mapping[UUID, CameraZones], roles: Mapping[str, str]
) -> tuple[EquipmentFact, ...]:
    """Максимум по кадрам камеры, затем максимум по камерам — но не сумма (4.2)."""
    best_by_camera: dict[UUID, dict[tuple[str, str], _Seen]] = defaultdict(dict)
    for frame in usable:
        camera = cameras[frame.camera_id]
        grouped: dict[tuple[str, str], list[FrameDetection]] = defaultdict(list)
        for det in frame.detections:
            placement = place(det.bbox, camera.zones, roles)
            # Опасная зона накладывается поверх: единица считается и в основном участке, и в ней.
            for area in (placement.area, *(z.area for z in placement.danger)):
                grouped[(area, det.equipment_class)].append(det)
        best = best_by_camera[camera.id]
        for key, dets in grouped.items():
            if key not in best or len(dets) > len(best[key].detections):
                best[key] = _Seen(frame.image_id, camera.code, tuple(dets))

    overall: dict[tuple[str, str], _Seen] = {}
    # При равенстве побеждает камера, раньшая по коду: результат не зависит от порядка в базе.
    for camera in sorted(cameras.values(), key=lambda c: c.code):
        for key, seen in best_by_camera.get(camera.id, {}).items():
            if key not in overall or len(seen.detections) > len(overall[key].detections):
                overall[key] = seen

    return tuple(
        EquipmentFact(
            area=area,
            equipment_class=cls,
            count=len(seen.detections),
            static=_static(seen.detections),
            evidence=_evidence(seen),
        )
        for (area, cls), seen in sorted(overall.items())
    )


def _static(detections: Sequence[FrameDetection]) -> int | None:
    """Сколько единиц не сдвинулись; None — ни одну не с чем сравнить (4.3).

    Единица без пары в прошлом окне неподвижной не считается: обвинять в простое можно
    только то, что видно стоящим.
    """
    known = [d.moved for d in detections if d.moved is not None]
    if not known:
        return None
    return sum(1 for moved in known if not moved)


def _evidence(seen: _Seen) -> tuple[dict[str, Any], ...]:
    ordered = sorted(seen.detections, key=lambda d: (-d.conf, str(d.detection_id)))
    return tuple(
        {
            "image_id": str(seen.image_id),
            "detection_id": str(d.detection_id),
            "camera": seen.camera,
            "conf": d.conf,
        }
        for d in ordered
    )


def _visibility(
    frames: Sequence[Frame], cameras: Sequence[CameraZones]
) -> tuple[AreaVisibility, ...]:
    """Видимость каждого участка: сколько его камер дали пригодный кадр (4.4)."""
    frames_by_camera: dict[UUID, list[Frame]] = defaultdict(list)
    for frame in frames:
        frames_by_camera[frame.camera_id].append(frame)

    areas: dict[str, tuple[str, str, set[UUID]]] = {}
    for camera in cameras:
        for zone in camera.zones:
            zone_type, name, members = areas.setdefault(
                zone.area, (zone.zone_type, zone.name, set())
            )
            members.add(camera.id)

    result = []
    for area, (zone_type, name, members) in sorted(areas.items()):
        blind_reasons = []
        for camera_id in members:
            camera_frames = frames_by_camera.get(camera_id, [])
            if not any(f.usable for f in camera_frames):
                blind_reasons.append(_camera_reason(camera_frames))
        total, usable = len(members), len(members) - len(blind_reasons)
        status = OK if usable == total else PARTIAL if usable else BLIND
        result.append(
            AreaVisibility(
                area=area,
                zone_type=zone_type,
                name=name,
                cameras_total=total,
                cameras_usable=usable,
                status=status,
                reason=_most_common(blind_reasons) if blind_reasons else None,
            )
        )
    return tuple(result)


def camera_states(
    frames: Sequence[Frame], cameras: Sequence[CameraZones]
) -> tuple[CameraState, ...]:
    """Каждая активная камера в окне, даже без снимков: `NO_IMAGES` — тоже наблюдение.

    Причина непригодности — та же, что делает участок камеры невидимым (4.4), поэтому
    «камера тёмная» в фактах и `DARK` у её участков не расходятся.
    """
    frames_by_camera: dict[UUID, list[Frame]] = defaultdict(list)
    for frame in frames:
        frames_by_camera[frame.camera_id].append(frame)
    result = []
    for camera in sorted(cameras, key=lambda c: c.code):
        own = sorted(frames_by_camera.get(camera.id, []), key=lambda f: str(f.image_id))
        usable = any(f.usable for f in own)
        result.append(
            CameraState(
                camera_id=camera.id,
                code=camera.code,
                images=len(own),
                usable=usable,
                reason=None if usable else _camera_reason(own),
                image_ids=tuple(f.image_id for f in own),
            )
        )
    return tuple(result)


def _camera_reason(frames: Sequence[Frame]) -> str:
    """Почему камера не видит участок: нет снимков или самая частая причина непригодности."""
    reasons = [f.reason for f in frames if f.reason]
    return _most_common(reasons) if reasons else NO_IMAGES


def _most_common(values: Sequence[str]) -> str:
    # При равной частоте — по алфавиту: причина не должна зависеть от порядка кадров.
    counts = Counter(values)
    return min(counts, key=lambda v: (-counts[v], v))


def _stage(usable: Sequence[Frame]) -> WindowStage | None:
    """Метка с наибольшей суммой вероятностей; её уверенность — среднее по кадрам (4.5)."""
    observed = [f.stage_scores for f in usable if f.stage_scores]
    if not observed:
        return None
    sums: dict[str, float] = defaultdict(float)
    for scores in observed:
        for label, value in scores.items():
            sums[label] += float(value)
    label = min(sums, key=lambda k: (-sums[k], k))
    return WindowStage(
        label=label,
        conf=round(sums[label] / len(observed), PRECISION),
        scores={k: round(v, PRECISION) for k, v in sorted(sums.items())},
    )
