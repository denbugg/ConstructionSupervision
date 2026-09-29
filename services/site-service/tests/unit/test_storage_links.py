"""Ссылки на снимки: браузеру — путь без хоста, сервисам — внутренний адрес (ADR-0017).

Подпись делается локально, без сети: регион у клиента задан явно.
"""

from urllib.parse import parse_qs, urlsplit

from src.clients.storage import ImageStorage

KEY = "0f3a/cam-north/2026-10-20/9e41.jpg"


def _storage(public_path: str = "/storage") -> ImageStorage:
    return ImageStorage(
        endpoint="http://s3:8333",
        public_path=public_path,
        access_key="key",
        secret_key="secret",
        bucket="images",
        presign_ttl_s=3600,
    )


async def test_ссылка_для_браузера_без_хоста_и_с_той_же_подписью():
    storage = _storage()

    browser = urlsplit(await storage.presigned_url(KEY))
    internal = urlsplit(await storage.internal_url(KEY))

    assert (browser.scheme, browser.netloc) == ("", "")
    # gateway отрезает /storage и передаёт хранилищу Host s3:8333: путь и подписанный заголовок
    # совпадают с тем, на что подписано.
    assert browser.path == f"/storage{internal.path}" == f"/storage/images/{KEY}"
    assert internal.netloc == "s3:8333"
    assert parse_qs(browser.query)["X-Amz-SignedHeaders"] == ["host"]
    assert "X-Amz-Signature" in parse_qs(browser.query)


async def test_косая_черта_в_конце_пути_не_удваивается():
    url = await _storage("/storage/").presigned_url(KEY)

    assert url.startswith(f"/storage/images/{KEY}?")
