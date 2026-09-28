"""Вердикт оператора отдельно от статуса отклонения

Закрытому отклонению тоже ставят вердикт, а у подтверждённого он не должен пропадать при
закрытии: статус описывает жизненный цикл, вердикт — решение оператора
(docs/methodology.md, раздел 9, правило 3; docs/data-model.md, п. 3.2).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("deviation", sa.Column("verdict", sa.String(16), nullable=True))
    op.create_check_constraint(
        "ck_deviation_verdict",
        "deviation",
        "verdict IS NULL OR verdict IN ('CONFIRMED', 'REJECTED')",
    )
    # Вердикт, который жил в статусе, переносится в поле. У закрытых с вердиктом его
    # значение раньше терялось — восстановить его не из чего, поле остаётся пустым.
    op.execute("UPDATE deviation SET verdict = status WHERE status IN ('CONFIRMED', 'REJECTED')")


def downgrade() -> None:
    op.drop_constraint("ck_deviation_verdict", "deviation", type_="check")
    op.drop_column("deviation", "verdict")
