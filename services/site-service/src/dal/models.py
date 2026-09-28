"""Модели sitedb. Описание полей и их смысла — docs/data-model.md, раздел 2.

Здесь только наблюдения: рабочего времени, статусов «работает / простой» и
отклонений нет, их вычисляет analysis-service (ADR-0012).

Перечисления хранятся как text + CHECK, а не как postgres enum: добавление
значения не должно требовать миграции. Ссылки на данные других сервисов
(`object_id`, `equipment_class`) — значения без внешних ключей: чужой базы
здесь нет и быть не может.
"""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ZONE_TYPES = ("PIT", "BUILDING_FOOTPRINT", "PERIMETER", "ENTRY_GATE", "STORAGE", "DANGER", "ROAD")
IMAGE_STATUSES = ("NEEDS_TIME", "PENDING", "PROCESSING", "ANALYZED", "FAILED")
IMAGE_SOURCES = ("UPLOAD", "API", "FOLDER_IMPORT")
TIME_SOURCES = ("EXIF", "FILENAME", "MANUAL", "UNKNOWN")
UNUSABLE_REASONS = ("DARK", "BLURRED", "OCCLUDED")
STAGE_LABELS = ("PIT", "PILES", "FOUNDATION", "FRAME", "FACADE", "LANDSCAPING")
VISIBILITY_STATUSES = ("OK", "PARTIAL", "BLIND")
VISIBILITY_REASONS = ("NO_IMAGES", "DARK", "BLURRED", "OCCLUDED")


def _in(column: str, values: tuple[str, ...]) -> str:
    """CHECK-ограничение «значение из списка»."""
    allowed = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({allowed})"


def _null_or_in(column: str, values: tuple[str, ...]) -> str:
    """CHECK-ограничение «пусто или значение из списка»."""
    return f"{column} IS NULL OR {_in(column, values)}"


