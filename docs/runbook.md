# Запуск, конфигурация и эксплуатация

---

## 1. Требования

| Что | Версия | Зачем |
| :--- | :--- | :--- |
| Docker + Docker Compose | 24+ / v2; на Windows — Docker Desktop с бэкендом WSL2 | Единственный обязательный способ запуска |
| Python | 3.12 | Только чтобы создать `.venv` (раздел 3): скрипты, ruff и LabelMe ставятся туда |
| ruff | **0.16.8** (как в `requirements-dev.txt`), ставится в `.venv` | Линт. Другая версия ruff проверяет по другим правилам |
| Node.js | 20+ | Локальная разработка фронтенда |
| GNU Make + bash | любая | Удобные обёртки. На Windows без bash не работают — раздел 3 |
| Оперативная память | 8 ГБ минимум, 16+ комфортно | CV-сервис + Postgres + S3-хранилище + воркеры |
| Диск | ~20 ГБ | Образ с CUDA весит несколько гигабайт, плюс остальные образы, веса и демо-снимки |
| GPU | NVIDIA, 4+ ГБ VRAM | Не обязателен, но целевой стенд — с ним |

**Целевой стенд:** ноутбук Ryzen 5 5600H, 32 ГБ, RTX 3060 Laptop 6 ГБ, Windows 10, Docker Desktop.

**GPU в Docker на Windows.** Docker Desktop с бэкендом WSL2 пробрасывает видеокарту сам. Нужен
только свежий драйвер NVIDIA для Windows, а `nvidia-container-toolkit` отдельно не ставится.
Проверка:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

Без GPU система работает целиком, но распознавание идёт секунды вместо миллисекунд. Для
отладки этого достаточно, для показа нет.

Карту в `vision-service` пробрасывает оверлей `docker-compose.gpu.yml` (раздел 5). На стенде
с картой стек поднимается так:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

Фактическое устройство показывает `GET /api/v1/vision/model` (поле `device`).

## 2. Первый запуск

Команды — для PowerShell на демо-стенде, из корня репозитория; Docker Desktop запущен. В Linux
и macOS вместо `.venv\Scripts\python` — `.venv/bin/python`.

**1. Настройки.**

```powershell
copy .env.example .env
```

В `.env` поменять пароли и `API_KEY`, а также:

- `GATEWAY_PORT` — если порт 8080 занят. На стенде его держит AdGuard, там `8088`;
- `VISION_DET_WEIGHTS` — дообученные веса, если они есть (шаг 3);
- `LLM_BASE_URL` и `LLM_MODEL` — если будет LLM (раздел 4). Без них резюме шаблонное.

**2. Окружение хоста и веса моделей.** `fetch_models.py` скачивает zero-shot детектор
`yolov8s-worldv2.pt`, OpenCLIP и текстовый CLIP в `data/models/`, около 940 МБ.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r tools\requirements.txt
.venv\Scripts\python scripts\fetch_models.py
```

**3. Дообученные веса — нужны для демо.** Сценарий раздела 6 на чистом стенде проходит с
`yolov8s-worldv2-ulima-v3.pt` (репетиция 27.09, board.md, T38). С `ce-ulima-v1` в «нормальный
день» 19.10 добавляется лишнее D4 «простой» башенного крана вне зон: рамка крана у этих весов
другая, и её нижняя точка не попадает ни в один участок. Скрипт весов не скачивает, в git их
нет: файл переносится со стенда в `data/models/`, в `.env` —
`VISION_DET_WEIGHTS=/models/yolov8s-worldv2-ulima-v3.pt`. Без дообученных весов vision работает
на zero-shot, а он технику Лимы почти не узнаёт (mAP50 0,07, [metrics.md](metrics.md), §3).

**4. Демо-снимки.** Их нет в git: это кадры открытого датасета Лимы
([ml/README.md](../ml/README.md), «Датасет Лимы», ссылка на DOI). Архив распаковывается как есть
в `ml/datasets/ulima/`, затем:

```powershell
.venv\Scripts\python scripts\seed_images.py   # 56 кадров → data/seed/images/cam-*/
```

**5. Стек.** На машине с картой NVIDIA — с оверлеем GPU (раздел 1). Все сторонние образы
скачиваются из публичных реестров; S3-хранилище — SeaweedFS с Docker Hub
([ADR-0016](decisions/0016-seaweedfs-instead-of-minio.md)). Сборка образа vision-service
с CUDA идёт 26 минут (образ 12,4 ГБ); если образы опубликованы, быстрее их скачать
(`docker compose pull`, раздел 10).

**Переход со стенда на MinIO** (`.env` с `S3_ENDPOINT=http://minio:9000`). Адреса в `.env`
поменять на `S3_ENDPOINT=http://s3:8333` и `S3_PUBLIC_ENDPOINT=http://localhost:8333`, ключи
оставить. Снимки и отчёты из старого тома переносятся зеркалом, пока контейнер MinIO ещё
запущен (`docker compose up -d s3` поднимает новое хранилище рядом):

