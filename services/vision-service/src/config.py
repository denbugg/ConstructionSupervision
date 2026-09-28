"""Конфигурация vision-service. Единственное место чтения окружения.

Смена модели — смена этих переменных, а не кода (README, раздел 5).
"""

from lct_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "vision-service"

    # Справочные файлы контрактов только для чтения: equipment_classes.yaml (словарь
    # детектора) и enums.yaml (метки стадий).
    contracts_dir: str = "/contracts"
    # Промпты стадий — справочник самого сервиса.
    stage_prompts_file: str = "data/stage_prompts.yaml"

    # Устройство инференса. На демо-стенде — cuda; если контейнер карту не видит, сервис
    # уходит на cpu и показывает фактическое устройство в GET /model (README, раздел 8).
    vision_device: str = "cuda"

    # Детектор: веса YOLO-World или дообученные на тех же классах.
    vision_det_weights: str = "/models/yolov8s-worldv2.pt"
    vision_det_conf: float = 0.35
    vision_det_iou: float = 0.5
    # Размер входа — главный рычаг «скорость против качества».
    vision_det_imgsz: int = 1280

    # Классификатор стадии: имя — каталог весов в vision_models_dir, архитектура — имя
    # модели OpenCLIP.
    vision_stage_enabled: bool = True
    vision_stage_model: str = "openclip-vit-b32"
    vision_stage_arch: str = "ViT-B-32"
    vision_models_dir: str = "/models"

    # Приём изображения.
    vision_max_mb: int = 20
    vision_fetch_timeout_s: float = 10.0

    # Качество кадра: длинная сторона кадра для метрик и дисперсия Лапласиана, при которой
    # размытость равна 0,5. Это масштаб шкалы, а не порог годности: порог MAX_BLUR — в site.
    vision_quality_side: int = 512
    vision_blur_ref: float = 100.0

    @property
    def stage_weights(self) -> str:
        return f"{self.vision_models_dir}/{self.vision_stage_model}/open_clip_model.safetensors"


settings = Settings()
