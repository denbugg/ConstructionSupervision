"""«Веха» → «этап» в обосновании длительности, уже лежащем в базе

Слово заменили в коде (коммит 133f6ab), но `stage.basis` пишется при импорте и генерации
графика, и у этапов, заведённых раньше, осталась «веха» — её видно на Ганте. Заменяются
только фразы, которые писал сам сервис.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Старая фраза → новая, как в core/plan_import.py и core/schedule_generator.py после замены.
PHRASES: list[tuple[str, str]] = [
    ("шаблон вехи", "шаблон этапа"),
    ("доля вехи", "доля этапа"),
]


def _replace(pairs: list[tuple[str, str]]) -> None:
    for old, new in pairs:
        op.execute(
            f"UPDATE stage SET basis = replace(basis, '{old}', '{new}') "
            f"WHERE strpos(basis, '{old}') > 0"
        )


def upgrade() -> None:
    _replace(PHRASES)


def downgrade() -> None:
    _replace([(new, old) for old, new in PHRASES])
