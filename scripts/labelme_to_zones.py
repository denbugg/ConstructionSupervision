"""Разметка LabelMe → зоны камер в data/seed/cameras.json.

    python scripts/labelme_to_zones.py data/seed/annotations/*.json

Один файл LabelMe — один эталонный кадр одной камеры. Камера берётся из пути кадра
(`imagePath`: `cam-torre-h/20261019_090500.jpg` → `cam-torre-h`), а если там нет папки — из имени
файла разметки. Метка полигона — `ТИП:Название` (`PIT:Пазухи`); без названия — только тип.
Координаты нормируются по `imageWidth` и `imageHeight` к долям 0…1. Зоны камеры в cameras.json
заменяются целиком, прочие камеры и поля не трогаются.
"""

import argparse
import json
import sys
from pathlib import Path

from _common import ROOT, use_utf8_output

CAMERAS = ROOT / "data" / "seed" / "cameras.json"


def camera_code(annotation: dict, file: Path) -> str:
    """Код камеры: папка кадра в imagePath, иначе имя файла разметки."""
    parts = Path(annotation.get("imagePath", "").replace("\\", "/")).parts
    return parts[-2] if len(parts) >= 2 else file.stem


def zones(annotation: dict, file: Path) -> list[dict]:
    """Полигоны файла в формате cameras.json; ошибки разметки — с именем файла и меткой."""
    width, height = annotation["imageWidth"], annotation["imageHeight"]
    out = []
    for shape in annotation["shapes"]:
        label = shape["label"].strip()
        if shape.get("shape_type", "polygon") != "polygon":
            raise SystemExit(f"{file.name}: «{label}» — не полигон ({shape['shape_type']})")
        zone_type, _, name = label.partition(":")
        polygon = [
            [round(min(max(x / width, 0.0), 1.0), 4), round(min(max(y / height, 0.0), 1.0), 4)]
            for x, y in shape["points"]
        ]
        zone = {"zone_type": zone_type.strip().upper()}
        if name.strip():
            zone["name"] = name.strip()
        out.append(zone | {"polygon": polygon})
    return out


def main() -> int:
    use_utf8_output()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path, help="JSON-файлы LabelMe")
    args = parser.parse_args()

    spec = json.loads(CAMERAS.read_text(encoding="utf-8"))
    by_code = {camera["code"]: camera for camera in spec["cameras"]}
    for file in args.files:
        annotation = json.loads(file.read_text(encoding="utf-8"))
        code = camera_code(annotation, file)
        camera = by_code.get(code)
        if camera is None:
            camera = {"code": code, "zones": []}
            spec["cameras"].append(camera)
            by_code[code] = camera
        camera["zones"] = zones(annotation, file)
        print(f"{code:<14} зон {len(camera['zones'])} из {file.name}")
    CAMERAS.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"записано в {CAMERAS.relative_to(ROOT)}; типы зон проверит site-service при импорте")
    return 0


if __name__ == "__main__":
    sys.exit(main())
