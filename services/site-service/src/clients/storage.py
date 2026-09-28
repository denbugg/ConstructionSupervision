"""Объектное хранилище снимков (S3-совместимое). Единственное место с кодом S3.

Клиент `minio` синхронный, поэтому каждый вызов уходит в пул потоков: обработчик запроса
не блокирует цикл событий (AGENTS.md, раздел 8). Ссылки для браузера подписываются вторым
клиентом на публичный адрес: подпись S3 привязана к хосту, и `s3:8333` браузер не откроет.
"""

import asyncio
import io
from datetime import timedelta
from urllib.parse import urlparse

from lct_common import UpstreamError, get_logger
from minio import Minio
from minio.error import S3Error
from urllib3.exceptions import HTTPError

log = get_logger(__name__)
# Регион задан явно: без него клиент идёт в сеть узнавать регион бакета даже для подписи ссылки.
REGION = "us-east-1"


class StorageUnavailable(UpstreamError):
    code = "STORAGE_UNAVAILABLE"


def _client(endpoint: str, access_key: str, secret_key: str) -> Minio:
    url = urlparse(endpoint)
    return Minio(
        url.netloc,
        access_key=access_key,
        secret_key=secret_key,
        secure=url.scheme == "https",
        region=REGION,
    )


class ImageStorage:
    def __init__(
        self,
        *,
        endpoint: str,
        public_endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        presign_ttl_s: int,
    ) -> None:
        self._client = _client(endpoint, access_key, secret_key)
        self._public = _client(public_endpoint, access_key, secret_key)
        self._bucket = bucket
        self._ttl = timedelta(seconds=presign_ttl_s)

    async def ensure_bucket(self) -> None:
        def ensure() -> None:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)

        await self._call(ensure)

    async def ping(self) -> bool:
        """Для /health/ready: хранилище отвечает и бакет на месте."""
        return await self._call(lambda: self._client.bucket_exists(self._bucket))

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        await self._call(
            lambda: self._client.put_object(
                self._bucket, key, io.BytesIO(content), len(content), content_type=content_type
            )
        )

    async def presigned_url(self, key: str) -> str:
        """Ссылка для браузера на публичный адрес хранилища, живёт S3_PRESIGN_TTL_S."""
        return await self._call(
            lambda: self._public.presigned_get_object(self._bucket, key, expires=self._ttl)
        )

    async def internal_url(self, key: str) -> str:
        """Ссылка для vision-service внутри сети Docker."""
        return await self._call(
            lambda: self._client.presigned_get_object(self._bucket, key, expires=self._ttl)
        )

    async def _call(self, operation):
        try:
            return await asyncio.to_thread(operation)
        except (S3Error, HTTPError, OSError) as exc:
            log.warning("storage.failed", error=str(exc))
            raise StorageUnavailable("Хранилище снимков недоступно") from exc
