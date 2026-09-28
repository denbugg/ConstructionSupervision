"""Точка входа analysis-service.

Сервис сверки план-факт: отклонения D1–D10 с объяснением, прогресс, SPI
и прогноз даты окончания (F7, F8, F9). План и факт читаются по API — своими
первичными данными сервис не владеет, его состояние пересчитывается с нуля.
"""

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
from lct_common.db import create_engine, create_session_factory, make_db_check
from sqlalchemy.exc import SQLAlchemyError

from src.api.routes import api_router
from src.clients.llm_client import LlmClient
from src.clients.plan_client import PlanClient
from src.clients.site_client import SiteClient
from src.clients.storage import ReportStorage, StorageUnavailable
from src.config import settings
from src.dal.repositories.rules import RuleRepository
from src.services.runs import default_rules

setup_logging(settings.service_name, settings.log_level, pretty=settings.is_dev)
log = get_logger(__name__)


def _client(cls, url: str, service: str):
    return cls(
        url,
        service=service,
        api_key=settings.api_key,
        timeout_s=settings.upstream_timeout_s,
        retries=settings.upstream_retries,
    )


async def _seed_rules(factory) -> None:
    """Первый старт: пороги D1–D10 из YAML в deviation_rule; правленые строки не трогаются.

    База может быть ещё не готова — тогда правила заполнит первый прогон, а сервис
    всё равно поднимется: /health/ready честно скажет, что БД недоступна.
    """
    try:
        async with factory() as session, session.begin():
            await RuleRepository(session).seed_missing(default_rules())
    except (OSError, SQLAlchemyError) as exc:
        log.warning("rules.seed_skipped", error=type(exc).__name__)


def _llm_client() -> LlmClient | None:
    """Клиент нейросети для резюме; None — резюме по шаблону (выключено или нет адреса)."""
    if not settings.llm_enabled or not settings.llm_base_url:
        return None
    return LlmClient(
        settings.llm_base_url,
        settings.llm_model,
        settings.llm_api_key,
        settings.llm_timeout_s,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ресурсы, живущие столько же, сколько процесс: пул БД, клиенты plan, site и LLM, хранилище."""
    engine = create_engine(settings.analysis_db_dsn, echo=settings.db_echo)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.plan_client = _client(PlanClient, settings.plan_url, "plan-service")
    app.state.site_client = _client(SiteClient, settings.site_url, "site-service")
    app.state.report_storage = ReportStorage(
        endpoint=settings.s3_endpoint,
        public_endpoint=settings.s3_public_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket_reports,
        presign_ttl_s=settings.s3_presign_ttl_s,
    )
    await _seed_rules(app.state.session_factory)
    try:
        await app.state.report_storage.ensure_bucket()
    except StorageUnavailable:
        # Без хранилища не работают только отчёты: сверка идёт, а /health/ready покажет s3: fail.
        log.warning("storage.unavailable_at_start", endpoint=settings.s3_endpoint)
    app.state.llm_client = _llm_client()

    log.info(
        "service.started",
        version=settings.version,
        env=settings.env,
        llm=settings.llm_model if app.state.llm_client else "off",
    )
    yield

    await app.state.plan_client.aclose()
    await app.state.site_client.aclose()
    if app.state.llm_client is not None:
        await app.state.llm_client.aclose()
    await engine.dispose()
    log.info("service.stopped")


app = FastAPI(
    title="analysis-service",
    version=settings.version,
    description=(
        "Сервис сверки план-факт: отклонения D1–D10 с объяснением, прогресс, SPI "
        "и прогноз. Каждое число сопровождается фактами, на которых оно построено."
    ),
    lifespan=lifespan,
    # В проде интерактивная документация закрыта: наружу её отдаёт gateway.
    docs_url="/docs" if settings.is_dev else None,
    redoc_url="/redoc" if settings.is_dev else None,
    openapi_url="/api/v1/analysis/openapi.json",
)

app.add_middleware(RequestIdMiddleware)
install_error_handlers(app)

app.include_router(
    make_health_router(
        settings.service_name,
        settings.version,
        checks=[
            HealthCheck("db", lambda: make_db_check(app.state.engine)()),
            # Хранилище нужно только отчётам: без него сервис деградирует, а не отказывает.
            # Проверка заодно заводит бакет, если хранилище поднялось позже сервиса.
            HealthCheck("s3", lambda: app.state.report_storage.ensure_bucket(), required=False),
        ],
    )
)
app.include_router(api_router)
