"""Индекс активности может быть пустым

День, когда участок этапа ни разу не был виден, — «не знаем», а не нулевая
активность (docs/data-model.md, п. 3.5; docs/methodology.md, раздел 10.2).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("daily_activity", "activity_index", nullable=True, server_default=None)


def downgrade() -> None:
    # Пустой индекс при откате становится нулём: старая схема «не знаем» выразить не может.
    op.execute("UPDATE daily_activity SET activity_index = 0 WHERE activity_index IS NULL")
    op.alter_column(
        "daily_activity",
        "activity_index",
        nullable=False,
        server_default=sa.text("0"),
        existing_type=sa.Float,
    )
