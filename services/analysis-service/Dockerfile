# Контекст сборки — корень репозитория: сервису нужен packages/py-common.
# Python-сервису нечего компилировать, поэтому образ одностадийный и лёгкий.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Pango и HarfBuzz — вёрстка PDF в WeasyPrint (README, раздел 5); DejaVu — шрифт с кириллицей:
# без него русский текст отчёта ляжет квадратами.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

COPY packages/py-common /app/packages/py-common
RUN pip install /app/packages/py-common

COPY services/analysis-service/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY services/analysis-service /app/services/analysis-service
WORKDIR /app/services/analysis-service

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
