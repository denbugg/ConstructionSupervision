# Межсервисные контракты

Всё, о чём сервисы договорились между собой. Пока кода нет, контрактом является этот
файл. Когда код появится, контрактом становятся снапшоты OpenAPI в `openapi/`, и они
обязаны совпадать с этим файлом. Меняется сначала контракт, потом поставщик, потом
потребитель (AGENTS.md, правило 8). Несовместимое изменение описывается в ADR.

| № | Контракт | Поставщик | Потребители | Когда вызывается |
| :--- | :--- | :--- | :--- | :--- |
| 1 | [Весь план объекта](#1-весь-план-объекта) | plan-service | analysis-service, web | один раз за прогон анализа; экран Ганта |
| 2 | [Факты за период](#2-факты-за-период) | site-service | analysis-service | один раз за прогон анализа; отчёт |
| 3 | [Распознавание снимка](#3-распознавание-снимка) | vision-service | site-worker | на каждый снимок |
| 4 | [Прогон анализа и сигнал «пересчитай»](#4-прогон-анализа-и-сигнал-пересчитай) | analysis-service | site-worker, plan-service, web, скрипты | после нового факта, правки плана, по кнопке |
| 5 | [Справочные файлы](#5-справочные-файлы) | этот каталог | все сервисы и `ml/` | при старте сервиса |
| 6 | [Снимки для отчёта](#6-снимки-для-отчёта) | site-service | analysis-service | при формировании PDF-отчёта |

Больше сервисы друг с другом не разговаривают. Схема вызовов и причины границ описаны в
[docs/architecture.md](../../docs/architecture.md), раздел 6.

## Общие правила

- Путь `/api/v1/<сервис>/…`, заголовок `X-API-Key` обязателен и во внутренних вызовах
  ([ADR-0010](../../docs/decisions/0010-auth.md)). `X-Request-Id` передаётся дальше без
  изменений.
- Ошибки приходят в едином конверте `{"error": {"code", "message", "details", "request_id"}}`
  ([docs/api-guidelines.md](../../docs/api-guidelines.md), раздел 5).
- Время указывается в ISO-8601 UTC с `Z`. Даты плана — `YYYY-MM-DD` без времени.
  Координаты на кадре нормированы в диапазон 0…1 от размера кадра, начало отсчёта —
  левый верхний угол.
- **Потребитель игнорирует неизвестные поля.** Поставщик может добавлять поля без
  согласования, но не может удалять, переименовывать или менять их смысл.
- Новое значение перечисления сначала добавляется в `enums.yaml`, и только потом
  начинает приходить в ответах.
- В примерах ниже UUID сокращены до вида `0f3a…`. В фикстурах тестов нужны полные UUID.

---

## 1. Весь план объекта

`GET /api/v1/plan/objects/{object_id}/plan`

Всё, что analysis-service нужно знать о плане, приходит одним ответом: этапы, связи,
правила «этап → техника», календарь и классы техники. Какие этапы активны на дату,
analysis решает сам, чистой функцией. Поэтому отдельного запроса «план на дату» нет.

- **Таймаут и ретраи:** 10 с, два повтора (запрос идемпотентен).
- **Ошибки:** `404 OBJECT_NOT_FOUND`. Объект без этапов не считается ошибкой: придёт
  `"stages": []`, и анализ выставит статус `UNKNOWN`.

```json
{
  "object": {
    "id": "0f3a…",
    "name": "Монолитный жилой дом, 17 этажей, 2 секции",
    "object_type": "RESIDENTIAL_MONOLITH",
    "plan_start": "2026-09-21"
  },
  "plan_version": 7,
  "calendar": {
    "code": "moscow-6day",
    "timezone": "Europe/Moscow",
    "weekend_days": [7],
    "holidays": ["2026-11-04"],
    "work_hours": {"start": "07:00", "end": "23:00"}
  },
  "equipment_classes": [
    {"code": "excavator", "name_ru": "Экскаватор", "group": "EARTHWORKS", "transient": false, "works_in_place": false},
    {"code": "dump_truck", "name_ru": "Самосвал", "group": "TRANSPORT", "transient": true, "works_in_place": false},
    {"code": "concrete_mixer", "name_ru": "Автобетоносмеситель", "group": "CONCRETE", "transient": true, "works_in_place": false},
    {"code": "concrete_pump", "name_ru": "Автобетононасос", "group": "CONCRETE", "transient": false, "works_in_place": true}
  ],
  "stages": [
    {
      "id": "5b20…",
      "code": "10.4-10.8",
      "name": "Подготовка территории",
      "phase": "PREPARATORY",
      "seq": 1,
      "work_codes": ["10.4", "10.5", "10.6", "10.7", "10.8"],
      "zone_type": "BUILDING_FOOTPRINT",
      "visual_stage": null,
      "plan_start": "2026-09-21",
      "plan_end": "2026-10-14",
      "norm_duration_days": 21,
      "predecessors": [],
      "is_critical": true,
      "total_float_days": 0,
      "basis": "Генератор: подготовительный период по МРР",
      "rule": {
        "id": "1c7e…",
        "version": 1,
        "required": [
          {"any_of": ["excavator"], "min": 1},
          {"any_of": ["dump_truck"], "min": 1}
        ],
        "allowed": ["bulldozer", "loader", "truck_crane"],
        "signature": {"equipment": ["excavator", "dump_truck"], "stage_label": null},
        "min_sessions": 2
      }
    },
    {
      "id": "7c1e…",
      "code": "12.3.1",
      "name": "Разработка котлована",
      "phase": "SUBSTRUCTURE",
      "seq": 2,
      "work_codes": ["12.3.1", "12.3.7"],
      "zone_type": "PIT",
      "visual_stage": "PIT",
      "plan_start": "2026-10-15",
      "plan_end": "2026-11-20",
      "norm_duration_days": 31,
      "predecessors": [{"stage_id": "5b20…", "type": "FS", "lag_days": 0}],
      "is_critical": true,
      "total_float_days": 0,
      "basis": "Генератор: подземная часть по МРР, доля этапа из шаблона",
      "rule": {
        "id": "a91d…",
        "version": 2,
        "required": [
          {"any_of": ["excavator"], "min": 1},
          {"any_of": ["dump_truck"], "min": 2}
        ],
        "allowed": ["bulldozer", "loader"],
        "signature": {"equipment": ["excavator", "dump_truck"], "stage_label": null},
        "min_sessions": 2
      }
    },
    {
      "id": "e4b9…",
      "code": "12.3.4",
      "name": "Фундаментная плита",
      "phase": "SUBSTRUCTURE",
      "seq": 3,
      "work_codes": ["12.3.4", "12.3.9"],
      "zone_type": "PIT",
      "visual_stage": "FOUNDATION",
      "plan_start": "2026-11-21",
      "plan_end": "2026-12-18",
      "norm_duration_days": 24,
      "predecessors": [{"stage_id": "7c1e…", "type": "FS", "lag_days": 0}],
      "is_critical": true,
      "total_float_days": 0,
      "basis": "Генератор: подземная часть по МРР, доля этапа из шаблона",
      "rule": {
        "id": "f02a…",
        "version": 1,
        "required": [
          {"any_of": ["concrete_mixer"], "min": 1},
          {"any_of": ["concrete_pump"], "min": 1}
        ],
        "allowed": ["tower_crane", "truck_crane", "truck"],
        "signature": {"equipment": ["concrete_mixer", "concrete_pump"], "stage_label": null},
        "min_sessions": 2
      }
    }
  ]
}
```

| Поле | Тип | Смысл |
| :--- | :--- | :--- |
| `object.plan_start` | date или `null` | Начало СМР; от него analysis запрашивает факты |
| `plan_version` | int | Растёт при любой правке этапов, правил или календаря объекта. Попадает в прогон |
| `calendar.timezone` | IANA | Рабочее время `work_hours` задано в местном времени, сессии — в UTC |
| `calendar.weekend_days` | int[] | Выходные по ISO: понедельник = 1, воскресенье = 7 |
| `equipment_classes` | object[] | Выдержка из `equipment_classes.yaml`: код, название, группа, транзитность, `works_in_place` — работает стоя, неподвижность на рабочем участке не простой |
| `stages` | object[] | Все этапы объекта, упорядочены по `seq` |
| `stages[].zone_type` | `zone_type` | Тип участка, где идут работы этапа. Всегда рабочая роль (см. `zone_type_role`) |
| `stages[].visual_stage` | `stage_label` или `null` | Как объект выглядит на фото во время этапа. Нужен для D7 и ограничения прогресса |
| `stages[].plan_start`, `plan_end` | date | Плановые даты, **обе включительно**: `plan_end` — последний рабочий день этапа |
| `stages[].norm_duration_days` | int > 0 | Нормативная длительность в рабочих днях — знаменатель прогресса. Может отличаться от окна дат, если даты правили руками |
| `stages[].predecessors` | object[] | Связи `FS` / `SS` / `FF` / `SF` с лагом в рабочих днях |
| `stages[].is_critical`, `total_float_days` | bool, int | Результат расчёта критического пути в plan-service |
| `stages[].basis` | string или `null` | Откуда взялась длительность: норматив генератора или «импорт» |
| `stages[].rule` | object или `null` | Правило «этап → техника». `null` — по этапу не проверяются D1, D2, D8, D9 |
| `stages[].completed_on` | date или `null` | Отметка оператора «этап выполнен» — последний день работ, включительно. Как analysis её учитывает — methodology.md, 10.3b. Необязательное поле: нет — отметки нет |
| `stages[].completed_by`, `completion_note` | string или `null` | Кто поставил отметку и комментарий к ней — для объяснения вывода |
| `rule.required` | object[] | Группы обязательной техники. Группа выполнена, если суммарное число единиц классов из `any_of` на участках типа `zone_type` не меньше `min` |
| `rule.allowed` | string[] | Допустимая техника: её присутствие не вызывает D3 |
| `rule.signature` | object | `equipment` — классы, которые должны появиться одновременно; `stage_label` — стадия по фото не раньше указанной. Можно задать одно из двух |
| `rule.min_sessions` | int ≥ 1 | Сколько рабочих сессий подряд должно держаться условие |

Коды классов в правилах берутся только из `equipment_classes`. plan-service проверяет их
при сохранении правила. Как именно analysis применяет группы, транзитные классы и
сигнатуру, описано в [docs/methodology.md](../../docs/methodology.md), разделы 5 и 8; технику,
работающую стоя, — там же, раздел 6.

---

## 2. Факты за период

`GET /api/v1/site/objects/{object_id}/facts?from=2026-10-20T00:00:00Z&to=2026-10-21T00:00:00Z`

Всё, что камеры увидели за период, разложено по 30-минутным сессиям и участкам. site
только описывает увиденное. Работает техника или простаивает, рабочее ли это время,
есть ли отклонение — здесь этого нет, эти выводы делает analysis
([ADR-0012](../../docs/decisions/0012-facts-without-judgement.md)).

- **Период:** полуинтервал `[from, to)` по началу окна сессии.
- **Таймаут и ретраи:** 10 с, два повтора.
- **Ошибки:** `400 INVALID_PERIOD`, если `from >= to`. Если у объекта ещё нет снимков,
  это не ошибка: придёт `"sessions": []`.

```json
{
  "object_id": "0f3a…",
  "from": "2026-10-20T00:00:00Z",
  "to": "2026-10-21T00:00:00Z",
  "zones_version": 5,
  "model_versions": ["yolov8s-worldv2"],
  "pending_images": 0,
  "sessions": [
    {
      "session_id": "3d0c…",
      "window_start": "2026-10-20T06:00:00Z",
      "window_end": "2026-10-20T06:30:00Z",
      "updated_at": "2026-10-20T06:41:12Z",
      "cameras": [
        {"code": "cam-north", "images": 1, "usable": true, "reason": null, "image_ids": ["9e41…"]},
        {"code": "cam-gate", "images": 1, "usable": false, "reason": "DARK", "image_ids": ["b07c…"]}
      ],
      "stage_observation": {
        "stage_label": "PIT", "conf": 0.78,
        "scores": {"PIT": 0.78, "FOUNDATION": 0.11, "FRAME": 0.05}
      },
      "areas": [
        {
          "area": "PIT:Котлован",
          "zone_type": "PIT",
          "name": "Котлован",
          "visibility": {"status": "OK", "cameras_total": 1, "cameras_usable": 1, "reason": null},
          "equipment": [
            {
              "equipment_class": "excavator", "count": 1, "static": 0,
              "evidence": [{"image_id": "9e41…", "detection_id": "d7a2…", "camera": "cam-north", "conf": 0.91}]
            }
          ]
        },
        {
          "area": "ENTRY_GATE:Въезд",
          "zone_type": "ENTRY_GATE",
          "name": "Въезд",
          "visibility": {"status": "PARTIAL", "cameras_total": 2, "cameras_usable": 1, "reason": "DARK"},
          "equipment": []
        }
      ],
      "outside_zones": []
    }
  ]
}
```

| Поле | Тип | Смысл |
| :--- | :--- | :--- |
| `zones_version` | int | Счётчик правок зон объекта. Попадает в прогон: по нему видно, на какой разметке построен вывод |
| `model_versions` | string[] | Версии детектора, давшие детекции периода |
| `pending_images` | int | Снимки периода, которые ещё не распознаны. Больше нуля — факты неполные |
| `sessions[]` | object[] | Только окна, где есть хотя бы один распознанный снимок. Окно без снимков означает «нет наблюдений», а не «нет техники» |
| `window_start`, `window_end` | UTC | Окно 30 минут, выровненное по :00 и :30 |
| `updated_at` | UTC | Когда факт окна пересчитан в последний раз. Пересчёт идёт после каждого обработанного снимка окна |
| `cameras[]` | object[] | Все активные камеры объекта. Камера без снимков в окне: `images: 0`, `usable: false`, `reason: NO_IMAGES` |
| `cameras[].image_ids` | uuid[] | Распознанные снимки камеры в окне. Нужны как доказательство там, где рамок нет: «на участке нет обязательной техники» (D1) показывается снимком пустого участка. Добавлено 23.09 |
| `stage_observation` | object или `null` | Стадия по фото за окно: метка с наибольшей суммой уверенности по пригодным кадрам |
| `areas[]` | object[] | Все участки объекта, даже пустые и невидимые. Участок — все зоны с одинаковыми типом и названием ([ADR-0013](../../docs/decisions/0013-zones-and-areas.md)) |
| `areas[].area` | string | Ключ участка `ТИП:Название`, например `PIT:Котлован` |
| `areas[].visibility.status` | `visibility_status` | `OK` — все камеры участка дали пригодный кадр, `PARTIAL` — часть, `BLIND` — ни одна |
| `areas[].visibility.reason` | `visibility_reason` или `null` | Главная причина непригодности для `PARTIAL` и `BLIND` |
| `equipment[].count` | int > 0 | Число единиц класса на участке: максимум по камерам участка, а не сумма |
| `equipment[].static` | int или `null` | Сколько из `count` не сдвинулись с прошлого окна той же камеры. `null` — у камеры не было прошлого окна |
| `equipment[].evidence` | object[] | Детекции, на которых стоит число. При `count > 0` список не пуст |
| `outside_zones[]` | object[] | То же для детекций, не попавших ни в одну зону |

Как считаются числа:
- **Количество.** Для каждой камеры участка берётся число рамок класса, у которых точка
  контакта (середина нижней стороны рамки) лежит внутри полигона этого участка на её кадре.
  По камерам берётся максимум.
- **Неподвижность.** Каждая рамка сравнивается с ближайшей рамкой того же класса у той же
  камеры в прошлом окне. Смещение центра меньше `MOVE_THRESHOLD` доли диагонали кадра
  означает, что единица не двигалась.
- **Опасные зоны (`DANGER`) накладываются поверх остальных.** Рамка внутри опасной зоны
  учитывается и в своём основном участке, и в опасном.
- **Непригодные кадры в факт не входят.** Детекции с тёмных, размытых и закрытых кадров
  не считаются. Участок, у которого нет ни одного пригодного кадра, получает `BLIND`.
- **Отсутствие класса означает ноль.** В `equipment` перечислены только классы с `count > 0`.
  Класс `person` учитывается наравне с техникой: он нужен analysis для D6.

---

## 3. Распознавание снимка

`POST /api/v1/vision/analyze`

Чистая функция «картинка → факты о картинке». vision-service ничего не знает про объекты,
зоны и график и никого не вызывает.

- **Таймаут и ретраи:** 30 с, два повтора с экспоненциальной паузой (задача идемпотентна).
- **Ошибки:** `400 UNSUPPORTED_MEDIA_TYPE`, `400 IMAGE_DECODE_FAILED`, `413 IMAGE_TOO_LARGE`,
  `503 MODEL_NOT_LOADED`, `500 INFERENCE_FAILED`.

Запрос — JSON с presigned-ссылкой на снимок во внутреннем адресе S3-хранилища:

```json
{"image_url": "http://s3:8333/images/0f3a…/cam-north/2026-10-20/9e41….jpg?X-Amz-…"}
```

Для ручной проверки в Swagger тот же эндпоинт принимает `multipart/form-data` с полем `file`.

```json
{
  "model": {
    "detector": "yolov8s-worldv2",
    "stage_classifier": "openclip-vit-b32",
    "device": "cuda",
    "classes_version": "3f9a1c2e"
  },
  "image": {"width": 1920, "height": 1080},
  "detections": [
    {"equipment_class": "excavator", "bbox": [0.41, 0.52, 0.49, 0.63], "conf": 0.91},
    {"equipment_class": "dump_truck", "bbox": [0.12, 0.55, 0.23, 0.64], "conf": 0.78}
  ],
  "stage": {"label": "PIT", "conf": 0.78, "scores": {"PIT": 0.78, "FOUNDATION": 0.11, "FRAME": 0.05}},
  "quality": {"brightness": 0.42, "blur": 0.08},
  "inference_ms": 84
}
```

| Поле | Смысл |
| :--- | :--- |
| `model.classes_version` | Первые 8 символов sha256 файла `equipment_classes.yaml`: вывод воспроизводим после правки классов |
| `detections[].equipment_class` | Код из `equipment_classes.yaml`, включая `person` |
| `detections[].bbox` | `[x1, y1, x2, y2]`, нормировано 0…1 |
| `detections[].conf` | Не ниже порога `VISION_DET_CONF` |
| `stage` | Стадия по фото, `null` при `VISION_STAGE_ENABLED=false` |
| `quality.brightness` | Средняя яркость кадра, 0…1 |
| `quality.blur` | Размытость кадра, 0…1; больше — хуже |

vision только измеряет качество кадра. Годен ли кадр, решает site-service по своим порогам
`MIN_BRIGHTNESS` и `MAX_BLUR`: это правило площадки, а не распознавания.

---

## 4. Прогон анализа и сигнал «пересчитай»

`POST /api/v1/analysis/runs`

Один эндпоинт служит и сигналом, и ручным запуском. site-worker шлёт его после
пересчёта факта окна, plan-service — после правки этапов, правил или календаря, интерфейс —
по кнопке, скрипты — в конце загрузки демо-данных.

```json
{"object_id": "0f3a…", "triggered_by": "FACTS_UPDATED", "as_of": null}
```

| Поле | Смысл |
| :--- | :--- |
| `object_id` | Обязательное |
| `triggered_by` | `FACTS_UPDATED` / `PLAN_CHANGED` / `MANUAL`, по умолчанию `MANUAL` |
| `as_of` | Момент, на который считается анализ. По умолчанию — конец последней сессии с фактами, а если фактов нет — текущее время. Именно этот момент подставляется вместо «сегодня» во все формулы методики |
| `?wait=true` | Дождаться конца прогона и вернуть его результат. Нужен скриптам и тестам |

Ответ `202`, а при `wait=true` — `200` с тем же телом, что у `GET /runs/{id}`:

```json
{"run_id": "b812…", "status": "RUNNING", "coalesced": false}
```

`GET /api/v1/analysis/runs/{run_id}`:

```json
{
  "run_id": "b812…",
  "object_id": "0f3a…",
  "triggered_by": "FACTS_UPDATED",
  "as_of": "2026-10-20T06:30:00Z",
  "plan_version": 7,
  "zones_version": 5,
  "status": "DONE",
  "started_at": "2026-10-20T06:41:13Z",
  "finished_at": "2026-10-20T06:41:14Z",
  "stats": {"sessions": 1, "deviations_open": 1, "deviations_opened": 1, "deviations_resolved": 0, "deviations_withdrawn": 0},
  "error": null
}
```

Правила:
- **На объект одновременно идёт не больше одного прогона.** Если прогон уже идёт, новый
  сигнал его не запускает: analysis отмечает, что нужен ещё один прогон, отвечает
  `coalesced: true` с номером текущего и после его окончания запускает ровно один новый.
- **Прогон считает всё с нуля.** Он забирает весь план (контракт 1) и факты за период
  `[object.plan_start, as_of]` (контракт 2). Результат зависит только от плана, фактов и
  `as_of`, поэтому повтор не создаёт дублей.
- **Отправитель сигнала не ждёт и не повторяет:** таймаут 2 с, ошибка только пишется в лог.
  Потерянный сигнал безопасен: любой следующий прогон или кнопка «пересчитать» считают
  всё заново.
- **Ошибки:** `404 OBJECT_NOT_FOUND` (plan не знает объект); `503 PLAN_SERVICE_UNAVAILABLE`
  или `503 SITE_SERVICE_UNAVAILABLE` — прогон завершён со статусом `FAILED`. Частичных,
  «додуманных» выводов не бывает.

---

## 5. Справочные файлы

Оба файла лежат в этом каталоге и монтируются в контейнеры только для чтения
(`./packages/contracts:/contracts:ro`, путь задаёт переменная `CONTRACTS_DIR`).

| Файл | Что в нём | Кто читает |
| :--- | :--- | :--- |
| [`equipment_classes.yaml`](equipment_classes.yaml) | Классы техники: код, название, группа, транзитность, работа стоя, промпты детектора, метки внешних датасетов | plan (отдаёт в API и проверяет правила), vision (промпты), `ml/` (метки датасетов). analysis получает классы в контракте 1 |
| [`enums.yaml`](enums.yaml) | Канонические перечисления: роли типов зон, порядок стадий по фото и остальные | все сервисы |

Добавить класс техники — значит добавить запись в `equipment_classes.yaml` и перезапустить
plan-service и vision-service. Код при этом не меняется
([ADR-0014](../../docs/decisions/0014-equipment-classes-file.md)).

---

## 6. Снимки для отчёта

Добавлено 26.09 (T34a). PDF-отчёт показывает снимки-доказательства с рамками и в разделе
«Ограничения» говорит, сколько снимков не попало в анализ без времени съёмки. Своих снимков у
analysis нет: он читает их у site теми же эндпоинтами, что и интерфейс, с одним отличием —
ссылкой на внутренний адрес S3-хранилища.

`GET /api/v1/site/images/{image_id}?link=internal`

Карточка снимка — та же, что отдаётся интерфейсу (`ImageDetail` в OpenAPI site): время
съёмки, размер кадра, пригодность, рамки `detections[]` с `id`, `equipment_class`, `bbox`,
`conf`. `link=internal` меняет только поле `url`: ссылка подписана на `S3_ENDPOINT`
(`http://s3:8333`), а не на публичный адрес — из сети Docker публичный `localhost:8333` не
открывается (architecture.md, 7.2). По умолчанию `link=public`.

`GET /api/v1/site/images?object_id={id}&status=NEEDS_TIME&limit=1`

Нужно только поле `total`: столько снимков объекта ждут ручного ввода времени и в факты не
попали.

- **Таймаут и ретраи:** 10 с, два повтора (оба запроса идемпотентны). Файл по ссылке analysis
  скачивает сам, тем же таймаутом.
- **Ошибки:** `404 IMAGE_NOT_FOUND` — снимок удалён или id из старого вывода: отчёт
  формируется без этого снимка и пишет почему. Недоступность site или хранилища — тоже не повод
  не выдать отчёт: снимки заменяются пометкой «недоступен», раздел «Ограничения» говорит об
  этом явно.
- **Сколько:** не больше `REPORT_MAX_EVIDENCE_IMAGES` снимков на отчёт.

| Поле | Смысл для отчёта |
| :--- | :--- |
| `url` | Ссылка на файл во внутренней сети, живёт `S3_PRESIGN_TTL_S` |
| `width`, `height` | Размер кадра: рамки рисуются в его пикселях |
| `captured_at` | Подпись снимка |
| `detections[].id` | Какие рамки выделить: те, что перечислены в `evidence` отклонения |
| `detections[].bbox` | `[x1, y1, x2, y2]` в долях 0…1 |
