"""Праздники календаря moscow-6day; объектам без календаря — календарь по умолчанию

Праздники — только с источником: нерабочие праздничные дни по
ТК РФ, ст. 112, ч. 1 (ред. Федерального закона от 23.04.2012 № 35-ФЗ) на 2026–2028 годы,
на которые приходится график демо-объекта. Переносы выходных (ст. 112, ч. 2, и
постановления Правительства РФ о переносе) не заведены: в репозитории нет документа.
Их и праздники других лет оператор добавляет через PATCH /calendars/{id}.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CALENDAR = "moscow-6day"
YEARS = (2026, 2027, 2028)
# ТК РФ, ст. 112, ч. 1: 1–6 и 8 января — новогодние каникулы; 7 января — Рождество
# Христово; 23 февраля; 8 марта; 1 мая; 9 мая; 12 июня; 4 ноября.
HOLIDAYS_MM_DD = (
    "01-01",
    "01-02",
    "01-03",
    "01-04",
    "01-05",
    "01-06",
    "01-07",
    "01-08",
    "02-23",
    "03-08",
    "05-01",
    "05-09",
    "06-12",
    "11-04",
)


def upgrade() -> None:
    holidays = [f"{year}-{day}" for year in YEARS for day in HOLIDAYS_MM_DD]
    op.execute(
        sa.text(
            "UPDATE work_calendar SET holidays = CAST(:holidays AS jsonb), updated_at = now() "
            "WHERE code = :code"
        ).bindparams(holidays=json.dumps(holidays), code=CALENDAR)
    )
    # Объекты, заведённые до этой миграции, создавались без календаря.
    op.execute(
        sa.text(
            "UPDATE object SET calendar_id = (SELECT id FROM work_calendar WHERE code = :code) "
            "WHERE calendar_id IS NULL"
        ).bindparams(code=CALENDAR)
    )


def downgrade() -> None:
    # Привязка объектов к календарю не откатывается: в 0001 календарь по умолчанию уже был.
    op.execute(
        sa.text("UPDATE work_calendar SET holidays = '[]'::jsonb WHERE code = :code").bindparams(
            code=CALENDAR
        )
    )
