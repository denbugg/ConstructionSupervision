"""Общее для скриптов: корень репозитория, чтение .env, адрес gateway, вывод в UTF-8.

Только стандартная библиотека: этот модуль нужен и скриптам без зависимостей
(fetch_models, health), которые идут на любом Python 3.12 (scripts/README.md).
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> dict[str, str]:
    """Переменные из .env в корне, поверх них — окружение процесса.

    Окружение главнее файла, как и у docker compose: `$env:GATEWAY_PORT='8088'` перед
    запуском скрипта должно действовать так же, как перед `docker compose up`.
    """
    values: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("\"'")
    values.update(os.environ)
    return values


def gateway_url(env: dict[str, str]) -> str:
    """Адрес gateway: с хоста — localhost и GATEWAY_PORT, из контейнера tools — GATEWAY_URL."""
    return env.get("GATEWAY_URL") or f"http://localhost:{env.get('GATEWAY_PORT', '8080')}"


def use_utf8_output() -> None:
    """Кириллица в консоли Windows: без этого cp866/cp1251 падает на символах вроде «—»."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
