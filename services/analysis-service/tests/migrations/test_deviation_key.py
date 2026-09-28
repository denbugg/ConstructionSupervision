"""Ключ открытого отклонения держит сама база.

Прогон идемпотентен только если второе открытое отклонение с тем же ключом
вставить нельзя. У части кодов нет участка или класса, поэтому проверяется
именно случай с NULL: без NULLS NOT DISTINCT он молча дал бы дубль.
"""

import asyncio
from uuid import uuid4

import pytest

INSERT = """
    INSERT INTO deviation (object_id, stage_id, area, equipment_class, code, severity,
                           title, message, status)
    VALUES (:object_id, :stage_id, :area, NULL, :code, 'HIGH', 't', 'm', :status)
"""


def _insert_twice(dsn: str, first_status: str, second_status: str) -> None:
    """Вставляет два отклонения с одним ключом в транзакции с откатом."""
    from lct_common.db import create_engine
    from sqlalchemy import text

    params = {"object_id": uuid4(), "stage_id": uuid4(), "area": "PIT:Котлован", "code": "D2"}

    async def run() -> None:
        engine = create_engine(dsn)
        try:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    await connection.execute(text(INSERT), {**params, "status": first_status})
                    await connection.execute(text(INSERT), {**params, "status": second_status})
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_второе_открытое_отклонение_с_тем_же_ключом_не_вставляется(migrated_database):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        _insert_twice(migrated_database, "NEW", "CONFIRMED")


def test_закрытое_отклонение_не_мешает_открыть_новое(migrated_database):
    # Лента — история: после RESOLVED то же условие открывает новую строку.
    _insert_twice(migrated_database, "RESOLVED", "NEW")
