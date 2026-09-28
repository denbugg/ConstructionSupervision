"""Начальная схема analysisdb: прогоны, отклонения, правила, прогресс, статусы

Соответствует docs/data-model.md, раздел 3. Перечисления — text + CHECK:
добавление значения не должно требовать миграции.

Revision ID: 0001
Revises:
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)
NEW_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")
SEVERITIES = "'INFO', 'LOW', 'MEDIUM', 'HIGH'"
CONFIDENCE = "'LOW', 'MEDIUM', 'HIGH'"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    ]


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False)


def upgrade() -> None:
    op.create_table(
        "analysis_run",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("object_id", UUID, nullable=False),
        sa.Column(
            "triggered_by", sa.String(32), server_default=sa.text("'MANUAL'"), nullable=False
        ),
        sa.Column("as_of", sa.DateTime(timezone=True)),
        sa.Column("plan_version", sa.Integer),
        sa.Column("zones_version", sa.Integer),
        sa.Column("status", sa.String(16), server_default=sa.text("'RUNNING'"), nullable=False),
        sa.Column("rerun_requested", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("stats", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error", JSONB),
        *_timestamps(),
        sa.CheckConstraint(
            "triggered_by IN ('FACTS_UPDATED', 'PLAN_CHANGED', 'MANUAL')",
            name="ck_run_trigger",
        ),
        sa.CheckConstraint("status IN ('RUNNING', 'DONE', 'FAILED')", name="ck_run_status"),
    )
    op.create_index("ix_analysis_run_object_id", "analysis_run", ["object_id"])

    op.create_table(
        "deviation",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("object_id", UUID, nullable=False),
        sa.Column("stage_id", UUID),
        sa.Column("area", sa.String(300)),
        sa.Column("equipment_class", sa.String(64)),
        sa.Column("session_id", UUID),
        sa.Column("code", sa.String(8), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("facts", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("rule_ref", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("evidence", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'NEW'"), nullable=False),
        sa.Column("verdict_comment", sa.Text),
        sa.Column("verdict_by", sa.String(200)),
        sa.Column("verdict_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("occurrences", sa.Integer, server_default=sa.text("1"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(f"severity IN ({SEVERITIES})", name="ck_deviation_severity"),
        sa.CheckConstraint(
            "status IN ('NEW', 'CONFIRMED', 'REJECTED', 'RESOLVED')", name="ck_deviation_status"
        ),
    )
    op.create_index("ix_deviation_object_code", "deviation", ["object_id", "code"])
    op.create_index("ix_deviation_severity", "deviation", ["severity"])
    op.create_index("ix_deviation_status", "deviation", ["status"])
    # NULLS NOT DISTINCT (PostgreSQL 15+) обязателен: у D7 нет участка, у D1 нет
    # класса, а два NULL по умолчанию считаются разными значениями — и повторный
    # прогон плодил бы дубли вместо обновления строки.
    op.create_index(
        "uq_deviation_open",
        "deviation",
        ["object_id", "stage_id", "area", "code", "equipment_class"],
        unique=True,
        postgresql_where=sa.text("status IN ('NEW', 'CONFIRMED')"),
        postgresql_nulls_not_distinct=True,
    )

    op.create_table(
        "deviation_rule",
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("predicate", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("params", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("message_template", sa.Text, nullable=False),
        *_timestamps(),
        sa.CheckConstraint(f"severity IN ({SEVERITIES})", name="ck_rule_severity"),
    )

    op.create_table(
        "stage_fact",
        sa.Column("object_id", UUID, primary_key=True),
        sa.Column("stage_id", UUID, primary_key=True),
        sa.Column("actual_start", sa.Date),
        sa.Column("last_activity_at", sa.DateTime(timezone=True)),
        sa.Column("effective_days", sa.Float, server_default=sa.text("0"), nullable=False),
        sa.Column("progress", sa.Float, server_default=sa.text("0"), nullable=False),
        sa.Column("planned_progress", sa.Float, server_default=sa.text("0"), nullable=False),
        sa.Column("spi", sa.Float),
        sa.Column("forecast_end", sa.Date),
        sa.Column("delay_days", sa.Integer),
        sa.Column("status", sa.String(16), server_default=sa.text("'NOT_STARTED'"), nullable=False),
        sa.Column("confidence", sa.String(8), server_default=sa.text("'LOW'"), nullable=False),
        sa.Column("facts", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('NOT_STARTED', 'IN_PROGRESS', 'DONE', 'LATE', 'AHEAD')",
            name="ck_stage_fact_status",
        ),
        sa.CheckConstraint(f"confidence IN ({CONFIDENCE})", name="ck_stage_fact_confidence"),
    )

    op.create_table(
        "daily_activity",
        sa.Column("object_id", UUID, nullable=False),
        sa.Column("stage_id", UUID, primary_key=True),
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("sessions_total", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("sessions_working", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("activity_index", sa.Float, server_default=sa.text("0"), nullable=False),
        sa.Column("blind_sessions", sa.Integer, server_default=sa.text("0"), nullable=False),
        _created_at(),
    )
    op.create_index("ix_daily_activity_object_id", "daily_activity", ["object_id"])

    op.create_table(
        "daily_equipment",
        sa.Column("object_id", UUID, primary_key=True),
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("equipment_class", sa.String(64), primary_key=True),
        sa.Column("sessions_seen", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("max_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        _created_at(),
    )

    op.create_table(
        "object_status",
        sa.Column("object_id", UUID, primary_key=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'UNKNOWN'"), nullable=False),
        sa.Column("delay_days", sa.Integer),
        sa.Column("spi", sa.Float),
        sa.Column("confidence", sa.String(8), server_default=sa.text("'LOW'"), nullable=False),
        sa.Column("counters", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("stages_at_risk", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.CheckConstraint(
            "status IN ('ON_TRACK', 'DELAY', 'AHEAD', 'UNKNOWN')", name="ck_object_status"
        ),
        sa.CheckConstraint(f"confidence IN ({CONFIDENCE})", name="ck_object_status_confidence"),
    )


def downgrade() -> None:
    op.drop_table("object_status")
    op.drop_table("daily_equipment")
    op.drop_table("daily_activity")
    op.drop_table("stage_fact")
    op.drop_table("deviation_rule")
    op.drop_table("deviation")
    op.drop_table("analysis_run")
