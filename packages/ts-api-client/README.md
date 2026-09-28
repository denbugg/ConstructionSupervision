# ts-api-client — типы API

TypeScript-типы, **сгенерированные** из снапшотов OpenAPI
(`packages/contracts/openapi/*.json`) генератором `openapi-typescript`.

## Правила

- **Руками не правится.** Любая правка будет затёрта следующей генерацией.
  Нужно другое поведение — меняется контракт в сервисе, затем `make contracts`
  (на Windows — `python scripts/contracts.py`).
- Единственный источник типов API для `apps/web`. Дублировать типы ответов
  в коде фронтенда запрещено.
- Результат генерации коммитится: сборка фронтенда не должна зависеть от поднятого бэкенда.

## Генерация

```bash
make contracts   # снапшоты OpenAPI → типы
```

Скрипт снимает снапшоты тем же `scripts/openapi_dump.py`, что и CI, поэтому CI сверяет
закоммиченный снапшот с кодом: разошлось — ошибка сборки. Что нужно для запуска — в
[scripts/README.md](../../scripts/README.md).

## Что внутри

```text
ts-api-client/
├── src/
│   ├── plan.gen.ts  site.gen.ts  analysis.gen.ts  vision.gen.ts   # по файлу на сервис
│   └── index.ts     # пространства имён: plan, site, analysis, vision
└── package.json     # только генератор; во время выполнения пакет не нужен
```

Типы разложены по сервисам, потому что у сервисов совпадают имена схем (`ObjectRead`,
`Page_…`), и в одном файле они бы столкнулись. В интерфейсе они подключаются алиасом `@api`:

```ts
import type { plan } from "@api";
type ObjectRead = plan.components["schemas"]["ObjectRead"];
```

Короткие имена схем — `apps/web/src/shared/api/schemas.ts`. HTTP-обёртка (базовый адрес,
`X-API-Key`, разбор конверта ошибки с `request_id`) живёт в интерфейсе,
`apps/web/src/shared/api/client.ts`: она пишется руками, а этот пакет — только генерируется.
