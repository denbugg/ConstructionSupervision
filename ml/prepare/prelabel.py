"""Шаг 2 авторазметки: класс рамки называет Gemma по вырезке, итог — LabelMe на проверку.

    python ml/prepare/prelabel.py            # detections.json → lct-test/review
    python ml/prepare/prelabel.py --force    # перезаписать уже проверенные файлы

Рамки-кандидаты даёт YOLOE (шаг 1, detect_open_vocab.py): машины он находит, но названия
путает и ловит столбы и дома. Поэтому каждая рамка вырезается с полями и уходит в Gemma 4 E4B
со зрением (llama-server с `--mmproj`, runbook, раздел 4). Модель выбирает одно название из
equipment_classes.yaml или «не техника»; ответ ограничен JSON-схемой, свободного текста нет.
Затем рамки одного класса, накрывающие одну машину, склеиваются.

Итог — JSON формата LabelMe рядом с копией снимка, подписи — русские названия классов.
Копия исходной авторазметки кладётся в `lct-test/prelabel/`: по ней потом видно, сколько
рамок человек удалил, добавил и переименовал. Это число идёт в docs/metrics.md рядом с
метриками — тест, размеченный с подсказки моделей, без него был бы нечестным.
"""

import argparse
import base64
import io
import json
import shutil
import sys
from pathlib import Path

import httpx
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "ml" / "datasets" / "lct-raw"
OUT = ROOT / "ml" / "datasets" / "lct-test"
CLASSES = ROOT / "packages" / "contracts" / "equipment_classes.yaml"
SKIP = {"person"}
NOT_MACHINE = "не техника"
LABELME_VERSION = "5.5.0"
# Рамка больше половины кадра — это «вся стройка», а не машина.
MAX_AREA = 0.5
# Поля вокруг рамки: по кузову без стрелы и гусениц класс не угадать.
CROP_MARGIN = 0.15
CROP_SIDE = 512
# Рамки одного класса с таким перекрытием — одна машина; так же и рамка, лежащая в другой
# этой долей своей площади (часть машины: стрела, кабина, мачта).
SAME_MACHINE_IOU = 0.5
PART_INSIDE = 0.7
PROMPT = (
    "На вырезке со снимка стройки — объект. Что это? Выбери ровно один вариант из списка. "
    "Если это не строительная машина (дом, столб, забор, бытовка, контейнер, человек, часть "
    "машины без самой машины) — «не техника». Буровая установка для свай с высокой мачтой — "
    "«Буровая/сваебойная установка», а не кран. Варианты: "
)


def load_names() -> dict[str, str]:
    """Код класса → русское название, в порядке файла; без людей."""
    data = yaml.safe_load(CLASSES.read_text(encoding="utf-8"))
    return {c["code"]: c["name_ru"] for c in data["equipment_classes"] if c["code"] not in SKIP}


def crop_uri(image: Image.Image, bbox: list[float]) -> str:
    width, height = image.size
    x1, y1, x2, y2 = bbox
    mx, my = (x2 - x1) * CROP_MARGIN, (y2 - y1) * CROP_MARGIN
    crop = image.crop(
        (
            max(0, (x1 - mx) * width),
            max(0, (y1 - my) * height),
            min(width, (x2 + mx) * width),
            min(height, (y2 + my) * height),
        )
    )
    crop.thumbnail((CROP_SIDE, CROP_SIDE))
    buffer = io.BytesIO()
    crop.save(buffer, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def classify(client: httpx.Client, url: str, uri: str, options: list[str]) -> str | None:
    """Название класса или «не техника» — один вариант из списка, по JSON-схеме.

    None — модель дважды не дала разборчивого ответа: схема допускает пробелы, и маленькая
    модель иногда тратит на них весь лимит токенов. Тогда решает человек.
    """
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string", "enum": options}},
        "required": ["answer"],
    }
    for temperature in (0.0, 0.4):
        response = client.post(
            url,
            json={
                "model": "local",
                "temperature": temperature,
                "max_tokens": 60,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "answer", "schema": schema},
                },
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": uri}},
                            {"type": "text", "text": PROMPT + "; ".join(options)},
                        ],
                    }
                ],
            },
        )
        response.raise_for_status()
        try:
            return json.loads(response.json()["choices"][0]["message"]["content"])["answer"]
        except (ValueError, KeyError):
            continue
    return None


def iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def inside(inner: list[float], outer: list[float]) -> float:
    """Какая доля рамки inner лежит внутри outer."""
    ix = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0]))
    iy = max(0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return ix * iy / area if area else 0.0


def merge(boxes: list[dict]) -> list[dict]:
    """Одна машина — одна рамка.

    YOLOE ставит рамки и на всю машину, и на её части: стрелу, кабину, мачту буровой. Рамка
    одного класса, сильно перекрытая другой или лежащая в ней почти целиком, — та же машина;
    остаётся внешняя, потому что проверяющему проще сузить рамку, чем собрать её из кусков.
    """
    kept: list[dict] = []
    for box in sorted(boxes, key=lambda b: -_area(b["bbox"])):
        same = [k["bbox"] for k in kept if k["label"] == box["label"]]
        if not any(
            iou(k, box["bbox"]) > SAME_MACHINE_IOU or inside(box["bbox"], k) >= PART_INSIDE
            for k in same
        ):
            kept.append(box)
    return kept


def _area(bbox: list[float]) -> float:
    return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])


def labelme(image: Path, width: int, height: int, boxes: list[dict]) -> dict:
    return {
        "version": LABELME_VERSION,
        "flags": {},
        "shapes": [
            {
                "label": b["label"],
                "points": [
                    [b["bbox"][0] * width, b["bbox"][1] * height],
                    [b["bbox"][2] * width, b["bbox"][3] * height],
                ],
                "group_id": None,
                "description": (
                    f"авто: YOLOE {b['code']} {b['conf']:.2f}; Gemma не ответила — проверить"
                    if b.get("unsure")
                    else f"авто: YOLOE {b['code']} {b['conf']:.2f}, Gemma — {b['label']}"
                ),
                "shape_type": "rectangle",
                "flags": {},
            }
            for b in boxes
        ],
        "imagePath": image.name,
        "imageData": None,
        "imageHeight": height,
        "imageWidth": width,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--llm", default="http://127.0.0.1:8091/v1/chat/completions")
    parser.add_argument("--force", action="store_true", help="перезаписать проверенные файлы")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    names = load_names()
    options = [*names.values(), NOT_MACHINE]
    detections = json.loads((OUT / "detections.json").read_text(encoding="utf-8"))
    review, prelabel = OUT / "review", OUT / "prelabel"
    review.mkdir(parents=True, exist_ok=True)
    prelabel.mkdir(parents=True, exist_ok=True)
    # Список подписей для LabelMe: выбор из списка вместо ввода с клавиатуры.
    (OUT / "labels.txt").write_text("\n".join(names.values()) + "\n", encoding="utf-8")

    counts: dict[str, int] = {}
    dropped = skipped = unsure = 0
    with httpx.Client(timeout=120) as client:
        for n, (file_name, found) in enumerate(sorted(detections.items()), 1):
            image_path = RAW / file_name
            target = review / f"{image_path.stem}.json"
            if target.exists() and not args.force:
                skipped += 1  # уже проверено человеком — не затираем его правки
                continue
            image = Image.open(image_path).convert("RGB")
            boxes = []
            for box in found["boxes"]:
                x1, y1, x2, y2 = box["bbox"]
                if (x2 - x1) * (y2 - y1) > MAX_AREA:
                    dropped += 1
                    continue
                label = classify(client, args.llm, crop_uri(image, box["bbox"]), options)
                if label == NOT_MACHINE:
                    dropped += 1
                    continue
                if label is None:
                    unsure += 1
                    boxes.append({**box, "label": names[box["code"]], "unsure": True})
                    continue
                boxes.append({**box, "label": label})
            boxes = merge(boxes)
            doc = labelme(image_path, found["width"], found["height"], boxes)
            shutil.copy2(image_path, review / image_path.name)
            text = json.dumps(doc, ensure_ascii=False, indent=2)
            target.write_text(text, encoding="utf-8")
            (prelabel / target.name).write_text(text, encoding="utf-8")
            for b in boxes:
                counts[b["label"]] = counts.get(b["label"], 0) + 1
            print(f"[{n}/{len(detections)}] {file_name}: рамок {len(boxes)}", flush=True)

    print(
        f"\nГотово: отброшено кандидатов {dropped}, без ответа Gemma {unsure}, "
        f"пропущено проверенных снимков {skipped}."
    )
    for label, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {label}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
