"""POST /analyze и GET /model на моделях-заглушках: форма ответа, ошибки контракта."""

import pytest
from src.config import settings
from src.core.detections import RawBox
from src.main import app
from src.reference import stage_prompts, vocabulary

from tests.conftest import BrokenDetector, StubDetector, image_bytes, make_models

URL = "/api/v1/vision/analyze"


def upload(content: bytes, name="frame.jpg", content_type="image/jpeg"):
    return {"files": {"file": (name, content, content_type)}}


async def test_снимок_файлом_форма_ответа_по_контракту(client):
    response = await client.post(URL, **upload(image_bytes((200, 100))))

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == {
        "detector": "stub-detector",
        "stage_classifier": "stub-stage",
        "device": "cpu",
        "classes_version": vocabulary().version,
    }
    assert body["image"] == {"width": 200, "height": 100}
    assert body["detections"] == []
    assert body["stage"]["label"] == stage_prompts().labels[0]
    assert set(body["stage"]["scores"]) == set(stage_prompts().labels)
    assert 0 <= body["quality"]["brightness"] <= 1
    assert body["quality"]["blur"] == 1.0  # однотонный кадр
    assert isinstance(body["inference_ms"], int)


async def test_детекции_с_кодами_классов_из_файла_и_без_дублей(client, models):
    vocab = vocabulary()
    excavator = vocab.prompt_codes.index("excavator")
    person = vocab.prompt_codes.index("person")
    models.detector = StubDetector(
        [
            RawBox(40, 20, 120, 80, 0.9, excavator),
            RawBox(42, 20, 120, 82, 0.6, excavator + 1),  # «digger» на той же машине
            RawBox(10, 10, 20, 40, 0.5, person),
            RawBox(0, 0, 5, 5, 0.1, person),  # ниже порога
        ]
    )

    body = (await client.post(URL, **upload(image_bytes((200, 100))))).json()

    assert body["detections"] == [
        {"equipment_class": "excavator", "bbox": [0.2, 0.2, 0.6, 0.8], "conf": 0.9},
        {"equipment_class": "person", "bbox": [0.05, 0.1, 0.1, 0.4], "conf": 0.5},
    ]


async def test_стадия_выключена_стадия_null(client, models):
    models.stage_classifier = None

    body = (await client.post(URL, **upload(image_bytes()))).json()

    assert body["stage"] is None
    assert body["model"]["stage_classifier"] is None


async def test_битый_файл(client):
    response = await client.post(URL, **upload(b"\xff\xd8\xff not really a jpeg"))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMAGE_DECODE_FAILED"


async def test_неподдерживаемый_формат(client):
    response = await client.post(URL, **upload(image_bytes(fmt="GIF"), "a.gif", "image/gif"))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


async def test_тело_не_json_и_не_форма(client):
    response = await client.post(URL, content=b"hello", headers={"Content-Type": "text/plain"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


async def test_форма_без_файла(client):
    response = await client.post(URL, data={"other": "x"}, files={"x": ("a", b"1")})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCHEMA_VALIDATION_FAILED"


async def test_слишком_большой_снимок(client, monkeypatch):
    monkeypatch.setattr(settings, "vision_max_mb", 0)

    response = await client.post(URL, **upload(image_bytes()))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "IMAGE_TOO_LARGE"


async def test_ссылка_скачивается_и_распознаётся(client, monkeypatch):
    seen = {}

    async def fake_fetch(url, max_bytes, timeout_s):
        seen["url"] = url
        return image_bytes((64, 48), "PNG")

    monkeypatch.setattr("src.services.analyze.fetch_image", fake_fetch)
    url = "http://s3:8333/images/a/b.jpg?X-Amz-Signature=abc"

    response = await client.post(URL, json={"image_url": url})

    assert response.status_code == 200
    assert response.json()["image"] == {"width": 64, "height": 48}
    assert seen["url"] == url


async def test_недоступная_ссылка(client):
    # Порт 9 на localhost закрыт: соединение отвергается сразу, без сети.
    response = await client.post(URL, json={"image_url": "http://127.0.0.1:9/frame.jpg"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"


@pytest.mark.parametrize("payload", [{"image_url": "ftp://x/y.jpg"}, {}])
async def test_ссылка_не_по_схеме(client, payload):
    response = await client.post(URL, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCHEMA_VALIDATION_FAILED"


async def test_битый_json(client):
    response = await client.post(
        URL, content=b"{oops", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422


async def test_модели_не_загружены(client):
    app.state.models = None

    response = await client.post(URL, **upload(image_bytes()))
    model = await client.get("/api/v1/vision/model")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_NOT_LOADED"
    assert model.status_code == 503


async def test_ошибка_модели(client):
    app.state.models = make_models(BrokenDetector())

    response = await client.post(URL, **upload(image_bytes()))

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INFERENCE_FAILED"


async def test_без_ключа_401(client):
    response = await client.post(URL, headers={"X-API-Key": "wrong"}, **upload(image_bytes()))

    assert response.status_code == 401


async def test_модель_словарь_как_в_файле(client):
    response = await client.get("/api/v1/vision/model")

    assert response.status_code == 200
    body = response.json()
    vocab = vocabulary()
    assert body["classes_version"] == vocab.version
    assert [c["code"] for c in body["classes"]] == list(vocab.codes)
    assert body["classes"][0]["prompts"] == list(vocab.prompts_of(vocab.codes[0]))
    assert body["stage_labels"] == list(stage_prompts().labels)
    assert body["det_conf"] == settings.vision_det_conf
    assert body["device"] == "cpu"
