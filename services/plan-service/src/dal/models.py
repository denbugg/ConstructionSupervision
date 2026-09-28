"""Модели plandb. Описание полей и их смысла — docs/data-model.md, раздел 1.

Перечисления хранятся как text + CHECK, а не как postgres enum: добавление
значения не должно требовать миграции. Ссылки на данные других сервисов —
только UUID без внешних ключей. Классов техники здесь нет: их единственный
источник — packages/contracts/equipment_classes.yaml (ADR-0014).
"""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

OBJECT_TYPES = ("RESIDENTIAL_MONOLITH", "RESIDENTIAL_PANEL", "PUBLIC_BUILDING", "ROAD")
OBJECT_LIFECYCLE = ("DRAFT", "ACTIVE", "ARCHIVED")
PHASES = (
    "PREPARATORY",
    "SUBSTRUCTURE",
    "SUPERSTRUCTURE",
    "ENVELOPE_ROOF",
    "NETWORKS",
    "LANDSCAPING",
)
# Только типы зон с ролью WORK (enums.yaml: zone_type_role): работы этапа идут на
# рабочем участке, а въезд, склад и опасная зона этапом не бывают.
STAGE_ZONE_TYPES = ("PIT", "BUILDING_FOOTPRINT", "PERIMETER", "ROAD")
STAGE_LABELS = ("PIT", "PILES", "FOUNDATION", "FRAME", "FACADE", "LANDSCAPING")
STAGE_SOURCES = ("GENERATED", "IMPORT", "MANUAL")


def _in(column: str, values: tuple[str, ...]) -> str:
    """CHECK-ограничение «значение из списка»."""
    allowed = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({allowed})"


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorkCalendar(Base, TimestampMixin):
    """Рабочий календарь: выходные, праздники, рабочие часы.

    Рабочие часы заданы в местном времени `timezone`, а сессии площадки — в UTC:
    перевод делает analysis-service, поэтому часовой пояс хранится рядом с часами.
    """

    __tablename__ = "work_calendar"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), server_default=text("'Europe/Moscow'"))
    weekend_days: Mapped[list] = mapped_column(JSONB, server_default=text("'[6, 7]'::jsonb"))
    holidays: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    work_hours: Mapped[dict] = mapped_column(
        JSONB, server_default=text("""'{"start": "07:00", "end": "23:00"}'::jsonb""")
    )


class ConstructionObject(Base, TimestampMixin):
    """Объект капитального строительства — корневая сущность системы."""

    __tablename__ = "object"
    __table_args__ = (
        CheckConstraint(_in("object_type", OBJECT_TYPES), name="ck_object_type"),
        CheckConstraint(_in("status", OBJECT_LIFECYCLE), name="ck_object_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text)
    object_type: Mapped[str] = mapped_column(String(32), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    # Параметры для генератора графика: этажность, площадь, секции, сваи, сменность.
    tep: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    plan_start: Mapped[date | None] = mapped_column(Date)
    calendar_id: Mapped[UUID | None] = mapped_column(ForeignKey("work_calendar.id"))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'DRAFT'"), index=True)
    # Растёт при любой правке этапов, правил или календаря и попадает в прогон анализа:
    # по нему видно, на какой версии плана построен вывод.
    plan_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class WorkType(Base):
    """Справочник строительных работ, 4 уровня.

    Загружается парсером XLSX заказчика. В source пишется файл, лист и номер
    строки: любое значение должно быть проверяемо по первоисточнику.
    """

    __tablename__ = "work_type"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    level: Mapped[int] = mapped_column(Integer)
    parent_code: Mapped[str | None] = mapped_column(String(32), index=True)
    # Отметки обязательности по девяти столбцам исходного файла: {"Жильё": true, …}
    applicable: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    source: Mapped[str | None] = mapped_column(Text)


class Stage(Base, TimestampMixin):
    """Этап календарного графика: укрупнённая единица работ с плановыми датами."""

    __tablename__ = "stage"
    __table_args__ = (
        CheckConstraint(_in("phase", PHASES), name="ck_stage_phase"),
        CheckConstraint(_in("zone_type", STAGE_ZONE_TYPES), name="ck_stage_zone_type"),
        CheckConstraint(
            f"visual_stage IS NULL OR {_in('visual_stage', STAGE_LABELS)}",
            name="ck_stage_visual_stage",
        ),
        CheckConstraint(_in("source", STAGE_SOURCES), name="ck_stage_source"),
        CheckConstraint("plan_end >= plan_start", name="ck_stage_dates"),
        CheckConstraint("norm_duration_days > 0", name="ck_stage_norm_duration"),
        Index("ix_stage_object_seq", "object_id", "seq"),
        Index("ix_stage_object_plan_start", "object_id", "plan_start"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    object_id: Mapped[UUID] = mapped_column(ForeignKey("object.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(64))
    work_codes: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    name: Mapped[str] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(String(32))
    seq: Mapped[int] = mapped_column(Integer)
    zone_type: Mapped[str] = mapped_column(String(32))
    # Как объект выглядит на фото во время этапа: нужен для D7 и ограничения прогресса.
    visual_stage: Mapped[str | None] = mapped_column(String(32))
    plan_start: Mapped[date] = mapped_column(Date)
    plan_end: Mapped[date] = mapped_column(Date)
    norm_duration_days: Mapped[int] = mapped_column(Integer)
    # [{"stage_id": "...", "type": "FS", "lag_days": 0}]
    predecessors: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    is_critical: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    total_float_days: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    source: Mapped[str] = mapped_column(String(16), server_default=text("'MANUAL'"))
    # Откуда длительность: норматив и доля этапа для генератора, «импорт» для файла.
    basis: Mapped[str | None] = mapped_column(Text)
    # Отметка оператора «этап выполнен» — факт о работах, а не правка плана (ADR-0015):
    # последний день работ включительно, кто отметил и почему.
    completed_on: Mapped[date | None] = mapped_column(Date)
    completed_by: Mapped[str | None] = mapped_column(Text)
    completion_note: Mapped[str | None] = mapped_column(Text)


class StageRule(Base, TimestampMixin):
    """Правило «этап → техника»: группы обязательной, допустимая и сигнатура старта.

    Создаётся из шаблона этапа, дальше редактируется оператором в интерфейсе. Где
    искать технику, задаёт `stage.zone_type`. Версия растёт при каждой правке и
    попадает в отклонение, чтобы вывод оставался воспроизводимым.
    """

    __tablename__ = "stage_rule"
    __table_args__ = (CheckConstraint("min_sessions >= 1", name="ck_rule_min_sessions"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    # У этапа не больше одного правила.
    stage_id: Mapped[UUID] = mapped_column(ForeignKey("stage.id", ondelete="CASCADE"), unique=True)
    # [{"any_of": ["excavator"], "min": 1}, {"any_of": ["dump_truck"], "min": 2}]
    required: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    allowed: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    # {"equipment": ["excavator", "dump_truck"], "stage_label": null}
    signature: Mapped[dict] = mapped_column(
        JSONB, server_default=text("""'{"equipment": [], "stage_label": null}'::jsonb""")
    )
    min_sessions: Mapped[int] = mapped_column(Integer, server_default=text("2"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
