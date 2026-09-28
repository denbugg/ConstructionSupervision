"""Метрики любого конвейера распознавания по JSON рамок: mAP50 и счёт ошибок при порогах.

    python ml/eval/score.py ml/runs/pred/<имя>.json --data ml/datasets/external/lct-test

evaluate.py умеет оценивать только модель Ultralytics целиком. Каскад «детектор + классификатор
вырезки» и смешанные веса дают рамки другим путём, поэтому оценка отделена от предсказания:
predict.py и cascade.py пишут рамки в JSON, этот скрипт считает по ним то же, что evaluate.py.
Правила счёта повторяют Ultralytics, чтобы числа совпадали с docs/metrics.md:
- mAP50 — сопоставление рамок одного класса по IoU ≥ 0,5, 101 точка кривой, среднее по классам
  разметки;
- ошибки при пороге — сопоставление без учёта класса по IoU > 0,45, как матрица ошибок.
Рамки людей не считаются: на снимках организаторов людей не размечали.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
CLASSES = ROOT / "packages" / "contracts" / "equipment_classes.yaml"
SKIP = {"person"}
MAP_IOU = 0.5
# Матрица ошибок Ultralytics: совпадение рамок при IoU строго больше 0,45.
MATRIX_IOU = 0.45
# Класс с таким числом рамок и больше входит в «mAP50 по крупным классам».
MAJOR_MIN = 10


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU каждой рамки a с каждой рамкой b, рамки [x1, y1, x2, y2]."""
    if not len(a) or not len(b):
        return np.zeros((len(a), len(b)))
    lt = np.maximum(a[:, None, :2], b[None, :, :2])
    rb = np.minimum(a[:, None, 2:], b[None, :, 2:])
    inter = np.clip(rb - lt, 0, None).prod(axis=2)
    area_a = (a[:, 2:] - a[:, :2]).prod(axis=1)
    area_b = (b[:, 2:] - b[:, :2]).prod(axis=1)
    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-9)


def unique_matches(iou: np.ndarray, allowed: np.ndarray) -> list[tuple[int, int]]:
    """Пары (разметка, ответ) жадно от наибольшего IoU, каждая рамка — не больше одного раза."""
    gi, pi = np.nonzero(allowed)
    order = np.argsort(-iou[gi, pi], kind="stable")
    used_g, used_p, pairs = set(), set(), []
    for k in order:
        g, p = int(gi[k]), int(pi[k])
        if g in used_g or p in used_p:
            continue
        used_g.add(g)
        used_p.add(p)
        pairs.append((g, p))
    return pairs


def load_truth(data: Path, split: str, codes: list[str]) -> dict[str, list]:
    """Разметка YOLO → {снимок: [(код, [x1, y1, x2, y2]), ...]} в долях кадра."""
    truth = {}
    for path in sorted((data / "labels" / split).glob("*.txt")):
        boxes = []
        for line in path.read_text(encoding="utf-8").split("\n"):
            if not line.strip():
                continue
            cls, cx, cy, w, h = line.split()
            cx, cy, w, h = map(float, (cx, cy, w, h))
            code = codes[int(cls)]
            if code not in SKIP:
                boxes.append((code, [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]))
        truth[path.stem] = boxes
    return truth


def merge_across_classes(boxes: list, iou_threshold: float) -> list:
    """Склейка как в vision-service: одна рамка на объект, остаётся самая уверенная."""
    kept: list = []
    for box in sorted(boxes, key=lambda b: -b[1]):
        arr = np.array([box[2:]])
        if kept and iou_matrix(np.array([k[2:] for k in kept]), arr).max() > iou_threshold:
            continue
        kept.append(box)
    return kept


def average_precision(tp: np.ndarray, conf: np.ndarray, n_truth: int) -> float:
    """AP по 101 точке огибающей кривой precision-recall, как в Ultralytics."""
    if not n_truth or not len(tp):
        return 0.0
    order = np.argsort(-conf, kind="stable")
    tpc = np.cumsum(tp[order])
    fpc = np.cumsum(1 - tp[order])
    recall = tpc / n_truth
    precision = tpc / (tpc + fpc)
    mrec = np.concatenate(([0.0], recall, [1.0]))
    mpre = np.concatenate(([1.0], precision, [0.0]))
    mpre = np.flip(np.maximum.accumulate(np.flip(mpre)))
    x = np.linspace(0, 1, 101)
    return float(np.trapezoid(np.interp(x, mrec, mpre), x))


