"""Зоны камер и участки объекта (ADR-0013); импорт разметки из `cameras.json`.

Зоны не удаляются, а деактивируются, и любая правка поднимает версию: сумма версий —
`zones_version` объекта, по ней analysis видит, на какой разметке построен факт.
"""

from typing import Any
from uuid import UUID

from lct_common import NotFoundError, ValidationError, get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.zones import ZoneCreate, ZonesImport, ZoneUpdate
from src.core.zones import (
    PolygonError,
    ZoneDraft,
    ZoneImportError,
    ZoneShape,
    area_key,
    check_polygon,
    sync_zones,
)
from src.dal.models import Camera, Zone
from src.dal.repositories.cameras import CameraRepository
from src.dal.repositories.zones import ZoneRepository
from src.reference import enums
from src.services.cameras import CameraService

log = get_logger(__name__)


class ZoneNotFound(NotFoundError):
    code = "ZONE_NOT_FOUND"

    def __init__(self, zone_id: UUID) -> None:
        super().__init__("Зона не найдена", zone_id=str(zone_id))


class InvalidPolygon(ValidationError):
    code = "INVALID_POLYGON"


class ZoneService:
    def __init__(self, session: AsyncSession) -> None:
        self._zones = ZoneRepository(session)
        self._cameras = CameraRepository(session)
        self._camera_service = CameraService(session)
        # Объекты, чья разметка поменялась: после commit их факты пересчитываются заново.
        self.touched: set[UUID] = self._camera_service.touched

    async def get(self, zone_id: UUID) -> Zone:
        zone = await self._zones.get(zone_id)
        if zone is None:
            raise ZoneNotFound(zone_id)
        return zone

    async def list(self, **filters: Any) -> tuple[list[Zone], int]:
        return await self._zones.list(**filters)

    async def create(self, payload: ZoneCreate) -> Zone:
        camera = await self._camera_service.get(payload.camera_id)
        zone = Zone(
            object_id=camera.object_id,
            camera_id=camera.id,
            zone_type=payload.zone_type,
            name=_name(payload.zone_type, payload.name),
            polygon=_polygon(payload.polygon),
        )
        zone = await self._zones.add(zone)
        self.touched.add(zone.object_id)
        log.info("zone.created", zone_id=str(zone.id), area=area_key(zone.zone_type, zone.name))
        return zone

    async def update(self, zone_id: UUID, payload: ZoneUpdate) -> Zone:
        zone = await self.get(zone_id)
        changes = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "polygon" in changes:
            changes["polygon"] = _polygon(changes["polygon"])
        if "name" in changes:
            changes["name"] = changes["name"].strip()
        changed = {k: v for k, v in changes.items() if getattr(zone, k) != v}
        if changed:
            for field, value in changed.items():
                setattr(zone, field, value)
            zone.version = Zone.version + 1
            self.touched.add(zone.object_id)
        return await self._zones.save(zone)

    async def deactivate(self, zone_id: UUID) -> None:
        zone = await self.get(zone_id)
        if zone.is_active:
            zone.is_active = False
            zone.version = Zone.version + 1
            self.touched.add(zone.object_id)
            await self._zones.save(zone)

    async def import_markup(self, payload: ZonesImport) -> dict[str, Any]:
        """Камеры по коду заводятся или переименовываются, зоны сверяются по подписи участка."""
        drafts, errors = _drafts(payload)
        if errors:
            raise InvalidPolygon(errors[0]["message"], errors=errors)
        counts = dict.fromkeys(
            ("cameras_created", "cameras_updated", "zones_created", "zones_updated"), 0
        ) | {"zones_deactivated": 0, "zones_unchanged": 0}
        for item, camera_drafts in zip(payload.cameras, drafts, strict=True):
            camera = await self._camera(payload.object_id, item.code, item.name, counts)
            existing = await self._zones.active_for_camera(camera.id)
            sync = sync_zones([_shape(z) for z in existing], camera_drafts)
            by_id = {z.id: z for z in existing}
            for draft in sync.create:
                await self._zones.add(
                    Zone(
                        object_id=payload.object_id,
                        camera_id=camera.id,
                        zone_type=draft.zone_type,
                        name=draft.name,
                        polygon=[list(p) for p in draft.polygon],
                    )
                )
            for zone_id, polygon in sync.update:
                by_id[zone_id].polygon = [list(p) for p in polygon]
                by_id[zone_id].version = Zone.version + 1
            for zone_id in sync.deactivate:
                by_id[zone_id].is_active = False
                by_id[zone_id].version = Zone.version + 1
            counts["zones_created"] += len(sync.create)
            counts["zones_updated"] += len(sync.update)
            counts["zones_deactivated"] += len(sync.deactivate)
            counts["zones_unchanged"] += sync.unchanged
        if any(counts[k] for k in ("zones_created", "zones_updated", "zones_deactivated")):
            self.touched.add(payload.object_id)
        result = counts | await self.areas(payload.object_id)
        log.info("zones.imported", object_id=str(payload.object_id), **counts)
        return result

    async def areas(self, object_id: UUID) -> dict[str, Any]:
        """Участки объекта по подписи зон активных камер и `zones_version`."""
        await self._zones.flush()
        grouped: dict[str, dict[str, Any]] = {}
        roles = enums().zone_roles
        for zone, camera in await self._zones.active_on_active_cameras(object_id):
            key = area_key(zone.zone_type, zone.name)
            area = grouped.setdefault(
                key,
                {
                    "area": key,
                    "zone_type": zone.zone_type,
                    "name": zone.name,
                    "role": roles.get(zone.zone_type, ""),
                    "cameras": [],
                },
            )
            area["cameras"].append(
                {"camera_id": camera.id, "camera_code": camera.code, "zone_id": zone.id}
            )
        return {
            "object_id": object_id,
            "zones_version": await self._zones.zones_version(object_id),
            "areas": list(grouped.values()),
        }

    async def _camera(
        self, object_id: UUID, code: str, name: str | None, counts: dict[str, int]
    ) -> Camera:
        camera = await self._cameras.by_code(object_id, code)
        title = (name or "").strip() or code
        if camera is None:
            counts["cameras_created"] += 1
            return await self._cameras.add(Camera(object_id=object_id, code=code, name=title))
        if not camera.is_active:
            self.touched.add(object_id)
        if camera.name != title or not camera.is_active:
            counts["cameras_updated"] += 1
            camera.name, camera.is_active = title, True
        return camera


