"""Зоны демо-объекта из site-service → data/seed/cameras.json.

    python scripts/export_zones.py [--object-id <uuid>]

Разметку делают в интерфейсе (редактор зон), а seed.py берёт её из cameras.json: этот скрипт
переносит одно в другое, чтобы демо-данные собирались на чистом стеке с той же разметкой.
Объект по умолчанию — демо-объект из data/seed/object.json (по имени). Камеры и их названия
берутся из site-service; эталонный кадр в файле не меняется. Адрес и ключ — из .env.
"""

import argparse
import json
import sys

import httpx
from _common import ROOT, gateway_url, load_env, use_utf8_output

SEED = ROOT / "data" / "seed"
CAMERAS = SEED / "cameras.json"
PAGE = 200


def find_object(client: httpx.Client) -> str:
    """id демо-объекта по имени из object.json: скрипт ничего не создаёт."""
    name = json.loads((SEED / "object.json").read_text(encoding="utf-8"))["name"]
    page = client.get("/plan/objects", params={"limit": PAGE}).raise_for_status().json()
    for item in page["items"]:
        if item["name"] == name and item["status"] != "ARCHIVED":
            return item["id"]
    raise SystemExit(f"Объекта «{name}» нет: сначала python scripts/seed.py")


def export(client: httpx.Client, object_id: str) -> dict:
    """cameras.json из site-service; эталонный кадр — из текущего файла, если он там был."""
    current = json.loads(CAMERAS.read_text(encoding="utf-8")) if CAMERAS.exists() else {}
    references = {c["code"]: c.get("reference_image") for c in current.get("cameras", [])}
    cameras = client.get(
        "/site/cameras", params={"object_id": object_id, "limit": PAGE}
    ).raise_for_status()
    out = []
    for camera in cameras.json()["items"]:
        if not camera["is_active"]:
            continue
        zones = client.get(
            "/site/zones", params={"camera_id": camera["id"], "limit": PAGE}
        ).raise_for_status()
        entry = {"code": camera["code"], "name": camera["name"]}
        if references.get(camera["code"]):
            entry["reference_image"] = references[camera["code"]]
        entry["zones"] = [
            {"zone_type": z["zone_type"], "name": z["name"], "polygon": z["polygon"]}
            for z in zones.json()["items"]
        ]
        out.append(entry)
    # Порядок камер — как в текущем файле, новые в конце: иначе каждая выгрузка давала бы diff.
    order = {code: i for i, code in enumerate(references)}
    out.sort(key=lambda c: order.get(c["code"], len(order)))
    return {"cameras": out}


def main() -> int:
    use_utf8_output()
    parser = argparse.ArgumentParser(description="Зоны объекта → data/seed/cameras.json")
    parser.add_argument("--object-id", help="объект; по умолчанию демо-объект из object.json")
    args = parser.parse_args()

    env = load_env()
    base = f"{gateway_url(env)}/api/v1"
    headers = {"X-API-Key": env.get("API_KEY", "")}
    try:
        with httpx.Client(base_url=base, headers=headers, timeout=30) as client:
            spec = export(client, args.object_id or find_object(client))
    except httpx.HTTPError as exc:
        print(f"Ошибка запроса к {base}: {exc}")
        return 1
    CAMERAS.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for camera in spec["cameras"]:
        areas = ", ".join(f"{z['zone_type']}:{z['name']}" for z in camera["zones"]) or "зон нет"
        print(f"{camera['code']:<14} {areas}")
    print(f"записано в {CAMERAS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