def map50(truth: dict, preds: dict) -> dict[str, float]:
    """AP50 по классам разметки."""
    tp, conf, cls = [], [], []
    n_truth = Counter(code for boxes in truth.values() for code, _ in boxes)
    for stem, gt in truth.items():
        pr = preds.get(stem, [])
        if not pr:
            continue
        g = np.array([b for _, b in gt]).reshape(-1, 4)
        p = np.array([b[2:] for b in pr]).reshape(-1, 4)
        iou = iou_matrix(g, p)
        same = np.array([[gc == b[0] for b in pr] for gc, _ in gt], dtype=bool)
        same = same.reshape(len(gt), len(pr))
        hit = np.zeros(len(pr))
        for _, j in unique_matches(iou, (iou >= MAP_IOU) & same):
            hit[j] = 1
        tp.extend(hit)
        conf.extend(b[1] for b in pr)
        cls.extend(b[0] for b in pr)
    tp, conf, cls = np.array(tp), np.array(conf), np.array(cls)
    return {
        code: average_precision(tp[cls == code], conf[cls == code], n)
        for code, n in sorted(n_truth.items(), key=lambda kv: -kv[1])
    }


def errors(truth: dict, preds: dict, threshold: float) -> dict:
    """Верно / другим классом / пропущено по классам разметки и ложные по классам ответа."""
    right, wrong, missed, false = Counter(), Counter(), Counter(), Counter()
    confused: dict[str, Counter] = defaultdict(Counter)
    for stem, gt in truth.items():
        pr = [b for b in preds.get(stem, []) if b[1] > threshold]
        g = np.array([b for _, b in gt]).reshape(-1, 4)
        p = np.array([b[2:] for b in pr]).reshape(-1, 4)
        iou = iou_matrix(g, p)
        pairs = unique_matches(iou, iou > MATRIX_IOU)
        matched_g = dict(pairs)
        for i, (code, _) in enumerate(gt):
            if i not in matched_g:
                missed[code] += 1
            elif pr[matched_g[i]][0] == code:
                right[code] += 1
            else:
                wrong[code] += 1
                confused[code][pr[matched_g[i]][0]] += 1
        matched_p = set(matched_g.values())
        for j, box in enumerate(pr):
            if j not in matched_p:
                false[box[0]] += 1
    return {"right": right, "wrong": wrong, "missed": missed, "false": false, "confused": confused}


def at_budget(truth: dict, preds: dict, budget: int) -> tuple[float, int, int]:
    """Самый низкий порог, при котором ложных не больше budget: (порог, верно, ложных).

    Сравнение конвейеров при одном рабочем пороге нечестно: у каскада уверенность — другая
    шкала. «Сколько машин найдено верно, если ложных не больше N» от шкалы не зависит.
    """
    best = (1.0, 0, 0)
    for threshold in np.round(np.arange(0.95, 0.0, -0.01), 2):
        result = errors(truth, preds, float(threshold))
        n_false = sum(result["false"].values())
        if n_false > budget:
            break
        best = (float(threshold), sum(result["right"].values()), n_false)
    return best


def report(truth: dict, preds: dict, thresholds: list[float], budgets: list[int]) -> str:
    n_truth = Counter(code for boxes in truth.values() for code, _ in boxes)
    ap = map50(truth, preds)
    lines = ["| Класс | Рамок | AP50 | " + " | ".join(f"верно@{t:g}" for t in thresholds) + " |"]
    lines.append("| :--- | ---: | ---: |" + " ---: |" * len(thresholds))
    per_threshold = [errors(truth, preds, t) for t in thresholds]
    for code, n in sorted(n_truth.items(), key=lambda kv: -kv[1]):
        cells = " | ".join(str(r["right"][code]) for r in per_threshold)
        lines.append(f"| {code} | {n} | {ap[code]:.2f} | {cells} |")
    total = sum(n_truth.values())
    cells = " | ".join(str(sum(r["right"].values())) for r in per_threshold)
    lines.append(f"| **все** | {total} | **{np.mean(list(ap.values())):.3f}** | {cells} |")
    lines.append("")
    lines.append("| Порог | Верно | Другим классом | Пропущено | Ложных | Ложные по классам |")
    lines.append("| ---: | ---: | ---: | ---: | ---: | :--- |")
    for t, r in zip(thresholds, per_threshold, strict=True):
        top = ", ".join(f"{k} {v}" for k, v in r["false"].most_common(4))
        lines.append(
            f"| {t:g} | {sum(r['right'].values())} | {sum(r['wrong'].values())} | "
            f"{sum(r['missed'].values())} | {sum(r['false'].values())} | {top} |"
        )
    lines.append("")
    budget_cells = []
    for budget in budgets:
        threshold, right, _ = at_budget(truth, preds, budget)
        budget_cells.append(f"≤{budget} ложных: {right} верно (порог {threshold:g})")
    lines.append("; ".join(budget_cells))
    return "\n".join(lines)


