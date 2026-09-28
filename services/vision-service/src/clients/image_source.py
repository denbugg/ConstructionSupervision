"""Скачивание снимка по ссылке: presigned-ссылка S3 от site-worker (interservice.md, раздел 3).

Повторов здесь нет: задача идемпотентна, и повторяет её вызывающий (30 с, два повтора).
Ссылка в лог не пишется целиком — в её параметрах подпись доступа.
"""

from urllib.parse import urlsplit

import httpx
from lct_common import UpstreamError, get_logger

log = get_logger(__name__)


class ImageSourceUnavailable(UpstreamError):
    """Снимок по ссылке не скачался: хранилище недоступно, ссылка истекла или не найдена."""


class ImageSourceTooLarge(ValueError):
    """Снимок по ссылке больше допустимого размера."""


async def fetch_image(url: str, max_bytes: int, timeout_s: float) -> bytes:
    """Байты снимка; скачивание обрывается, как только превышен предел размера."""
    host = urlsplit(url).netloc
    try:
        async with (
            httpx.AsyncClient(timeout=timeout_s) as client,
            client.stream("GET", url) as response,
        ):
            if response.status_code != 200:
                raise ImageSourceUnavailable(
                    "Снимок по ссылке недоступен", host=host, status=response.status_code
                )
            declared = int(response.headers.get("content-length") or 0)
            if declared > max_bytes:
                raise ImageSourceTooLarge(declared)
            chunks: list[bytes] = []
            received = 0
            async for chunk in response.aiter_bytes():
                received += len(chunk)
                if received > max_bytes:
                    raise ImageSourceTooLarge(received)
                chunks.append(chunk)
            return b"".join(chunks)
    except httpx.HTTPError as exc:
        log.warning("image_source.failed", host=host, error=type(exc).__name__)
        raise ImageSourceUnavailable(
            "Снимок по ссылке недоступен", host=host, reason=type(exc).__name__
        ) from exc
