"""Сервис обязан отвечать на проверки здоровья, а готовым быть только с моделями в памяти.

Тест дешёвый, но ловит самое дорогое: приложение, которое не импортируется
или не поднимается. Внешних зависимостей у vision-service нет, поэтому
проверка работает без докера и без базы.
"""

from httpx import ASGITransport, AsyncClient
from src.main import app


async def test_живой_и_готовый(client):
    alive = await client.get("/health")
    ready = await client.get("/health/ready")

    assert alive.status_code == 200
    assert alive.json()["service"] == "vision-service"
    assert ready.status_code == 200
    assert ready.json()["status"] == "healthy"


async def test_без_моделей_живой_но_не_готовый():
    app.state.models = None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        alive = await client.get("/health")
        ready = await client.get("/health/ready")

    assert alive.status_code == 200
    assert ready.status_code == 503
    assert ready.json()["checks"] == {"models": "fail"}