def summary_row(name: str, meta: dict, truth: dict, preds: dict, budgets: list[int]) -> str:
    """Строка сводной таблицы: mAP50, ошибки при рабочем пороге 0,35, верные при бюджете ложных."""
    ap = map50(truth, preds)
    n_truth = Counter(code for boxes in truth.values() for code, _ in boxes)
    # Классы с 1–6 рамками дают AP 0 или 1 случайно и весят в среднем столько же, сколько
    # экскаватор с 243 рамками; среднее по крупным классам меньше шумит.
    major = [ap[c] for c, n in n_truth.items() if n >= MAJOR_MIN]
    r = errors(truth, preds, 0.35)
    cells = [f"{at_budget(truth, preds, b)[1]}" for b in budgets]
    ms = meta.get("inference_ms_median", "")
    extra = meta.get("classifier_ms_median")
    ms = f"{ms} + {extra}" if extra is not None else ms
    return (
        f"| {name} | {np.mean(list(ap.values())):.3f} | {np.mean(major):.3f} | "
        f"{sum(r['right'].values())} | "
        f"{sum(r['wrong'].values())} | {sum(r['missed'].values())} | "
        f"{sum(r['false'].values())} | " + " | ".join(cells) + f" | {ms} |"
    )


def load_preds(path: Path, merge_iou: float | None, allowed: set | None) -> tuple[dict, dict]:
    """Рамки из JSON без людей; allowed — оставить только эти классы (до склейки)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    preds = {}
    for stem, item in doc["images"].items():
        boxes = [
            b for b in item["boxes"] if b[0] not in SKIP and (allowed is None or b[0] in allowed)
        ]
        preds[stem] = merge_across_classes(boxes, merge_iou) if merge_iou else boxes
    return doc.get("meta", {}), preds


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("preds", type=Path, nargs="+")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--thresholds", default="0.2,0.35,0.5")
    parser.add_argument("--budgets", default="20,50,100")
    parser.add_argument("--merge", type=float, help="склейка рамок разных классов, как в сервисе")
    parser.add_argument("--only", help="только эти классы разметки через запятую")
    parser.add_argument("--agnostic", action="store_true", help="без классов: только «нашёл ли»")
    parser.add_argument("--summary", action="store_true", help="строка на файл вместо таблиц")
    # В Лиме размечены 8 классов: фургон на её кадре настоящий, но в разметке его нет, и
    # рамка «малотоннажный грузовик» считалась бы ложной.
    parser.add_argument(
        "--truth-classes",
        action="store_true",
        help="только ответы классов, которые есть в разметке",
    )
    args = parser.parse_args()

    codes = [c["code"] for c in yaml.safe_load(CLASSES.read_text("utf-8"))["equipment_classes"]]
    truth = load_truth(args.data, args.split, codes)
    if args.agnostic:
        truth = {k: [("machine", b) for _, b in v] for k, v in truth.items()}
    if args.only:
        keep = set(args.only.split(","))
        truth = {k: [b for b in v if b[0] in keep] for k, v in truth.items()}
    thresholds = [float(t) for t in args.thresholds.split(",")]
    budgets = [int(b) for b in args.budgets.split(",")]
    labelled = {code for boxes in truth.values() for code, _ in boxes}
    allowed = labelled if args.truth_classes else None
    if args.summary:
        print(
            f"| Конвейер | mAP50 | mAP50, классы ≥{MAJOR_MIN} | Верно@0,35 | Другим классом | "
            "Пропущено | Ложных | "
            + " | ".join(f"Верно при ≤{b} ложных" for b in budgets)
            + " | мс |"
        )
        print("| :--- |" + " ---: |" * (7 + len(budgets)))
    for path in args.preds:
        meta, preds = load_preds(path, args.merge, allowed)
        if args.agnostic:
            preds = {k: [["machine", *b[1:]] for b in v] for k, v in preds.items()}
        if args.summary:
            name = path.stem.replace(f"-{args.data.name}-{args.split}", "")
            print(summary_row(name, meta, truth, preds, budgets), flush=True)
            continue
        merged = f", склейка IoU > {args.merge:g}" if args.merge else ""
        print(f"\n### {path.stem}{merged}\n")
        if meta:
            print(", ".join(f"{k}: {v}" for k, v in meta.items()) + "\n")
        print(report(truth, preds, thresholds, budgets))


if __name__ == "__main__":
    main()
