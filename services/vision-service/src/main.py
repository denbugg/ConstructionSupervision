"""Точка входа vision-service.

Распознавание на снимке: детекция техники, стадия объекта, качество кадра
(F2, F6). Сервис ничего не знает о предметной области и не хранит состояние —
это чистая функция «картинка → факты о картинке», масштабируемая репликами.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from lct_common import (
    HealthCheck,
    RequestIdMiddleware,
    get_logger,
    install_error_handlers,
    make_health_router,
    setup_logging,
)

from src.api.routes import api_router
from src.config import settings
from src.core.stages import StagePrompts
from src.core.vocabulary import Vocabulary
from src.reference import stage_prompts, vocabulary

setup_logging(settings.service_name, settings.log_level, pretty=settings.is_dev)
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Справочные файлы читаются сразу, веса — в фоне: /health отвечает, пока они грузятся."""
    app.state.models = None
    # Испорченный справочник — ошибка старта, а не сервис, который вечно «загружается».
    vocab, prompts = vocabulary(), stage_prompts()
    loading = asyncio.create_task(_load_models(app, vocab, prompts))
    log.info(
        "service.started",
        version=settings.version,
        env=settings.env,
        classes=len(vocab.codes),
        classes_version=vocab.version,
    )
    yield
    loading.cancel()
    log.info("service.stopped")


async def _load_models(app: FastAPI, vocab: Vocabulary, prompts: StagePrompts) -> None:
    # Импорт здесь, а не в шапке: вместе с ним приходят torch и Ultralytics.
    from src.models.runtime import load_models

    try:
        models = await asyncio.to_thread(load_models, settings, vocab, prompts)
    except Exception as exc:
        # Сервис остаётся живым и честно не готовым: причина — в логе, статус — в /health/ready.
        log.exception("vision.models_failed", error=type(exc).__name__)
        return
    app.state.models = models
    log.info(
        "vision.models_loaded",
        detector=models.detector.name,
        stage_classifier=models.stage_classifier.name if models.stage_classifier else None,
        device=models.device,
    )


async def _models_ready() -> None:
    if getattr(app.state, "models", None) is None:
        raise RuntimeError("модели не загружены")


app = FastAPI(
    title="vision-service",
    version=settings.version,
    description=(
        "Сервис компьютерного зрения: детекция строительной техники, стадия объекта "
        "по внешнему виду и оценка качества кадра. Состояния и зависимостей нет."
    ),
    lifespan=lifespan,
    # В проде интерактивная документация закрыта: наружу её отдаёт gateway.
    docs_url="/docs" if settings.is_dev else None,
    redoc_url="/redoc" if settings.is_dev else None,
    openapi_url="/api/v1/vision/openapi.json",
)

app.add_middleware(RequestIdMiddleware)
install_error_handlers(app)

# Готовность — это модели в памяти: до этого распознавание отвечает MODEL_NOT_LOADED.
app.include_router(
    make_health_router(
        settings.service_name, settings.version, checks=[HealthCheck("models", _models_ready)]
    )
)
app.include_router(api_router)
