# Контекст сборки — корень репозитория: сервису нужен packages/py-common.
# Веса в образ не входят: они монтируются в /models (make models → data/models/).
FROM python:3.12-slim

# Индекс колёс PyTorch определяет устройство: cu128 — GPU демо-стенда, cpu — запасной
# образ в разы легче (README, раздел 8). В compose задаётся VISION_TORCH_INDEX_URL.
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Ultralytics пишет настройки в домашний каталог и без этого пытается ходить в сеть.
    YOLO_OFFLINE=1 \
    YOLO_CONFIG_DIR=/tmp/ultralytics

# OpenCV внутри Ultralytics требует libGL и glib даже без окна.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Самый тяжёлый слой — первым: он пересобирается только при смене версии torch.
RUN pip install --index-url ${TORCH_INDEX_URL} torch==2.8.0 torchvision==0.23.0

COPY services/vision-service/requirements-ml.txt /tmp/requirements-ml.txt
RUN pip install -r /tmp/requirements-ml.txt

COPY packages/py-common /app/packages/py-common
RUN pip install /app/packages/py-common

COPY services/vision-service/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# YOLO-World кодирует промпты классов текстовым энкодером OpenAI CLIP. Ultralytics ищет его в
# weights_dir своих настроек (по умолчанию ./weights) и иначе качает из интернета: каталог
# весов — смонтированный /models, файл — /models/clip/ViT-B-32.pt (scripts/fetch_models.py).
RUN mkdir -p ${YOLO_CONFIG_DIR} \
    && python -c "from ultralytics import settings; settings.update({'weights_dir': '/models'})"
# OpenCLIP грузит веса из файла; без этого он заглядывает в Hugging Face при старте.
ENV HF_HUB_OFFLINE=1

COPY services/vision-service /app/services/vision-service
WORKDIR /app/services/vision-service

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
