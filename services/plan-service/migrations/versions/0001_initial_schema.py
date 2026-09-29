"""Начальная схема plandb: объекты, справочник работ, календари, этапы, правила

Соответствует docs/data-model.md, раздел 1. Перечисления — text + CHECK:
добавление значения не должно требовать миграции. Классов техники в базе нет,
их источник — equipment_classes.yaml (ADR-0014).

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


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "work_calendar",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "timezone", sa.String(64), server_default=sa.text("'Europe/Moscow'"), nullable=False
        ),
        sa.Column("weekend_days", JSONB, server_default=sa.text("'[6, 7]'::jsonb"), nullable=False),
        sa.Column("holidays", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column(
            "work_hours",
            JSONB,
            server_default=sa.text("""'{"start": "07:00", "end": "23:00"}'::jsonb"""),
            nullable=False,
        ),
        *_timestamps(),
    )

    op.create_table(
        "object",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("address", sa.Text),
        sa.Column("tep", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("plan_start", sa.Date),
        sa.Column("calendar_id", UUID, sa.ForeignKey("work_calendar.id")),
        sa.Column("status", sa.String(16), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column("plan_version", sa.Integer, server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "object_type IN ('RESIDENTIAL_MONOLITH', 'RESIDENTIAL_PANEL', "
            "'PUBLIC_BUILDING', 'ROAD')",
            name="ck_object_type",
        ),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')", name="ck_object_status"),
    )
    op.create_index("ix_object_status", "object", ["status"])
    op.create_index("ix_object_object_type", "object", ["object_type"])

    op.create_table(
        "work_type",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("parent_code", sa.String(32)),
        sa.Column("applicable", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("source", sa.Text),
        sa.CheckConstraint("level BETWEEN 1 AND 4", name="ck_work_type_level"),
    )
    op.create_index("ix_work_type_parent_code", "work_type", ["parent_code"])

    op.create_table(
        "stage",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column(
            "object_id", UUID, sa.ForeignKey("object.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("work_codes", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("zone_type", sa.String(32), nullable=False),
        sa.Column("visual_stage", sa.String(32)),
        sa.Column("plan_start", sa.Date, nullable=False),
        sa.Column("plan_end", sa.Date, nullable=False),
        sa.Column("norm_duration_days", sa.Integer, nullable=False),
        sa.Column("predecessors", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("is_critical", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("total_float_days", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("source", sa.String(16), server_default=sa.text("'MANUAL'"), nullable=False),
        sa.Column("basis", sa.Text),
        *_timestamps(),
        sa.CheckConstraint(
            "phase IN ('PREPARATORY', 'SUBSTRUCTURE', 'SUPERSTRUCTURE', "
            "'ENVELOPE_ROOF', 'NETWORKS', 'LANDSCAPING')",
            name="ck_stage_phase",
        ),
        # Только типы зон с ролью WORK (enums.yaml: zone_type_role).
        sa.CheckConstraint(
            "zone_type IN ('PIT', 'BUILDING_FOOTPRINT', 'PERIMETER', 'ROAD')",
            name="ck_stage_zone_type",
        ),
        sa.CheckConstraint(
            "visual_stage IS NULL OR visual_stage IN ('PIT', 'PILES', 'FOUNDATION', "
            "'FRAME', 'FACADE', 'LANDSCAPING')",
            name="ck_stage_visual_stage",
        ),
        sa.CheckConstraint("source IN ('GENERATED', 'IMPORT', 'MANUAL')", name="ck_stage_source"),
        sa.CheckConstraint("plan_end >= plan_start", name="ck_stage_dates"),
        sa.CheckConstraint("norm_duration_days > 0", name="ck_stage_norm_duration"),
    )
    op.create_index("ix_stage_object_plan_start", "stage", ["object_id", "plan_start"])
    op.create_index("ix_stage_object_seq", "stage", ["object_id", "seq"])

    op.create_table(
        "stage_rule",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column(
            "stage_id",
            UUID,
            sa.ForeignKey("stage.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("required", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("allowed", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column(
            "signature",
            JSONB,
            server_default=sa.text("""'{"equipment": [], "stage_label": null}'::jsonb"""),
            nullable=False,
        ),
        sa.Column("min_sessions", sa.Integer, server_default=sa.text("2"), nullable=False),
        sa.Column("version", sa.Integer, server_default=sa.text("1"), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("min_sessions >= 1", name="ck_rule_min_sessions"),
    )

    # Календарь по умолчанию: шестидневка, как на большинстве московских площадок.
    # Праздники здесь не заводятся: каждая дата должна иметь источник.
    op.execute(
        """
        INSERT INTO work_calendar (code, name, timezone, weekend_days, work_hours)
        VALUES (
            'moscow-6day',
            'Москва, шестидневная рабочая неделя',
            'Europe/Moscow',
            '[7]'::jsonb,
            '{"start": "07:00", "end": "23:00"}'::jsonb
        )
        """
    )


def downgrade() -> None:
    op.drop_table("stage_rule")
    op.drop_table("stage")
    op.drop_table("work_type")
    op.drop_table("object")
    op.drop_table("work_calendar")