```powershell
docker exec lct-minio-1 sh -c 'mc alias set old http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"; mc alias set new http://s3:8333 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"; for b in images reports; do mc mb --ignore-existing new/$b; mc mirror --quiet old/$b new/$b; done'
docker compose up -d --remove-orphans      # сервисы на новом адресе, контейнер MinIO удалён
```

Том `lct_miniodata` после этого не нужен: `docker volume rm lct_miniodata`. Без переноса
данные загружаются заново `seed.py`.

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
.venv\Scripts\python scripts\health.py        # все готовы; vision грузит модели ~40 с
```

**6. Демо-данные и проверка.**

```powershell
.venv\Scripts\python scripts\seed.py          # объект, график, правила, снимки, зоны, анализ
.venv\Scripts\python scripts\e2e.py           # лента совпадает со сценарием → «E2E пройден»
```

`seed.py` ждёт распознавания 56 снимков (на GPU около минуты) и пересчёта фактов по зонам.
`e2e.py` работает на отдельном объекте «E2E: …» и демо-объект не трогает.

| Адрес (порт gateway — `GATEWAY_PORT`, по умолчанию 8080) | Что |
| :--- | :--- |
| <http://localhost:8080> | Интерфейс |
| <http://localhost:8080/docs> | Сводный Swagger с выбором сервиса; страница грузит Swagger UI с cdnjs, нужен интернет |
| <http://localhost:8001/docs> … <http://localhost:8004/docs> | Swagger отдельных сервисов |
| <http://localhost:23646> | Веб-интерфейс SeaweedFS (вход — `S3_ACCESS_KEY` / `S3_SECRET_KEY`) |

## 3. Команды

Все скрипты проекта написаны на Python и работают одинаково в Linux, macOS и Windows. Цели
`Makefile` — короткие обёртки над теми же командами. Их рецепты требуют bash, поэтому на Windows
(`make` из Chocolatey запускает рецепты через cmd) пользуйтесь правым столбцом.

| `make` | PowerShell (Windows) | Что делает |
| :--- | :--- | :--- |
| `make up` / `make down` | `docker compose up -d --build` / `docker compose down` | Поднять / остановить стек |
| `make pull` | `docker compose pull` | Забрать опубликованные образы из ghcr вместо локальной сборки |
| `make third-party` | `docker compose pull postgres s3 redis; docker compose up -d --wait postgres s3 redis` | Сторонние образы скачиваются и поднимаются — та же проверка, что в CI |
| `make restart s=site` | `docker compose restart site-service` | Перезапустить один сервис |
| `make logs s=analysis f=1` | `docker compose logs -f --tail=200 analysis-service` | Логи сервиса |
| `make ps` | `docker compose ps` | Состояние контейнеров |
| `make health` | `.venv\Scripts\python scripts/health.py` | Опросить `/health/ready` всех сервисов |
| `make seed` | `.venv\Scripts\python scripts/seed.py` | Загрузить демо-данные и прогнать анализ |
| `make demo` | `.venv\Scripts\python scripts/demo.py` | Сценарий показа: четыре дня объекта с заложенными отклонениями, ссылки на снимки |
| `make reset` | `docker compose down -v` | Полная очистка: тома БД, бакеты S3, очередь |
| `make test s=plan` | `.venv\Scripts\python scripts/test.py plan` (без имени — все сервисы) | Тесты сервиса в одноразовом контейнере его образа, с базой `<база>_test` |
| `make lint` | `.venv\Scripts\ruff check --config tools/ruff.toml packages services scripts; .venv\Scripts\ruff format --check --config tools/ruff.toml packages services scripts` | Линт и проверка формата |
| `make fmt` | `.venv\Scripts\ruff format --config tools/ruff.toml packages services scripts` | Автоформатирование |
| `make e2e` | `.venv\Scripts\python scripts/e2e.py` | Сквозной сценарий на поднятом стеке |
| `make contracts` | `.venv\Scripts\python scripts/contracts.py` | Пересобрать снапшоты OpenAPI и TS-клиент |
| `make migrate s=plan m="…"` | `cd services/plan-service; $env:PYTHONPATH='.'; alembic revision --autogenerate -m "…"` | Создать миграцию Alembic |
| `make models` | `.venv\Scripts\python scripts/fetch_models.py` | Скачать веса моделей |
| `make dev` | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build` | Стек с hot-reload |
| `make backup` | — | Не реализовано: `backup.py` — заготовка (раздел 8) |

