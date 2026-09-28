"""Опрос готовности всех сервисов стека и сводка одной таблицей.

    python scripts/health.py [--host localhost] [--timeout 3]

Код выхода 0 — все сервисы готовы, 1 — хотя бы один недоступен или не готов.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

from _common import load_env, use_utf8_output

# Порты на хосте заданы в docker-compose.yml (architecture.md, раздел 3.3). Внешний порт
# gateway настраивается, поэтому берётся из GATEWAY_PORT. У gateway нет зависимостей,
# и /health/ready у него нет: его готовность — это /health.
SERVICE_PORTS = {
    "plan-service": 8001,
    "site-service": 8002,
    "analysis-service": 8003,
    "vision-service": 8004,
}


def probe(url: str, timeout: float) -> tuple[bool, str, str]:
    """Один опрос: (готов ли, состояние, проверки зависимостей)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = json.loads(resp.read() or b"{}")
            ok = True
    except urllib.error.HTTPError as exc:
        # 503 от /health/ready — сервис жив, но не готов; тело объясняет почему.
        try:
            body = json.loads(exc.read() or b"{}")
        except ValueError:
            body = {}
        ok = False
        if not body:
            return False, f"HTTP {exc.code}", ""
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False, "недоступен", ""
    except ValueError:
        return False, "ответ не JSON", ""

    checks = body.get("checks") or {}
    details = ", ".join(f"{name}={state}" for name, state in checks.items())
    return ok, str(body.get("status", "?")), details


def main() -> int:
    use_utf8_output()
    parser = argparse.ArgumentParser(description="Готовность сервисов стека")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    env = load_env()
    targets = [
        (name, f"http://{args.host}:{port}/health/ready") for name, port in SERVICE_PORTS.items()
    ]
    gateway_port = env.get("GATEWAY_PORT", "8080")
    targets.append(("gateway", f"http://{args.host}:{gateway_port}/health"))

    ready = 0
    print(f"{'сервис':<18} {'готов':<6} {'состояние':<11} проверки")
    for name, url in targets:
        ok, status, details = probe(url, args.timeout)
        ready += ok
        print(f"{name:<18} {'да' if ok else 'НЕТ':<6} {status:<11} {details}")

    print(f"\nГотовы {ready} из {len(targets)}")
    return 0 if ready == len(targets) else 1


if __name__ == "__main__":
    sys.exit(main())
