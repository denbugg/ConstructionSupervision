"""Факты за период (interservice.md, контракт 2) и состав окон наблюдения.

Факт окна уже материализован при распознавании (`session_fact`, `area_visibility`, стадия
окна), здесь он только собирается в ответ. Оценок нет: работает ли техника и рабочее ли это
время, решает analysis-service (ADR-0012).
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from lct_common import NotFoundError
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.aggregation import CameraState, CameraZones, Frame, camera_states
from src.core.zones import OUTSIDE
from src.dal.models import AreaVisibility, ObservationSession, SessionFact
from src.dal.repositories.cameras import CameraRepository
from src.dal.repositories.sessions import SessionRepository, in_period, one_window
from src.dal.repositories.zones import ZoneRepository
from src.services.image_catalog import InvalidPeriod


class SessionNotFound(NotFoundError):
    code = "SESSION_NOT_FOUND"

    def __init__(self, session_id: UUID) -> None:
        super().__init__("Окно наблюдения не найдено", session_id=str(session_id))


class FactsService:
    def __init__(self, session: AsyncSession) -> None:
        self._sessions = SessionRepository(session)
        self._cameras = CameraRepository(session)
        self._zones = ZoneRepository(session)

    async def period(self, object_id: UUID, start: datetime, end: datetime) -> dict[str, Any]:
        """Факты окон с началом в [start, end). Нет снимков — пустой список, а не ошибка."""
        start, end = _period(start, end)
        where = in_period(object_id, start, end)
        windows = await self._sessions.observed(where)
        return {
            "object_id": object_id,
            "from": start,
            "to": end,
            "zones_version": await self._zones.zones_version(object_id),
            "model_versions": await self._sessions.model_versions(where),
            "pending_images": await self._sessions.pending_images(where),
            "sessions": await self._window_facts(object_id, windows, where),
        }

    async def detail(self, session_id: UUID) -> dict[str, Any]:
        """Окно целиком: камеры, факт окна и все снимки — и распознанные, и ждущие."""
        window = await self._sessions.get(session_id)
        if window is None:
            raise SessionNotFound(session_id)
        [fact] = await self._window_facts(window.object_id, [window], one_window(session_id))
        return {
            **{column: getattr(window, column) for column in _SESSION_COLUMNS},
            **fact,
            "images": await self._sessions.window_images(session_id),
        }

    async def _window_facts(
        self, object_id: UUID, windows: Sequence[ObservationSession], where: ColumnElement[bool]
    ) -> list[dict[str, Any]]:
        # Все выборки — по условию на окна, а не по окну в цикле: окон в периоде тысячи.
        cameras = [
            CameraZones(c.id, c.code, ())
            for c in await self._cameras.for_object(object_id)
            if c.is_active
        ]
        frames: dict[UUID, list[Frame]] = defaultdict(list)
        for image in await self._sessions.analyzed_images(where):
            frames[image.session_id].append(
                Frame(image.id, image.camera_id, bool(image.usable), image.usable_reason)
            )
        visibility: dict[UUID, list[AreaVisibility]] = defaultdict(list)
        for row in await self._sessions.visibility(where):
            visibility[row.session_id].append(row)
        facts: dict[UUID, list[SessionFact]] = defaultdict(list)
        for row in await self._sessions.facts(where):
            facts[row.session_id].append(row)
        return [
            _window(w, camera_states(frames[w.id], cameras), visibility[w.id], facts[w.id])
            for w in windows
        ]

    # Последним: имя метода в теле класса затеняет встроенный list в аннотациях ниже него.
    async def list(
        self, *, start: datetime | None, end: datetime | None, **filters: Any
    ) -> tuple[list[ObservationSession], int]:
        if start is not None and end is not None:
            start, end = _period(start, end)
        return await self._sessions.list(start=_utc(start), end=_utc(end), **filters)


def _window(
    window: ObservationSession,
    cameras: Sequence[CameraState],
    visibility: Sequence[AreaVisibility],
    facts: Sequence[SessionFact],
) -> dict[str, Any]:
    """Окно в форме контракта: участки — все, даже пустые; техника вне зон — отдельно."""
    equipment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in facts:
        equipment[row.area].append(
            {
                "equipment_class": row.equipment_class,
                "count": row.count,
                "static": row.static,
                "evidence": row.evidence,
            }
        )
    return {
        "session_id": window.id,
        "window_start": window.window_start,
        "window_end": window.window_end,
        "updated_at": window.updated_at,
        # camera_id контракт не содержит (схема его отбросит), а состав окна показывает.
        "cameras": [
            {
                "camera_id": c.camera_id,
                "code": c.code,
                "images": c.images,
                "usable": c.usable,
                "reason": c.reason,
                "image_ids": list(c.image_ids),
            }
            for c in cameras
        ],
        "stage_observation": {
            "stage_label": window.stage_label,
            "conf": window.stage_conf,
            "scores": window.stage_scores,
        }
        if window.stage_label
        else None,
        "areas": [
            {
                "area": v.area,
                "zone_type": v.zone_type,
                "name": v.name,
                "visibility": {
                    "status": v.status,
                    "cameras_total": v.cameras_total,
                    "cameras_usable": v.cameras_usable,
                    "reason": v.reason,
                },
                "equipment": equipment.get(v.area, []),
            }
            for v in visibility
        ],
        "outside_zones": equipment.get(OUTSIDE, []),
    }


def _utc(moment: datetime | None) -> datetime | None:
    """Время без смещения в запросе считается UTC: так договорено для всех контрактов."""
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=UTC)


def _period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    start, end = _utc(start), _utc(end)
    if end <= start:
        raise InvalidPeriod(
            "Конец периода должен быть позже начала", start=start.isoformat(), end=end.isoformat()
        )
    return start, end


_SESSION_COLUMNS = (
    "id",
    "object_id",
    "window_start",
    "window_end",
    "image_count",
    "camera_count",
    "stage_label",
    "stage_conf",
    "updated_at",
)