**Окружение хоста — `.venv` в корне репозитория, глобальный Python не используется.** В нём
всё, что запускается вне контейнеров: скрипты `scripts/` и `ml/prepare`, ruff той же версии,
что в CI, LabelMe. Список — `tools/requirements.txt`; сервисы, их тесты, torch и Ultralytics
живут в образах. Создать или обновить:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r tools\requirements.txt
```

Команды вызывают `.venv\Scripts\python` и `.venv\Scripts\ruff` прямо, без активации: на стенде
политика PowerShell `AllSigned` не даёт запустить `Activate.ps1`. В Linux и macOS — `.venv/bin/`,
там можно и `source .venv/bin/activate`. Окружение лежит в каталоге проекта, а не в профиле
пользователя, поэтому пакеты, поставленные из сессии агента, видны и в терминале человека.

## 4. Переменные окружения

Один `.env` в корне на весь compose. Секции — по назначению.

### Общие

| Переменная | По умолчанию | Смысл |
| :--- | :--- | :--- |
| `ENV` | `dev` | `dev` / `prod`: влияет на подробность логов и показ `/docs` |
| `LOG_LEVEL` | `INFO` | |
| `API_KEY` | `dev-key-change-me` | Ключ для `X-API-Key`; в проде обязателен к замене |
| `TZ` | `Europe/Moscow` | Отображение времени; хранение всегда UTC |
| `RUN_MIGRATIONS` | `true` | Применять Alembic при старте контейнера |
| `CONTRACTS_DIR` | `/contracts` | Куда смонтирован `packages/contracts` (классы техники, перечисления) |
| `GATEWAY_PORT` | `8080` | Внешний порт gateway; поменять, если 8080 на машине занят |

### Образы

| Переменная | По умолчанию | Смысл |
| :--- | :--- | :--- |
| `IMAGE_REGISTRY` | `ghcr.io/cerxxxx/constructionsupervision` | Откуда `make pull` тянет образы (раздел 10) |
| `IMAGE_TAG` | `latest` | Версия образов: `latest` или тег релиза, например `v0.2.0` |

### Базы данных

| Переменная | По умолчанию |
| :--- | :--- |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `postgres` / `5432` |
| `POSTGRES_SUPERUSER` / `POSTGRES_PASSWORD` | `postgres` / задаётся в `.env` |
| `PLAN_DB_DSN` | `postgresql+asyncpg://plan_user:***@postgres:5432/plandb` |
| `SITE_DB_DSN` | `postgresql+asyncpg://site_user:***@postgres:5432/sitedb` |
| `ANALYSIS_DB_DSN` | `postgresql+asyncpg://analysis_user:***@postgres:5432/analysisdb` |

Базы и роли создаются один раз скриптом инициализации Postgres (`infra/postgres/init/`). Роль
имеет права только на свою базу — граница сервисов защищена самой СУБД.

