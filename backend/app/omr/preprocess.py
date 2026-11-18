"""Utilitários de imagem: normalização de iluminação e diagnóstico de qualidade da foto."""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

# Limiares empíricos — calibre com fotos reais da sua base.
SHARPNESS_MIN = 40.0        # variância do Laplaciano (imagem ≤1200 px)
BRIGHTNESS_MIN = 70.0
BRIGHTNESS_MAX = 225.0
GLARE_MAX_FRAC = 0.40       # fração de pixels saturados

HINTS = {
    "blurry": "Imagem desfocada. Segure o celular firme e toque na folha para focar.",
    "too_dark": "Foto escura demais. Acenda a luz do ambiente ou ative o flash.",
    "overexposed": "Excesso de brilho/reflexo. Mude o ângulo para evitar o reflexo da luz.",
}


def normalize_illumination(gray: np.ndarray, feature_px: int) -> np.ndarray:
    """
    Correção de "flat-field": estima o fundo (papel iluminado) e divide a imagem por ele.
    Remove sombras e gradientes de luz, deixando o papel ≈255 em qualquer região.

    `feature_px` deve ser MAIOR que o maior elemento escuro a preservar (marcador/bolha
    preenchida); a dilatação apaga esses elementos antes de estimar o fundo.
    """
    k = int(feature_px) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    background = cv2.dilate(gray, kernel)
    background = cv2.GaussianBlur(background, (0, 0), k / 2)
    return cv2.divide(gray, np.maximum(background, 1), scale=255)


@dataclass
class QualityReport:
    sharpness: float
    brightness: float
    glare_frac: float
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def hint(self) -> str | None:
        return " ".join(HINTS[i] for i in self.issues) if self.issues else None


def assess_quality(bgr: np.ndarray) -> QualityReport:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    scale = 1200 / max(gray.shape)
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    mean = float(gray.mean())
    glare = float((gray >= 250).mean())
    issues = []
    if sharp < SHARPNESS_MIN:
        issues.append("blurry")
    if mean < BRIGHTNESS_MIN:
        issues.append("too_dark")
    if mean > BRIGHTNESS_MAX or glare > GLARE_MAX_FRAC:
        issues.append("overexposed")
    return QualityReport(sharp, mean, glare, issues)