class Base(DeclarativeBase):
    # Всё время в базе — timestamptz (AGENTS.md, раздел 7), и модели обязаны это знать:
    # иначе SQLAlchemy шлёт момент как наивный TIMESTAMP и теряет часовой пояс.
    type_annotation_map: ClassVar[dict] = {datetime: DateTime(timezone=True)}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Camera(Base, TimestampMixin):
    """Камера объекта. `code` совпадает с именем папки при пакетной загрузке."""

    __tablename__ = "camera"
    __table_args__ = (UniqueConstraint("object_id", "code", name="uq_camera_object_code"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    object_id: Mapped[UUID] = mapped_column(index=True)  # внешняя ссылка на plandb.object
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    # Эталонный кадр — один из снимков камеры, на нём размечают зоны. Без внешнего
    # ключа: иначе camera и image ссылались бы друг на друга циклом.
    reference_image_id: Mapped[UUID | None]
    # Высота подвеса, азимут, ИК-подсветка: исходные данные для рекомендаций по камерам.
    install_meta: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Zone(Base, TimestampMixin):
    """Зона — полигон на кадре камеры с типом и названием.

    Полигон хранится в нормированных координатах 0…1 от размера кадра и потому
    не зависит от разрешения камеры (ADR-0006). Зоны с одинаковыми типом и
    названием на разных камерах — один участок `ТИП:Название` (ADR-0013).
    """

    __tablename__ = "zone"
    __table_args__ = (CheckConstraint(_in("zone_type", ZONE_TYPES), name="ck_zone_type"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    object_id: Mapped[UUID] = mapped_column(index=True)  # внешняя ссылка
    camera_id: Mapped[UUID] = mapped_column(ForeignKey("camera.id", ondelete="CASCADE"))
    zone_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    polygon: Mapped[list] = mapped_column(JSONB)
    # Растёт при правке полигона; сумма по объекту — zones_version в фактах и прогоне.
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    # Зоны не удаляются, а деактивируются: иначе zones_version могла бы уменьшиться.
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class ObservationSession(Base, TimestampMixin):
    """Окно наблюдения по объекту: 30 минут, выровнено по :00 и :30 UTC.

    Состав техники считается по окну, а не по кадру: одна машина, попавшая в две
    камеры, иначе была бы посчитана дважды. Статусов у окна нет: его факт
    пересчитывается после каждого обработанного снимка (`updated_at`).
    """

    __tablename__ = "session"
    __table_args__ = (
        UniqueConstraint("object_id", "window_start", name="uq_session_object_window"),
        CheckConstraint("window_end > window_start", name="ck_session_window"),
        CheckConstraint(_null_or_in("stage_label", STAGE_LABELS), name="ck_session_stage_label"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    object_id: Mapped[UUID] = mapped_column(index=True)  # внешняя ссылка
    window_start: Mapped[datetime]
    window_end: Mapped[datetime]
    image_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    camera_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Стадия за окно: метка с наибольшей суммой уверенности по пригодным кадрам.
    stage_label: Mapped[str | None] = mapped_column(String(32))
    stage_conf: Mapped[float | None] = mapped_column(Float)
    stage_scores: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class Image(Base, TimestampMixin):
    """Снимок камеры — первичное доказательство в системе."""

    __tablename__ = "image"
    __table_args__ = (
        # Повторная загрузка того же файла не создаёт второй снимок и не удваивает
        # технику в окне; клиенту возвращается ID существующего.
        UniqueConstraint("object_id", "checksum", name="uq_image_object_checksum"),
        CheckConstraint(_in("status", IMAGE_STATUSES), name="ck_image_status"),
        CheckConstraint(_in("source", IMAGE_SOURCES), name="ck_image_source"),
        CheckConstraint(_in("captured_at_source", TIME_SOURCES), name="ck_image_time_source"),
        CheckConstraint(
            _null_or_in("usable_reason", UNUSABLE_REASONS), name="ck_image_usable_reason"
        ),
        Index("ix_image_object_captured_at", "object_id", "captured_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    object_id: Mapped[UUID]  # внешняя ссылка
    camera_id: Mapped[UUID] = mapped_column(ForeignKey("camera.id", ondelete="CASCADE"))
    # Время съёмки может быть неизвестно: снимок остаётся в статусе NEEDS_TIME,
    # но не теряется — источник времени хранится рядом со значением.
    captured_at: Mapped[datetime | None]
    captured_at_source: Mapped[str] = mapped_column(String(16), server_default=text("'UNKNOWN'"))
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("session.id", ondelete="SET NULL"), index=True
    )
    storage_key: Mapped[str] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16), server_default=text("'UPLOAD'"))
    exif: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # Яркость и размытость от vision-service; годность по ним решает site-service.
    quality: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # Непригодный кадр не превращается в вывод «техники нет», а делает участок
    # невидимым. null — снимок ещё не распознан.
    usable: Mapped[bool | None] = mapped_column(Boolean)
    usable_reason: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'PENDING'"), index=True)
    error: Mapped[str | None] = mapped_column(Text)


class Detection(Base):
    """Единица техники (или человек), найденная на снимке."""

    __tablename__ = "detection"
    __table_args__ = (Index("ix_detection_session_class", "session_id", "equipment_class"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    image_id: Mapped[UUID] = mapped_column(ForeignKey("image.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("session.id", ondelete="SET NULL"))
    # Камера нужна для сравнения с прошлым окном той же камеры: смещение между
    # разными камерами не имеет смысла.
    camera_id: Mapped[UUID] = mapped_column(ForeignKey("camera.id", ondelete="CASCADE"))
    # Код класса из equipment_classes.yaml — связь по значению (ADR-0014).
    equipment_class: Mapped[str] = mapped_column(String(64))
    bbox: Mapped[list] = mapped_column(JSONB)
    conf: Mapped[float] = mapped_column(Float)
    # Нижняя середина рамки: точка контакта с землёй, по ней идёт привязка к зоне.
    anchor: Mapped[list] = mapped_column(JSONB)
    # Основная зона: самая маленькая не опасная зона камеры с anchor внутри.
    zone_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("zone.id", ondelete="SET NULL"), index=True
    )
    # Сдвинулась ли единица с прошлого окна той же камеры. Это наблюдение, а не
    # статус «простой»: вывод делает analysis-service. null — прошлого окна нет.
    moved: Mapped[bool | None] = mapped_column(Boolean)
    # Смещение центра рамки в долях диагонали кадра.
    displacement: Mapped[float | None] = mapped_column(Float)
    # Версия модели у каждой детекции: вывод воспроизводим после смены весов.
    model_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class StageObservation(Base):
    """Стадия объекта, определённая по снимку."""

    __tablename__ = "stage_observation"
    __table_args__ = (
        CheckConstraint(_in("stage_label", STAGE_LABELS), name="ck_stage_observation_label"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    image_id: Mapped[UUID] = mapped_column(ForeignKey("image.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("session.id", ondelete="SET NULL"))
    stage_label: Mapped[str] = mapped_column(String(32))
    conf: Mapped[float] = mapped_column(Float)
    # Все вероятности, а не только победившая: без них вывод нечем объяснить.
    scores: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AreaVisibility(Base):
    """Видимость участка в окне — основание для D10 «вне контроля ИИ»."""

    __tablename__ = "area_visibility"
    __table_args__ = (
        CheckConstraint(_in("zone_type", ZONE_TYPES), name="ck_visibility_zone_type"),
        CheckConstraint(_in("status", VISIBILITY_STATUSES), name="ck_visibility_status"),
        CheckConstraint(_null_or_in("reason", VISIBILITY_REASONS), name="ck_visibility_reason"),
    )

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), primary_key=True
    )
    # Ключ участка `ТИП:Название` (ADR-0013); тип и название — для показа без разбора.
    area: Mapped[str] = mapped_column(String(300), primary_key=True)
    zone_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    cameras_total: Mapped[int] = mapped_column(Integer)
    cameras_usable: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SessionFact(Base):
    """Факт окна: участок × класс техники × количество.

    Пересчитывается после каждого обработанного снимка окна и при правке зон —
    это то, что читает analysis-service через контракт «факты за период».
    """

    __tablename__ = "session_fact"
    # Отсутствие класса означает ноль, поэтому нулевые строки не хранятся.
    __table_args__ = (CheckConstraint("count > 0", name="ck_session_fact_count"),)

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), primary_key=True
    )
    # Ключ участка `ТИП:Название` или `OUTSIDE` для детекций вне всех зон.
    area: Mapped[str] = mapped_column(String(300), primary_key=True)
    equipment_class: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Максимум по камерам участка, а не сумма: камеры видят одно и то же, иначе двойной счёт.
    count: Mapped[int] = mapped_column(Integer)
    # Сколько из count не двигались с прошлого окна; null — сравнивать не с чем.
    static: Mapped[int | None] = mapped_column(Integer)
    # Снимки и детекции, на которые опирается число: без них факт неотличим от мнения.
    evidence: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
