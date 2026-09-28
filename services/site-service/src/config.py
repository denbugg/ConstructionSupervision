"""Конфигурация site-service. Единственное место чтения окружения."""

from lct_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "site-service"

    # База сервиса. Роль site_user имеет права только на sitedb (ADR-0003).
    site_db_dsn: str = "postgresql+asyncpg://site_user:site@postgres:5432/sitedb"
    db_echo: bool = False

    # Справочные файлы контрактов, смонтированные только для чтения: enums.yaml (типы и роли
    # зон, статусы видимости).
    contracts_dir: str = "/contracts"

    # Длина окна сессии наблюдения: состав техники считается по сессии, а не по
    # кадру, иначе одна машина в двух камерах была бы посчитана дважды.
    session_window_minutes: int = 30
    # Часовой пояс часов камер: EXIF и имена файлов хранят местное время без пояса.
    camera_timezone: str = "Europe/Moscow"

    # Приём снимков (api-guidelines.md, раздел 7).
    max_image_mb: int = 20
    max_files_per_request: int = 200
    # Папка для POST /images/import, смонтированная только для чтения: подпапка = код камеры.
    import_dir: str = "/import"

    # S3-хранилище (ADR-0016): оригиналы снимков. Внутренний адрес — для загрузки и для
    # vision-service, публичный — для подписи ссылок, которые открывает браузер.
    s3_endpoint: str = "http://s3:8333"
    s3_public_endpoint: str = "http://localhost:8333"
    s3_access_key: str = "s3admin"
    s3_secret_key: str = "s3admin"
    s3_bucket_images: str = "images"
    s3_presign_ttl_s: int = 3600

    # Конвейер распознавания (README, раздел 4). Очередь — только ускоритель: источник истины —
    # статус снимка в базе, и проход по базе раз в SWEEP_INTERVAL_S подбирает всё, что
    # очередь потеряла.
    redis_url: str = "redis://redis:6379/0"
    worker_concurrency: int = 4
    sweep_interval_s: int = 30
    # Снимок в PROCESSING дольше этого — воркер упал посреди задачи, снимок берётся заново.
    stale_processing_minutes: int = 10
    # Пересчёт фактов всех окон объекта после правки зон: без распознавания, но окон — тысячи.
    reapply_timeout_s: int = 600

    # vision: 30 с и два повтора — задача идемпотентна (interservice.md, раздел 3).
    vision_url: str = "http://vision-service:8000"
    vision_timeout_s: float = 30.0
    vision_retries: int = 2
    # Сигнал «пересчитай»: 2 с без повторов, потерянный сигнал безопасен (раздел 4).
    analysis_url: str = "http://analysis-service:8000"
    analysis_timeout_s: float = 2.0

    # Факт окна (methodology.md, раздел 4): пригодность кадра и порог смещения — доля
    # диагонали кадра, с которой единица считается сдвинувшейся.
    min_brightness: float = 0.15
    max_blur: float = 0.6
    move_threshold: float = 0.01


settings = Settings()
