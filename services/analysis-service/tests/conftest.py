"""Общие фикстуры.

Тесты схемы требуют настоящий PostgreSQL (docs/testing.md, п. 5): JSONB и CHECK
на SQLite не воспроизводятся, а тестировать на другой СУБД, чем в проде, —
способ узнать о проблеме в самый неподходящий момент.

Базы нет — такие тесты пропускаются с понятным сообщением, а не падают:
unit-тесты на core/ должны проходить всегда и без докера.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
# Справочные файлы: в контейнере — CONTRACTS_DIR, в рабочей копии и CI — packages/contracts.
CONTRACTS_DIR = Path(os.getenv("CONTRACTS_DIR") or SERVICE_ROOT.parents[1] / "packages/contracts")

# Одна переменная на все сервисы: CI не должен знать про каждый в отдельности.
TEST_DSN = os.getenv(
    "TEST_DB_DSN",
    "postgresql+asyncpg://analysis_user:analysis-change-me@localhost:5432/analysisdb",
)


def _database_is_reachable() -> bool:
    import asyncio

    from lct_common.db import create_engine
    from sqlalchemy import text

    async def probe() -> bool:
        engine = create_engine(TEST_DSN)
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 — причина недоступности БД здесь не важна
            return False
        finally:
            await engine.dispose()

    return asyncio.run(probe())


@pytest.fixture(scope="session")
def alembic_config():
    """Конфиг Alembic, нацеленный на тестовую базу.

    Пути абсолютные: тесты запускаются и из каталога сервиса, и из корня репозитория.
    """
    from alembic.config import Config

    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", TEST_DSN)
    return config


@pytest.fixture(scope="session")
def migrated_database(alembic_config) -> str:
    """Схема поднимается миграциями, а не `create_all`.

    Так каждый прогон тестов заодно проверяет, что миграции применяются: иначе
    о сломанном `upgrade` узнают при старте контейнера, а не в CI.

    Фикстура синхронная намеренно: Alembic внутри поднимает свой event loop,
    и вызывать его из уже работающего цикла нельзя.
    """
    from alembic import command

    if not _database_is_reachable():
        pytest.skip("нужен PostgreSQL: make up postgres (или задайте TEST_DB_DSN)")

    command.upgrade(alembic_config, "head")
    return TEST_DSN


@pytest.fixture(autouse=True)
def contracts_dir(monkeypatch):
    """Справочники из рабочей копии — во всех тестах, а не только в тех, что берут `client`.

    Иначе сервис ищет их в `CONTRACTS_DIR` по умолчанию (`/contracts`): в контейнере
    `scripts/test.py` переменная задана, в CI — нет, и тест, запустивший прогон без `client`,
    падал только там. Кеши сбрасываются, чтобы справочник не пережил тест.
    """
    from src.config import settings
    from src.services import reports, runs

    monkeypatch.setattr(settings, "contracts_dir", str(CONTRACTS_DIR))
    runs.enums.cache_clear()
    reports.labels.cache_clear()
    yield
    runs.enums.cache_clear()
    reports.labels.cache_clear()


@pytest.fixture(scope="session")
def enums():
    """Перечисления из настоящего enums.yaml: тесты сверяются с контрактом, а не с копией."""
    from src.core.enums import load_enums

    return load_enums(CONTRACTS_DIR)


# Все таблицы выводов: прогон пишет своими транзакциями, поэтому API-тесты изолируются
# очисткой, а не откатом транзакции.
TABLES = (
    "analysis_run, deviation, deviation_rule, stage_fact, daily_activity, daily_equipment, "
    "object_status"
)


@pytest.fixture
async def session_factory(migrated_database):
    """Фабрика сессий к чистой тестовой базе."""
    from lct_common.db import create_engine, create_session_factory
    from sqlalchemy import text

    engine = create_engine(migrated_database)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {TABLES}"))
    yield create_session_factory(engine)
    await engine.dispose()


class StubPlanClient:
    """plan-service на фикстуре: отдаёт план или бросает заданную ошибку."""

    def __init__(self) -> None:
        from tests.factories import load_plan

        self.plan = load_plan()
        self.error: Exception | None = None

    async def get_plan(self, object_id):
        if self.error is not None:
            raise self.error
        return self.plan


class StubSiteClient:
    """site-service на фикстуре: запоминает запрошенный период и, как настоящий, отдаёт
    только сессии с началом окна в [from, to) — иначе ошибка в периоде была бы не видна."""

    def __init__(self) -> None:
        self.facts = None
        self.error: Exception | None = None
        self.calls: list[tuple] = []
        # Контракт 6: снимки без времени и карточки снимков; удалённые — 404, как у site.
        self.images_without_time = 2
        self.deleted_images: set[str] = set()

    async def get_facts(self, object_id, period_from, period_to):
        self.calls.append((object_id, period_from, period_to))
        if self.error is not None:
            raise self.error
        if self.facts is None:
            return None
        sessions = tuple(
            s for s in self.facts.sessions if period_from <= s.window_start < period_to
        )
        return self.facts.model_copy(update={"sessions": sessions})

    async def count_images_without_time(self, object_id):
        if self.error is not None:
            raise self.error
        return self.images_without_time

    async def get_image(self, image_id):
        from lct_common import UpstreamError

        if self.error is not None:
            raise self.error
        if str(image_id) in self.deleted_images:
            error = UpstreamError("Снимок не найден", upstream_code="IMAGE_NOT_FOUND")
            error.http_status = 404
            raise error
        return {
            "id": str(image_id),
            "url": f"http://s3:8333/images/{image_id}.jpg",
            "captured_at": "2026-10-20T09:00:00Z",
            "width": 64,
            "height": 48,
            "detections": [
                {"id": "d-1", "equipment_class": "excavator", "bbox": [0.1, 0.2, 0.5, 0.7]}
            ],
        }

    async def download(self, url):
        import io

        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (64, 48), (120, 110, 90)).save(buffer, format="JPEG")
        return buffer.getvalue()


class StubLlm:
    """Нейросеть-заглушка: отдаёт заданный текст или бросает LlmUnavailable, помнит запросы."""

    model = "stub-llm"

    def __init__(self) -> None:
        self.reply = ""
        self.unavailable = False
        self.prompts: list[tuple[str, str]] = []

    async def complete(self, system, user):
        from src.clients.llm_client import LlmUnavailable

        self.prompts.append((system, user))
        if self.unavailable:
            raise LlmUnavailable("ReadTimeout")
        return self.reply


class StubStorage:
    """Бакет `reports` в памяти: ключ → (байты, время записи)."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, object]] = {}

    async def ensure_bucket(self) -> None:
        return None

    async def put(self, key, content, content_type):
        from datetime import UTC, datetime

        self.files[key] = (content, datetime.now(UTC))

    async def list_files(self, prefix):
        from src.clients.storage import StoredFile

        return [
            StoredFile(key=k, size=len(c), modified_at=t)
            for k, (c, t) in self.files.items()
            if k.startswith(prefix)
        ]

    async def stat(self, key):
        found = [f for f in await self.list_files(key) if f.key == key]
        return found[0] if found else None

    async def presigned_url(self, key):
        return f"http://localhost:8333/reports/{key}?X-Amz-Signature=stub"


