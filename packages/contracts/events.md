# Доменные события

События **названы сейчас, реализованы прямыми HTTP-вызовами**. Это сделано намеренно
([ADR-0004](../../docs/decisions/0004-sync-rest-and-queue.md)): брокер не окупается на
хакатоне, но переход на него не должен требовать переписывания логики.

Когда брокер появится, изменится только реализация в `clients/`: вместо вызова будет
публикация.

| Событие | Кто порождает | Полезная нагрузка | Кто реагирует сейчас |
| :--- | :--- | :--- | :--- |
| `image.registered` | site-service | `image_id, object_id, camera_id, captured_at, session_id` | Очередь задач воркера (`analyze_image`) |
| `image.analyzed` | site-worker | `image_id, session_id, detections_count, stage_label, model_version` | Пересчёт факта окна |
| `image.failed` | site-worker | `image_id, error_code` | Статус снимка в интерфейсе |
| `zones.updated` | site-service | `object_id, zones_version, changed_zone_ids` | Задача `reapply_zones`, после неё — `facts.updated` |
| `facts.updated` | site-worker | `object_id, session_id, window_start, zones_version` | Сигнал `POST /analysis/runs` с `FACTS_UPDATED` |
| `plan.updated` | plan-service | `object_id, plan_version, changed_stage_ids` | Сигнал `POST /analysis/runs` с `PLAN_CHANGED` |
| `analysis.completed` | analysis-service | `run_id, object_id, as_of, opened, resolved, status, delay_days` | Обновление дашборда (по запросу интерфейса) |
| `deviation.opened` | analysis-service | `deviation_id, object_id, code, severity, stage_id, area` | Лента; в будущем — уведомления |
| `deviation.resolved` | analysis-service | `deviation_id, object_id, code, resolved_at` | Лента |

Правка правила «этап → техника» и правка календаря — это тоже `plan.updated`: для
analysis они отличаются только номером `plan_version`.

## Правила

1. Событие — факт в прошедшем времени, а не команда: `facts.updated`, а не `update_facts`.
2. Полезная нагрузка — идентификаторы и минимум контекста. Подробности потребитель
   запрашивает у владельца данных: событие не должно превращаться в способ передачи состояния.
3. Событие не гарантирует доставку и может прийти дважды. Любой обработчик идемпотентен —
   это требование действует уже сейчас, до всякого брокера.
4. Потеря события не должна ломать состояние. Восстановление — повторный прогон
   (`POST /analysis/runs`, `POST /site/images/reanalyze`). Поэтому сигналы пересчёта
   ничего не возвращают и не входят в транзакции.
