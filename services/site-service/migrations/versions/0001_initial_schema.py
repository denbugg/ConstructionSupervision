"""Начальная схема sitedb: камеры, зоны, снимки, окна, детекции, факты окон

Соответствует docs/data-model.md, раздел 2. Перечисления — text + CHECK:
добавление значения не должно требовать миграции. Участок — не таблица, а
ключ `ТИП:Название` (ADR-0013).

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

ZONE_TYPES = "'PIT', 'BUILDING_FOOTPRINT', 'PERIMETER', 'ENTRY_GATE', 'STORAGE', 'DANGER', 'ROAD'"
STAGE_LABELS = "'PIT', 'PILES', 'FOUNDATION', 'FRAME', 'FACADE', 'LANDSCAPING'"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    ]


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False)


def _session_fk(**kwargs) -> sa.Column:
    return sa.Column("session_id", UUID, sa.ForeignKey("session.id", ondelete="CASCADE"), **kwargs)


def upgrade() -> None:
    op.create_table(
        "camera",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("object_id", UUID, nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        # Без внешнего ключа: иначе camera и image ссылались бы друг на друга циклом.
        sa.Column("reference_image_id", UUID),
        sa.Column("install_meta", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("object_id", "code", name="uq_camera_object_code"),
    )
    op.create_index("ix_camera_object_id", "camera", ["object_id"])

    op.create_table(
        "zone",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("object_id", UUID, nullable=False),
        sa.Column(
            "camera_id", UUID, sa.ForeignKey("camera.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("zone_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("polygon", JSONB, nullable=False),
        sa.Column("version", sa.Integer, server_default=sa.text("1"), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(f"zone_type IN ({ZONE_TYPES})", name="ck_zone_type"),
    )
    op.create_index("ix_zone_object_id", "zone", ["object_id"])

    op.create_table(
        "session",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("object_id", UUID, nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("image_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("camera_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("stage_label", sa.String(32)),
        sa.Column("stage_conf", sa.Float),
        sa.Column("stage_scores", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("object_id", "window_start", name="uq_session_object_window"),
        sa.CheckConstraint("window_end > window_start", name="ck_session_window"),
        sa.CheckConstraint(
            f"stage_label IS NULL OR stage_label IN ({STAGE_LABELS})",
            name="ck_session_stage_label",
        ),
    )
    op.create_index("ix_session_object_id", "session", ["object_id"])

    op.create_table(
        "image",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("object_id", UUID, nullable=False),
        sa.Column(
            "camera_id", UUID, sa.ForeignKey("camera.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True)),
        sa.Column(
            "captured_at_source",
            sa.String(16),
            server_default=sa.text("'UNKNOWN'"),
            nullable=False,
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("session_id", UUID, sa.ForeignKey("session.id", ondelete="SET NULL")),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("width", sa.Integer),
        sa.Column("height", sa.Integer),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("source", sa.String(16), server_default=sa.text("'UPLOAD'"), nullable=False),
        sa.Column("exif", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("quality", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("usable", sa.Boolean),
        sa.Column("usable_reason", sa.String(16)),
        sa.Column("status", sa.String(16), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("error", sa.Text),
        *_timestamps(),
        sa.UniqueConstraint("object_id", "checksum", name="uq_image_object_checksum"),
        sa.CheckConstraint(
            "status IN ('NEEDS_TIME', 'PENDING', 'PROCESSING', 'ANALYZED', 'FAILED')",
            name="ck_image_status",
        ),
        sa.CheckConstraint("source IN ('UPLOAD', 'API', 'FOLDER_IMPORT')", name="ck_image_source"),
        sa.CheckConstraint(
            "captured_at_source IN ('EXIF', 'FILENAME', 'MANUAL', 'UNKNOWN')",
            name="ck_image_time_source",
        ),
        sa.CheckConstraint(
            "usable_reason IS NULL OR usable_reason IN ('DARK', 'BLURRED', 'OCCLUDED')",
            name="ck_image_usable_reason",
        ),
    )
    op.create_index("ix_image_object_captured_at", "image", ["object_id", "captured_at"])
    op.create_index("ix_image_session_id", "image", ["session_id"])
    op.create_index("ix_image_status", "image", ["status"])

    op.create_table(
        "detection",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("image_id", UUID, sa.ForeignKey("image.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID, sa.ForeignKey("session.id", ondelete="SET NULL")),
        sa.Column(
            "camera_id", UUID, sa.ForeignKey("camera.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("equipment_class", sa.String(64), nullable=False),
        sa.Column("bbox", JSONB, nullable=False),
        sa.Column("conf", sa.Float, nullable=False),
        sa.Column("anchor", JSONB, nullable=False),
        sa.Column("zone_id", UUID, sa.ForeignKey("zone.id", ondelete="SET NULL")),
        sa.Column("moved", sa.Boolean),
        sa.Column("displacement", sa.Float),
        sa.Column("model_version", sa.String(64), nullable=False),
        _created_at(),
    )
    op.create_index("ix_detection_image_id", "detection", ["image_id"])
    op.create_index("ix_detection_zone_id", "detection", ["zone_id"])
    op.create_index("ix_detection_session_class", "detection", ["session_id", "equipment_class"])

    op.create_table(
        "stage_observation",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("image_id", UUID, sa.ForeignKey("image.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID, sa.ForeignKey("session.id", ondelete="SET NULL")),
        sa.Column("stage_label", sa.String(32), nullable=False),
        sa.Column("conf", sa.Float, nullable=False),
        sa.Column("scores", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        _created_at(),
        sa.CheckConstraint(f"stage_label IN ({STAGE_LABELS})", name="ck_stage_observation_label"),
    )
    op.create_index("ix_stage_observation_image_id", "stage_observation", ["image_id"])

    op.create_table(
        "area_visibility",
        _session_fk(primary_key=True),
        sa.Column("area", sa.String(300), primary_key=True),
        sa.Column("zone_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("cameras_total", sa.Integer, nullable=False),
        sa.Column("cameras_usable", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(16)),
        _created_at(),
        sa.CheckConstraint(f"zone_type IN ({ZONE_TYPES})", name="ck_visibility_zone_type"),
        sa.CheckConstraint("status IN ('OK', 'PARTIAL', 'BLIND')", name="ck_visibility_status"),
        sa.CheckConstraint(
            "reason IS NULL OR reason IN ('NO_IMAGES', 'DARK', 'BLURRED', 'OCCLUDED')",
            name="ck_visibility_reason",
        ),
    )

    op.create_table(
        "session_fact",
        _session_fk(primary_key=True),
        sa.Column("area", sa.String(300), primary_key=True),
        sa.Column("equipment_class", sa.String(64), primary_key=True),
        sa.Column("count", sa.Integer, nullable=False),
        sa.Column("static", sa.Integer),
        sa.Column("evidence", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        _created_at(),
        # Отсутствие класса означает ноль, поэтому нулевые строки не хранятся.
        sa.CheckConstraint("count > 0", name="ck_session_fact_count"),
    )


def downgrade() -> None:
    op.drop_table("session_fact")
    op.drop_table("area_visibility")
    op.drop_table("stage_observation")
    op.drop_table("detection")
    op.drop_table("image")
    op.drop_table("session")
    op.drop_table("zone")
    op.drop_table("camera")
