"""Линейная голова классификатора вырезок для каскада (ml/eval/cascade.py) по открытым наборам.

    python ml/training/probe.py --clip ViT-B-32

Дообучение детектора на открытых наборах стирает классы, которых в них нет (docs/metrics.md,
§2). Голова учится на вырезках тех же наборов, но детектор не трогает, а сама стартует с
zero-shot весов по промптам и штрафуется за уход от них (L2-SP). Класс, которого в наборах
нет (каток, асфальтоукладчик, гусеничный кран), остаётся почти zero-shot, а не стирается.

Вырезки: рамки разметки train-частей Construction Equipment, KICT и Лимы. «Не техника» —
рамки-кандидаты YOLOE на тех же кадрах, которые не пересекаются с разметкой и названы
детектором классом, размеченным в этом наборе: иначе неразмеченный в наборе башенный кран
стал бы примером «не техники».
"""

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
# Соседний каталог, а не пакет: путь добавлен строкой выше.
from cascade import (
    BACKGROUND,
    CLASSES,
    CLIP_WEIGHTS,
    crops,
    embed,
    inside,
    iou,
    load_clip,
    to_pixels,
    zero_shot_head,
)

ROOT = Path(__file__).resolve().parents[2]
EXTERNAL = ROOT / "ml" / "datasets" / "external"
SOURCES = ("construction-equipment", "kict", "ulima")
# Мелкие рамки по вырезке не распознать: короче 32 px на кадре — не берём.
MIN_SIDE_PX = 32
# Вырезок одного класса из одного набора не больше этого: иначе самосвалы KICT задавят всё.
PER_CLASS = 600
# Кандидат «не техника» не пересекается с разметкой и не лежит в размеченной рамке.
FREE_IOU = 0.1
# «Не техника» — только кандидаты, которых детектор считает машиной хоть сколько-то уверенно:
# такие каскад и должен отсеивать; тот же порог, что у кандидатов в cascade.py.
NEGATIVE_CONF = 0.05


def truth_boxes(label: Path, codes: list[str]) -> list[tuple[str, list[float]]]:
    boxes = []
    for line in label.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            cls, cx, cy, w, h = line.split()
            cx, cy, w, h = map(float, (cx, cy, w, h))
            boxes.append((codes[int(cls)], [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]))
    return boxes


def gather(source: str, codes: list[str], proposals: dict, rng: random.Random) -> list:
    """(путь к кадру, рамка, код) одного набора: рамки разметки и «не техника»."""
    # Индекс кадров один раз: поиск по каталогу на каждый кадр через монтирование Docker
    # на Windows занимает минуты.
    images = {p.stem: p for p in (EXTERNAL / source / "images" / "train").iterdir()}
    by_class: dict[str, list] = defaultdict(list)
    annotated: set[str] = set()
    negatives = []
    for label in sorted((EXTERNAL / source / "labels" / "train").glob("*.txt")):
        image = images[label.stem]
        truth = truth_boxes(label, codes)
        annotated.update(code for code, _ in truth)
        for code, box in truth:
            by_class[code].append((image, box, code))
        for box in proposals.get(label.stem, {}).get("boxes", []):
            if box[1] < NEGATIVE_CONF:
                continue
            if all(iou(box[2:], t) < FREE_IOU and inside(box[2:], t) < 0.5 for _, t in truth):
                negatives.append((image, box[2:], box[0]))
    samples = []
    for code, items in by_class.items():
        if code == "person":
            continue
        rng.shuffle(items)
        samples += items[:PER_CLASS]
    negatives = [
        (im, b, BACKGROUND) for im, b, code in negatives if code in annotated and code != "person"
    ]
    rng.shuffle(negatives)
    return samples + negatives[:PER_CLASS]


