"""Смешивание весов zero-shot и дообученного YOLO-World (WiSE-FT) — без обучения.

    python ml/training/interpolate.py --tuned /models/yolov8s-worldv2-ce-ulima-v1.pt --alpha 0.5

θ = α·θ_дообученная + (1 − α)·θ_zero-shot. Дообучение стирает то, чего нет в обучающих наборах
(docs/metrics.md, §2): автокраны, буровые. Смесь весов модели, обученной с тех же начальных
весов, часто сохраняет и новое, и старое (Wortsman et al., «Robust fine-tuning of zero-shot
models», 2022). Для CNN с BatchNorm это не гарантировано, поэтому смесь только проверяется
на тестах, а в сервис идёт по метрикам.
"""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def module(checkpoint: dict):
    """Модель из чекпойнта Ultralytics: после обучения она лежит в model или в ema."""
    return checkpoint.get("model") or checkpoint["ema"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zero-shot", default="/models/yolov8s-worldv2.pt")
    parser.add_argument("--tuned", required=True)
    parser.add_argument("--alpha", type=float, required=True, help="доля дообученных весов")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "ml" / "runs" / "wise")
    args = parser.parse_args()

    import torch

    base = torch.load(args.zero_shot, map_location="cpu", weights_only=False)
    tuned = torch.load(args.tuned, map_location="cpu", weights_only=False)
    base_state = module(base).float().state_dict()
    tuned_model = module(tuned).float()
    mixed, skipped = {}, []
    for key, value in tuned_model.state_dict().items():
        other = base_state.get(key)
        if other is None or other.shape != value.shape or not value.is_floating_point():
            # Словарь классов (txt_feats) и счётчики BatchNorm берутся у дообученной модели.
            mixed[key] = value
            skipped.append(key)
            continue
        mixed[key] = args.alpha * value + (1 - args.alpha) * other
    tuned_model.load_state_dict(mixed)
    tuned["model"] = tuned_model.half()
    tuned["ema"] = None
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{Path(args.tuned).stem}-wise{round(args.alpha * 100):03d}.pt"
    torch.save(tuned, out)
    other = [k for k in skipped if not k.endswith("num_batches_tracked")]
    print(f"→ {out}; не смешаны счётчики BatchNorm и {len(other)} ключей: {', '.join(other)}")


if __name__ == "__main__":
    main()
