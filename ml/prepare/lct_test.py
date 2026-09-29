"""Проверенная разметка снимков организаторов → тестовый набор YOLO и счёт правок.

    python ml/prepare/lct_test.py     # lct-test/review → external/lct-test

В набор идут только снимки, отмеченные в LabelMe флажком «проверено»: неотмеченный файл
неотличим от нетронутой авторазметки, а непроверенная подсказка модели в тесте — подлог.
Подписи — русские названия классов, номера — места классов в equipment_classes.yaml, как у
датасета Лимы (ulima.py), поэтому evaluate.py работает с набором без изменений.

Печатает, сколько рамок авторазметки человек оставил, переименовал, удалил и сколько
добавил сам. Эти числа идут в docs/metrics.md: они показывают, насколько тест зависит от
подсказок моделей.
"""

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
# Соседний скрипт, а не пакет: путь добавлен строкой выше.
from prelabel import iou

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ml" / "datasets" / "lct-test"
OUT = ROOT / "ml" / "datasets" / "external" / "lct-test"
CLASSES = ROOT / "packages" / "contracts" / "equipment_classes.yaml"
REVIEWED = "проверено"
# Совпадение рамки проверки с рамкой авторазметки — «та же машина».
SAME_BOX_IOU = 0.5
MAX_SIDE = 1280


def boxes(doc: dict) -> list[tuple[str, list[float]]]:
    """Прямоугольники LabelMe → (подпись, [x1, y1, x2, y2] в долях кадра)."""
    width, height = doc["imageWidth"], doc["imageHeight"]
    out = []
    for shape in doc["shapes"]:
        if shape.get("shape_type") != "rectangle":
            continue
        (ax, ay), (bx, by) = shape["points"]
        out.append(
            (
                shape["label"].strip(),
                [
                    min(ax, bx) / width,
                    min(ay, by) / height,
                    max(ax, bx) / width,
                    max(ay, by) / height,
                ],
            )
        )
    return out


def compare(before: list, after: list) -> Counter:
    """Правки человека: сопоставление рамок по перекрытию, жадно от лучшего."""
    pairs = sorted(
        ((iou(b[1], a[1]), i, j) for i, b in enumerate(before) for j, a in enumerate(after)),
        reverse=True,
    )
    used_b, used_a, stats = set(), set(), Counter()
    for overlap, i, j in pairs:
        if overlap < SAME_BOX_IOU or i in used_b or j in used_a:
            continue
        used_b.add(i)
        used_a.add(j)
        stats["оставлено" if before[i][0] == after[j][0] else "переименовано"] += 1
    stats["удалено"] += len(before) - len(used_b)
    stats["добавлено"] += len(after) - len(used_a)
    return stats


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    classes = yaml.safe_load(CLASSES.read_text(encoding="utf-8"))["equipment_classes"]
    index = {c["name_ru"]: i for i, c in enumerate(classes)}

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "images" / "test").mkdir(parents=True)
    (OUT / "labels" / "test").mkdir(parents=True)

    edits, per_class, unknown = Counter(), Counter(), Counter()
    reviewed = pending = 0
    for path in sorted((SOURCE / "review").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not doc.get("flags", {}).get(REVIEWED):
            pending += 1
            continue
        reviewed += 1
        after = boxes(doc)
        before_path = SOURCE / "prelabel" / path.name
        if before_path.exists():
            edits += compare(boxes(json.loads(before_path.read_text(encoding="utf-8"))), after)
        lines = []
        for label, (x1, y1, x2, y2) in after:
            if label not in index:
                unknown[label] += 1
                continue
            per_class[classes[index[label]]["code"]] += 1
            cx, cy, w, h = (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
            lines.append(f"{index[label]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
        with Image.open(SOURCE / "review" / doc["imagePath"]) as image:
            image = image.convert("RGB")
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            image.save(OUT / "images" / "test" / f"{path.stem}.jpg", quality=92)
        (OUT / "labels" / "test" / f"{path.stem}.txt").write_text(
            "\n".join(lines) + "\n" if lines else "", encoding="utf-8"
        )

    # train и val обязательны для Ultralytics; набор только тестовый, поэтому все три — test.
    for name, names in (
        ("data.yaml", [c["code"] for c in classes]),
        ("data-world.yaml", [c["prompts"][0] for c in classes]),
    ):
        data = {"train": "images/test", "val": "images/test", "test": "images/test"}
        data["names"] = dict(enumerate(names))
        (OUT / name).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), "utf-8")

    print(f"Снимков проверено: {reviewed}, ещё не проверено: {pending}")
    print("Рамок по классам: " + ", ".join(f"{k} {v}" for k, v in per_class.most_common()))
    print("Правки авторазметки: " + ", ".join(f"{k} {v}" for k, v in edits.items()))
    if unknown:
        print(
            "Неизвестные подписи пропущены: " + ", ".join(f"«{k}» {v}" for k, v in unknown.items())
        )
    print(f"→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
