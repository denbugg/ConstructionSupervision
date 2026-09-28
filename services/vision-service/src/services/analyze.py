"""Распознавание снимка: байты или ссылка → детекции, стадия, качество (F2, F6).

Вся работа с пикселями идёт в пуле потоков: декодирование и модели блокируют, а цикл событий
должен успевать отвечать на /health, пока идёт инференс.
"""

import asyncio
import time

from lct_common import DomainError, ValidationError, get_logger
from PIL import Image

from src.api.schemas.analyze import (
    AnalyzeResult,
    ClassRead,
    DetectionRead,
    ImageSize,
    ModelInfo,
    ModelRead,
    QualityRead,
    StageRead,
)
from src.clients.image_source import ImageSourceTooLarge, fetch_image
from src.config import Settings
from src.core.detections import postprocess
from src.core.imaging import (
    ImageDecodeError,
    UnsupportedImageFormat,
    decode_image,
    gray_for_quality,
)
from src.core.quality import frame_quality
from src.core.stages import stage_from_logits
from src.models.runtime import LoadedModels

log = get_logger(__name__)


class UnsupportedMediaType(ValidationError):
    code = "UNSUPPORTED_MEDIA_TYPE"


class ImageDecodeFailed(ValidationError):
    code = "IMAGE_DECODE_FAILED"


class ImageTooLarge(DomainError):
    code = "IMAGE_TOO_LARGE"
    http_status = 413


class ModelNotLoaded(DomainError):
    code = "MODEL_NOT_LOADED"
    http_status = 503


class InferenceFailed(DomainError):
    code = "INFERENCE_FAILED"
    http_status = 500


class Analyzer:
    def __init__(self, models: LoadedModels | None, config: Settings) -> None:
        self._models = models
        self._config = config

    @property
    def max_bytes(self) -> int:
        return self._config.vision_max_mb * 1024 * 1024

    def describe(self) -> ModelRead:
        """Что загружено и с какими порогами работает детектор."""
        models = self._require_models()
        vocabulary = models.vocabulary
        return ModelRead(
            **self._model_info(models).model_dump(),
            classes=[
                ClassRead(code=c, prompts=list(vocabulary.prompts_of(c))) for c in vocabulary.codes
            ],
            stage_labels=list(models.stage_labels),
            det_conf=self._config.vision_det_conf,
            det_iou=self._config.vision_det_iou,
            det_imgsz=self._config.vision_det_imgsz,
        )

    async def analyze_url(self, url: str) -> AnalyzeResult:
        self._require_models()
        try:
            content = await fetch_image(url, self.max_bytes, self._config.vision_fetch_timeout_s)
        except ImageSourceTooLarge as exc:
            raise self._too_large(exc.args[0]) from exc
        return await self.analyze_bytes(content)

    async def analyze_bytes(self, content: bytes) -> AnalyzeResult:
        models = self._require_models()
        if len(content) > self.max_bytes:
            raise self._too_large(len(content))
        return await asyncio.to_thread(self._run, models, content)

    def _run(self, models: LoadedModels, content: bytes) -> AnalyzeResult:
        image = self._decode(content)
        quality = frame_quality(
            gray_for_quality(image, self._config.vision_quality_side), self._config.vision_blur_ref
        )
        with models.lock:
            started = time.perf_counter()
            try:
                boxes = models.detector.detect(image)
                logits = models.stage_classifier.logits(image) if models.stage_classifier else None
            except Exception as exc:
                log.exception("vision.inference_failed", error=type(exc).__name__)
                raise InferenceFailed("Ошибка распознавания", error=type(exc).__name__) from exc
            inference_ms = round((time.perf_counter() - started) * 1000)

        detections = postprocess(
            boxes,
            image.width,
            image.height,
            models.vocabulary.prompt_codes,
            self._config.vision_det_conf,
            self._config.vision_det_iou,
        )
        stage = stage_from_logits(models.stage_labels, logits) if logits is not None else None
        return AnalyzeResult(
            model=self._model_info(models),
            image=ImageSize(width=image.width, height=image.height),
            detections=[
                DetectionRead(equipment_class=d.equipment_class, bbox=list(d.bbox), conf=d.conf)
                for d in detections
            ],
            stage=StageRead(label=stage.label, conf=stage.conf, scores=stage.scores)
            if stage
            else None,
            quality=QualityRead(brightness=quality.brightness, blur=quality.blur),
            inference_ms=inference_ms,
        )

    def _decode(self, content: bytes) -> Image.Image:
        try:
            return decode_image(content)
        except UnsupportedImageFormat as exc:
            raise UnsupportedMediaType(
                "Формат изображения не поддерживается: нужен JPEG, PNG или WebP", reason=str(exc)
            ) from exc
        except ImageDecodeError as exc:
            raise ImageDecodeFailed("Изображение не читается", reason=str(exc)) from exc

    def _require_models(self) -> LoadedModels:
        if self._models is None:
            raise ModelNotLoaded("Модели ещё загружаются или не загрузились")
        return self._models

    def _model_info(self, models: LoadedModels) -> ModelInfo:
        return ModelInfo(
            detector=models.detector.name,
            stage_classifier=models.stage_classifier.name if models.stage_classifier else None,
            device=models.device,
            classes_version=models.vocabulary.version,
        )

    def _too_large(self, size: int) -> ImageTooLarge:
        return ImageTooLarge(
            f"Изображение больше {self._config.vision_max_mb} МБ",
            limit_mb=self._config.vision_max_mb,
            size_bytes=size,
        )
