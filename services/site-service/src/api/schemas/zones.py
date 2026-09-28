"""DTO зон и участков (ADR-0013). Полигон — в долях 0…1 от размера кадра (ADR-0006)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.api.schemas.cameras import CODE_PATTERN
from src.api.schemas.common import ZoneType
from src.core.zones import area_key

POLYGON_EXAMPLE = [[0.09, 0.47], [0.30, 0.43], [0.33, 0.68], [0.08, 0.71]]


class ZoneCreate(BaseModel):
    camera_id: UUID
    zone_type: ZoneType
    name: str | None = Field(
        default=None,
        max_length=200,
        description="Название участка; по умолчанию — название типа из enums.yaml («Котлован»). "
        "Одинаковые тип и название на разных камерах — один участок",
    )
    polygon: list[list[float]] = Field(examples=[POLYGON_EXAMPLE])


class ZoneUpdate(BaseModel):
    """Правка полигона, типа или названия; `is_active: true` возвращает зону. Версия растёт."""

    zone_type: ZoneType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    polygon: list[list[float]] | None = None
    is_active: bool | None = None


class ZoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_id: UUID
    camera_id: UUID
    zone_type: str
    name: str
    polygon: list[list[float]]
    version: int
    is_active: bool

    @computed_field(description="Ключ участка `ТИП:Название`")
    @property
    def area(self) -> str:
        return area_key(self.zone_type, self.name)


class ImportZone(BaseModel):
    zone_type: ZoneType
    name: str | None = Field(default=None, max_length=200)
    polygon: list[list[float]]


class ImportCamera(BaseModel):
    code: str = Field(pattern=CODE_PATTERN)
    name: str | None = Field(default=None, max_length=200)
    reference_image: str | None = Field(
        default=None,
        description="Путь снимка в папке загрузки. Пока не используется: эталонным кадром "
        "становится первый загруженный снимок камеры",
    )
    zones: list[ImportZone] = Field(default_factory=list)


class ZonesImport(BaseModel):
    """Формат `data/seed/cameras.json` (data/README.md) плюс объект, к которому он относится."""

    object_id: UUID
    cameras: list[ImportCamera] = Field(min_length=1)


class AreaCamera(BaseModel):
    camera_id: UUID
    camera_code: str
    zone_id: UUID


class AreaRead(BaseModel):
    area: str = Field(description="Ключ участка `ТИП:Название`")
    zone_type: str
    name: str
    role: str = Field(description="Роль типа зоны из enums.yaml: WORK, SERVICE, SAFETY")
    cameras: list[AreaCamera] = Field(description="Активные камеры, на которых размечен участок")


class ObjectAreas(BaseModel):
    object_id: UUID
    zones_version: int = Field(
        description="Сумма версий всех зон объекта, включая неактивные: растёт при любой правке"
    )
    areas: list[AreaRead]


class ZonesReapply(BaseModel):
    object_id: UUID


class ReapplyQueued(BaseModel):
    object_id: UUID
    queued: bool = Field(description="Пересчёт поставлен в очередь site-worker")


class ZonesImportResult(ObjectAreas):
    cameras_created: int
    cameras_updated: int
    zones_created: int
    zones_updated: int
    zones_deactivated: int
    zones_unchanged: int
