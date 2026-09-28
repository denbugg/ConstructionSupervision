"""Конфигурация analysis-service. Единственное место чтения окружения."""

from lct_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "analysis-service"

    # База сервиса. Роль analysis_user имеет права только на analysisdb (ADR-0003).
    analysis_db_dsn: str = "postgresql+asyncpg://analysis_user:analysis@postgres:5432/analysisdb"
    db_echo: bool = False

    # Справочные файлы контрактов, смонтированные только для чтения: enums.yaml
    # задаёт роли типов зон и порядок стадий по фото.
    contracts_dir: str = "/contracts"
    # Начальные настройки D1–D10: переносятся в deviation_rule при первом старте.
    deviation_rules_file: str = "data/deviation_rules.yaml"

    # Источники плана и фактов (interservice.md, контракты 1 и 2): 10 с, два повтора.
    plan_url: str = "http://plan-service:8000"
    site_url: str = "http://site-service:8000"
    upstream_timeout_s: float = 10.0
    upstream_retries: int = 2

    # Прогон (interservice.md, раздел 4): на объект один прогон. Прогон, который висит
    # в RUNNING дольше RUN_STALE_AFTER_S, считается брошенным (процесс упал) и объект не
    # блокирует. `?wait=true` во время чужого прогона ждёт его не дольше RUN_WAIT_TIMEOUT_S.
    run_stale_after_s: float = 900.0
    run_wait_timeout_s: float = 120.0
    run_wait_poll_s: float = 0.5

    # /explain показывает не больше стольких последних сессий эпизода (два рабочих дня).
    explain_max_sessions: int = 64

    # Параметры методики (docs/methodology.md, раздел 11) — экспертные допущения,
    # вынесенные в окружение для калибровки на площадке.
    transient_window_sessions: int = 4
    min_stage_conf: float = 0.5
    # Прогноз (раздел 10.5): нижняя граница темпа, окно усреднения, минимум дней наблюдений.
    min_activity: float = 0.1
    forecast_window_days: int = 5
    min_days_for_forecast: int = 3
    on_track_tolerance_days: int = 2
    # Уверенность и UNKNOWN (разделы 10.7–10.8): сколько дней и какая доля видимых
    # сессий нужны для HIGH и MEDIUM; доля слепых сессий, после которой статус UNKNOWN.
    confidence_high_days: int = 5
    confidence_high_visible: float = 0.8
    confidence_medium_visible: float = 0.5
    unknown_blind_share: float = 0.5

    # Отчёты (README, раздел 5): бакет в S3-хранилище; ссылка для браузера — на публичный адрес.
    s3_endpoint: str = "http://s3:8333"
    s3_public_endpoint: str = "http://localhost:8333"
    s3_access_key: str = "s3admin"
    s3_secret_key: str = "s3admin"
    s3_bucket_reports: str = "reports"
    s3_presign_ttl_s: int = 3600
    report_labels_file: str = "data/report_labels.yaml"
    # Снимков-доказательств в отчёте не больше этого, а длинная сторона снимка ужимается
    # до REPORT_IMAGE_MAX_PX: оригиналы камер по 1–2 МБ раздули бы PDF до десятков мегабайт.
    report_max_evidence_images: int = 12
    report_image_max_px: int = 1280
    # Период по умолчанию: столько местных дней, заканчивая днём момента анализа.
    report_default_days: int = 7

    # Резюме нейросетью (ADR-0008): любой OpenAI-совместимый API — облачный провайдер,
    # llama.cpp или Ollama. Выключено или без адреса — резюме по шаблону.
    llm_enabled: bool = True
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    llm_timeout_s: float = 30.0
    llm_prompt_file: str = "prompts/summary.ru.md"


settings = Settings()
