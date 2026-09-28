"""Общее для скриптов: корень репозитория, чтение .env, честная заглушка.

Только стандартная библиотека: скрипты запускаются системным Python на демо-стенде,
где ничего «ради одного скрипта» не ставится (scripts/README.md).
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


def use_utf8_output() -> None:
    """Кириллица в консоли Windows: без этого cp866/cp1251 падает на символах вроде «—»."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def not_implemented(script: str, task: str, what: str) -> int:
    """Заглушка ещё не написанного скрипта: сообщение и код 1 вместо тихого успеха."""
    use_utf8_output()
    print(f"Скрипт «{script}» не реализован, задача {task} (docs/board.md).")
    print(f"Что он будет делать: {what}")
    return 1
