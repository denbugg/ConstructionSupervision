"""«Веха» → «этап» в текстах, уже лежащих в базе

Слово заменили в коде и в deviation_rules.yaml (коммит 133f6ab), но шаблоны правил попадают
в базу только при первом старте, а отклонения, факты прогноза и ошибки прогонов хранят текст,
собранный старым кодом. На стенде, поднятом до замены, «веха» так и доходила до карточек
и PDF-отчёта. Заменяются только фразы, которые писал сам сервис: названия этапов и участков
из плана не трогаются.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Старая фраза → новая, как в коде после замены. Порядок важен: длинные раньше коротких.
PHRASES: list[tuple[str, str]] = [
    # deviation_rules.yaml
    ("Правило вехи,", "Правило этапа,"),
    ("в правилах активных вех участка", "в правилах активных этапов участка"),
    ("но она нужна вехе «", "но она нужна этапу «"),
    ("», которая по плану начинается", "», который по плану начинается"),
    ("Активные по плану вехи:", "Активные по плану этапы:"),
    # core/equipment_state.py
    ("за пределами участков работ вехи не ведутся", "за пределами участков работ этапа не ведутся"),
    (
        "где по плану нет активной вехи этого типа",
        "где по плану нет активного этапа этого типа",
    ),
    ("на участке идёт веха", "на участке идёт этап"),
    ("на дату нет ни одной активной вехи", "на дату нет ни одного активного этапа"),
    # core/forecast.py
    (
        "у вехи нет правила: по снимкам её не проверить",
        "у этапа нет правила: по снимкам его не проверить",
    ),
    ("участок вехи с плановой даты начала", "участок этапа с плановой даты начала"),
    (
        "плановое окно вехи закончилось до начала наблюдений — выполнена по плану",
        "плановое окно этапа закончилось до начала наблюдений — выполнен по плану",
    ),
    ("Цикл в связях вех:", "Цикл в связях этапов:"),
    # core/stage_predicates.py
    (
        "у вехи нет размеченного участка её типа — снимков по ней нет",
        "у этапа нет размеченного участка его типа — снимков по нему нет",
    ),
    # services/runs.py
    ("ни даты начала СМР, ни вех:", "ни даты начала СМР, ни этапов:"),
]

TEXT_COLUMNS = [
    ("deviation_rule", "title_template"),
    ("deviation_rule", "message_template"),
    ("deviation", "title"),
    ("deviation", "message"),
]
JSONB_COLUMNS = [
    ("deviation_rule", "params"),
    ("deviation", "facts"),
    ("stage_fact", "facts"),
    ("object_status", "stages_at_risk"),
    ("analysis_run", "error"),
]


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _replace(pairs: list[tuple[str, str]]) -> None:
    for old, new in pairs:
        o, n = _quote(old), _quote(new)
        for table, column in TEXT_COLUMNS:
            op.execute(
                f"UPDATE {table} SET {column} = replace({column}, {o}, {n}) "
                f"WHERE strpos({column}, {o}) > 0"
            )
        # В фразах нет кавычек и обратных слешей, поэтому замена в тексте JSON его не портит.
        for table, column in JSONB_COLUMNS:
            op.execute(
                f"UPDATE {table} SET {column} = replace({column}::text, {o}, {n})::jsonb "
                f"WHERE strpos({column}::text, {o}) > 0"
            )


def upgrade() -> None:
    _replace(PHRASES)


def downgrade() -> None:
    _replace([(new, old) for old, new in reversed(PHRASES)])
