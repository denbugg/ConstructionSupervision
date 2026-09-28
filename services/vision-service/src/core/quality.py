"""Качество кадра: яркость и размытость классическими метриками, без модели.

vision только измеряет. Годен ли кадр, решает site-service по своим порогам `MIN_BRIGHTNESS`
и `MAX_BLUR` (methodology.md, раздел 4): это правило площадки, а не распознавания.
"""

from dataclasses import dataclass

import numpy as np

PRECISION = 4


@dataclass(frozen=True)
class Quality:
    """Средняя яркость 0…1 и размытость 0…1 (больше — хуже)."""

    brightness: float
    blur: float


def frame_quality(gray: np.ndarray, blur_ref: float) -> Quality:
    """Метрики по кадру в оттенках серого (значения 0…255).

    Размер кадра должен быть одним и тем же для всех снимков (его приводит вызывающий):
    дисперсия Лапласиана зависит от разрешения, и без этого 4K и 720p сравнивались бы нечестно.
    """
    if gray.ndim != 2:
        raise ValueError("ожидался кадр в оттенках серого")
    if blur_ref <= 0:
        raise ValueError("масштаб размытости должен быть положительным")
    brightness = float(gray.mean()) / 255.0 if gray.size else 0.0
    return Quality(
        brightness=round(brightness, PRECISION),
        blur=round(blur_score(laplacian_variance(gray), blur_ref), PRECISION),
    )


def laplacian_variance(gray: np.ndarray) -> float:
    """Дисперсия отклика Лапласиана 3×3: мало резких перепадов — кадр размыт.

    Считается срезами numpy без OpenCV: ядро [[0,1,0],[1,-4,1],[0,1,0]] по внутренним
    пикселям. Кадр меньше 3×3 перепадов не содержит — дисперсия 0.
    """
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    g = gray.astype(np.float64)
    lap = g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:] - 4.0 * g[1:-1, 1:-1]
    return float(lap.var())


def blur_score(variance: float, blur_ref: float) -> float:
    """Дисперсию 0…∞ переводим в 0…1: при дисперсии, равной `blur_ref`, размытость 0,5.

    Монотонно и без порога внутри: резкий кадр стремится к 0, однотонный — ровно 1.
    """
    return blur_ref / (blur_ref + max(variance, 0.0))
