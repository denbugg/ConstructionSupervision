"""OpenCLIP zero-shot: стадия объекта по сходству снимка с промптами меток (F6)."""

from PIL import Image

from src.core.stages import StagePrompts


class OpenClipStageClassifier:
    """Текстовые эмбеддинги меток считаются один раз при загрузке, на снимок — один проход."""

    def __init__(
        self, name: str, arch: str, weights: str, prompts: StagePrompts, device: str
    ) -> None:
        import open_clip
        import torch

        self.name = name
        self._torch = torch
        self._device = device
        model, _, preprocess = open_clip.create_model_and_transforms(
            arch, pretrained=weights, device=device
        )
        model.eval()
        tokenizer = open_clip.get_tokenizer(arch)
        with torch.no_grad():
            # Ансамбль промптов: средний нормированный эмбеддинг метки (как в статье CLIP).
            per_label = []
            for label in prompts.labels:
                emb = model.encode_text(tokenizer(list(prompts.prompts[label])).to(device))
                emb = emb / emb.norm(dim=-1, keepdim=True)
                mean = emb.mean(dim=0)
                per_label.append(mean / mean.norm())
            self._text = torch.stack(per_label)
        self._model = model
        self._preprocess = preprocess
        self._scale = float(model.logit_scale.exp().item())

    def logits(self, image: Image.Image) -> list[float]:
        torch = self._torch
        with torch.no_grad():
            pixels = self._preprocess(image).unsqueeze(0).to(self._device)
            emb = self._model.encode_image(pixels)
            emb = emb / emb.norm(dim=-1, keepdim=True)
            return (self._scale * emb @ self._text.T).squeeze(0).float().cpu().tolist()
