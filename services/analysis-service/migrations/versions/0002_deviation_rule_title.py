"""Шаблон заголовка у правила отклонения

У отклонения есть заголовок карточки, и он, как и текст, собирается из шаблона
правила: тексты для пользователя живут в данных, а не в коде (docs/data-model.md, п. 3.3).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deviation_rule",
        sa.Column("title_template", sa.Text, server_default=sa.text("''"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("deviation_rule", "title_template")
