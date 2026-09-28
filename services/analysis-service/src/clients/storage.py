"""Хранилище отчётов (S3, бакет `reports`). Единственное место с кодом S3 в analysis.

Клиент `minio` синхронный, поэтому вызовы уходят в пул потоков. Ссылка для браузера
подписывается вторым клиентом на публичный адрес: подпись привязана к хосту, и
`s3:8333` браузер не откроет (architecture.md, 7.2). Повторяет клиент site-service:
импортировать код чужого сервиса нельзя (AGENTS.md, раздел 6).
"""

import asyncio
import io
from dataclasses import dataclass
from datetime import datetime, timedelta
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


@dataclass(frozen=True)
class StoredFile:
    key: str
    size: int
    modified_at: datetime


def _client(endpoint: str, access_key: str, secret_key: str) -> Minio:
    url = urlparse(endpoint)
    return Minio(
        url.netloc,
        access_key=access_key,
        secret_key=secret_key,
        secure=url.scheme == "https",
        region=REGION,
    )


class ReportStorage:
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

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        await self._call(
            lambda: self._client.put_object(
                self._bucket, key, io.BytesIO(content), len(content), content_type=content_type
            )
        )

    async def list_files(self, prefix: str) -> list[StoredFile]:
        def collect() -> list[StoredFile]:
            return [
                StoredFile(key=o.object_name, size=o.size or 0, modified_at=o.last_modified)
                for o in self._client.list_objects(self._bucket, prefix=prefix, recursive=True)
                if o.object_name and o.last_modified
            ]

        return await self._call(collect)

    async def stat(self, key: str) -> StoredFile | None:
        """Файл по ключу; None — такого нет."""

        def stat() -> StoredFile | None:
            try:
                found = self._client.stat_object(self._bucket, key)
            except S3Error as exc:
                if exc.code in ("NoSuchKey", "NoSuchObject"):
                    return None
                raise
            return StoredFile(key=key, size=found.size or 0, modified_at=found.last_modified)

        return await self._call(stat)

    async def presigned_url(self, key: str) -> str:
        """Ссылка для браузера на публичный адрес хранилища, живёт S3_PRESIGN_TTL_S."""
        return await self._call(
            lambda: self._public.presigned_get_object(self._bucket, key, expires=self._ttl)
        )

    async def _call(self, operation):
        try:
            return await asyncio.to_thread(operation)
        except (S3Error, HTTPError, OSError) as exc:
            log.warning("storage.failed", error=str(exc))
            raise StorageUnavailable("Хранилище отчётов недоступно") from exc
