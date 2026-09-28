"""Рамки open-vocabulary детектора на размеченной выборке → JSON для score.py и cascade.py.

    python ml/eval/predict.py --weights /models/yoloe-26m-seg.pt \
        --data ml/datasets/external/lct-test --prompts all

Запускается в образе vision-service (ml/README.md, «Обучение и оценка»). Словарь:
- first — первый промпт каждого класса, как у evaluate.py и в docs/metrics.md;
- all — все промпты equipment_classes.yaml, как в vision-service; синонимы одного класса
  схлопываются подавлением внутри класса, склейку разных классов делает score.py --merge.
Порог низкий (0,001), как у кривой PR: рабочий порог выбирает оценка, а не предсказание.

--multi-label повторяет валидацию Ultralytics (evaluate.py): одна рамка может прийти сразу
несколькими классами, у каждого свой балл. В сервисе у рамки один класс, поэтому по умолчанию
флаг выключен; с ним числа сверяются с docs/metrics.md.
"""

import argparse
import json
import statistics
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CLASSES = ROOT / "packages" / "contracts" / "equipment_classes.yaml"
# Подавление повторов внутри класса: как NMS Ultralytics при валидации.
NMS_IOU = 0.7


def vocabulary(mode: str) -> list[tuple[str, str]]:
    """Пары (промпт, код класса) словаря детектора."""
    classes = yaml.safe_load(CLASSES.read_text(encoding="utf-8"))["equipment_classes"]
    if mode == "first":
        return [(c["prompts"][0], c["code"]) for c in classes]
    return [(p, c["code"]) for c in classes for p in c["prompts"]]


def load_model(weights: str, prompts: list[str]):
    from ultralytics import YOLOE, YOLOWorld

    if "yoloe" in Path(weights).name:
        model = YOLOE(weights)
        model.set_classes(prompts, model.get_text_pe(prompts))
    else:
        model = YOLOWorld(weights)
        model.set_classes(prompts)
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--weights", required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--prompts", choices=["first", "all"], default="first")
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--conf", type=float, default=0.001)
    parser.add_argument("--multi-label", action="store_true", help="как валидация Ultralytics")
    parser.add_argument("--limit", type=int, help="не больше N снимков, равномерно по списку")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    import functools

    import torch
    from torchvision.ops import batched_nms
    from ultralytics.utils import nms

    if args.multi_label:
        nms.non_max_suppression = functools.partial(nms.non_max_suppression, multi_label=True)

    vocab = vocabulary(args.prompts)
    codes = sorted({code for _, code in vocab})
    model = load_model(args.weights, [p for p, _ in vocab])
    images = sorted((args.data / "images" / args.split).iterdir())
    if args.limit and len(images) > args.limit:
        images = images[:: -(-len(images) // args.limit)]
    result, times = {}, []
    for n, image in enumerate(images, 1):
        r = model.predict(
            str(image), imgsz=args.imgsz, conf=args.conf, iou=NMS_IOU, max_det=300, verbose=False
        )[0]
        times.append(r.speed["inference"])
        h, w = r.orig_shape
        xyxy, conf = r.boxes.xyxy.cpu(), r.boxes.conf.cpu()
        code_idx = torch.tensor([codes.index(vocab[int(c)][1]) for c in r.boxes.cls.tolist()])
        if args.prompts == "all" and len(conf):
            keep = batched_nms(xyxy, conf, code_idx, NMS_IOU)
            xyxy, conf, code_idx = xyxy[keep], conf[keep], code_idx[keep]
        result[image.stem] = {
            "width": w,
            "height": h,
            "boxes": [
                [codes[int(c)], round(float(s), 4), x1 / w, y1 / h, x2 / w, y2 / h]
                for (x1, y1, x2, y2), s, c in zip(xyxy.tolist(), conf, code_idx, strict=True)
            ],
        }
        if n % 25 == 0:
            print(f"{n}/{len(images)}", flush=True)

    mode = f"{args.prompts}-ml" if args.multi_label else args.prompts
    name = f"{Path(args.weights).stem}-{mode}-{args.data.name}-{args.split}"
    out = args.out or ROOT / "ml" / "runs" / "pred" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "weights": Path(args.weights).name,
        "prompts": args.prompts,
        "multi_label": args.multi_label,
        "imgsz": args.imgsz,
        # Первый снимок — прогрев, в медиану не идёт.
        "inference_ms_median": round(statistics.median(times[1:]), 1),
    }
    out.write_text(json.dumps({"meta": meta, "images": result}), encoding="utf-8")
    print(f"→ {out}, {meta}")


if __name__ == "__main__":
    main()
