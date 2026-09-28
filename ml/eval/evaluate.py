"""Метрики детектора на размеченной выборке: precision / recall / mAP50 по классам.

    python ml/eval/evaluate.py --weights data/models/yolov8s-worldv2.pt \
        --data ml/datasets/external/ulima/data-world.yaml --split test

Одинаково для zero-shot и дообученных весов, чтобы в docs/metrics.md шли обе колонки
(ml/README.md, «Метрики»). У YOLO-World словарь задаётся именами классов датасета — в
data-world.yaml это первые промпты классов из equipment_classes.yaml.
Печатает две таблицы Markdown — метрики и ошибки по классам; картинки матрицы ошибок —
в ml/runs/eval/<имя>/.

--min-side N считает без мелких машин: рамки короче N пикселей по меньшей стороне (на входе
детектора) убираются и из разметки, и из ответа модели. Иначе найденная мелкая машина,
которой нет в разметке, считалась бы ложной (ml/README.md, «Разметка тестового набора»).
"""

import argparse
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]


def markdown_table(names: dict[int, str], counts: dict[int, int], metrics) -> str:
    """Строка на класс и итог: число рамок в выборке, P, R, mAP50, mAP50-95."""
    lines = [
        "| Класс | Рамок | Precision | Recall | mAP50 | mAP50-95 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
    ]
    box = metrics.box
    for row, cls in enumerate(box.ap_class_index):
        p, r, ap50, ap = box.class_result(row)
        lines.append(f"| {names[int(cls)]} | {counts.get(int(cls), 0)} | {p:.2f} | {r:.2f} | "
                     f"{ap50:.2f} | {ap:.2f} |")  # fmt: skip
    lines.append(f"| **все** | {sum(counts.values())} | {box.mp:.2f} | {box.mr:.2f} | "
                 f"{box.map50:.2f} | {box.map:.2f} |")  # fmt: skip
    return "\n".join(lines)


def errors_table(names: dict[int, str], matrix: np.ndarray, conf: float) -> str:
    """Матрица ошибок строкой на класс: найдено верно, другим классом, пропущено, ложных.

    matrix[предсказание, разметка]; последняя строка и столбец — фон.
    """
    nc = len(names)
    lines = [
        f"Ошибки при пороге уверенности {conf:g}, совпадение рамок IoU > 0,45:",
        "",
        "| Класс | Рамок | Верно | Другим классом | Пропущено | Ложных |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for c in range(nc):
        total, false = int(matrix[:, c].sum()), int(matrix[c, nc])
        if not total and not false:
            continue
        wrong = {names[p]: int(matrix[p, c]) for p in range(nc) if p != c and matrix[p, c]}
        wrong_text = ", ".join(f"{k} {v}" for k, v in sorted(wrong.items(), key=lambda kv: -kv[1]))
        lines.append(f"| {names[c]} | {total} | {int(matrix[c, c])} | {wrong_text or 0} | "
                     f"{int(matrix[nc, c])} | {false} |")  # fmt: skip
    return "\n".join(lines)


def validator_class(base, min_side: float, errors_conf: float):
    """Валидатор с порогом матрицы ошибок errors_conf, не видящий рамок короче min_side.

    Мелкие рамки убираются и из разметки, и из ответа модели; при min_side = 0 не убирается ничего.
    """

    def large(xyxy):
        return (xyxy[:, 2:4] - xyxy[:, 0:2]).min(dim=1).values >= min_side

    class Validator(base):
        def init_metrics(self, model):
            super().init_metrics(model)
            # Кривая PR строится от 0,001, а матрица ошибок имеет смысл только при рабочем пороге.
            self.confusion_matrix_conf = errors_conf

        def _prepare_batch(self, si, batch):
            pbatch = super()._prepare_batch(si, batch)
            if pbatch["cls"].shape[0]:
                keep = large(pbatch["bboxes"])
                pbatch["cls"], pbatch["bboxes"] = pbatch["cls"][keep], pbatch["bboxes"][keep]
            return pbatch

        def postprocess(self, preds):
            return [
                {k: v[large(p["bboxes"])] for k, v in p.items()} for p in super().postprocess(preds)
            ]

    return Validator


def run_name(weights: Path) -> str:
    """Имя для отчёта: у весов из ml/runs/<прогон>/weights/ файл всегда last.pt или best.pt."""
    return weights.parent.parent.name if weights.parent.name == "weights" else weights.stem


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--weights", required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--conf", type=float, default=0.001, help="порог для кривой PR, не рабочий")
    parser.add_argument("--min-side", type=float, default=0, help="без рамок короче N px входа")
    # 0,35 — VISION_DET_CONF в .env.example, рабочий порог vision-service.
    parser.add_argument("--errors-conf", type=float, default=0.35, help="порог матрицы ошибок")
    args = parser.parse_args()

    from ultralytics import YOLO, YOLOWorld
    from ultralytics.models.yolo.detect import DetectionValidator

    names = yaml.safe_load(args.data.read_text(encoding="utf-8"))["names"]
    if "world" in Path(args.weights).name:
        model = YOLOWorld(args.weights)
        model.set_classes(list(names.values()))
    else:
        model = YOLO(args.weights)
    finished = {}
    model.add_callback("on_val_end", lambda validator: finished.update(validator=validator))
    name = f"{run_name(Path(args.weights))}-{args.split}"
    metrics = model.val(
        validator=validator_class(DetectionValidator, args.min_side, args.errors_conf),
        data=str(args.data),
        split=args.split,
        imgsz=args.imgsz,
        conf=args.conf,
        batch=4,
        project=str(ROOT / "ml" / "runs" / "eval"),
        name=f"{name}-min{args.min_side:g}" if args.min_side else name,
        exist_ok=True,
        plots=True,
        verbose=False,
    )
    validator = finished["validator"]
    matrix = validator.confusion_matrix.matrix
    # Каждая рамка разметки попадает в матрицу ровно раз — верно, другим классом или пропуском.
    counts = {c: int(matrix[:, c].sum()) for c in range(len(names))}
    small = f", без рамок короче {args.min_side:g} px" if args.min_side else ""
    print(f"\n{args.weights} на {args.data.parent.name}/{args.split}, вход {args.imgsz}{small}\n")
    print(markdown_table(names, counts, metrics))
    print()
    print(errors_table(names, matrix, validator.confusion_matrix_conf))


if __name__ == "__main__":
    main()
