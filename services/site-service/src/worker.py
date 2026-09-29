"""site-worker: распознавание снимков и пересчёт фактов окон (README, раздел 4).

Тот же образ, что у API, другой процесс: `arq src.worker.WorkerSettings`. Воркеров может быть
сколько угодно — снимок забирается в работу одним UPDATE, окно пересчитывается под замком.
"""

import logging
from typing import Any, ClassVar
from uuid import UUID

from arq import cron, func
from arq.connections import RedisSettings
from lct_common import get_logger, setup_logging
from lct_common.db import create_engine, create_session_factory

from src.clients.analysis_client import AnalysisClient
from src.clients.queue import ANALYZE_IMAGE, REAPPLY_ZONES, RecognitionQueue
from src.clients.storage import ImageStorage
from src.clients.vision_client import VisionClient
from src.config import settings
from src.reference import enums
from src.services.recognition import Recognition

setup_logging("site-worker", settings.log_level, pretty=settings.is_dev)
# У arq свой обработчик логов; без этого каждая его строка дублировалась бы через наш корневой.
logging.getLogger("arq").propagate = False
log = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    engine = create_engine(settings.site_db_dsn, echo=settings.db_echo)
    clients = {
        "vision": VisionClient(
            settings.vision_url,
            api_key=settings.api_key,
            timeout_s=settings.vision_timeout_s,
            retries=settings.vision_retries,
        ),
        "analysis": AnalysisClient(
            settings.analysis_url,
            service="analysis",
            api_key=settings.api_key,
            timeout_s=settings.analysis_timeout_s,
            retries=0,
        ),
        "queue": RecognitionQueue(settings.redis_url),
    }
    ctx.update(engine=engine, **clients)
    ctx["recognition"] = Recognition(
        create_session_factory(engine),
        ImageStorage(
            endpoint=settings.s3_endpoint,
            public_path=settings.s3_public_path,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            bucket=settings.s3_bucket_images,
            presign_ttl_s=settings.s3_presign_ttl_s,
        ),
        clients["vision"],
        clients["analysis"],
        clients["queue"],
        settings,
    )
    # enums.yaml читается сразу: испорченный файл — ошибка старта, а не каждой задачи.
    log.info("worker.started", zone_types=len(enums().zone_types), jobs=settings.worker_concurrency)


async def shutdown(ctx: dict[str, Any]) -> None:
    for name in ("vision", "analysis", "queue"):
        await ctx[name].aclose()
    await ctx["engine"].dispose()
    log.info("worker.stopped")


async def analyze_image(ctx: dict[str, Any], image_id: str) -> str:
    outcome = await ctx["recognition"].analyze_image(UUID(image_id))
    log.info("recognition.done", image_id=image_id, outcome=outcome)
    return outcome


async def reapply_zones(ctx: dict[str, Any], object_id: str) -> int:
    windows = await ctx["recognition"].reapply_zones(UUID(object_id))
    log.info("zones.reapplied", object_id=object_id, windows=windows)
    return windows


async def sweep(ctx: dict[str, Any]) -> None:
    queued = await ctx["recognition"].sweep()
    if queued:
        log.info("recognition.sweep", queued=queued)


class WorkerSettings:
    functions: ClassVar[list] = [
        # Таймаут задачи покрывает все попытки vision и запись результата.
        func(
            analyze_image,
            name=ANALYZE_IMAGE,
            timeout=settings.vision_timeout_s * (settings.vision_retries + 1) + 60,
            max_tries=1,
        ),
        func(reapply_zones, name=REAPPLY_ZONES, timeout=settings.reapply_timeout_s, max_tries=1),
    ]
    # Проход по базе: SWEEP_INTERVAL_S делит минуту нацело (cron arq задаётся секундами).
    cron_jobs: ClassVar[list] = [
        cron(sweep, second=set(range(0, 60, settings.sweep_interval_s)), run_at_startup=True)
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.worker_concurrency
    # Результат задачи не хранится: иначе снимок нельзя было бы поставить в очередь снова
    # тем же ID задачи ещё час (повторное распознавание, возврат из PENDING).
    keep_result = 0
    on_startup = startup
    on_shutdown = shutdown