def features(samples: list, model, size: int, device: str) -> list:
    """Эмбеддинг вырезки на каждую выборку; мелкие рамки — None. Кадр читается один раз."""
    by_image: dict[Path, list[int]] = defaultdict(list)
    for n, (image, _, _) in enumerate(samples):
        by_image[image].append(n)
    out: list = [None] * len(samples)
    for done, (image_path, idx) in enumerate(by_image.items(), 1):
        with Image.open(image_path) as image:
            w, h = image.size
            keep = [
                n for n in idx
                if min((samples[n][1][2] - samples[n][1][0]) * w,
                       (samples[n][1][3] - samples[n][1][1]) * h) >= MIN_SIDE_PX
            ]  # fmt: skip
            if not keep:
                continue
            pixels = to_pixels(image, model, device)
        emb = embed(model, crops(pixels, [samples[n][1] for n in keep], size)).cpu()
        for n, e in zip(keep, emb, strict=True):
            out[n] = e
        if done % 500 == 0:
            print(f"  кадров {done}/{len(by_image)}", flush=True)
    return out


def train_head(x, y, weight0, steps: int, l2sp: float):
    """Логистическая регрессия от zero-shot весов со штрафом за уход от них и весами классов."""
    import torch

    weight = weight0.clone().requires_grad_(True)
    bias = torch.zeros(weight0.shape[0], requires_grad=True)
    counts = torch.bincount(y, minlength=weight0.shape[0]).float()
    present = counts > 0
    class_weight = torch.where(present, counts.sum() / (counts.clamp(min=1) * present.sum()), 0)
    optimizer = torch.optim.Adam([weight, bias], lr=1e-2)
    loss_fn = torch.nn.CrossEntropyLoss(weight=class_weight)
    for _ in range(steps):
        optimizer.zero_grad()
        loss = loss_fn(x @ weight.T + bias, y) + l2sp * (weight - weight0).pow(2).sum()
        loss.backward()
        optimizer.step()
    return weight.detach(), bias.detach()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--clip", default="ViT-B-32", choices=list(CLIP_WEIGHTS))
    parser.add_argument("--proposals-dir", type=Path, default=ROOT / "ml" / "runs" / "pred")
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--l2sp", type=float, default=1e-3)
    args = parser.parse_args()

    import torch

    rng = random.Random(0)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    codes = [c["code"] for c in yaml.safe_load(CLASSES.read_text("utf-8"))["equipment_classes"]]
    model, tokenizer = load_clip(args.clip, device)
    size = model.visual.image_size
    size = size[0] if isinstance(size, tuple) else size
    head_codes, weight0, _ = zero_shot_head(model, tokenizer, "described", device)
    cache = ROOT / "ml" / "runs" / "probe" / f"crops-{args.clip}.pt"
    if cache.exists():
        x, y = torch.load(cache)
    else:
        samples = []
        for source in SOURCES:
            path = args.proposals_dir / f"yoloe-26m-seg-all-{source}-train.json"
            part = gather(source, codes, json.loads(path.read_text("utf-8"))["images"], rng)
            print(source, dict(Counter(code for _, _, code in part)), flush=True)
            samples += part
        feats = features(samples, model, size, device)
        pairs = [
            (f, head_codes.index(s[2]))
            for f, s in zip(feats, samples, strict=True)
            if f is not None
        ]
        x = torch.stack([f for f, _ in pairs])
        y = torch.tensor([c for _, c in pairs])
        cache.parent.mkdir(parents=True, exist_ok=True)
        torch.save((x, y), cache)
    print("вырезок по классам:", {head_codes[k]: v for k, v in sorted(Counter(y.tolist()).items())})
    weight, bias = train_head(x, y, weight0.cpu(), args.steps, args.l2sp)
    accuracy = float(((x @ weight.T + bias).argmax(dim=1) == y).float().mean())
    out = cache.parent / f"head-{args.clip}-l2sp{args.l2sp:g}.pt"
    torch.save({"codes": head_codes, "weight": weight, "bias": bias}, out)
    print(f"→ {out}; точность на обучающих вырезках {accuracy:.3f}")


if __name__ == "__main__":
    main()
