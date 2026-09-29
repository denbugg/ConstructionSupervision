"""Схемы распознавания: вход и выход POST /analyze, описание моделей GET /model.

Контракт — packages/contracts/interservice.md, раздел 3. Коды классов и метки стадий — строки,
а не перечисления в коде: их набор задают справочные файлы (CONTRIBUTING.md, раздел 7).
"""

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    image_url: str = Field(
        pattern=r"^https?://",
        description="Ссылка на снимок; site-worker передаёт presigned-ссылку S3",
        examples=["http://s3:8333/images/0f3a/cam-north/2026-10-20/9e41.jpg?X-Amz-Signature=…"],
    )


class ModelInfo(BaseModel):
    detector: str = Field(examples=["yolov8s-worldv2"])
    stage_classifier: str | None = Field(
        examples=["openclip-vit-b32"], description="`null` при `VISION_STAGE_ENABLED=false`"
    )
    device: str = Field(examples=["cuda"], description="Фактическое устройство инференса")
    classes_version: str = Field(
        examples=["3f9a1c2e"], description="Первые 8 символов sha256 файла equipment_classes.yaml"
    )


class ImageSize(BaseModel):
    width: int
    height: int


class DetectionRead(BaseModel):
    equipment_class: str = Field(description="Код из equipment_classes.yaml, включая `person`")
    bbox: list[float] = Field(
        min_length=4,
        max_length=4,
        description="[x1, y1, x2, y2], доли кадра 0…1 от левого верхнего угла",
        examples=[[0.41, 0.52, 0.49, 0.63]],
    )
    conf: float = Field(description="Не ниже `VISION_DET_CONF`")


class StageRead(BaseModel):
    label: str = Field(description="Значение `stage_label` из enums.yaml")
    conf: float
    scores: dict[str, float] = Field(description="Вероятность каждой метки стадии")


class QualityRead(BaseModel):
    brightness: float = Field(description="Средняя яркость кадра, 0…1")
    blur: float = Field(description="Размытость кадра, 0…1; больше — хуже")


class AnalyzeResult(BaseModel):
    model: ModelInfo
    image: ImageSize
    detections: list[DetectionRead]
    stage: StageRead | None = Field(description="`null` при `VISION_STAGE_ENABLED=false`")
    quality: QualityRead
    inference_ms: int = Field(description="Время моделей на снимок без скачивания и очереди")


class ClassRead(BaseModel):
    code: str
    prompts: list[str]


class ModelRead(ModelInfo):
    classes: list[ClassRead] = Field(description="Словарь детектора из equipment_classes.yaml")
    stage_labels: list[str]
    det_conf: float
    det_iou: float
    det_imgsz: int
