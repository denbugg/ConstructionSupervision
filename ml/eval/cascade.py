"""Каскад «найти → назвать»: рамки детектора, класс — CLIP по вырезке. JSON для score.py.

    python ml/eval/cascade.py ml/runs/pred/yoloe-26m-seg-all-lct-test-test.json \
        --data ml/datasets/external/lct-test --clip ViT-L-14

Авторазметка H5 показала: YOLOE находит машины, но путает их названия, а по вырезке класс
назвать проще (ml/README.md, «Разметка тестового набора»). Там классы называла Gemma — секунды
на рамку. Здесь то же делает CLIP за миллисекунды, поэтому каскад может работать в сервисе.
Класс детектора не используется: от него нужна только рамка.

Классификатор — zero-shot по промптам (yaml — короткие промпты equipment_classes.yaml,
described — описания из crop_prompts.yaml) или линейная голова, обученная probe.py.
Балл рамки — среднее геометрическое вероятности класса и уверенности детектора: одна
вероятность класса ранжирует хуже — уверенно названный столб выходит наверх.

--trusted — гибрид с дообученным детектором: его рамки не ниже --trusted-conf остаются как
есть, а каскад называет только кандидатов, которые с ними не совпадают. Дообученный детектор
на снимках организаторов почти не путает классы, а только пропускает машины; на своей
площадке (Лима) он сильнее каскада (docs/metrics.md, §4).
"""

import argparse
import json
import statistics
import time
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CLASSES = ROOT / "packages" / "contracts" / "equipment_classes.yaml"
CROP_PROMPTS = Path(__file__).with_name("crop_prompts.yaml")
CLIP_WEIGHTS = {
    "ViT-B-32": "/models/openclip-vit-b32/open_clip_model.safetensors",
    "ViT-L-14": "/models/openclip-vit-l14-laion2b/open_clip_pytorch_model.bin",
}
BACKGROUND, PERSON = "background", "person"
# Рамка больше половины кадра — «вся стройка», а не машина (как в prelabel.py).
MAX_AREA = 0.5
# Поля вокруг рамки: по кузову без стрелы и гусениц класс не угадать (как в prelabel.py).
MARGIN = 0.15
# Рамки-кандидаты одной машины: оставляем самую уверенную (как склейка в vision-service).
PROPOSAL_IOU = 0.5
# Рамка того же класса, лежащая в другой этой долей площади, — часть машины (стрела, мачта).
PART_INSIDE = 0.7


def iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def inside(inner: list[float], outer: list[float]) -> float:
    ix = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0]))
    iy = max(0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return ix * iy / area if area else 0.0


def area(box: list[float]) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def proposals(boxes: list, min_conf: float, top_k: int = 0) -> list:
    """Рамки-кандидаты без классов: не люди, не весь кадр, одна на объект, не больше top_k."""
    kept: list = []
    candidates = [
        b for b in boxes if b[1] >= min_conf and b[0] != PERSON and area(b[2:]) <= MAX_AREA
    ]
    for box in sorted(candidates, key=lambda b: -b[1]):
        if not any(iou(k[2:], box[2:]) > PROPOSAL_IOU for k in kept):
            kept.append(box)
    return kept[:top_k] if top_k else kept


def load_clip(arch: str, device: str):
    import open_clip

    model, _, _ = open_clip.create_model_and_transforms(
        arch, pretrained=CLIP_WEIGHTS[arch], device=device
    )
    return model.eval(), open_clip.get_tokenizer(arch)


def to_pixels(image: Image.Image, model, device: str):
    """Кадр целиком на устройстве, уже нормированный под CLIP: вырезки режутся из него на GPU."""
    import numpy as np
    import torch

    mean = torch.tensor(model.visual.image_mean, device=device)[:, None, None]
    std = torch.tensor(model.visual.image_std, device=device)[:, None, None]
    x = torch.from_numpy(np.array(image.convert("RGB"))).to(device)
    return (x.permute(2, 0, 1).float() / 255 - mean) / std


def crops(pixels, boxes: list, size: int):
    """Вырезки с полями, вписанные в квадрат без искажения пропорций.

    Поля квадрата — нули, то есть средний цвет после нормировки: центральная обрезка CLIP
    срезала бы стрелу крана или мачту буровой.
    """
    import torch
    from torchvision.ops import roi_align

    _, h, w = pixels.shape
    b = torch.tensor(boxes, device=pixels.device, dtype=torch.float32)
    sign = torch.tensor([-1, -1, 1, 1], device=b.device)
    margin = torch.cat([b[:, 2:] - b[:, :2]] * 2, dim=1) * MARGIN * sign
    rect = (b + margin).clamp(0, 1) * torch.tensor([w, h, w, h], device=b.device)
    # Квадрат вокруг рамки с полями: одна вырезка на рамку одним вызовом roi_align.
    side = (rect[:, 2:] - rect[:, :2]).max(dim=1).values.clamp(min=1e-6)
    center = (rect[:, :2] + rect[:, 2:]) / 2
    square = torch.cat([center - side[:, None] / 2, center + side[:, None] / 2], dim=1)
    rois = torch.cat([torch.zeros(len(b), 1, device=b.device), square], dim=1)
    out = roi_align(pixels[None], rois, (size, size), sampling_ratio=-1, aligned=True)
    # Всё, что в квадрате вне рамки с полями, — средний цвет, как у дополнения до квадрата.
    grid = (torch.arange(size, device=b.device) + 0.5) / size
    lo = (rect[:, :2] - square[:, :2]) / side[:, None]
    hi = (rect[:, 2:] - square[:, :2]) / side[:, None]
    inside_x = (grid[None] >= lo[:, 0:1]) & (grid[None] <= hi[:, 0:1])
    inside_y = (grid[None] >= lo[:, 1:2]) & (grid[None] <= hi[:, 1:2])
    return out * (inside_y[:, :, None] & inside_x[:, None, :])[:, None]


def embed(model, batch):
    import torch

    with torch.no_grad(), torch.autocast(device_type="cuda", enabled=batch.is_cuda):
        emb = model.encode_image(batch).float()
    return emb / emb.norm(dim=-1, keepdim=True)


def zero_shot_head(model, tokenizer, mode: str, device: str):
    """Текстовые эмбеддинги классов: среднее по промптам и шаблонам, как у стадии в vision."""
    import torch

    spec = yaml.safe_load(CROP_PROMPTS.read_text(encoding="utf-8"))
    if mode == "yaml":
        classes = yaml.safe_load(CLASSES.read_text(encoding="utf-8"))["equipment_classes"]
        phrases = {c["code"]: c["prompts"] for c in classes}
    else:
        phrases = dict(spec["classes"])
    phrases[BACKGROUND] = spec["background"]
    codes, rows = list(phrases), []
    with torch.no_grad():
        for code in codes:
            texts = [t.format(p) for p in phrases[code] for t in spec["templates"]]
            emb = model.encode_text(tokenizer(texts).to(device)).float()
            emb = emb / emb.norm(dim=-1, keepdim=True)
            mean = emb.mean(dim=0)
            rows.append(mean / mean.norm())
        weight = torch.stack(rows) * model.logit_scale.exp().float()
    return codes, weight, torch.zeros(len(codes), device=device)


def finish(boxes: list) -> list:
    """Части машин долой, затем одна рамка на объект независимо от класса."""
    wholes: list = []
    for box in sorted(boxes, key=lambda b: -area(b[2:])):
        if not any(k[0] == box[0] and inside(box[2:], k[2:]) >= PART_INSIDE for k in wholes):
            wholes.append(box)
    kept: list = []
    for box in sorted(wholes, key=lambda b: -b[1]):
        if not any(iou(k[2:], box[2:]) > PROPOSAL_IOU for k in kept):
            kept.append(box)
    return kept


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("proposals", type=Path)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--clip", default="ViT-L-14", choices=list(CLIP_WEIGHTS))
    parser.add_argument("--prompts", default="described", choices=["yaml", "described"])
    parser.add_argument("--head", type=Path, help="линейная голова probe.py вместо промптов")
    parser.add_argument("--min-conf", type=float, default=0.05, help="порог рамок-кандидатов")
    parser.add_argument("--top-k", type=int, default=0, help="не больше K кандидатов на снимок")
    parser.add_argument("--trusted", type=Path, help="JSON рамок дообученного детектора")
    parser.add_argument("--trusted-conf", type=float, default=0.35)
    args = parser.parse_args()
    trusted = json.loads(args.trusted.read_text("utf-8"))["images"] if args.trusted else {}

    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, tokenizer = load_clip(args.clip, device)
    size = model.visual.image_size
    size = size[0] if isinstance(size, tuple) else size
    if args.head:
        head = torch.load(args.head, map_location=device)
        codes, weight, bias = head["codes"], head["weight"], head["bias"]
    else:
        codes, weight, bias = zero_shot_head(model, tokenizer, args.prompts, device)
    machine = torch.tensor([i for i, c in enumerate(codes) if c not in (BACKGROUND, PERSON)])

    doc = json.loads(args.proposals.read_text(encoding="utf-8"))
    images_dir = {p.stem: p for p in (args.data / "images" / args.split).iterdir()}
    result, times = {}, []
    for stem, item in doc["images"].items():
        # Рамки дообученного детектора не трогаем: правило «часть машины» сняло бы вложенные
        # рамки башенных кранов, которые в разметке Лимы стоят отдельно.
        kept = [
            b
            for b in trusted.get(stem, {}).get("boxes", [])
            if b[1] >= args.trusted_conf and b[0] != PERSON
        ]
        found = [
            b
            for b in proposals(item["boxes"], args.min_conf)
            if not any(iou(k[2:], b[2:]) > PROPOSAL_IOU for k in kept)
        ]
        found = found[: args.top_k] if args.top_k else found
        image = Image.open(images_dir[stem])
        boxes = []
        if found:
            if device == "cuda":
                torch.cuda.synchronize()
            start = time.perf_counter()
            batch = crops(to_pixels(image, model, device), [b[2:] for b in found], size)
            with torch.no_grad():
                probs = (embed(model, batch) @ weight.T + bias).softmax(dim=-1)[:, machine].cpu()
            times.append((time.perf_counter() - start) * 1000)
            p, best = probs.max(dim=1)
            for box, prob, idx in zip(found, p.tolist(), best.tolist(), strict=True):
                code = codes[int(machine[idx])]
                boxes.append([code, round((prob * box[1]) ** 0.5, 4), *box[2:]])
        named = [
            b
            for b in finish(boxes)
            if not any(k[0] == b[0] and inside(b[2:], k[2:]) >= PART_INSIDE for k in kept)
        ]
        result[stem] = {"width": item["width"], "height": item["height"], "boxes": kept + named}

    head_name = args.head.stem if args.head else args.prompts
    base = args.proposals.stem.replace(f"-{args.data.name}-{args.split}", "")
    suffix = f"-k{args.top_k}" if args.top_k else ""
    suffix += f"-c{args.min_conf:g}" if args.min_conf != 0.05 else ""
    if args.trusted:
        trusted_name = args.trusted.stem.replace(f"-{args.data.name}-{args.split}", "")
        suffix += f"+{trusted_name}@{args.trusted_conf:g}"
    meta = {
        **doc.get("meta", {}),
        "classifier": f"{args.clip}/{head_name}",
        "min_conf": args.min_conf,
        "top_k": args.top_k,
        # Вырезки и CLIP: без декодирования снимка, как inference_ms в vision-service.
        "classifier_ms_median": round(statistics.median(times[1:]), 1),
    }
    name = f"cascade-{base}-{args.clip}-{head_name}{suffix}-{args.data.name}-{args.split}.json"
    out = args.proposals.parent / name
    out.write_text(json.dumps({"meta": meta, "images": result}), encoding="utf-8")
    print(f"→ {out}, классификатор {meta['classifier_ms_median']} мс")


if __name__ == "__main__":
    main()
