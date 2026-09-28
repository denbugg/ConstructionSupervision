"""Шаг 1 авторазметки: рамки-кандидаты open-vocabulary детектором YOLOE (H5).

Запускается в образе vision-service, где есть Ultralytics (ml/README.md, «Обучение и оценка»):

    docker run --rm --gpus all -v "${PWD}:/repo" -v "${PWD}/data/models:/models" -w /repo \
      --entrypoint python <образ vision> ml/prepare/detect_open_vocab.py

YOLOE, а не наш детектор: подсказки для тестового набора не должна давать модель, которую на
нём потом оценивают, иначе тест подыгрывает ей. К тому же дообученный на Лиме YOLO-World на
снимках организаторов экскаваторы не находит вовсе. YOLOE хорошо находит машины, но путает
их названия и ловит столбы и дома — поэтому класс назначает шаг 2 (prelabel.py).
Словарь — все промпты классов из equipment_classes.yaml, кроме людей.
"""

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "ml" / "datasets" / "lct-raw"
OUT = ROOT / "ml" / "datasets" / "lct-test" / "detections.json"
CLASSES = ROOT / "packages" / "contracts" / "equipment_classes.yaml"
SKIP = {"person"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--weights", default="/models/yoloe-26m-seg.pt")
    # Низкий порог: пропущенную машину человек заметит хуже, чем лишнюю рамку.
    parser.add_argument("--conf", type=float, default=0.3)
    parser.add_argument("--imgsz", type=int, default=1280)
    args = parser.parse_args()

    from ultralytics import YOLOE

    classes = yaml.safe_load(CLASSES.read_text(encoding="utf-8"))["equipment_classes"]
    prompts = [(p, c["code"]) for c in classes if c["code"] not in SKIP for p in c["prompts"]]
    model = YOLOE(args.weights)
    texts = [p for p, _ in prompts]
    model.set_classes(texts, model.get_text_pe(texts))

    result = {}
    images = sorted(p for p in RAW.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    for image in images:
        r = model.predict(str(image), conf=args.conf, imgsz=args.imgsz, verbose=False)[0]
        h, w = r.orig_shape
        boxes = [
            {
                "code": prompts[int(cls)][1],
                "conf": round(conf, 3),
                "bbox": [x1 / w, y1 / h, x2 / w, y2 / h],
            }
            for (x1, y1, x2, y2), conf, cls in zip(
                r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist(), strict=True
            )
        ]
        result[image.name] = {"width": w, "height": h, "boxes": boxes}
        print(f"{image.name}: {len(boxes)}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
