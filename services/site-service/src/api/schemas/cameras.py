"""DTO камер. Камера — точка съёмки: подпапка при загрузке снимков совпадает с `code`."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"


class CameraCreate(BaseModel):
    object_id: UUID
    code: str = Field(
        pattern=CODE_PATTERN,
        examples=["cam-north"],
        description="Он же имя подпапки при пакетной загрузке; в объекте не повторяется",
    )
    name: str | None = Field(
        default=None, max_length=200, description="По умолчанию совпадает с кодом"
    )
    install_meta: dict = Field(
        default_factory=dict, description="Высота подвеса, азимут, ИК-подсветка"
    )


class CameraUpdate(BaseModel):
    """Частичное изменение. Код не меняется: по нему снимки раскладываются по камерам."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    reference_image_id: UUID | None = Field(
        default=None, description="Эталонный кадр — снимок этой камеры, на нём размечают зоны"
    )
    install_meta: dict | None = None
    is_active: bool | None = None


class CameraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_id: UUID
    code: str
    name: str
    reference_image_id: UUID | None
    install_meta: dict
    is_active: bool
