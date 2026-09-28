"""Клиент vision-service: распознавание снимка по ссылке (interservice.md, раздел 3)."""

import asyncio
from typing import Any

from lct_common import ServiceClient, UpstreamError, get_logger

log = get_logger(__name__)


class VisionUnavailable(UpstreamError):
    """vision не ответил: снимок вернётся в очередь и будет распознан позже."""

    code = "VISION_UNAVAILABLE"


class VisionRejected(UpstreamError):
    """vision отказался распознавать снимок (битый файл, не тот формат): повтор не поможет."""

    code = "VISION_REJECTED"


class VisionClient(ServiceClient):
    def __init__(self, base_url: str, *, api_key: str, timeout_s: float, retries: int) -> None:
        # Повторы — здесь, а не в ServiceClient: тот не повторяет POST, а распознавание
        # идемпотентно — тот же снимок даёт тот же ответ.
        super().__init__(
            base_url, service="vision", api_key=api_key, timeout_s=timeout_s, retries=0
        )
        self._attempts = retries + 1

    async def analyze(self, image_url: str) -> dict[str, Any]:
        """Рамки, стадия и качество кадра; отказ по самому снимку не повторяется."""
        last: UpstreamError | None = None
        for attempt in range(self._attempts):
            try:
                return await self.post("/api/v1/vision/analyze", json={"image_url": image_url})
            except UpstreamError as exc:
                # Ответ с кодом ошибки vision — отказ по самому снимку; без кода — сбой сети
                # или 5xx, который может пройти.
                if "upstream_code" in exc.details:
                    raise VisionRejected(exc.message, **exc.details) from exc
                last = exc
            if attempt < self._attempts - 1:
                log.warning("vision.retry", attempt=attempt + 1)
                await asyncio.sleep(self._backoff_s * 2**attempt)
        details = last.details if last else {}
        raise VisionUnavailable("Сервис распознавания недоступен", **details) from last
