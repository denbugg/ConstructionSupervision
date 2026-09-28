# Порядок работ

Единственный список задач проекта: что делать, в каком порядке, как понять, что готово.
Рубежи, порядок сокращения объёма и риски — в [roadmap.md](roadmap.md). Правила кода — в
[AGENTS.md](../AGENTS.md).

---

## 1. Протокол для агента: «начинай» / «продолжай»

Если человек назвал конкретную задачу — делай её. Если сказал «начинай», «продолжай» или
«делай дальше» — работай по этому протоколу.

1. **Прочитай** (если ещё не читал в этой сессии) `CLAUDE.md` → `AGENTS.md` →
   `docs/architecture.md` → `packages/contracts/interservice.md`.
2. **Найди задачу:**
   - первая задача со статусом `[~]` — незаконченная, продолжай её с заметки «остановился»;
   - если таких нет — первая `[ ]` сверху, у которой все задачи из «ждёт» закрыты `[x]`;
   - задачи с пометкой **(человек)** не делаешь, а в конце сессии напоминаешь о незакрытых.
3. **Поставь `[~]`** у взятой задачи.
4. **Прочитай всё из «спец»** задачи и README затрагиваемого сервиса.
5. **Сделай задачу** снизу вверх: `core/` с тестами → `dal/` → `services/` → `api/`. Не выходи
   за пределы задачи. Соседний баг, найденный по пути, — запиши строкой в раздел 9, не чини молча.
6. **Проверь** (команды — раздел 2):
   - линт;
   - тесты затронутого сервиса;
   - если менялись контейнеры или compose — стек поднимается и отвечает `/health/ready`.

   Не проходит — чини. После трёх безуспешных подходов остановись и опиши проблему в задаче.
7. **Обнови документы** по DoD из AGENTS.md, раздел 5:
   - README сервиса — если менялись эндпоинты, конфигурация или модель;
   - `docs/traceability.md` — если закрыто требование ТЗ.
8. **Закрой задачу:** поставь `[x]` и допиши в её строку одну фразу — что сделано и где.
9. **Закоммить** код и `board.md` одним коммитом в текущую ветку: `feat(<сервис>): <кратко> (T07)`.
   Добавляй в коммит только свои файлы (`git add <пути>`, не `git add -A`): чужие незакоммиченные
   правки в рабочем дереве не трогай. Не пушь: это решает человек.
10. **Бери следующую задачу** (шаг 2).

**Когда останавливаться и спрашивать человека:**
- доступных задач нет — всё закрыто или ждёт задач человека;
- нужны данные, которых нет в репозитории: снимки, XLSX, нормы, ключи;
- спецификация противоречит сама себе или коду так, что выбор меняет контракт или методику;
- Docker не запущен, а задаче он нужен. В этом случае сначала сделай всё, что возможно без
  Docker (`core/` и unit-тесты);
- контекст на исходе. Закоммить готовое, если проверки зелёные, оставь `[~]` и строку
  «остановился: …; дальше: …».

**Чего не делать:**
- **Не выдумывай данные.** Нормативы, метрики, результаты замеров, праздники, пути к весам —
  только из документов и реальных запусков. Нет данных — пиши «не измерено» или «ждёт H3».
- **Не меняй молча документы-источники** (`architecture.md`, `methodology.md`, `data-model.md`,
  `interservice.md`). Если реализация требует отступить, сначала правка документа или ADR
  отдельным коммитом `docs: …` с объяснением, потом код.
- **Не дроби без записи.** Если задача разрастается больше чем на ~300 строк диффа, раздели её
  здесь же на `T15a`, `T15b` и делай по одной.

## 2. Команды проверки на демо-стенде (Windows, PowerShell)

`make` здесь не работает: рецепты Makefile требуют bash. Используй прямые команды.

```powershell
# окружение хоста — .venv (runbook, раздел 3); глобальный Python не используется
py -3.12 -m venv .venv; .venv\Scripts\python -m pip install -r tools\requirements.txt

# линт (ruff 0.16.8 из .venv)
.venv\Scripts\ruff check --config tools/ruff.toml packages services scripts
.venv\Scripts\ruff format --check --config tools/ruff.toml packages services scripts

# тесты: сервис в одноразовом контейнере его образа, база <база>_test (без имени — все)
.venv\Scripts\python scripts\test.py analysis

# стек (нужен запущенный Docker Desktop)
docker compose up -d --build
docker compose ps
curl.exe -s http://localhost:8001/health/ready
```

API-тесты с базой требуют `TEST_DB_DSN` и поднятый `postgres`. Без базы они пропускаются: это
не ошибка, но и не проверка слоя API.

## 3. Формат записи

```markdown
- [ ] `T07` analysis: календарь и активные этапы
      спец: … · ждёт: T06 · готово, когда: …
```

| Знак | Значение |
| :--- | :--- |
| `[ ]` | не начата |
| `[~]` | в работе или остановлена; ниже строка «остановился: …» |
| `[x]` | закрыта по DoD и закоммичена |
| `[-]` | снята: не делаем в MVP (раздел 8) |

---

## 4. Задачи человека — параллельно, с первого дня

Агент их не делает, но от них зависят его задачи. Чем раньше, тем лучше.

- [x] `H1` **(человек)** Демо-хронология. Неподвижных камер в материалах организаторов нет: там
      фото хода строительства с разных точек ([data/README.md](../data/README.md), «Материалы
      организаторов»). Из `ml/datasets/lct-raw/` (или своих снимков) выбрать один объект.
      Каждую точку съёмки завести отдельной «камерой», снимки разложить в
      `data/seed/images/cam-<код>/YYYYMMDD_HHMMSS.jpg` на 3 «дня» по сценарию
      [runbook.md](runbook.md), раздел 6, плюс «нормальный день». Зоны разметить на каждой точке
      (LabelMe или CVAT, метка `ТИП:Название`). Если сценарий не собирается из кадров — поправить
      сценарий, а не кадры. · нужно к: 25.09 · блокирует T27
      остановился (26.09): кадры организаторов отвергнуты, демо строится на датасете Лимы —
      агент собрал хронологию (`data/seed/chronology.json`, `scripts/seed_images.py`: камеры
      `cam-torre-h` и `cam-d3`, 19–22.10.2026), объект и график; за человеком — зоны на
      эталонных кадрах в редакторе зон (T40 готов: `/objects/<id>/settings/zones`), затем
      `python scripts/export_zones.py` и правка сценария §6 по результату прогона
      26.09: зоны размечены (пятно застройки на обеих камерах) и выгружены. Котлована на кадрах
      нет, поэтому график подогнан под надземную часть: засыпка 12.3.10 до демо, новый этап
      12.4.10 «Бетонирование колонн и перекрытий» 21–23.10 с правилом из `rules.json`; агент
      добавил «Въезд» (дорога справа на Torre H) и «Склад» (D3). На чистом объекте: 19.10 без
      D2; 20.10 D3 и D4 на погрузчик; 21.10 D1 утром, D2 после прихода миксеров без насоса,
      D10 на склад (камера D3 закрыта); 22.10 полный комплект.
      закрыто 26.09: ложные D4 на кране и насосе сняты признаком `works_in_place`, фантомы
      ленты — удалением пересмотренных эпизодов (раздел 9); «Въезд» с вырезом под точку крана;
      runbook §6 переписан под каркас, шаг «правка правила» проверен через API. Три объекта
      стенда (свежий, проверочный, демо) дают одну и ту же ленту из 7 строк
- [x] `H2` XLSX справочника работ лежит в `data/reference/`, его устройство описано в
      [data/README.md](../data/README.md). 23.09
- [x] `H3` **(человек)** МРР-3.2.81 последней редакции → `data/reference/`: таблицы сроков для
      жилого монолитного дома с номерами пунктов. · нужно к: 25.09 · блокирует T21 — сделано
      агентом по поручению 23.09: `data/reference/МРР-3.2.81-12.htm`, полный текст со страницы,
      указанной в ТЗ (meganorm.ru); редакции новее -12 не найдено. Жилые здания — п. 5.1,
      табл. 1 (п. 5.1.21)
