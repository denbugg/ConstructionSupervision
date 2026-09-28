"""Конфигурация plan-service. Единственное место чтения окружения."""

from lct_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "plan-service"

    # База сервиса. Роль plan_user имеет права только на plandb (ADR-0003).
    plan_db_dsn: str = "postgresql+asyncpg://plan_user:plan@postgres:5432/plandb"
    db_echo: bool = False

    # Календарь по умолчанию для новых объектов.
    default_calendar: str = "moscow-6day"

    # Справочные файлы контрактов, смонтированные только для чтения: классы техники
    # (equipment_classes.yaml) и перечисления (enums.yaml). ADR-0014.
    contracts_dir: str = "/contracts"
    # Шаблоны этапов по типам объектов, путь от каталога сервиса.
    wbs_templates_file: str = "data/wbs_templates.json"
    # Нормы МРР для генератора графика, путь от каталога сервиса.
    mrr_norms_file: str = "data/mrr_norms.json"
    # Предел размера загружаемого файла: графика и справочника работ.
    plan_import_max_mb: int = 5

    # Сигнал «пересчитай» после правки плана (interservice.md, раздел 4): отправитель
    # не ждёт и не повторяет — потерянный сигнал безопасен, следующий прогон посчитает всё.
    analysis_url: str = "http://analysis-service:8000"
    signal_timeout_s: float = 2.0


settings = Settings()