### Хранилище и очередь

| Переменная | По умолчанию | Смысл |
| :--- | :--- | :--- |
| `S3_ENDPOINT` | `http://s3:8333` | S3-хранилище (SeaweedFS) внутри сети Docker |
| `S3_PUBLIC_ENDPOINT` | `http://localhost:8333` | Адрес хранилища для браузера: на него подписываются ссылки, которые открывает интерфейс |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | задаются в `.env` | Ключи S3 и вход в веб-интерфейс SeaweedFS |
| `S3_BUCKET_IMAGES` / `S3_BUCKET_REPORTS` | `images` / `reports` | |
| `S3_PRESIGN_TTL_S` | `3600` | Срок жизни ссылок |
| `REDIS_URL` | `redis://redis:6379/0` | Очередь задач site-worker |

### Адреса сервисов

| Переменная | По умолчанию |
| :--- | :--- |
| `PLAN_URL` | `http://plan-service:8000` |
| `SITE_URL` | `http://site-service:8000` |
| `ANALYSIS_URL` | `http://analysis-service:8000` |
| `VISION_URL` | `http://vision-service:8000` |

### Компьютерное зрение

| Переменная | По умолчанию | Смысл |
| :--- | :--- | :--- |
| `VISION_DEVICE` | `cuda` | `cuda` на демо-стенде, `cpu` — запасной путь |
| `VISION_DET_WEIGHTS` | `/models/yolov8s-worldv2.pt` | Веса детектора; дообученные подставляются сюда же |
| `VISION_DET_CONF` | `0.35` | Порог уверенности |
| `VISION_DET_IMGSZ` | `1280` | Размер входа |
| `VISION_STAGE_MODEL` | `openclip-vit-b32` | Классификатор стадии |

### Конвейер и методика

| Переменная | По умолчанию | Смысл |
| :--- | :--- | :--- |
| `SESSION_WINDOW_MINUTES` | `30` | Длина окна сессии |
| `MAX_IMAGE_MB` | `20` | Предел размера снимка |
| `WORKER_CONCURRENCY` | `4` | Параллельных задач в воркере |
| `MOVE_THRESHOLD` | `0.01` | Смещение (доля диагонали кадра), с которого единица считается сдвинувшейся |
| `MIN_BRIGHTNESS` / `MAX_BLUR` | `0.15` / `0.6` | Пригодность кадра |
| `TRANSIENT_WINDOW_SESSIONS` | `4` | Окно присутствия транзитной техники |
| `MIN_STAGE_CONF` | `0.5` | Порог уверенной стадии по фото |
| `MIN_ACTIVITY` | `0.1` | Нижняя граница темпа в прогнозе |
| `ON_TRACK_TOLERANCE_DAYS` | `2` | Порог статуса «в графике» |

Пороги отклонений D1–D10 живут в таблице `deviation_rule` и правятся в интерфейсе; начальные
значения — `services/analysis-service/data/deviation_rules.yaml`.

### LLM

| Переменная | По умолчанию | Смысл |
| :--- | :--- | :--- |
| `LLM_ENABLED` | `true` | `false` → шаблонные резюме без модели |
| `LLM_BASE_URL` | — | Адрес OpenAI-совместимого API с `/v1`; пусто — шаблонные резюме |
| `LLM_API_KEY` | — | **Настоящий секрет.** Только в `.env`, никогда в git |
| `LLM_MODEL` | — | Имя модели у провайдера |
| `LLM_TIMEOUT_S` | `30` | По истечении — шаблонное резюме |

Годится любой OpenAI-совместимый API: облачный провайдер или локальный сервер. В модель уходят
только структурированные факты — названия этапов, даты, числа, коды отклонений; ни снимков, ни
персональных данных. Прямой доступ к OpenAI и Anthropic из РФ без прокси не работает:
облачного провайдера нужно проверить **с той машины, на которой будет демонстрация**, заранее.