- [ ] `H4` **(человек)** LLM: провайдер, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` в `.env`;
      проверить доступ с демо-машины. · нужно к: 26.09 · для T35
      26.09: платного API не будет (решение человека). Для T35 разрешена локальная модель:
      llama.cpp на хосте, `gemma-4-E4B-it-Q4_K_M.gguf` из `D:\LMStudio\models\…` через
      OpenAI-совместимый `llama-server`; клиент не привязан к провайдеру (GigaChat, YandexGPT)
- [ ] `H5` **(человек)** Тестовый набор CV: разметить рамки техники на 100 снимках организаторов
      из `ml/datasets/lct-raw/` (лето, зима, разные стадии) в CVAT или LabelMe →
      `ml/datasets/lct-test/`. Классы — коды из `equipment_classes.yaml`. · нужно к: 27.09 · блокирует T36
      26.09, по поручению: агент сделал авторазметку — YOLOE-26m находит рамки, Gemma 4 E4B со
      зрением называет класс (`ml/prepare/detect_open_vocab.py`, `prelabel.py`), 563 рамки на
      100 снимках в `ml/datasets/lct-test/review/`. За человеком — проверка в LabelMe с флажком
      «проверено» (ml/README.md, «Разметка тестового набора»), затем агент: `lct_test.py` → T36
- [ ] `H6` **(человек)** Запустить Docker Desktop, проверить GPU:
      `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`. · нужно к: 24.09
- [ ] `H7` **(человек)** Презентация (слайды 7–11 шаблона без изменения дизайна), видео демо,
      документация .docx/.pdf, загрузка на платформу до 20:00 29.09.

## 5. Сделано ранее

- [x] `A-01` plan-service: каркас, схема `plandb`, миграция `0001`
- [x] `A-02` plan-service: CRUD объектов
- [x] `B-01` site-service: каркас, схема `sitedb`, миграция `0001`
- [x] `C-02` analysis-service: каркас, схема `analysisdb`, миграция `0001`
- [x] `D-01` docker compose, gateway, `.env.example`, Makefile
- [x] `D-02` CI: линт, тесты по сервисам, сборка образов, сверка снапшота OpenAPI, шаблон PR
- [x] vision-service: каркас в compose; web: каркас SPA, сборка в образ gateway
- [x] Документы переписаны под целевую схему (ADR-0011…0014, контракты, методика), 23.09
- [x] Материалы организаторов разложены: README кейса — `docs/official-readme.md`, справочник
      работ и ссылки на датасеты — `data/reference/`, 100 снимков — `ml/datasets/lct-raw/`
      (вне git), 23.09

---

## 6. Задачи по порядку

### R0. Выравнивание кода с документами — 23.09

- [x] `T01` infra: убрать pos-engine и report-service, смонтировать справочные файлы — сделано:
      Makefile, gateway (неизвестный `/api/…` → 404 в конверте ошибки), `.env.example`, том
      `/contracts:ro`; попутно для подъёма стека: MinIO с quay.io, `GATEWAY_PORT`, `.gitattributes`
      (LF для `*.sh`), healthcheck gateway на 127.0.0.1
      спец: [architecture.md](architecture.md) §3, [runbook.md](runbook.md) §4 и §9 · ждёт: —
      что: `Makefile` (`SERVICES`, `NAME_*`, `PORT_*` без pos и report); `services/gateway/nginx.conf`
      и `swagger/index.html` без pos и report; `.env.example` без `POS_URL`, `REPORT_URL`,
      `S3_BUCKET_PREVIEWS`, `SESSION_CLOSE_GRACE_MINUTES`, с `S3_PUBLIC_ENDPOINT`, `CONTRACTS_DIR` и
      переменными методики из runbook §4; том `./packages/contracts:/contracts:ro` у plan, site,
      analysis и vision в `docker-compose.yml`
      готово, когда: `docker compose config` без ошибок; стек поднимается; `/api/v1/pos/…` → 404
- [x] `T02` scripts: скрипты на Python — сделано: `scripts/health.py`, `scripts/fetch_models.py`
      (sha256 обоих файлов сверены, OpenCLIP — с Hugging Face), `_common.py`, заготовки остальных;
      Makefile вызывает `python scripts/…`, `*.sh` удалены
      спец: [scripts/README.md](../scripts/README.md) · ждёт: T01
      что: `health.py` и `fetch_models.py` — полностью (YOLO-World `yolov8s-worldv2` и OpenCLIP
      в `data/models/`); `seed.py`, `demo.py`, `e2e.py`, `contracts.py`, `backup.py`,
      `labelme_to_zones.py` — заготовки, которые печатают «не реализовано, задача Txx» и
      возвращают 1; цели Makefile вызывают `python scripts/…`; `*.sh` и `_not_implemented.sh` удалить
      готово, когда: `python scripts/health.py` печатает сводку по поднятым сервисам
- [x] `T03` plan-service: убрать клиент pos-engine, схема по data-model §1 — сделано:
      `dal/models.py` и миграция `0001` по data-model §1, `plan_version` в API объекта,
      pos-engine удалён из клиентов, конфига и health; 21 тест зелёный в контейнере
      спец: [data-model.md](data-model.md) §1, [ADR-0011](decisions/0011-generator-and-reports-as-modules.md) · ждёт: —
      что: удалить `clients/pos_client.py`, `pos_url`, проверку pos в health, `PosDep`, упоминания
      в комментариях; `object.current_revision` → `plan_version`; `work_calendar.timezone`;
      `stage`: + `visual_stage`, `basis`, − `free_float_days`, `shifts_per_day`, `regulatory_basis`,
      источники `GENERATED/IMPORT/MANUAL`; `stage_rule`: без `zone_type`, `stage_id` уникален,
      `required` — список групп, `signature` — объект; удалить таблицы `equipment_class` и
      `plan_revision`. Миграцию `0001` править на месте: реальных данных нет, после правки
      локально `docker compose down -v`
      готово, когда: тесты plan-service зелёные, включая тест миграций (если есть база)
- [x] `T04` site-service: схема по data-model §2 — сделано: `dal/models.py` и миграция `0001`;
      видимость и факты окна по участку `ТИП:Название`, `session_fact.count > 0`; тесты зелёные
      в контейнере, стек отвечает `/health/ready`
      спец: [data-model.md](data-model.md) §2, [ADR-0012](decisions/0012-facts-without-judgement.md), [ADR-0013](decisions/0013-zones-and-areas.md) · ждёт: —
      что: `camera.reference_image_id`; `zone` без `overlaps_with`; `image.usable`,
      `usable_reason`, без `thumb_key`; `session` без `is_working_time` и `status`, + `stage_label`,
      `stage_conf`, `stage_scores`; `detection`: + `camera_id`, `moved`, `displacement`,
      − `state`, `state_reason`; `stage_observation` без `floors_estimate`;
      `zone_visibility` → `area_visibility`; `session_fact` по `area` со `static`.
      Миграцию `0001` править на месте
      готово, когда: тесты site-service зелёные
- [x] `T05` analysis-service: схема по data-model §3 — сделано: `dal/models.py` и миграция
      `0001`; тест `tests/migrations/test_deviation_key.py` проверяет ключ открытого отклонения
      с `NULLS NOT DISTINCT`; начало и конец прогона — `created_at`/`updated_at`
      спец: [data-model.md](data-model.md) §3 · ждёт: —
      что: `analysis_run` (`as_of`, триггеры `FACTS_UPDATED/PLAN_CHANGED/MANUAL`, `plan_version`,
      `zones_version`, `rerun_requested`, `error`, без `period_*` и `rules_version`); `deviation`
      (`area`, `equipment_class`, `verdict_*`, уникальный индекс по
      `(object_id, stage_id, area, code, equipment_class)` с `NULLS NOT DISTINCT`);
      `stage_fact.facts`; `daily_activity.object_id`; новая `daily_equipment`; `object_status`
      (`as_of`, `confidence`, `stages_at_risk`); удалить `deviation_feedback`. Миграцию `0001`
      править на месте
      готово, когда: тесты analysis-service зелёные
- [x] `T06` analysis: входные модели контрактов, фикстуры демо-дней, чтение enums — сделано:
      `core/inputs.py`, `core/enums.py` (+ `pyyaml`, `CONTRACTS_DIR` в конфиге),
      `tests/factories.py`; факты демо-дней собирает `tests/fixtures/build_fixtures.py`
      (окна 06:00–12:00 UTC), тесты сверяют сценарий дней и значения с `enums.yaml`
      спец: [interservice.md](../packages/contracts/interservice.md) §1–2, [methodology.md](methodology.md), [runbook.md](runbook.md) §6 · ждёт: —
      что: `src/core/inputs.py` — Pydantic-модели «весь план» и «факты за период»
      (`extra="ignore"`); `src/core/enums.py` — чтение `enums.yaml` из `CONTRACTS_DIR` (роли
      типов зон, порядок стадий). `tests/fixtures/`:
      - `plan.json` — пример из interservice §1 с полными UUID;
      - `facts_normal_day.json` (2026-10-19): экскаватор работает, самосвалы видны раз в 2 часа,
        по два за раз → без D2;
      - `facts_day1.json` (2026-10-20): экскаватор в котловане, самосвалов нет весь день → D2;
      - `facts_day2.json` (2026-10-21): появился бетононасос → D3 по будущему этапу «Фундаментная плита»;
      - `facts_day3.json` (2026-10-22): экскаватор неподвижно на въезде, его видит обзорная
        `cam-north` → D4; камера въезда `cam-gate` тёмная весь день → участок «Склад»,
        размеченный только на ней, `BLIND` → D10, а въезд остаётся `PARTIAL` за счёт обзорной камеры.

      Участки — как в примере `data/README.md`: котлован (`cam-north`), въезд (`cam-north` и
      `cam-gate`), склад (только `cam-gate`).

      Окна — рабочие часы 04:00–20:00 UTC (07:00–23:00 МСК), не обязательно каждое.
      Плюс `tests/factories.py`
      готово, когда: все фикстуры разбираются моделями; тест сверяет роли зон с `enums.yaml`

### R1. Методика на фикстурах — 24.09

Всё в `services/analysis-service/src/core/`, чистые функции с unit-тестами.

- [x] `T07` analysis: календарь, рабочие сессии, активные этапы — сделано: `core/calendar.py`
      (рабочая сессия целиком в рабочих часах местного дня, `working_days_between` со знаком
      и обратная ей `add_working_days`), `core/plan_on_date.py`; тесты в `tests/unit/`
      спец: [methodology.md](methodology.md) §2, §8 · ждёт: T06
      что: `core/calendar.py` (рабочие дни, `add/count_working_days`, рабочая сессия по
      `timezone` и `work_hours`); `core/plan_on_date.py` (активные этапы на местную дату, плановая
      визуальная стадия). Даты этапов включительно
      готово, когда: тесты на границы дня, выходные, праздник 4 ноября, окно на границе рабочих часов
- [x] `T08` analysis: проверка правила этапа — сделано: `core/rules.py` (`check_rule` →
      группы с числами и доказательствами, `complete` / `partial` / `nothing_required`,
      сигнатура; окно транзитной техники по времени), параметры в `config.py`, допущения в
      README
      спец: [methodology.md](methodology.md) §5 · ждёт: T07
      что: `core/rules.py` — группы `any_of/min`, транзитное окно `TRANSIENT_WINDOW_SESSIONS`,
      `allowed`, сигнатура с `stage_label`, учёт только видимых участков типа этапа
      готово, когда: тесты, включая «нормальный день» — группа самосвалов выполнена через окно
- [x] `T09` analysis: статус техники — сделано: `core/equipment_state.py` (`equipment_states`
      по таблице §6 с обоснованием строкой; `person`, опасные и слепые участки статуса не
      получают); тест на каждую строку таблицы
      спец: [methodology.md](methodology.md) §6 · ждёт: T08
      что: `core/equipment_state.py` по таблице §6 с обоснованием статуса строкой
      готово, когда: тест на каждую строку таблицы для транзитного и нетранзитного класса и для `person`
- [x] `T10` analysis: реестр предикатов, D1, D2, объяснение — сделано: `core/predicates.py`
      (контекст только из рабочих сессий, серии, эскалация, реестр, D1, D2), `core/explain.py`,
      `data/deviation_rules.yaml` с десятью кодами, миграция `0002` (`title_template`);
      контракт дополнен `cameras[].image_ids` для доказательств D1
      спец: [methodology.md](methodology.md) §9, §12 · ждёт: T09
      что: `core/predicates.py` (реестр, ключ отклонения); D1, D2;
      `data/deviation_rules.yaml` — все десять кодов (предикат, серьёзность, `params`, шаблон);
      `core/explain.py` — текст из шаблона и `facts`
      готово, когда: тесты «срабатывает / не срабатывает / граница»; инварианты: без `facts` и
      `evidence` нет отклонения, по слепому участку ничего, кроме D10, вне рабочего времени ничего
- [x] `T11` analysis: D3, D4, D5, D6 — сделано: `core/equipment_predicates.py` (ключ
      «участок × класс», серии по `params.min_sessions`, D3 «возможное опережение» с ключом
      будущего этапа через `params.variants` в `deviation_rules.yaml`), тесты в
      `tests/unit/test_equipment_predicates.py`; допущения — в README сервиса
      спец: [methodology.md](methodology.md) §6, §9 · ждёт: T10
      готово, когда: день 2 → D3 с ключом будущего этапа; день 3 → D4; транзитные классы не дают D4 и D5
- [x] `T12` analysis: фактический старт, активность, загрузка техники, D8, D9, D10 — сделано:
      `core/activity.py` (старт, индекс активности, загрузка техники), `core/context.py`
      (контекст прогона вынесен из реестра, добавлен `as_of`), D8 в `core/predicates.py`,
      D9 и D10 в `core/stage_predicates.py`; «по въезду» ниже — опечатка: въезд `PARTIAL`,
      D10 дня 3 — по складу (как в T06 и T14); D10 без снимков при `NO_IMAGES` — правка
      methodology §12 отдельным коммитом
      спец: [methodology.md](methodology.md) §7, §9, §10.1–10.2 · ждёт: T10
      что: `core/activity.py` — фактический старт по сигнатуре, индекс активности по дням,
      агрегат «загрузка техники по дням»; предикаты D8, D9, D10 (участок и этап без участка)
      готово, когда: день 3 → D10 по въезду; тесты D8 и D9 на синтетике
- [x] `T13` analysis: прогресс, SPI, прогноз, статус объекта, D7 — сделано:
      `core/forecast.py` (прогресс с ограничением по стадии, SPI, прогноз по темпу, перенос
      по FS/SS/FF/SF, `stages_at_risk`, статус и уверенность объекта), D7 в
      `core/stage_predicates.py`; пороги уверенности вынесены в окружение (правка
      methodology §11 отдельным коммитом)
      спец: [methodology.md](methodology.md) §8, §10 · ждёт: T12
      что: `core/forecast.py` — прогресс с ограничением по стадии, плановый прогресс на `as_of`,
      SPI, прогноз, перенос по связям, `stages_at_risk`, статус объекта, `confidence`; D7
      готово, когда: тесты на деление на ноль, полный простой (`MIN_ACTIVITY`), `as_of` в прошлом,
      нехватку данных (`UNKNOWN`)
- [x] `T14` analysis: прогон целиком как чистая функция — сделано: `core/run.py`
      (`analyze` → отклонения с текстами, факт этапов, активность, загрузка техники, статус,
      счётчики), тесты `tests/unit/test_run.py`; на четырёх демо-днях подряд объект `DELAY`
      +14 рабочих дней, уверенность MEDIUM. Рубеж R1 пройден
      спец: [analysis-service README](../services/analysis-service/README.md) §4 · ждёт: T11, T12, T13
      что: `core/run.py` — `analyze(plan, facts, as_of, rules) -> AnalysisResult`
      готово, когда: на фикстурах: день 1 → D2, день 2 → D3, день 3 → D4 и D10,
      нормальный день → ни одного D2; повторный вызов даёт тот же результат. **Рубеж R1.**

### R2. Сервисы и сквозной прогон — 25–26.09

- [x] `T15a` analysis: прогон как сервис — сделано: клиенты `src/clients/`, сценарий
      `src/services/runs.py`, сверка ленты `core/ledger.py`, репозитории `dal/repositories/`,
      `POST /runs` и `GET /runs/{id}`, миграция `0003`, `timestamptz` в моделях; 14 api-тестов
      на базе `analysisdb_test`; в стеке правила D1–D10 заполняются при старте. Живой прогон ждёт
      `GET /plan` из T19
      спец: [interservice.md](../packages/contracts/interservice.md) §4, [analysis-service README](../services/analysis-service/README.md) §4 · ждёт: T05, T14
      что: клиенты plan и site (py-common http: 10 с, 2 повтора); `POST /runs` с `?wait=true`
      и фоновым запуском без него; `GET /runs/{id}`; запись результатов (UPSERT по ключу,
      `RESOLVED`); заполнение `deviation_rule` из YAML при первом старте; миграция `0003`
      (`activity_index` nullable)
      готово, когда: api-тесты с клиентами-заглушками на фикстурах; повтор не создаёт дублей
- [x] `T15b` analysis: схлопывание сигналов прогона — сделано: advisory-блокировка объекта,
      `rerun_requested` с атомарным снятием и одним повтором (`services/runs.py`), брошенный
      прогон → `RUN_ABANDONED`, `wait=true` ждёт чужой прогон; 6 api-тестов
      `tests/api/test_run_coalescing.py`
      спец: [interservice.md](../packages/contracts/interservice.md) §4 · ждёт: T15a
      что: на объект один прогон; сигнал во время прогона — `rerun_requested` и ответ
      `coalesced: true` с номером текущего; по окончании ровно один новый прогон
      готово, когда: api-тест: два сигнала подряд → один прогон + один повтор
- [x] `T16a` analysis: статус, прогресс, загрузка техники, настройки правил — сделано:
      роуты `objects.py`, `rules.py`, сценарии `services/results.py`, `services/rules.py`,
      проверка настройки `validate_rule` в `core/explain.py`; `X-Actor` в URL-кодировке
      (api-guidelines §6); 15 api-тестов `test_results.py`, `test_deviation_rules.py`
      спец: [analysis-service README](../services/analysis-service/README.md) §3 · ждёт: T15
      что: `/objects/{id}/status`, `/progress`, `/equipment`; `GET /deviation-rules`,
      `GET/PATCH /deviation-rules/{code}` с проверкой порогов и шаблонов
      готово, когда: api-тест на каждый эндпоинт
- [x] `T16b` analysis: лента отклонений, карточка, объяснение, вердикт — сделано: роут
      `deviations.py`, сценарий `services/deviations.py`, репозиторий с фильтрами и сортировкой
      по порядку серьёзностей из `enums.yaml`; `/explain` с сессиями эпизода от site-service и
      честным `null` без него; 15 api-тестов `tests/api/test_deviations.py`
      спец: [analysis-service README](../services/analysis-service/README.md) §3, [methodology.md](methodology.md) §9, §12 · ждёт: T16a
      что: `/deviations` с фильтрами и пагинацией; `/deviations/{id}`, `/explain`;
      `PATCH /deviations/{id}` (вердикт, `X-Actor`)
      готово, когда: api-тест на каждый эндпоинт
- [x] `T17` plan: справочные файлы и классы техники — сделано: `core/reference.py` (разбор и
      проверка файлов), `src/reference.py` (чтение при старте), `GET /equipment-classes`,
      `check_equipment_codes` → `UNKNOWN_EQUIPMENT_CLASS` для T18; `StrEnum` в схемах заменены
      `Literal` из `enums.yaml`; в контейнере 15 классов, как в файле
      спец: [ADR-0014](decisions/0014-equipment-classes-file.md), [plan-service README](../services/plan-service/README.md) · ждёт: T01, T03
      что: чтение `equipment_classes.yaml` и `enums.yaml` из `CONTRACTS_DIR`;
      `GET /equipment-classes`; проверка кодов классов (`UNKNOWN_EQUIPMENT_CLASS`)
      готово, когда: тесты; в контейнере список классов совпадает с файлом
- [x] `T18a` plan: календари, этапы, сигнал «пересчитай» — сделано: миграция `0002`
      (праздники `moscow-6day` по ТК РФ ст. 112 ч. 1 на 2026–2028, объектам — календарь по
      умолчанию), `/calendars` с проверкой `core/calendar.py`, `GET /objects/{id}/stages` и
      `PATCH /stages/{id}` с проверкой `core/stages.py`, рост `plan_version` и сигнал после
      commit (`services/plan_version.py`, `clients/analysis_client.py`: 2 с, без повторов)
      спец: [plan-service README](../services/plan-service/README.md) §3 · ждёт: T17
      что: календарь `moscow-6day` (часовой пояс `Europe/Moscow`, выходной `[7]`, праздники
      только с источником, для 2026 минимум 4 ноября); `GET /objects/{id}/stages`,
      `PATCH /stages/{id}`; рост `plan_version`; клиент сигнала в analysis (2 с, без повторов,
      ошибки — в лог)
      готово, когда: api-тесты; правка этапа и календаря увеличивает `plan_version` и шлёт сигнал
- [x] `T18b` plan: правила «этап → техника» — сделано: `/rules` (список с фильтрами, создание,
      правка, удаление), проверка формы `core/stage_rules.py` и кодов по
      `equipment_classes.yaml`, версия правила растёт в SQL, `plan_version` и сигнал через
      `services/plan_version.py`; правило в ответе этапов; `X-Actor` в журнал
      спец: [plan-service README](../services/plan-service/README.md) §3, [interservice.md](../packages/contracts/interservice.md) §1 · ждёт: T18a
      что: CRUD `/rules` в новом формате (группы `any_of`/`min`, `allowed`, `signature`,
      `min_sessions`), коды классов — `check_equipment_codes`; версия правила и `plan_version`
      растут; правило в ответе `GET /objects/{id}/stages`
      готово, когда: api-тесты; правка правила увеличивает `plan_version` и шлёт сигнал (заглушка)
- [x] `T19a` plan: «весь план» и критический путь — сделано: `core/cpm.py` (обратный проход
      по номерам рабочих дней, FS/SS/FF/SF с лагом, отрицательный резерв при нарушенных
      связях), `GET /objects/{id}/plan` по контракту 1 (выключенное правило — `rule: null`),
      пересчёт резервов после правки дат этапа и календаря (`services/critical_path.py`)
      спец: [interservice.md](../packages/contracts/interservice.md) §1 · ждёт: T18
      что: `GET /objects/{id}/plan` строго по контракту (календарь объекта — `calendar_id`);
      `core/cpm.py`; `PATCH /stages/{id}` после правки дат пересчитывает критический путь;
      правило с `is_active: false` — решить и записать в README
      готово, когда: api-тест сверяет форму `/plan` с контрактом; unit-тесты CPM
- [x] `T19b` plan: шаблон этапов жилого монолита и импорт графика — сделано:
      `data/wbs_templates.json` (12 этапов по ТЗ §5.2, проверка при старте `core/templates.py`),
      `core/plan_import.py` (CSV/XLSX, шаблон заполняет недостающее, ошибки всех строк с
      номерами, код из даты Excel), `POST /objects/{id}/plan/import` с `force`; демо-график
      `tests/fixtures/demo_schedule.csv` даёт `/plan` со значениями фикстуры T06; в стеке
      analysis забирает импортированный план (прогон падает на фактах site — ждёт T26)
      спец: [ТЗ §3, §5.2](<ТЗ Мониторинг строительной площадки по снимкам камер (ЛЦТ 2026, кейс 07).md>) · ждёт: T19a
      что: `POST /objects/{id}/plan/import` (CSV/XLSX: код, наименование, начало, окончание;
      необязательно тип участка, визуальная стадия, связи); проверка дат и циклов.
      `data/wbs_templates.json`: этапы жилого монолита с типом участка, визуальной стадией,
      связями и правилами по таблице ТЗ §5.2, включая группы «любой из». Доли фаз пока
      `null` — их заполнит T21
      готово, когда: ответ `/plan` на демо-графике совпадает по форме с `tests/fixtures/plan.json`
      из T06; импорт с ошибкой возвращает номер строки
- [x] `T20` plan: парсер справочника работ — сделано: `core/reference_import.py` (коды из
      дат и чисел, точка в конце, строки без кода — `<родитель>/<n>` 4-го уровня, отметки по
      столбцам шапки, ошибки всех строк), `POST /work-types/import` (замена целиком),
      `GET /work-types` в порядке файла; на настоящем файле 377 строк, 250 без кода, 19 кодов
      восстановлены — тестом и в стеке
      спец: [plan-service README](../services/plan-service/README.md) §4 · ждёт: T03
      что: `core/reference_import.py` по описанию файла в [data/README.md](../data/README.md):
      коды из дат Excel (`d.m.2025` → `d.m`), код-число, точка в конце кода, строки без кода,
      отметка `˅` в девяти столбцах типов объектов; `POST /work-types/import`, `GET /work-types`
      готово, когда: unit-тесты на крайних случаях; на настоящем файле из `data/reference/`
      разобраны все 377 строк данных, 19 испорченных кодов восстановлены
- [x] `T21a` plan: нормы МРР и генератор графика как чистая функция · **режется первым** —
      сделано: `data/mrr_norms.json` (32 строки табл. 1, тест сверяет каждое число с HTML МРР),
      `core/mrr_norms.py`, `core/schedule_generator.py`, доли и `piles` в шаблоне; демо-объект —
      12 этапов с 21.09.2026 по 19.06.2027, у каждой `basis` со ссылкой на пункт; месяцы МРР
      откладываются по обычному календарю (`add_months`). Кст = 1,1 для монолита в МРР есть
      только у школ и больниц, жильё считается без поправки (README §4); московских норм
      свежее МРР-3.2.81-12 поиск 24.09 не нашёл
      спец: [plan-service README](../services/plan-service/README.md) §4 · ждёт: T19, H3
      что: `data/mrr_norms.json` (табл. 1 п. 5.1.21, интерполяция и экстраполяция п. 4.9 и
      5.1.3–5.1.4, сменность п. 4.10, сваи п. 5.1.6; у каждого числа `source`), доли этапов в
      `wbs_templates.json`, `core/schedule_generator.py` (фазы → этапы → даты по календарю)
      готово, когда: unit-тесты: 17 этажей, 10 000 м² → 8,7 мес. = 1,0 + 1,5 + 4,7 + 1,5 (ТЗ §8);
      интерполяция, экстраполяция и её пределы, сменность, сваи; ни одного числа без источника
- [x] `T21b` plan: `POST /objects/{id}/plan/generate` · **режется первым** — сделано:
      `services/plan_generate.py`, запись графика вынесена из импорта в
      `services/plan_writer.py`, нормы сверяются с шаблоном при старте
      (`check_generator_template`), коды `NORMS_NOT_AVAILABLE` и `GENERATOR_PARAMS_INVALID`;
      5 api-тестов; в стеке демо-объект — 12 этапов, 21.09.2026–21.06.2027 по `moscow-6day`
      спец: [plan-service README](../services/plan-service/README.md) §4 · ждёт: T21a
      что: сценарий и роут (`force`, `NORMS_NOT_AVAILABLE`), запись этапов и правил как при
      импорте, критический путь, `plan_version` и сигнал; README
      готово, когда: api-тест; график демо-объекта строится в стеке
- [x] `T22a` site: привязка к зонам как чистая функция — сделано: `core/zones.py`
      (точка контакта, основная зона — наименьшая не опасная, опасные поверх по роли `SAFETY`,
      граница — внутри, `check_polygon`), `core/reference.py` (типы и роли зон из `enums.yaml`),
      `shapely` и `pyyaml` в зависимостях; 18 unit-тестов; тестовая база `sitedb_test`
      спец: [methodology.md](methodology.md) §3, [ADR-0013](decisions/0013-zones-and-areas.md) · ждёт: T01, T04
      что: `core/zones.py` (точка контакта, основная зона, опасные поверх, ключ участка,
      проверка полигона; `shapely`); `core/reference.py` — типы зон и их роли из `enums.yaml`
      готово, когда: unit-тесты: граница, перекрытие, опасная зона поверх рабочей, вне зон
- [x] `T22b` site: API камер и зон — сделано: `/cameras`, `/zones` (CRUD, деактивация с
      ростом версии), `POST /zones/import` (сверка по коду камеры и подписи участка,
      повтор ничего не меняет, ошибки полигонов с путём), `GET /objects/{id}/areas` с
      `zones_version`; названия типов зон — `zone_type_name` в `enums.yaml` (отдельный коммит);
      7 api-тестов, демо-разметка даёт въезд на `cam-north` и `cam-gate`
      спец: [site-service README](../services/site-service/README.md) §3 · ждёт: T22a
      что: CRUD `/cameras` и `/zones`; `POST /zones/import` из формата `data/seed/cameras.json`;
      `zones_version`
      готово, когда: api-тесты; импорт демо-камер из data/README.md даёт участки въезда на двух камерах
- [x] `T23a` site: время снимка, метаданные кадра, окно сессии — чистые функции — сделано:
      `core/timestamp.py` (проверка правдоподобия, смещение EXIF главнее пояса камеры),
      `core/image_meta.py` (формат по содержимому, EXIF из Exif IFD), `core/sessions.py`,
      `CAMERA_TIMEZONE`, `timestamptz` в моделях site; 23 unit-теста
      спец: [site-service README](../services/site-service/README.md) §4 · ждёт: T22
      что: `core/timestamp.py` (EXIF → имя файла → поле формы → `NEEDS_TIME`; наивное время —
      в `CAMERA_TIMEZONE`), `core/image_meta.py` (размер, EXIF, формат; Pillow),
      `core/sessions.py` (окно 30 мин по :00 и :30 UTC); `timestamptz` в моделях (раздел 9)
      готово, когда: unit-тесты времени, включая нестандартные имена файлов и EXIF со смещением
- [x] `T23b` site: загрузка снимков в MinIO — сделано: `clients/storage.py` (клиент `minio`
      в пуле потоков, подпись ссылок на публичный адрес), `services/images.py` (точка
      сохранения на файл, дедуп по sha256, камера из подпапки, окно и счётчики, эталонный
      кадр), `POST /images`, `POST /images/import` (`./data/seed/images` → `/import`), MinIO в
      `/health/ready`; 7 api-тестов; на живом MinIO запись и обе ссылки отвечают 200.
      Верхняя граница времени из T23a снята: она отбрасывала демо-даты графика
      спец: [api-guidelines.md](api-guidelines.md) §7, §8 · ждёт: T23a
      что: `POST /images` (до 200 файлов, частичный успех `202`) и `/images/import` (камера из
      подпапки, заводится автоматически, первый снимок — эталонный кадр); sha256; MinIO;
      привязка к окну; MinIO в `/health/ready`
      готово, когда: api-тест частичного успеха пакета
- [x] `T23c` site: список, карточка снимка, ручное время — сделано: `services/image_catalog.py`,
      `GET /images` (фильтры, без времени — в конце), `GET /images/{id}` (ссылка на публичный
      MinIO, рамки, стадия), `PATCH /images/{id}` (только `NEEDS_TIME` → окно и `PENDING`);
      3 api-теста, в стеке роуты отвечают через gateway
      ждёт: T23b
      что: `GET /images`, `GET /images/{id}` со ссылкой на `S3_PUBLIC_ENDPOINT`;
      `PATCH /images/{id}` для `NEEDS_TIME`
      готово, когда: api-тесты
- [x] `T24` vision: распознавание — сделано: `POST /analyze` (JSON-ссылка или файл) и
      `GET /model`; `core/` — словарь, склейка рамок, качество кадра, стадия; адаптеры моделей в
      `src/models/`, фоновая загрузка с прогревом; образ torch cu128 (сборка 26 мин, CPU-вариант —
      аргументом `VISION_TORCH_INDEX_URL`), GPU — оверлей `docker-compose.gpu.yml`; веса CLIP для
      промптов в `fetch_models.py`, контейнер работает без сети; 63 теста. На 100 снимках
      lct-raw: GPU медиана 56 мс, CPU (960) — 900 мс (README vision §8)
      спец: [interservice.md](../packages/contracts/interservice.md) §3, [vision-service README](../services/vision-service/README.md) · ждёт: T01
      что: `POST /analyze` (YOLO-World с промптами из `equipment_classes.yaml`; OpenCLIP с
      метками из `data/stage_prompts.yaml`; яркость и размытость), `GET /model`, устройство по
      `VISION_DEVICE`, веса из `/models`; образ с torch — если сборка CUDA-образа идёт дольше
      20 минут, сначала CPU-вариант
      готово, когда: тесты постобработки на модели-заглушке; снимки из `ml/datasets/lct-raw/`
      распознаются в контейнере; время на снимок (CPU, GPU при H6) записано в README vision, §8
- [x] `T25a` site: смещение и факт окна как чистые функции — сделано: `core/movement.py`
      (ближайшая рамка класса, смещение в долях диагонали с пропорциями кадра),
      `core/aggregation.py` (`frame_usability`, `aggregate_window`: максимум по кадрам и
      камерам, `static`, опасные зоны поверх, видимость с причиной, стадия за окно); 26 тестов
      спец: [methodology.md](methodology.md) §4, [site-service README](../services/site-service/README.md) §4 · ждёт: T23, T24
      что: `core/movement.py` (смещение относительно прошлого окна камеры);
      `core/aggregation.py` (пригодность кадра, максимум по камерам, `static`, видимость
      участков, `OUTSIDE`, опасные зоны поверх, стадия за окно)
      готово, когда: unit-тесты: максимум по камерам, непригодный кадр, `OK` / `PARTIAL` /
      `BLIND`, нет прошлого окна
- [x] `T25b` site-worker: конвейер распознавания — сделано: `src/worker.py` (arq, задача
      `analyze_image` и проход по базе каждые 30 с), `services/recognition.py` (захват снимка
      одним UPDATE, vision с тремя попытками → иначе снова `PENDING`, отказ → `FAILED`, замок на
      окно), `services/window_facts.py`, клиенты vision, analysis и очереди; постановка в
      очередь после ответа; контейнер `site-worker`; 8 тестов конвейера на базе. В стеке:
      снимок `ANALYZED` за ~1 с, факт окна и видимость записаны, остановка vision переживается
      спец: [site-service README](../services/site-service/README.md) §4, [interservice.md](../packages/contracts/interservice.md) §3, §4 · ждёт: T25a
      что: `src/worker.py` (arq), задача `analyze_image`; клиент vision (30 с, 2 повтора);
      запись детекций, стадии, пересчёт факта окна; сигнал в analysis; постановка в очередь
      при загрузке; контейнер `site-worker` в compose
      готово, когда: загруженный снимок доходит до `ANALYZED`, факт окна появляется
- [x] `T26a` site: «факты за период» и окна — сделано: `GET /objects/{id}/facts`
      (`services/facts.py` собирает материализованный факт окон одной выборкой на таблицу,
      камеры окна — `camera_states` в `core/aggregation.py`), `GET /sessions`,
      `GET /sessions/{id}`; 6 api-тестов `tests/api/test_facts.py`; живой ответ в стеке
      разбирается моделью `Facts` analysis, прогон анализа доходит до `DONE`
      спец: [interservice.md](../packages/contracts/interservice.md) §2 · ждёт: T25
      что: `GET /objects/{id}/facts` строго по контракту, включая `cameras[].image_ids`
      (добавлено 23.09 для доказательств D1); `/sessions`, `/sessions/{id}`
      готово, когда: ответ совпадает по форме с фикстурами T06 (разбирается моделью analysis)
- [x] `T26b` site: пересчёт фактов после правки зон и повторное распознавание — сделано:
      задача `reapply_zones` (`WindowFacts.reapply`: новая привязка детекций и факты всех окон
      объекта одной транзакцией, затем сигнал), её ставят правки зон и активности камер после
      commit и `POST /zones/reapply` (`QUEUE_UNAVAILABLE`); `POST /images/reanalyze` — снимки
      в `PENDING` одним UPDATE (architecture §7.3 поправлена отдельным коммитом); 6 тестов. В
      стеке правка полигона пересчитала 3 окна за 0,11 с без вызова vision
      спец: [architecture.md](architecture.md) §5.5, §7.3 · ждёт: T26a
      что: задачи воркера `reapply_zones` и `reanalyze_object`; `POST /zones/reapply`;
      `POST /images/reanalyze`; правка, деактивация и импорт зон сами ставят `reapply_zones`
      готово, когда: api-тест: правка зоны пересчитывает факты окон; в стеке после правки зоны
      факты меняются без повторного распознавания
- [x] `T27` scripts: `seed.py` и `labelme_to_zones.py` — сделано 26.09: `seed.py` (объект по
      имени, график если его нет или `--force-plan`, снимки раньше зон — эталоном становится
      первый снимок камеры, ожидание распознавания, прогон, сводка), `labelme_to_zones.py`,
      новый `seed_images.py` (хронология из датасета Лимы). В стеке: 56 снимков распознаны за
      ~1 мин, прогон `DONE`, отклонения D10 2, D4 4, D7 1 — зон ещё нет (H1); повторный запуск
      ничего не меняет. Проверено на новом объекте в живом стеке, без `down -v`: он стёр бы
      базы стенда
      спец: [scripts/README.md](../scripts/README.md), [data/README.md](../data/README.md) · ждёт: T16, T19, T26, H1
      что: объект → импорт `data/seed/schedule.xlsx` → зоны из `cameras.json` → загрузка
      снимков → ожидание распознавания → `POST /analysis/runs?wait=true` → сводка
      готово, когда: на чистом стеке (`docker compose down -v` → `up`) `python scripts/seed.py`
      даёт отклонения в `GET /analysis/deviations`
- [x] `T28` scripts: `e2e.py` и `demo.py` — сделано 26.09: сценарий по дням в
      `data/seed/expected.json`, общий код в `scripts/_scenario.py`, `seed.py` разбит на
      `prepare` и `run_analysis`. `e2e.py` на отдельном объекте «E2E: …»: лента совпадает со
      сценарием (7 строк, в нормальный день D2 нет), у всех, кроме D10, есть снимки, правка
      правила 12.4.10 убирает D2 и оставляет D1, откат возвращает сценарий; дважды подряд
      зелёный (новый и существующий объект); сверка ловит пропуск, лишнее и не тот этап.
      `demo.py` ведёт по дням со ссылками на снимок на экране камер (проверено в браузере)
      спец: [runbook.md](runbook.md) §6, [testing.md](testing.md) · ждёт: T27
      готово, когда: `python scripts/e2e.py` находит D2, D3, D4, D10 на своих днях и не находит D2
      в «нормальный день». **Рубеж R2.**

### R3. Интерфейс, отчёт, качество — 27.09

- [x] `T29a` contracts: снапшоты OpenAPI и TS-типы — сделано: `scripts/contracts.py`
      (снапшот — `openapi_dump.py` в одноразовом контейнере из образа сервиса, настройки по
      умолчанию, как в CI; `openapi_dump.py` сам находит `packages/contracts`), типы
      `openapi-typescript` 7.13 по файлу на сервис в `packages/ts-api-client/src`, алиас
      `@api` и `shared/api/schemas.ts` в web, gateway копирует типы в сборку; повторный
      запуск ничего не меняет, `npm run build` и образ gateway собираются
      спец: [scripts/README.md](../scripts/README.md), [packages/ts-api-client](../packages/ts-api-client/README.md) · ждёт: T16, T19
      что: `scripts/contracts.py` (снапшоты OpenAPI четырёх сервисов тем же `openapi_dump.py`,
      что в CI, + TS-типы в `packages/ts-api-client`); web видит типы, gateway собирает с ними
      готово, когда: `python scripts/contracts.py` повторно ничего не меняет; `npm run build`;
      образ gateway собирается
- [x] `T29b` web: объекты и дашборд — сделано: `features/objects` (объекты plan со статусом,
      отставанием и числом отклонений из analysis), `features/dashboard` (статус, SPI,
      уверенность с числами из `facts`, слепые участки, отклонения по серьёзности, этапы по
      статусам и в риске, последние снимки, кнопка «Пересчитать» на том же `as_of`),
      `shared/ui` (загрузка / пусто / ошибка с `request_id`), `entities/` (форматтеры).
      Проверено в стеке на «Демо T19» с 8 снимками lct-raw, собранном вручную
      спец: [apps/web/README.md](../apps/web/README.md) · ждёт: T29a
      что: экраны «Объекты» и «Дашборд»: статус, SPI, уверенность, счётчики, этапы в риске
      готово, когда: `npm run build`; экраны показывают данные после `seed.py` (до T27 — на
      объекте, собранном вручную в стеке)
- [x] `T30` web: лента предупреждений и карточка — сделано 26.09: `/objects/:id/deviations`,
      лента по дням с фильтрами в адресе, карточка: текст, группы правила с нормой и
      наблюдением, числа из `facts`, правило, снимок с рамками из вывода и зоной участка,
      проверенные сессии из `/explain`, вердикт с комментарием (`X-Actor`); ссылки с дашборда.
      Проверено в браузере: D2 демо — миксер 1 ✓, насос 0 ✗, рамка миксера; D10 — без снимка
      с причиной; фильтр 20.10 — 3 строки; вердикт «подтвердить» на проверочном объекте
      ждёт: T29
      что: лента с фильтрами; карточка: текст, числа из `facts`, правило, снимок с рамками
      (SVG поверх), `/explain`, кнопки «подтвердить / ложное»
      готово, когда: на демо-данных у D2 видны числа и снимок с рамкой миксера
- [x] `T31` web: редактор правил «этап → техника» · **не режется** — сделано 26.09:
      `/objects/:id/settings/rules`, черновик `draft.ts`, «Сохранить и пересчитать» показывает,
      какие отклонения исчезли и появились; кнопка «Правила» на дашборде. Проверено в браузере
      на демо-объекте: без группы «бетононасос» у 12.4.10 — «исчезли из ленты: D2», группа
      возвращена — D2 снова в ленте, лента совпадает со сценарием
      ждёт: T29, T18
      что: группы «любой из» с минимумом, допустимая техника, сигнатура, `min_sessions`;
      сохранение → пересчёт → обновление ленты
      готово, когда: в правиле 12.4.10 убрана группа «бетононасос» — D2 исчезает из ленты без
      перезагрузки стека (runbook §6, шаг 8)
- [x] `T32` web: Гант план-факт — разделена на T32a и T32b (дифф больше 300 строк), обе закрыты
      26.09
      ждёт: T29
      что: плановые полосы, фактический старт, прогнозный хвост, критический путь; правка дат
      формой (перетаскивание — по желанию); выбранная библиотека записана в README web
      готово, когда: правка даты этапа пересчитывает прогноз
- [x] `T32a` web: диаграмма Ганта только для чтения — сделано 26.09: `features/gantt`
      (геометрия — `layout.ts`, свой SVG без библиотеки, решение в README web), карточка этапа,
      кнопка «График» и ссылки из «Этапов в риске» на дашборде. Проверено в браузере: 12 этапов
      демо-объекта, критический путь 12.4.8 → 12.7, хвост «+1» у 12.4.4; без анализа — только
      план, без графика — пояснение
      что: `/objects/:id/gantt` — плановые полосы, прогресс, фактический старт, прогнозный хвост,
      критический путь, связи, линия момента анализа, масштаб; карточка этапа; кнопка на дашборде
      готово, когда: на демо-объекте видны 12 этапов, критический путь и хвост 12.4.4
- [x] `T32b` web: правка дат этапа с пересчётом прогноза · ждёт: T32a — сделано 26.09: форма
      дат в карточке этапа и перетаскивание полосы (`gantt/workdays.ts`: края прилипают к рабочим
      дням, сдвиг целиком сохраняет длительность в рабочих днях), `useSaveDates` — PATCH, прогон
      с ожиданием, «было → стало». Проверено в браузере на «проверке 2»: 12.5.1 сдвинута на
      18.12.2026–17.02.2027 (46 раб. дн. через праздники) — прогноз 25.12.2026 → 17.02.2027,
      резерв 149 → 110; даты возвращены формой; нерабочий день не сохраняется
      что: форма дат и перетаскивание полосы (с привязкой к рабочим дням календаря объекта);
      «Сохранить и пересчитать» — PATCH этапа, прогон анализа, «было → стало» по прогнозу этапа и
      отставанию объекта
      готово, когда: правка даты этапа пересчитывает прогноз
- [x] `T33` web: просмотр камеры — сделано 26.09: `/objects/:id/cameras` — вкладки камер,
      снимки по дням и времени, кадр с зонами и рамками (SVG в пикселях кадра), у машины —
      участок и сдвиг с прошлого окна, скрытие классов, «сделать эталонным кадром»; камера и
      снимок в адресе. Проверено в браузере на демо-объекте (Torre H, D3)
      ждёт: T29, T26
      что: снимок, полигоны зон, рамки детекций, переключение камер и окон
      готово, когда: на демо-данных видны зоны и рамки
- [x] `T34` analysis: PDF-отчёт и экран отчётов — разделена на T34a–T34d (четыре слоя и два
      сервиса: контракт снимков, чистая сборка, PDF с API, экран), все закрыты 26.09
      спец: [analysis-service README](../services/analysis-service/README.md) §5 · ждёт: T16
      что: `src/report/` (Jinja2 → WeasyPrint, восемь разделов, SVG-графики, снимки с рамками);
      `/reports`; в web — список отчётов и кнопка «сформировать»
      готово, когда: PDF по демо-объекту формируется, раздел «Ограничения» заполнен
- [x] `T34a` contracts + site: снимки-доказательства для отчёта — сделано 26.09: контракт 6 в
      interservice.md, `GET /images/{id}?link=internal` (`ImageCatalog.detail`), api-тест;
      в стеке ссылка открывается из контейнера analysis (200, 1,7 МБ)
      что: interservice.md, контракт 6 — analysis читает карточку снимка с рамками и ссылкой на
      внутренний адрес MinIO (architecture.md §7.2), число снимков без времени; в site —
      `GET /images/{id}?link=internal`
      готово, когда: api-тест site: внутренняя ссылка подписана на `S3_ENDPOINT`
- [x] `T34b` analysis: отчёт как чистая функция · ждёт: T34a — сделано 26.09: `src/report/`
      (`model`, `context`, `charts`, `html`, шаблоны), `data/report_labels.yaml`, Jinja2 в
      зависимостях; 8 unit-тестов `tests/unit/test_report.py` на прогоне четырёх демо-дней:
      «Склад» не виден в 12 из 48 рабочих сессий, резюме со ссылками на ID
      что: `src/report/` — контекст отчёта из выводов, плана и фактов периода; SVG Ганта и
      загрузки техники; шаблонное резюме (LLM — T35); HTML восьми разделов (Jinja2)
      готово, когда: unit-тесты: все восемь разделов, «Ограничения» со слепыми участками и
      снимками без времени, ни одного числа не из выводов
- [x] `T34c` analysis: PDF, хранилище и `/reports` · ждёт: T34b — сделано 26.09: WeasyPrint 63.1
      в образе (Pango, DejaVu), `clients/storage.py` (бакет `reports`, заводится при старте и в
      `/health/ready` как необязательная проверка), `report/images.py` (EXIF-поворот, ужатие,
      рамки из `evidence`), `report/pdf.py` (ключ `{object}/{дата}-{начало}_{конец}.pdf`),
      `services/reports.py` (без site отчёт выходит с пометками), `POST/GET /reports`,
      `GET /reports/{key}`; 10 тестов. В стеке PDF демо-объекта за 16–22.10: 7 страниц,
      1,1 МБ, 6 снимков с рамками, ~2 с; попутно — подписи рамок у края кадра и шрифт колонтитула
      что: WeasyPrint в образе, снимки с рамками, бакет `reports`, `POST/GET /reports`,
      `GET /reports/{key}`, `NO_DATA_FOR_PERIOD`, `RENDER_FAILED`
      готово, когда: api-тест; PDF по демо-объекту формируется в стеке
- [x] `T34d` web: экран отчётов · ждёт: T34c — сделано 26.09: `features/reports`
      (`/objects/:id/reports`, кнопка «Отчёты» на дашборде): период по умолчанию — неделя по день
      анализа, проверка периода на клиенте, результат со ссылкой, снимками и источником резюме,
      список со ссылками. Проверено в браузере: PDF за 20–21.10 сформирован и открывается (200,
      853 КБ); объект без наблюдений — сообщение `NO_DATA_FOR_PERIOD` с `request_id`
      что: `/objects/:id/reports` — период, «сформировать», список с ссылками
      готово, когда: из интерфейса формируется и открывается PDF демо-объекта
- [x] `T35` analysis: резюме по фактам — сделано 26.09: `report/summary.py` (JSON для модели,
      проверка чисел и ссылок на ID), `clients/llm_client.py` (OpenAI-совместимый API),
      `services/summary.py` (шаблон всегда, текст модели — только после проверки),
      `prompts/summary.ru.md`, `POST /summary`, резюме в PDF; 13 тестов. Модель — локальная
      Gemma 4 E4B в llama-server (runbook §4, вместо H4): на демо-объекте 3–5 с, 5 из 5 текстов
      прошли проверку, PDF подписан «нейросеть gemma-4-e4b»
      спец: [ADR-0008](decisions/0008-llm-narrative-only.md), [analysis-service README](../services/analysis-service/README.md) §5 · ждёт: T34
      что: `POST /summary`; сборка контекста; `prompts/summary.ru.md`; клиент
      OpenAI-совместимого API; валидатор чисел; шаблонное резюме (его чистая часть — в T34b:
      без неё раздел 7 отчёта пуст)
      готово, когда: тесты валидатора; при `LLM_ENABLED=false` резюме шаблонное; с ключом из H4 —
      LLM-текст со ссылками на ID отклонений
- [x] `T36` ml: метрики распознавания — сделано 27.09: `docs/metrics.md` §2–3 на 100 проверенных
      снимках H5 (600 машин): по классам, без мелких (`evaluate.py --min-side 32`), ошибки при
      рабочем пороге 0,35 (`--errors-conf`), счёт правок авторазметки; zero-shot 0,16 mAP50,
      `ce-ulima-v1` 0,11, но при пороге 83 верных и 18 ложных против 59 и 521; буровые не
      распознаёт ни одна модель
      спец: [ml/README.md](../ml/README.md), [testing.md](testing.md) §7 · ждёт: T24, H5
      что: `ml/eval/evaluate.py`; таблица precision / recall / mAP50 по классам и матрица ошибок
      в `docs/metrics.md` с размером выборки и условиями съёмки
      готово, когда: метрики посчитаны на наборе H5; ничего не выдумано
- [x] `T37` docs: актуализация к сдаче — сделано 27.09: runbook §2 — пошаговый первый запуск
      с нуля (порт gateway, дообученные веса, демо-кадры Лимы, GPU, seed и e2e), §3 и §8
      правдивы (`backup.py` — заготовка, ручной дамп проверен), §7 — два новых симптома, §9 —
      фактический состав и `env_file`; `scripts/test.py` — тесты сервисов в контейнерах с базой
      `<база>_test`; статусы F1–F15 и нефункциональных требований в `traceability.md` по
      замерам; раздел «Ограничения» в README. На стенде: линт, тесты четырёх сервисов, сборка
      web, `health.py` 5/5, `seed.py`, `e2e.py` — зелёные. Прогон с `down -v` — в T38
      ждёт: T28, T31
      что: статусы в `traceability.md`; README и runbook сверены с реальным поведением; раздел
      ограничений; линт и тесты всех сервисов зелёные
      готово, когда: человек может пройти runbook §2 с нуля без вопросов. **Рубеж R3.**

### Сдача — 28.09

- [x] `T38` release: репетиция на чистом стенде — сделано 27.09: тег `v0.1.0` → Release
      опубликовал все 5 образов в ghcr; `down -v` → `pull` (9 мин, vision 12,4 ГБ) → `up`
      (готовы через 50–109 с) → `seed.py` 20 с → `e2e.py` 20 с → `demo.py` без пауз 4 с; PDF с
      LLM-резюме 8,7 с; экраны дашборда, ленты, Ганта, камер и отчётов работают. Найдено и
      записано в runbook §2 и §10: (1) сценарий держится на весах `ulima-v3`, с `ce-ulima-v1`
      лишнее D4 крана вне зон 19.10; (2) образ MinIO больше не скачивается — перенос файлом.
      Стенд после репетиции восстановлен из копии томов (`backup/t38/`), в `.env` снова
      `ce-ulima-v1`. Какие веса ставить к показу — решает человек
      спец: [runbook.md](runbook.md) §10 · ждёт: T37
      что: тег → образы в ghcr → на стенде `docker compose down -v`, `pull`, `up`, `seed.py`,
      `e2e.py` → демо по runbook §6 с секундомером; дальше только исправление блокеров
      готово, когда: сценарий проходит за 5 минут без ручных правок

## 7. После R3, если осталось время

- [x] `T39` web: экран загрузки снимков с ручным вводом времени для `NEEDS_TIME` · ждёт: T29, T23
      — сделано 27.09 в T45: `/objects/:id/upload` — файлы и папки (перетаскиванием и выбором),
      камера по подпапке или из списка, пакеты по 200 файлов с прогрессом, итог «принято /
      ждёт времени / отклонено с причиной», очередь распознавания с автообновлением, ручное
      время для `NEEDS_TIME`, «распознать заново»
- [x] `T40` web: редактор зон на эталонном кадре (F11, Could) · ждёт: T33 · поднят человеком
      26.09: без него не разметить зоны демо (H1) — сделано 26.09: `/objects/:id/settings/zones`
      — рисование щелчками, вершины тянутся, «+» на ребре, двойной щелчок удаляет, сдвиг зоны
      целиком; тип с ролью, название с подсказками участков других камер; слой «где стояла
      техника» (точки контакта со всех снимков камеры); черновик (`draft.ts`) сохраняется одной
      кнопкой, частичный успех не теряет несохранённое. `scripts/export_zones.py` переносит
      разметку в `data/seed/cameras.json`. В браузере проверены создание, правка вершин, сдвиг,
      вставка вершины и удаление: site пересчитал привязку (119 детекций в тестовой зоне),
      тестовая зона удалена
- [x] `T41` ml: дообучение детектора на размеченном датасете Лимы (1046 кадров, 4 камеры одной
      стройки) · взята раньше T36 по решению человека 25.09: zero-shot на кадрах Лимы — ~3 %
      верных рамок у YOLO-World v8s и ~14 % у YOLOE-26m при полноте ниже 40 % — сделано 26.09:
      `ml/prepare/ulima.py` (+ `ulima.yaml`: серии, разбиение по сериям), `ml/training/train.py`,
      `ml/eval/evaluate.py`; aliases «ulima:…» в `equipment_classes.yaml`. Дообучен сам
      YOLO-World (`yolov8s-worldv2-ulima-v3.pt`, код vision не менялся): mAP50 на отложенном
      тесте 0,77 против 0,07 у zero-shot, ложных рамок в сервисе 0,1 на кадр против 8,6
      ([metrics.md](metrics.md)). Веса подключены в `.env` стенда; в `.env.example` остался
      zero-shot — дообученные веса не раздаются `fetch_models.py`
- [-] `T42` ml: дообучение на открытых наборах ради снимков организаторов · **приостановлена
      человеком 27.09**, работа идёт дальше без неё. Сделано 26–27.09: сведены Construction
      Equipment (Kaggle, CC0) и KICT (Mendeley, CC BY 4.0) — `ml/prepare/`, aliases `ce:`/`kict:`,
      класс `light_truck`; MOCS, ACID и др. проверены и отклонены по лицензиям (ml/README.md);
      `train.py --resume`. Прогоны поверх Лимы: `world-s-ce-ulima-v1` (в сервисе с 27.09) и
      `world-s-ce-ulima-kict-v1` (не принят). mAP50, `evaluate.py`, вход 1280, замер 27.09:

      | Веса | lct-test, 600 рамок | буровая, 143 | автокран, 89 | экскаватор, 243 | Лима, тест |
      | :--- | ---: | ---: | ---: | ---: | ---: |
      | zero-shot `yolov8s-worldv2` | **0,16** | **0,23** | **0,29** | 0,22 | 0,07 |
      | `ulima-v3` (T41) | 0,02 | 0,00 | 0,00 | 0,01 | 0,77 |
      | `ce-ulima-v1` | 0,11 | 0,00 | 0,07 | **0,46** | **0,81** |
      | `ce-ulima-kict-v1` | 0,11 | 0,00 | 0,01 | 0,44 | 0,77 |

      Вывод: по mAP50 на снимках организаторов впереди zero-shot — за счёт кранов и буровых при
      низких порогах. При рабочем пороге 0,35 картина обратная (docs/metrics.md, §2): zero-shot —
      59 машин из 600 верно и 521 ложная рамка, буровые все названы кранами; `ce-ulima-v1` —
      83 верно и 18 ложных, но пропускает большинство, буровые и автокраны почти не видит.
      Дообучение учит экскаватор и технику Лимы и стирает то, чего нет в обучающих наборах.
      Открытых наборов с буровыми и гусеничными кранами под подходящей лицензией не нашлось.
      Если вернуться: учить на части снимков организаторов (разбиение по объектам), заморозить
      больше слоёв или держать два детектора. Какие веса показывать на защите — решает человек
      27.09, T43: mAP50 этой таблицы посчитан с несколькими классами на рамку; в условиях
      сервиса zero-shot — 0,07, `ce-ulima-v1` — 0,13 (docs/metrics.md, §4.1)
- [x] `T43` ml: распознавание без нового обучения детектора · поручение человека 27.09 —
      сделано 27.09: оценка конвейеров в условиях сервиса (`ml/eval/predict.py`, `score.py`,
      `speed.py`), каскад «детектор находит — CLIP по вырезке называет» и гибрид с
      `ce-ulima-v1` (`cascade.py`), смесь весов (`training/interpolate.py`), голова CLIP по
      вырезкам открытых наборов (`training/probe.py`); крупные YOLO-World и YOLOE-26 zero-shot.
      Итог в docs/metrics.md, §4: узкое место — назвать машину, а не найти; каскад
      `yolov8x-worldv2` + ViT-L-14 на снимках организаторов при ≤ 20 ложных находит 216 машин
      против 81, но ~450 мс на снимок; гибрид `ce-ulima-v1` + YOLOE-26s + ViT-B-32 (12 вырезок) —
      112 / 167 / 201 против 81 / 103 / 122 при ≤ 20 / 50 / 100 ложных, на Лиме на уровне
      `ce-ulima-v1` (mAP50 0,825 против 0,840), 106 мс на снимок — на границе ТЗ. Смесь весов и
      голова по открытым наборам не помогли. Поправлен вывод T42 о zero-shot (§4.1)
- [ ] `T44` vision: гибрид «дообученный детектор + YOLOE-26s + CLIP по вырезкам» в сервисе ·
      **ждёт решения человека** · ждёт: T43
      что: адаптер YOLOE и классификатор вырезок в `src/models/`, склейка в `core/` с тестами,
      переменные окружения (веса YOLOE, порог и число кандидатов), ViT-B-32 общий со стадией;
      ADR и README vision §4, §5, §8; веса YOLOE-26s — в `fetch_models.py`
      риски: ~106 мс на снимок при требовании ≤ 100 мс (запас — маски YOLOE, 8 мс, и общая
      предобработка); легковые на Лиме называются «малотоннажным грузовиком», столбы и краны —
      «буровой», а буровая есть в правиле этапа «Сваи» — демо-сценарий нужно проверить `e2e.py`
      готово, когда: `speed.py` ≤ 100 мс; метрики §4 повторяются через `POST /analyze`;
      `e2e.py` зелёный
- [x] `T45` web: переделка интерфейса под работу оператора · поручение человека 27.09:
      «на главной ни одной кнопки управления объектом» — сделано 27.09: боковая навигация с
      разделами объекта и счётчиками, закреплённая шапка объекта («Пересчитать», «Загрузить
      снимки», меню правки, графика и архива); объекты — создание с графиком по МРР или из файла,
      правка, архив и возврат, поиск, фильтр, «сначала проблемные»; обзор — чек-лист подготовки
      нового объекта, «требует внимания», ход работ; лента — по умолчанию открытые, ↑/↓, переход
      к следующей после вердикта; настройки объекта (реквизиты, ТЭП, перестройка графика);
      справочники «пороги D1–D10» (правка) и «классы техники»; камеры — завести, переименовать,
      выключить, распознать заново; удаление правила этапа; свои диалоги подтверждения и
      уведомления. Бэкенд не менялся. Проверено в браузере на стенде: создание объекта с
      генерацией графика, загрузка, ручное время, PDF, правка реквизитов, архив. Дополнено по
      просьбе человека 27.09: ссылки резюме на отклонения открывают их карточки; в PDF резюме —
      сразу за титулом, ссылки `[id]` ведут к строкам таблицы отклонений (analysis, `report/`)
- [x] `T46` plan, analysis, web: отметка оператора «этап выполнен» · поручение человека 27.09 ·
      спец: ADR-0015, methodology.md 10.3b, interservice.md раздел 1
      что: поля этапа `completed_on`, `completed_by`, `completion_note` в plan-service
      (`PATCH /plan/stages/{id}`, «весь план»); analysis: этап `DONE` с окончанием в дату отметки,
      после неё — не активен для D1–D10 и индекса активности; web: «Отметить выполненным» и
      «Снять отметку» в карточке этапа на Ганте
      готово, когда: отметка меняет статус этапа, прогноз последователей и ленту; снимается
      сделано: plan-service хранит отметку и отдаёт её в «весь план»; analysis закрывает этап
      датой отметки (прогноз, связи, SPI, D1–D10, активность, строка в «Ограничениях» PDF); web —
      блок отметки в карточке этапа на Ганте (`features/gantt/StageCompletion.tsx`), галочка в
      списке этапов. Проверено на стенде: отметка и снятие через API и в браузере, пересчёт
      «было → стало»
- [x] `T47` infra: SeaweedFS вместо MinIO · поручение человека 27.09 · спец: ADR-0016
      что: сервис `s3` в compose (`chrislusf/seaweedfs`, тег + digest), адреса `s3:8333` и
      `localhost:8333`, проверка `s3` в `/health/ready` site и analysis; runbook, architecture,
      README; перенос бакетов стенда из тома MinIO; CI: `docker compose pull` на чистом раннере
      готово, когда: `pull` без локальных образов проходит; на стенде снимки и PDF пишутся,
      ссылки открываются в браузере; `e2e.py` зелёный
      сделано 27.09: сервис `s3` — `chrislusf/seaweedfs:4.47` по digest, `weed mini`, ключи из
      `S3_*`; проверка `s3` в `/health/ready`; бакеты стенда перенесены `mc mirror` (307 снимков,
      4 отчёта), MinIO остановлен, том `miniodata` оставлен до решения человека; `e2e.py` зелёный,
      ссылка на снимок и PDF с `localhost:8333` — 200; CI-джоб `third-party` и `make third-party`;
      runbook §2 — переход со старого `.env`
- [x] `T48` analysis: каждое формирование отчёта — отдельный файл · поручение человека 27.09:
      в «Сформированных отчётах» новый отчёт затирал прежний того же периода и дня
      что: время формирования в ключе `reports` (`{дата}T{ЧЧММСС}`), старые ключи читаются;
      README analysis §5, architecture.md 7.2; unit- и api-тест
      готово, когда: два отчёта подряд за один период — два файла в списке
      сделано 27.09: ключ `{дата}T{ЧЧММСС}` (`report/pdf.py`), старые ключи читаются; unit- и
      api-тест (часы отчётов подменяются в `conftest`); на стенде два отчёта подряд — два файла,
      старый отчёт без времени в списке и открывается; подсказка на экране отчётов поправлена

## 8. Снято в MVP

- [-] Второй тип объекта «дорога» — глубина важнее ширины (ТЗ, таблица Q&A).
- [-] Профиль `llm` с локальной Ollama — внешний API и шаблон закрывают F12.
- [-] XLSX-отчёты и экспорт графика — в ТЗ только PDF.
- [-] История правок плана (`plan_revision`) — вместо неё `plan_version`.

## 9. Замечено по ходу (не в рамках текущих задач)

Сюда агент записывает найденное попутно: баг, противоречие, долг. Одна строка — одна находка,
со ссылкой на файл. Человек решает, превращать ли её в задачу.

- `docker-compose.yml`: якорь `service-base` с `env_file: [.env]` передаёт каждому контейнеру
  все переменные, включая DSN с паролями чужих баз. Это расходится с runbook §9 («ни один
  контейнер не знает пароля от чужой базы»). Нужно убрать `env_file` и перечислить переменные
  каждого сервиса в `environment`.
- `scripts/backup.py` (`make backup`, runbook §8) не закреплён ни за одной задачей: сейчас это
  заготовка.
- ~~**Образ MinIO недоступен (T38, 27.09).**~~ Закрыто в T47: хранилище — SeaweedFS (ADR-0016).
- **Демо зависит от весов детектора (T38, 27.09).** На чистом стенде с `ce-ulima-v1` в
  «нормальный день» 19.10 появляется D4 башенного крана на `OUTSIDE`: нижняя точка его рамки не
  попадает ни в одну зону, а признак `works_in_place` снимает простой только в рабочем участке.
  С `ulima-v3` лента совпадает со сценарием. Варианты: показывать на `ulima-v3`; расширить зоны
  под кран в `cameras.json`; или не считать простоем неподвижность `works_in_place` вне зон
  (правка методики, раздел 6).
- ~~YOLO-World в Ultralytics для `set_classes`, насколько известно, берёт текстовый энкодер CLIP
  и при первом вызове качает его из интернета.~~ Подтвердилось и закрыто в T24: веса в
  `data/models/clip/`, `weights_dir` Ultralytics в образе — `/models`.
- `packages/contracts/equipment_classes.yaml`: промпт `tipper truck` у `dump_truck` забирает на
  себя почти всю технику. На 100 снимках lct-raw (T24) — 825 рамок `dump_truck` и ни одного
  `excavator`, хотя экскаваторы на кадрах есть (Screenshot_100: подписаны `tipper truck`).
  Промпты нужно подбирать по размеченному набору H5 вместе с метриками T36, а не вслепую.
  На Лиме подтвердилось и лечится дообучением (T41), а не промптами.
- Дообученные веса (с 27.09 — `yolov8s-worldv2-ce-ulima-v1.pt`) есть только в `data/models/` стенда:
  `scripts/fetch_models.py` их не скачивает, в git веса не хранятся. На чистой машине
  vision поднимется на zero-shot. Нужен источник раздачи (например, ассет релиза GitHub) и
  строка в `fetch_models.py`.
- Датасет Лимы — одна стройка. Если демо (H1) строится на его кадрах, часть демо-кадров
  окажется из обучающих серий. Это честно, только если так и сказано (docs/metrics.md, §1).
- Docker Desktop на демо-стенде ограничен в `%USERPROFILE%\.wslconfig`: `memory=4GB`,
  `processors=2`. Стек с vision на GPU помещается (~1 ГБ у vision), но запас мал: для показа
  лучше поднять лимит (человек, нужен `wsl --shutdown`).
- ~~Раздел 2 этого файла: `pytest -q` на хосте не работает.~~ Закрыто в T37:
  `scripts/test.py`. Было: `pytest -q` на хосте не работает — нет `lct_common`, `pytest-asyncio`
  и зависимостей сервиса. Рабочий способ (T03): одноразовый контейнер из образа сервиса в сети
  `lct_lct` с каталогом сервиса, смонтированным в `/app/services/<сервис>`, `pip install pytest
  pytest-asyncio`, `TEST_DB_DSN` на `postgres:5432`. Стоит записать в §2 или в `scripts/`.
  Для analysis-service ещё смонтировать `packages/contracts` в `/app/packages/contracts`.
- `services/plan-service/src/dal/models.py`: поля `Mapped[datetime]` без
  `DateTime(timezone=True)`, хотя колонки в миграциях — `timestamptz`. SQLAlchemy шлёт момент
  как наивный `TIMESTAMP`, и запись момента с часовым поясом падает (`can't subtract
  offset-naive and offset-aware datetimes`); в analysis это исправлено в T15a, в site — в T23a
  тем же `type_annotation_map` в `Base`. plan сам моменты пока не пишет, поэтому не падает.
- ~~`services/analysis-service/src/services/runs.py`: без `as_of` прогон запрашивает факты
  до текущего момента.~~ Исправлено 24.09 по поручению: без `as_of` факты запрашиваются без
  верхней границы, момент — конец последней сессии; заглушка site в тестах фильтрует период,
  как настоящий. В стеке сигнал без `as_of` по «Демо T19» видит 8 сессий, ничего не закрыто.
  Было: прогон запрашивал факты до текущего момента. Демо-хронология датирована графиком (октябрь 2026), поэтому любой
  сигнал без `as_of` — от site-worker после снимка или правки зон, от plan после правки этапа
  или правила — считает «на сейчас», видит 0 сессий и закрывает все отклонения как `RESOLVED`
  (проверено в T29b). Это ломает показ T31 «правило 2 → 1, D2 исчезает»: исчезнут все.
  Вариант: `as_of` по умолчанию — конец последней сессии с фактами без верхней границы
  «сейчас», как и сказано в interservice.md §4. Кнопка дашборда обходит это, передавая
  `as_of` показанного статуса.
- `services/analysis-service/src/api/schemas/objects.py`: `stages_at_risk` — `list[dict]`,
  в OpenAPI это объекты без схемы, и web разбирает их вручную (`useDashboard.ts`). Стоит
  описать элемент моделью (`stage_id`, `name`, `plan_end`, `forecast_end`, `delay_days`) —
  изменение совместимое.
- ~~`services/plan-service/src/api/schemas/common.py` дублирует в коде списки `object_type`,
  `construction_phase`, `zone_type` и др. в виде `StrEnum`, что запрещено AGENTS.md §7.~~
  Закрыто в T17: типы строятся из `enums.yaml`.
- ~~Методика, раздел 6: неподвижность — признак простоя для любого нетранзитного класса.~~
  Закрыто 26.09 по поручению: признак класса `works_in_place` (кран, автокран, насос). Было: но
  башенный кран и бетононасос работают стоя на месте, поэтому на демо (H1, 26.09) D4 «простой»
  висит на кране каждый день, а на насосе — в день бетонирования при полном комплекте. К тому же
  рамка крана захватывает стрелу, и нижняя точка рамки уходит далеко от башни: на Torre H кран
  попадает во «Въезд». Вариант: признак класса в `equipment_classes.yaml` «работает стоя»:
  в рабочем участке с активным этапом неподвижность такого класса не делает его `IDLE`. Правка
  методики — сначала документ.
- Методика, раздел 8: «плановая визуальная стадия на дату» берётся от активного этапа с
  наибольшим `seq`. Если параллельный этап идёт позже по порядку, но раньше по стадии (засыпка
  пазух 12.3.10 после начала каркаса), план ждёт `FOUNDATION` при каркасе на фото — ложное D7
  «опережение». Правильнее брать самую позднюю стадию среди активных этапов.
- ~~Вердикт только открытым.~~ Закрыто 26.09 по поручению: поле `verdict`, миграция 0004,
  вердикт принимает и закрытое. Было: вердикт оператора принимается только открытым отклонениям (`VERDICT_CONFLICT` у `RESOLVED`,
  analysis-service README). В демо на момент последнего снимка (22.10) все отклонения закрыты,
  поэтому кнопки «подтвердить / ложное» на демо-объекте не видны (T30). Варианты: разрешить
  вердикт закрытым («да, это было») — правка методики, раздел 9, правило 3; или показывать
  шаг демо на анализе на прошлый момент (`as_of` 21.10 12:00 — D2 открыт).
- ~~**Важно для демо.** Этапы до начала наблюдений дают ложную задержку.~~ Закрыто 26.09 по
  поручению: methodology.md, 10.3a; демо-объект — `ON_TRACK`, SPI 0.979, e2e проверяет статус.
  Попутно закрыта гонка `?wait=true`: ожидание возвращалось в зазоре между концом прогона и
  заведением его повтора (e2e падал раз из нескольких). Было: этапы, чьё плановое окно закончилось до начала
  наблюдений, оцениваются по наблюдениям. Демо-наблюдения — с 19.10, а подготовка территории
  (10.4-10.8, март) и монтаж крана (май) на видимом пятне застройки без сигнатуры получают
  `LATE` с задержкой 198 и 134 рабочих дня; каркас 12.4.4 с плановым стартом 31.08 набирает
  прогресс только с 19.10 (SPI 0.087, задержка 42). Итог объекта на дашборде — «Задержка
  41 день», SPI 0.066 (`/analysis/objects/{id}/status`, 26.09). Вариант: до первого
  наблюдения участка этап идёт по плану (как уже сделано для «участок ни разу не был виден»,
  `basis: PLAN`), фактический прогресс считается от начала наблюдений. Правка методики.
- ~~`services/analysis-service/src/core/ledger.py`: пересмотренный эпизод остаётся в истории.~~
  Закрыто 26.09 по поручению: строка без вердикта в пересчитанном периоде без эпизода
  удаляется; `seed.py` ждёт пересчёта фактов по новым зонам. Было: эпизод, который исчез, потому что факты его
  сессий пересчитали, закрывается как `RESOLVED` и остаётся в истории. Прогоны по сигналам во
  время распознавания (окно ещё без кадра второй камеры) и до конца `reapply_zones` оставляют
  в ленте фантомы: на проверочном объекте 26.09 — D10, D1, D2 за последний час 22.10 при
  нормальных кадрах. Сюда же: `seed.py` не ждёт `reapply_zones` после импорта зон, поэтому его
  сводка бывает по старой разметке (повторный запуск без изменений дал 23 → 28 отклонений).
  Для e2e (T28) это нестабильность: сверять нужно только открытые и настоящие эпизоды.
