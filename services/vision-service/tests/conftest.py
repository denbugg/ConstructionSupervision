"""Общие фикстуры: настоящие справочные файлы и модели-заглушки.

Настоящие модели в тестах не грузятся: качество модели проверяется метриками на тестовом
наборе (ml/README.md), а здесь — всё, что вокруг неё (README, раздел 7).
"""

import io
import os
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

SERVICE_ROOT = Path(__file__).resolve().parents[1]
# Справочные файлы: в контейнере — CONTRACTS_DIR, в рабочей копии и CI — packages/contracts.
CONTRACTS_DIR = Path(os.getenv("CONTRACTS_DIR") or SERVICE_ROOT.parents[1] / "packages/contracts")
os.environ["CONTRACTS_DIR"] = str(CONTRACTS_DIR)

from src.config import settings  # noqa: E402
from src.core.detections import RawBox  # noqa: E402
from src.main import app  # noqa: E402
from src.models.runtime import LoadedModels  # noqa: E402
from src.reference import stage_prompts, vocabulary  # noqa: E402

API_KEY = {"X-API-Key": settings.api_key}


class StubDetector:
    """Детектор, который возвращает заранее заданные рамки и запоминает кадры."""

    name = "stub-detector"

    def __init__(self, boxes: Sequence[RawBox] = ()) -> None:
        self.boxes = list(boxes)
        self.seen: list[tuple[int, int]] = []

    def detect(self, image: Image.Image) -> list[RawBox]:
        self.seen.append(image.size)
        return self.boxes


class StubStageClassifier:
    name = "stub-stage"

    def __init__(self, logits: Sequence[float]) -> None:
        self._logits = list(logits)

    def logits(self, image: Image.Image) -> list[float]:
        return self._logits


class BrokenDetector:
    name = "broken"

    def detect(self, image: Image.Image) -> list[RawBox]:
        raise RuntimeError("CUDA out of memory")


def image_bytes(size: tuple[int, int] = (200, 100), fmt: str = "JPEG", color="gray") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def make_models(detector=None, stage=None) -> LoadedModels:
    prompts = stage_prompts()
    return LoadedModels(
        detector=detector or StubDetector(),
        stage_classifier=stage,
        device="cpu",
        vocabulary=vocabulary(),
        stage_labels=prompts.labels,
    )


@pytest.fixture
def models() -> LoadedModels:
    """Детектор без рамок и классификатор, уверенно выбирающий первую стадию."""
    labels = stage_prompts().labels
    return make_models(StubDetector(), StubStageClassifier([30.0] + [10.0] * (len(labels) - 1)))


@pytest.fixture
async def client(models: LoadedModels) -> AsyncIterator[AsyncClient]:
    app.state.models = models
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=API_KEY) as c:
        yield c
    app.state.models = None