**Локальная модель на демо-стенде** (26.09, платного API нет): llama.cpp на хосте, Gemma 4 E4B
Q4_K_M. Модель занимает ~3,3 ГБ видеопамяти и помещается на 6 ГБ рядом с vision; резюме —
3–5 с. Запуск до показа, в отдельном окне PowerShell:

```powershell
D:\localllamacpp\bin\b11099\llama-server.exe `
  -m D:\LMStudio\models\lmstudio-community\gemma-4-E4B-it-GGUF\gemma-4-E4B-it-Q4_K_M.gguf `
  --host 127.0.0.1 --port 8091 -c 8192 -ngl 99 --alias gemma-4-e4b `
  --chat-template-kwargs '{\"enable_thinking\":false}'
```

В `.env`: `LLM_BASE_URL=http://host.docker.internal:8091/v1`, `LLM_MODEL=gemma-4-e4b`,
`LLM_TIMEOUT_S=60`, затем `docker compose up -d analysis-service`. Режим рассуждений Gemma
выключен: для пересказа фактов он только тратит время. Порт 8080 на стенде занят (AdGuard),
поэтому 8091. Сервер не запущен — отчёт выйдет с шаблонным резюме, это не ошибка.

## 5. Профили и оверлеи compose

Разработка — это **оверлей**, а не профиль: отдельный файл `docker-compose.dev.yml` поверх
основного. Он добавляет hot-reload и монтирование исходников; `packages/py-common` намеренно
не монтируется — его правка требует пересборки образа, иначе получается «работает только у меня».

| Профиль | Что добавит | Когда | Состояние |
| :--- | :--- | :--- | :--- |
| `llm` | Ollama + загрузка модели | Закрытый контур без внешнего API | не делается: локальная модель — любой OpenAI-совместимый сервер на хосте через `LLM_BASE_URL` (раздел 4) |
| `gpu` | `vision-service` с пробросом видеокарты | Целевой стенд | сделан **оверлеем** `docker-compose.gpu.yml`: профиль добавляет сервисы, но не дополняет описанный |

## 6. Демо-сценарий (5 минут)

`python scripts/demo.py` готовит данные и ведёт по шагам ниже: по каждому дню печатает, что
рассказать, найденные отклонения и ссылки на снимки-доказательства в интерфейсе. Ожидаемые
отклонения — `data/seed/expected.json`; `python scripts/e2e.py` проверяет, что лента с ними
совпадает.

Объект — монолитный каркас на кадрах датасета Лимы ([data/README.md](../data/README.md)): две
камеры, обзорная `cam-torre-h` и наземная `cam-d3`, демо-дни 19–22.10.2026. По графику идёт
надземная часть: каркас 12.4.4 (правило ТЗ: башенный кран) и с 21.10 — бетонирование колонн и
перекрытий 12.4.10 (миксер и бетононасос). Участки: «Пятно застройки» на обеих камерах, «Въезд»
(дорога вдоль корпуса) на Torre H, «Склад» (навесы) только на D3.

1. **График.** Импорт графика из XLSX (или генерация по МРР из типа и параметров объекта):
   этапы, даты, критический путь, правила «этап → техника».
2. **19.10 — нормальный день.** Кран на каркасе, погрузчики и самосвалы на въезде. D2 нет.
   Погрузчик у въезда даёт **D4 «простой»**: по методике нетранзитная машина на служебном
   участке простаивает (methodology.md, раздел 6).
3. **20.10 — простой и чужая техника.** Погрузчики весь день на месте: у въезда и на пятне
   застройки → **D4**. Погрузчика нет в правилах этапов каркаса → **D3 «техника не по этапу»**.
   Кран стоит на месте, но простоем не считается: он работает стоя.
4. **21.10 — бетонирование и слепой участок.** По графику бетонирование, а с утра нет ни
   миксера, ни насоса → **D1**. С 11:00 приходят миксеры, насоса нет → **D2 «неполный
   комплект»**: бетон ждёт насоса. Открываем карточку: правило, числа, снимок с рамками.
   Камера D3 закрыта → склад, который видит только она, получает **D10 «участок вне контроля
   ИИ, проверить вручную»**. Пятно застройки при этом видно частично, с Torre H: наглядный плюс
   нескольких камер на участок.
