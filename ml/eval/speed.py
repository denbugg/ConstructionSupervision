"""Время конвейера на снимок в одном процессе на GPU: детектор(ы) + CLIP по вырезкам.

    python ml/eval/speed.py --detector /models/yoloe-26s-seg.pt --prompts all --clip ViT-B-32 \
        --trusted /models/yolov8s-worldv2-ce-ulima-v1.pt --data ml/datasets/external/lct-test

predict.py и cascade.py меряют части по отдельности и в разных процессах, а требование ТЗ
(≤ 100 мс на GPU) — к снимку целиком. Время — как inference_ms в vision-service: модели,
вырезки и постобработка, без чтения и декодирования файла. Первые 3 снимка — прогрев.
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
# Соседние скрипты, а не пакет: путь добавлен строкой выше.
from cascade import (
    PERSON,
    PROPOSAL_IOU,
    crops,
    embed,
    finish,
    iou,
    load_clip,
    proposals,
    to_pixels,
    zero_shot_head,
)
from predict import load_model, vocabulary

WARMUP = 3


def boxes_of(model, image, vocab: list, imgsz: int, conf: float) -> list:
    r = model.predict(image, imgsz=imgsz, conf=conf, iou=0.7, verbose=False)[0]
    h, w = r.orig_shape
    return [
        [vocab[int(c)][1], float(s), x1 / w, y1 / h, x2 / w, y2 / h]
        for (x1, y1, x2, y2), s, c in zip(
            r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist(), strict=True
        )
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--detector", required=True)
    parser.add_argument("--prompts", choices=["first", "all"], default="all")
    parser.add_argument("--clip", default="ViT-B-32", help="none — только детектор")
    parser.add_argument("--trusted", help="дообученный детектор для гибрида")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--top-k", type=int, default=0)
    parser.add_argument("--imgsz", type=int, default=1280)
    args = parser.parse_args()

    import torch

    vocab = vocabulary(args.prompts)
    detector = load_model(args.detector, [p for p, _ in vocab])
    trusted_vocab = vocabulary("first")
    trusted = load_model(args.trusted, [p for p, _ in trusted_vocab]) if args.trusted else None
    if args.clip != "none":
        clip, tokenizer = load_clip(args.clip, "cuda")
        size = clip.visual.image_size
        size = size[0] if isinstance(size, tuple) else size
        codes, weight, bias = zero_shot_head(clip, tokenizer, "described", "cuda")
        machine = torch.tensor([i for i, c in enumerate(codes) if c not in ("background", PERSON)])

    paths = sorted((args.data / "images" / args.split).iterdir())[: args.limit + WARMUP]
    times, crops_count = [], []
    for path in paths:
        image = Image.open(path).convert("RGB")
        torch.cuda.synchronize()
        start = time.perf_counter()
        kept = []
        if args.clip == "none":
            boxes_of(detector, image, vocab, args.imgsz, 0.35)
            torch.cuda.synchronize()
            times.append((time.perf_counter() - start) * 1000)
            crops_count.append(0)
            continue
        if trusted:
            kept = [b for b in boxes_of(trusted, image, trusted_vocab, args.imgsz, 0.35)
                    if b[0] != PERSON]  # fmt: skip
        found = [
            b
            for b in proposals(boxes_of(detector, image, vocab, args.imgsz, 0.05), 0.05)
            if not any(iou(k[2:], b[2:]) > PROPOSAL_IOU for k in kept)
        ]
        found = found[: args.top_k] if args.top_k else found
        named = []
        if found:
            batch = crops(to_pixels(image, clip, "cuda"), [b[2:] for b in found], size)
            with torch.no_grad():
                probs = (embed(clip, batch) @ weight.T + bias).softmax(dim=-1)[:, machine]
            p, best = probs.max(dim=1)
            for box, prob, idx in zip(found, p.tolist(), best.tolist(), strict=True):
                code = codes[int(machine[idx])]
                named.append([code, (prob * box[1]) ** 0.5, *box[2:]])
        finish(named)
        torch.cuda.synchronize()
        times.append((time.perf_counter() - start) * 1000)
        crops_count.append(len(found))
    times, crops_count = times[WARMUP:], crops_count[WARMUP:]
    q = statistics.quantiles(times, n=10)
    print(
        f"{Path(args.detector).stem} + {args.clip}"
        + (f" + {Path(args.trusted).stem}" if args.trusted else "")
        + (f", top-{args.top_k}" if args.top_k else "")
        + f": медиана {statistics.median(times):.0f} мс, p90 {q[-1]:.0f} мс, "
        f"вырезок на снимок — медиана {statistics.median(crops_count):.0f} ({len(times)} снимков)"
    )


if __name__ == "__main__":
    main()
