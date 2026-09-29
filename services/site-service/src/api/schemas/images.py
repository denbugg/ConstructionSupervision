"""DTO приёма снимков (api-guidelines.md, раздел 7)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AcceptedImage(BaseModel):
    image_id: UUID
    file: str
    camera_code: str
    captured_at: datetime | None = Field(description="UTC; null — ждёт ручного ввода")
    captured_at_source: str = Field(description="EXIF, FILENAME, MANUAL или UNKNOWN")
    time_detail: str = Field(description="Откуда взято время, словами")
    status: str = Field(description="PENDING — ждёт распознавания, NEEDS_TIME — ждёт времени")


class RejectedImage(BaseModel):
    file: str
    code: str = Field(
        description="IMAGE_ALREADY_EXISTS, IMAGE_TOO_LARGE, UNSUPPORTED_MEDIA_TYPE, "
        "CAMERA_REQUIRED, STORAGE_UNAVAILABLE"
    )
    message: str
    image_id: UUID | None = Field(default=None, description="Для повтора — id уже загруженного")


class IntakeResult(BaseModel):
    """Частичный успех: отклонённый файл — строка в `rejected`, а не ошибка запроса."""

    accepted: list[AcceptedImage]
    rejected: list[RejectedImage]


class ImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_id: UUID
    camera_id: UUID
    captured_at: datetime | None
    captured_at_source: str
    session_id: UUID | None = Field(description="Окно наблюдения; null — пока нет времени")
    width: int | None
    height: int | None
    status: str
    usable: bool | None = Field(description="Пригоден ли кадр; null — ещё не распознан")
    usable_reason: str | None
    source: str
    received_at: datetime


class DetectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    equipment_class: str
    bbox: list[float] = Field(description="[x1, y1, x2, y2] в долях 0…1 от размера кадра")
    conf: float
    anchor: list[float] = Field(description="Точка контакта с землёй — по ней выбрана зона")
    zone_id: UUID | None
    moved: bool | None
    displacement: float | None
    model_version: str


class StageObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage_label: str
    conf: float
    scores: dict[str, float]


class ImageDetail(ImageRead):
    url: str = Field(
        description="Для браузера — путь без хоста под S3_PUBLIC_PATH (`/storage/images/…`), "
        "открывается относительно адреса gateway; при link=internal — полная ссылка на "
        "S3_ENDPOINT. Живёт S3_PRESIGN_TTL_S"
    )
    exif: dict
    quality: dict = Field(description="Яркость и размытость от vision-service")
    error: str | None
    detections: list[DetectionRead] = Field(description="Рамки техники; пусто до распознавания")
    stage: StageObservationRead | None = Field(description="Стадия объекта по снимку")


class ImageTimeUpdate(BaseModel):
    captured_at: str = Field(
        description="ISO-8601; без смещения — местное время камеры (`CAMERA_TIMEZONE`)",
        examples=["2026-10-20T12:03:00", "2026-10-20T09:03:00Z"],
    )


class ReanalyzeRequest(BaseModel):
    object_id: UUID
    camera_id: UUID | None = Field(default=None, description="Только снимки этой камеры")


class ReanalyzeResult(BaseModel):
    object_id: UUID
    images: int = Field(description="Сколько распознанных и отказных снимков снова в PENDING")


class FolderImport(BaseModel):
    object_id: UUID
    path: str = Field(
        default="",
        description="Папка внутри IMPORT_DIR; каждая её подпапка — код камеры. Пусто — сам "
        "IMPORT_DIR",
        examples=["", "day1"],
    )
