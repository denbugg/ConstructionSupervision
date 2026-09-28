"""Миграции обязаны накатываться и откатываться.

Схему тестов поднимает `upgrade head` (tests/conftest.py), так что накат
проверяется каждым прогоном сам собой. Откат не проверяется ничем — а узнать
о нерабочем `downgrade` в момент, когда он понадобился, худший из вариантов
(docs/testing.md, п. 5).

Тесты синхронные: Alembic поднимает внутри собственный event loop.
"""

import asyncio


def _table_names(dsn: str) -> set[str]:
    from lct_common.db import create_engine
    from sqlalchemy import inspect

    async def read() -> set[str]:
        engine = create_engine(dsn)
        try:
            async with engine.connect() as connection:
                return set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
        finally:
            await engine.dispose()

    return asyncio.run(read())


def test_откат_до_нуля_и_накат_обратно(alembic_config, migrated_database):
    from alembic import command

    command.downgrade(alembic_config, "base")
    tables_at_base = _table_names(migrated_database)
    assert "image" not in tables_at_base, "downgrade оставил таблицы сервиса"

    command.upgrade(alembic_config, "head")
    tables_at_head = _table_names(migrated_database)
    assert {
        "camera",
        "zone",
        "session",
        "image",
        "detection",
        "stage_observation",
        "area_visibility",
        "session_fact",
    } <= tables_at_head
    # Видимость считается по участку, а не по зоне камеры (ADR-0013).
    assert "zone_visibility" not in tables_at_head
