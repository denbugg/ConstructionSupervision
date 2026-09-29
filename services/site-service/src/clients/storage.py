"""Объектное хранилище снимков (S3-совместимое). Единственное место с кодом S3.

Клиент `minio` синхронный, поэтому каждый вызов уходит в пул потоков: обработчик запроса
не блокирует цикл событий (CONTRIBUTING.md, раздел 8). Ссылка для браузера — относительный путь
на gateway (ADR-0017): подписана на внутренний адрес, gateway отдаёт её из хранилища.
"""

import asyncio
import io
from datetime import timedelta
from urllib.parse import urlparse, urlsplit

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
        public_path: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        presign_ttl_s: int,
    ) -> None:
        self._client = _client(endpoint, access_key, secret_key)
        self._public_path = public_path.rstrip("/")
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
        """Ссылка для браузера: путь под S3_PUBLIC_PATH на том же адресе, что и интерфейс.

        Хост в ссылку не попадает: браузер откроет её по тому адресу, по которому пришёл
        (localhost, локальная сеть, туннель). Подпись сделана на внутренний адрес, и gateway
        передаёт хранилищу именно его в `Host`, поэтому подпись сходится.
        """
        signed = urlsplit(await self.internal_url(key))
        return f"{self._public_path}{signed.path}?{signed.query}"

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
