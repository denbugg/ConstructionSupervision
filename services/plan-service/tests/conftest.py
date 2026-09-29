"""Общие фикстуры.

API-тесты требуют настоящий PostgreSQL (docs/testing.md, п. 5): JSONB и CHECK
на SQLite не воспроизводятся, а тестировать на другой СУБД, чем в проде, —
способ узнать о проблеме в самый неподходящий момент.

Базы нет — API-тесты пропускаются с понятным сообщением, а не падают:
unit-тесты на core/ должны проходить всегда и без докера.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

# Зависимости API-тестов (httpx, sqlalchemy) импортируются внутри фикстур,
# а не здесь: unit-тесты на core/ обязаны запускаться без окружения сервиса —
# это и есть смысл правила «доменная логика не знает про БД и сеть».

SERVICE_ROOT = Path(__file__).resolve().parents[1]
# Справочные файлы: в контейнере — CONTRACTS_DIR, в рабочей копии и CI — packages/contracts.
# Выставляется до импорта сервиса: типы перечислений строятся из enums.yaml при импорте схем.
CONTRACTS_DIR = Path(os.getenv("CONTRACTS_DIR") or SERVICE_ROOT.parents[1] / "packages/contracts")
os.environ["CONTRACTS_DIR"] = str(CONTRACTS_DIR)

# Одна переменная на все сервисы: CI не должен знать про каждый в отдельности.
TEST_DSN = os.getenv(
    "TEST_DB_DSN",
    "postgresql+asyncpg://plan_user:plan-change-me@localhost:5432/plandb",
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


@pytest.fixture
async def engine(migrated_database) -> AsyncIterator:
    from lct_common.db import create_engine

    engine = create_engine(migrated_database)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator:
    """Сессия в транзакции с откатом: тесты не видят изменений друг друга."""
    from sqlalchemy.ext.asyncio import AsyncSession

    connection = await engine.connect()
    transaction = await connection.begin()
    db_session = AsyncSession(bind=connection, expire_on_commit=False)

    yield db_session

    await db_session.close()
    await transaction.rollback()
    await connection.close()


class StubAnalysisClient:
    """analysis-service в тестах: запоминает, по каким объектам ушёл сигнал «пересчитай»."""

    def __init__(self) -> None:
        self.signals: list = []

    async def request_run(self, object_id) -> None:
        self.signals.append(object_id)


@pytest.fixture
def analysis() -> StubAnalysisClient:
    return StubAnalysisClient()


@pytest.fixture
async def client(session, analysis) -> AsyncIterator:
    """HTTP-клиент поверх приложения, с подменённой сессией, заглушкой analysis и ключом."""
    from httpx import ASGITransport, AsyncClient
    from src.api.deps import get_analysis_client, get_session
    from src.config import settings
    from src.main import app

    async def _session_override() -> AsyncIterator:
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_analysis_client] = lambda: analysis
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": settings.api_key},
    ) as http_client:
        yield http_client

    app.dependency_overrides.clear()


@pytest.fixture
async def demo_stage(client, session) -> dict:
    """Объект с одним этапом «Разработка котлована», записанным в базу напрямую: тестам
    этапов не нужен импорт графика целиком."""
    from datetime import date
    from uuid import UUID

    from src.dal.models import Stage

    obj = (
        await client.post(
            "/api/v1/plan/objects",
            json={"name": "Монолитный жилой дом, 17 этажей", "plan_start": "2026-10-15"},
        )
    ).json()
    stage = Stage(
        object_id=UUID(obj["id"]),
        code="12.3.1",
        work_codes=["12.3.1", "12.3.7"],
        name="Разработка котлована",
        phase="SUBSTRUCTURE",
        seq=1,
        zone_type="PIT",
        visual_stage="PIT",
        plan_start=date(2026, 10, 15),
        plan_end=date(2026, 11, 20),
        norm_duration_days=31,
        source="IMPORT",
        basis="импорт",
    )
    session.add(stage)
    await session.flush()
    return {"object": obj, "stage_id": str(stage.id)}
