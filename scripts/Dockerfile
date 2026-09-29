# Контейнер tools: скрипты scripts/ без Python на хосте — нужен только Docker.
#   docker compose run --rm tools python scripts/seed.py
# Код не копируется: репозиторий монтируется в /repo (docker-compose.yml, сервис tools),
# поэтому образ пересобирается только при смене scripts/requirements.txt.
FROM python:3.12-slim

# Контекст сборки — каталог scripts/: весь репозиторий с весами в data/models весит гигабайты.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check --root-user-action=ignore \
    -r /tmp/requirements.txt

ENV PYTHONUNBUFFERED=1
WORKDIR /repo
