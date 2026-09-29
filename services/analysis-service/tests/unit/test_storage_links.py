"""Ссылка на отчёт для браузера — путь без хоста, подписанный на внутренний адрес (ADR-0017).

Подпись делается локально, без сети: регион у клиента задан явно.
"""

from urllib.parse import parse_qs, urlsplit

from src.clients.storage import ReportStorage


async def test_ссылка_на_отчёт_без_хоста():
    storage = ReportStorage(
        endpoint="http://s3:8333",
        public_path="/storage",
        access_key="key",
        secret_key="secret",
        bucket="reports",
        presign_ttl_s=3600,
    )

    url = urlsplit(await storage.presigned_url("0f3a/2026-10-22T150000-2026-10-16_2026-10-22.pdf"))

    assert (url.scheme, url.netloc) == ("", "")
    assert url.path == "/storage/reports/0f3a/2026-10-22T150000-2026-10-16_2026-10-22.pdf"
    assert parse_qs(url.query)["X-Amz-SignedHeaders"] == ["host"]
