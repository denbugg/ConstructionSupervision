"""Очередь задач распознавания (arq поверх Redis).

Очередь только ускоряет: задача, потерянная вместе с Redis, не теряет снимок — его статус
`PENDING` в базе, и проход воркера по базе поставит его снова (README, раздел 4).
"""

from collections.abc import Iterable
from uuid import UUID

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from lct_common import get_logger
from redis.exceptions import RedisError

log = get_logger(__name__)

ANALYZE_IMAGE = "analyze_image"
REAPPLY_ZONES = "reapply_zones"


def job_id(image_id: UUID) -> str:
    """Один снимок — одна задача в очереди: повторная постановка ничего не добавляет."""
    return f"{ANALYZE_IMAGE}:{image_id}"


class RecognitionQueue:
    def __init__(self, redis_url: str) -> None:
        self._settings = RedisSettings.from_dsn(redis_url)
        self._pool: ArqRedis | None = None

    async def ping(self) -> None:
        """Для /health/ready: очередь отвечает."""
        await (await self._connection()).ping()

    async def enqueue(self, image_ids: Iterable[UUID]) -> None:
        """Поставить снимки в очередь; недоступный Redis только пишется в лог."""
        ids = list(image_ids)
        if not ids:
            return
        try:
            pool = await self._connection()
            for image_id in ids:
                await pool.enqueue_job(ANALYZE_IMAGE, str(image_id), _job_id=job_id(image_id))
        except (RedisError, OSError) as exc:
            log.warning("queue.unavailable", images=len(ids), error=type(exc).__name__)

    async def enqueue_reapply(self, object_id: UUID) -> bool:
        """Поставить пересчёт зон объекта; False — очередь недоступна (записано в лог).

        ID задачи не фиксирован: правка во время уже идущего пересчёта должна дать ещё один,
        иначе он посчитал бы факты по разметке до правки. Два пересчёта подряд безвредны —
        окна пересчитываются под замком и целиком.
        """
        try:
            await (await self._connection()).enqueue_job(REAPPLY_ZONES, str(object_id))
        except (RedisError, OSError) as exc:
            log.warning("queue.unavailable", object_id=str(object_id), error=type(exc).__name__)
            return False
        return True

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()

    async def _connection(self) -> ArqRedis:
        if self._pool is None:
            # Одна попытка без ожидания: запрос загрузки не должен висеть из-за Redis.
            self._settings.conn_retries = 0
            self._pool = await create_pool(self._settings)
        return self._pool