5. **22.10 — комплект полный.** Миксер и насос на месте, D2 закрыт. Насос стоит на опорах весь
   день, но работает стоя: простоя нет.
6. **Гант.** Фактический старт, прогноз окончания, задержка, перенос на зависимые этапы.
7. **Отчёт.** PDF с планом-фактом, загрузкой техники и LLM-резюме со ссылками на ID отклонений.
8. **Правка правила.** Дашборд → «Правила» → этап 12.4.10: убираем из обязательной техники
   группу «бетононасос» (бетон можно подавать краном в бадье) → «Сохранить и пересчитать» →
   экран сообщает, что D2 исчез из ленты, утреннее D1 остаётся. Вернули группу — D2 вернулся. Это демонстрация главного архитектурного тезиса:
   логика — данные, а не код. Проверено через API 26.09 на свежем объекте.

## 7. Диагностика

| Симптом | Причина | Что делать |
| :--- | :--- | :--- |
| `vision-service` не готов | Не скачаны веса | `python scripts/fetch_models.py`, затем `docker compose restart vision-service` |
| Снимки остаются в статусе `PENDING` | Воркер не поднялся или недоступен Redis | `docker compose logs site-worker`, проверить `REDIS_URL` |
| Снимки в статусе `NEEDS_TIME` | Нет EXIF и время не распознано из имени файла | Указать время при загрузке или переименовать по шаблону `YYYYMMDD_HHMMSS.jpg` |
| Анализ не находит отклонений | Нет активных этапов на дату снимков, не размечены зоны или участок невидим | Проверить `GET /api/v1/plan/objects/{id}/plan`, зоны камер и `as_of` прогона |
| Все участки `BLIND` | Зоны не размечены или кадры непригодны | Проверить `data/seed/cameras.json` и `usable` у снимков |
| Снимки не открываются в браузере | Ссылка подписана на внутренний адрес хранилища | Проверить `S3_PUBLIC_ENDPOINT` (`http://localhost:8333`) |
| Отчёт без LLM-резюме | Нет сети, неверный ключ или таймаут | Проверить `LLM_BASE_URL` и `LLM_API_KEY`; `LLM_ENABLED=false` — резюме станет шаблонным |
| Распознавание идёт на CPU, хотя есть карта | Docker не видит GPU | `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`; обновить драйвер NVIDIA; проверить `GET /api/v1/vision/model` |
| Скрипт (`seed.py`, `e2e.py`) пишет `HTTP 401` или не видит сервисы | Скрипт стучится не в тот порт: `GATEWAY_PORT` не в `.env`, а задан только при `docker compose up` | Записать `GATEWAY_PORT` в `.env`; на стенде 8080 занят AdGuard, отвечает он |
| `health.py`: сервис «недоступен», а `docker compose ps` показывает `healthy` | Docker Desktop перестал пробрасывать порт контейнера (было 27.09 с analysis после суток работы; через gateway сервис отвечал) | `docker compose restart <сервис>` |
| `make` пишет `'grep' is not recognized` | Windows: рецепты Makefile исполняет cmd | Команды из правого столбца раздела 3 |
| Повторная загрузка того же файла в `rejected` | Защита от дублей по sha256 | Это не ошибка |

**Куда смотреть в первую очередь:** `request_id` из ответа об ошибке —
`docker compose logs | Select-String <request_id>` (PowerShell) или `| grep <request_id>` (bash)
показывает всю цепочку вызовов через все сервисы.

## 8. Резервное копирование и перенос

- Данные: тома `pgdata` (три базы) и `s3data`. `docker compose down` их сохраняет,
  `docker compose down -v` стирает.
- `scripts/backup.py` не реализован (заготовка, задачи на него нет). Дамп базы вручную,
  по одной на команду (`plandb`, `sitedb`, `analysisdb`):

  ```powershell
  New-Item -ItemType Directory -Force backup   # в .gitignore
  docker compose exec -T postgres pg_dump -U postgres -Fc -f /tmp/plandb.dump plandb
  docker compose cp postgres:/tmp/plandb.dump backup\plandb.dump
  ```

  Снимки и отчёты — бакеты `images` и `reports` в S3; их зеркало скриптом не сделано.