@pytest.fixture
async def seeded_rules(session_factory) -> None:
    """Правила D1–D10 в таблице, как после старта сервиса."""
    from src.dal.repositories.rules import RuleRepository
    from src.services.runs import default_rules

    async with session_factory() as session, session.begin():
        await RuleRepository(session).seed_missing(default_rules())


@pytest.fixture
def upstream():
    """Заглушки plan и site: внешние сервисы в тестах не вызываются (AGENTS.md, раздел 10)."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    # llm = None — нейросеть выключена, резюме по шаблону; тест резюме подставляет StubLlm.
    # clock — часы отчётов: тест подменяет их, чтобы момент формирования не зависел от скорости.
    return SimpleNamespace(
        plan=StubPlanClient(),
        site=StubSiteClient(),
        storage=StubStorage(),
        llm=None,
        clock=lambda: datetime.now(UTC),
    )


@pytest.fixture
async def client(session_factory, upstream) -> AsyncIterator:
    """HTTP-клиент поверх приложения с тестовой базой, заглушками и рабочим ключом."""
    from httpx import ASGITransport, AsyncClient
    from lct_common.db import session_dependency
    from src.api.deps import (
        SessionDep,
        get_report_service,
        get_run_service,
        get_session,
        get_site_client,
    )
    from src.config import settings
    from src.main import app
    from src.services.reports import ReportService
    from src.services.runs import RunService
    from src.services.summary import Summarizer

    async def _session_override() -> AsyncIterator:
        async for session in session_dependency(session_factory):
            yield session

    def _report_service(session: SessionDep) -> ReportService:
        return ReportService(
            session,
            upstream.plan,
            upstream.site,
            upstream.storage,
            Summarizer(upstream.llm),
            now=lambda: upstream.clock(),
        )

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_site_client] = lambda: upstream.site
    app.dependency_overrides[get_run_service] = lambda: RunService(
        session_factory, upstream.plan, upstream.site
    )
    app.dependency_overrides[get_report_service] = _report_service
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": settings.api_key},
    ) as http_client:
        yield http_client
    app.dependency_overrides.clear()


DEMO_OBJECT_ID = "0f3a6c1e-8d4b-4c2a-9e71-5b0d2f6a8c31"
DEMO_DAYS = ("facts_normal_day.json", "facts_day1.json", "facts_day2.json", "facts_day3.json")


@pytest.fixture
async def analyzed(client, upstream):
    """Демо-объект после прогона по четырём демо-дням (19–22.10)."""
    from tests.factories import load_facts, make_facts

    upstream.site.facts = make_facts(*(s for n in DEMO_DAYS for s in load_facts(n).sessions))
    response = await client.post(
        "/api/v1/analysis/runs", json={"object_id": DEMO_OBJECT_ID}, params={"wait": True}
    )
    assert response.status_code == 200, response.text
