# Сборка интерфейса: SPA собирается здесь же и уезжает в статику nginx —
# отдельного веб-сервера у apps/web нет (docs/architecture.md, раздел 3.2).
FROM node:22-alpine AS web

WORKDIR /repo/apps/web
# Сначала манифесты: слой с зависимостями переиспользуется, пока они не менялись.
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
# Типы API генерируются в packages/ts-api-client и лежат рядом, как в репозитории.
COPY packages/ts-api-client/src /repo/packages/ts-api-client/src
COPY apps/web ./
RUN npm run build

FROM nginx:1.27-alpine

# Контекст сборки — корень репозитория, как у всех сервисов: одно правило на всех.
COPY services/gateway/nginx.conf /etc/nginx/conf.d/default.conf
COPY services/gateway/swagger /usr/share/nginx/swagger
COPY --from=web /repo/apps/web/dist /usr/share/nginx/html

EXPOSE 80