def _drafts(payload: ZonesImport) -> tuple[list[list[ZoneDraft]], list[dict[str, str]]]:
    """Зоны файла по камерам с проверкой полигонов; ошибки — по всему файлу, с путём."""
    result, errors = [], []
    for c, camera in enumerate(payload.cameras):
        drafts = []
        for z, zone in enumerate(camera.zones):
            try:
                polygon = check_polygon(zone.polygon)
            except PolygonError as exc:
                errors.append({"path": f"cameras[{c}].zones[{z}].polygon", "message": str(exc)})
                continue
            drafts.append(ZoneDraft(zone.zone_type, _name(zone.zone_type, zone.name), polygon))
        try:
            sync_zones([], drafts)
        except ZoneImportError as exc:
            errors.append({"path": f"cameras[{c}] ({camera.code})", "message": str(exc)})
        result.append(drafts)
    codes = [c.code for c in payload.cameras]
    for code in sorted({c for c in codes if codes.count(c) > 1}):
        errors.append({"path": "cameras", "message": f"Камера {code} описана в файле дважды"})
    return result, errors


def _shape(zone: Zone) -> ZoneShape:
    return ZoneShape(zone.id, zone.zone_type, zone.name, tuple(tuple(p) for p in zone.polygon))


def _name(zone_type: str, name: str | None) -> str:
    """Название участка; не задано — русское название типа из enums.yaml."""
    return (name or "").strip() or enums().zone_names[zone_type]


def _polygon(points: Any) -> list[list[float]]:
    try:
        return [list(p) for p in check_polygon(points)]
    except PolygonError as exc:
        raise InvalidPolygon(str(exc)) from exc