- Перенос к заказчику: те же образы, свой `.env`, свои адреса Postgres и S3.
  Ничего, кроме переменных окружения, менять не требуется.

## 9. Состав docker-compose

Один файл `docker-compose.yml` на весь стек, оверлей `docker-compose.dev.yml` для разработки.
Порядок запуска задаётся через `depends_on: condition: service_healthy`. Файлы
`packages/contracts/*.yaml` монтируются в сервисы только для чтения
(`./packages/contracts:/contracts:ro`).

Состав на 27.09, без `ollama`: профиль `llm` не делается (раздел 5).

| Контейнер | Образ / сборка | Команда | Зависит от | Тома |
| :--- | :--- | :--- | :--- | :--- |
| `postgres` | `postgres:16-alpine` | — | — | `pgdata`, скрипт инициализации трёх баз и ролей |
| `s3` | `chrislusf/seaweedfs` (тег + digest) | `mini -dir=/data` | — | `s3data` |
| `redis` | `redis:7-alpine` | — | — | — |
| `plan-service` | `services/plan-service` | `uvicorn src.main:app` | `postgres` | `contracts` |
| `site-service` | `services/site-service` | `uvicorn src.main:app` | `postgres`, `s3`, `redis` | `contracts` |
| `site-worker` | тот же образ, что `site-service` | `arq src.worker.WorkerSettings` | `redis`, `vision-service` | `contracts` |
| `analysis-service` | `services/analysis-service` | `uvicorn src.main:app` | `postgres`, `s3` | `contracts` |
| `vision-service` | `services/vision-service` | `uvicorn src.main:app` | — | `data/models` → `/models`, `contracts` |
| `gateway` | `services/gateway` | nginx | — | собранная статика `apps/web` |

Особенности:

- `site-service` и `site-worker` — **один образ, разные команды**. Воркеров можно поднять
  несколько: `docker compose up -d --scale site-worker=3`.
- Веса моделей монтируются томом, а не копируются в образ: образ остаётся лёгким, а смена
  модели не требует пересборки.
- У каждого сервиса своя роль и свой DSN, и роль имеет права только на свою базу. Но пароли
  чужих ролей контейнер **видит**: общий якорь `service-base` передаёт всем контейнерам весь
  `.env` (`env_file`). Поэтому граница держится на том, что сервис подключается своим DSN, а не
  на незнании чужого пароля. Это известное расхождение, оно записано в [board.md](board.md),
  раздел 9.

## 10. Публикация и получение образов

Образы собирает и публикует `.github/workflows/release.yml` — **не** демо-ноутбук. Сервисы
конвейер находит сам, по наличию `Dockerfile`; перечислять их нигде не нужно.

```bash
git tag v0.2.0 && git push origin v0.2.0   # релиз по тегу
gh workflow run Release                    # то же самое вручную, без тега
```

Образы уезжают в `ghcr.io/<владелец>/<репозиторий>/<сервис>` с тегами `v0.2.0` и `latest`.
Реестр приватный, поэтому на машине, которая их забирает, нужен вход:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u <логин> --password-stdin
docker compose pull
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --no-build
```

Токену достаточно права `read:packages`. Репетиция 27.09 (`v0.1.0`): `pull` — 9 минут, из них
почти всё — образ vision-service 12,4 ГБ; от `up` до «готовы 5 из 5» — 109 с.

`IMAGE_REGISTRY` и `IMAGE_TAG` в `.env` задают, откуда и какую версию тянуть. Имя образа в
`docker-compose.yml` стоит рядом с `build:`, поэтому собранный локально образ получает то же имя,
что опубликованный.

**Зачем это вообще.** Образ `vision-service` с CUDA весит несколько гигабайт и собирается десятки
минут. За час до показа собирать его на ноутбуке нельзя — только скачать. Поэтому перед
демонстрацией ставится тег, конвейер собирает образы на своих машинах, а на стенде выполняется
`docker compose pull`.
