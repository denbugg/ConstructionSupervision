"""Загрузка моделей при старте и их общее состояние в процессе.

Веса грузятся в фоне: /health отвечает сразу, а /health/ready и распознавание ждут, пока
модели окажутся в памяти (README, раздел 6).
"""

import threading
from dataclasses import dataclass, field
from typing import Protocol

from lct_common import get_logger
from PIL import Image

from src.config import Settings
from src.core.detections import RawBox
from src.core.stages import StagePrompts
from src.core.vocabulary import Vocabulary

log = get_logger(__name__)

# Размер кадра прогрева: первый проход на GPU компилирует ядра и длится секунды, пусть это
# случится до готовности, а не на первом снимке site-worker.
WARMUP_SIZE = (640, 480)


class Detector(Protocol):
    name: str

    def detect(self, image: Image.Image) -> list[RawBox]: ...


class StageClassifier(Protocol):
    name: str

    def logits(self, image: Image.Image) -> list[float]: ...


@dataclass
class LoadedModels:
    """Всё, что нужно для распознавания: модели, устройство, словарь, метки стадий."""

    detector: Detector
    stage_classifier: StageClassifier | None
    device: str
    vocabulary: Vocabulary
    stage_labels: tuple[str, ...]
    # Предсказатель Ultralytics не потокобезопасен, а GPU одна: запросы проходят через
    # модели по одному, параллельность даёт число реплик.
    lock: threading.Lock = field(default_factory=threading.Lock)


def load_models(
    config: Settings, vocabulary: Vocabulary, stage_prompts: StagePrompts
) -> LoadedModels:
    """Загрузить модели на устройство из настроек и прогнать один пустой кадр."""
    from src.models.detector import YoloWorldDetector
    from src.models.stage_classifier import OpenClipStageClassifier

    device = resolve_device(config.vision_device)
    detector = YoloWorldDetector(
        config.vision_det_weights,
        vocabulary.prompts,
        device,
        imgsz=config.vision_det_imgsz,
        conf=config.vision_det_conf,
        iou=config.vision_det_iou,
    )
    stage_classifier = None
    if config.vision_stage_enabled:
        stage_classifier = OpenClipStageClassifier(
            config.vision_stage_model,
            config.vision_stage_arch,
            config.stage_weights,
            stage_prompts,
            device,
        )

    blank = Image.new("RGB", WARMUP_SIZE)
    detector.detect(blank)
    if stage_classifier is not None:
        stage_classifier.logits(blank)
    return LoadedModels(detector, stage_classifier, device, vocabulary, stage_prompts.labels)


def resolve_device(requested: str) -> str:
    """Запрошенное устройство или cpu, если карты в контейнере не видно."""
    import torch

    if requested.startswith("cuda") and not torch.cuda.is_available():
        log.warning("vision.cuda_unavailable", requested=requested, fallback="cpu")
        return "cpu"
    return requested
