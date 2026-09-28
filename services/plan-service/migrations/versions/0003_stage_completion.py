"""Отметка оператора «этап выполнен»: дата, автор, комментарий (ADR-0015)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stage", sa.Column("completed_on", sa.Date(), nullable=True))
    op.add_column("stage", sa.Column("completed_by", sa.Text(), nullable=True))
    op.add_column("stage", sa.Column("completion_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("stage", "completion_note")
    op.drop_column("stage", "completed_by")
    op.drop_column("stage", "completed_on")
