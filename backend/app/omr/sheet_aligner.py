"""
PASSO 2 — Alinhamento: foto distorcida → página canônica 1680x2376 px → ROI das respostas.

Pipeline
  1. detect_fiducials   : acha os 4 quadrados pretos (robusto a luz/sombra, ignora o QR)
  2. warp_to_canonical  : homografia que leva os 4 centros aos pontos conhecidos do layout
  3. read_qr            : o QR só existe na zona do canto superior direito → resolve a ROTAÇÃO
  4. recorte da ROI     : devolve apenas a área das bolhas
"""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass

import cv2
import numpy as np

from .errors import MarkersNotFoundError, QRNotFoundError
from .layout import (CANVAS_H_PX, CANVAS_W_PX, PPMM, QR_ZONE_MM, fiducial_centers_px,
                     roi_slices_px)
from .preprocess import assess_quality, normalize_illumination

log = logging.getLogger(__name__)

MAX_SIDE = 1600            # detecção roda numa versão reduzida (rápido); a warp usa a original
MIN_AREA_FRAC = 0.00008    # área do marcador / área da imagem
MAX_AREA_FRAC = 0.02
MAX_MARKER_CIRCULARITY = 0.845


@dataclass
class _Candidate:
    center: np.ndarray
    area: float
    score: float


@dataclass
class AlignedSheet:
    canonical: np.ndarray       # página inteira normalizada (BGR)
    roi: np.ndarray             # só a área das bolhas (BGR)
    qr_text: str
    corners_px: np.ndarray      # 4x2, coordenadas na foto original (TL,TR,BR,BL no sentido do cartão)
    rotation_steps: int         # quantos quartos de volta o cartão estava girado na foto


# ───────────────────────────── 1. Marcadores ──────────────────────────────────
def order_clockwise(pts: np.ndarray) -> np.ndarray:
    """Ordena 4 pontos no sentido horário (tela), começando pelo mais próximo do canto sup-esq."""
    c = pts.mean(axis=0)
    ang = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    ordered = pts[np.argsort(ang)]
    return np.roll(ordered, -int(np.argmin(ordered.sum(axis=1))), axis=0)


def _binarizations(gray: np.ndarray):
    """Gera binarizações (preto = 255) de estratégias diferentes; a próxima só roda se a anterior falhar."""
    h, w = gray.shape
    flat = normalize_illumination(gray, feature_px=int(max(h, w) * 0.08))
    blur = cv2.GaussianBlur(flat, (5, 5), 0)
    yield "flat+otsu", cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    yield "flat+fixed", ((blur < 90).astype(np.uint8) * 255)
    block = (int(min(h, w) * 0.08) | 1)
    yield "adaptive", cv2.adaptiveThreshold(cv2.GaussianBlur(gray, (5, 5), 0), 255,
                                            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                            cv2.THRESH_BINARY_INV, block, 12)


def _marker_candidates(binary: np.ndarray) -> list[_Candidate]:
    h, w = binary.shape
    img_area = h * w
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out: list[_Candidate] = []
    for c in contours:
        area = cv2.contourArea(c)
        if not (MIN_AREA_FRAC * img_area <= area <= MAX_AREA_FRAC * img_area):
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        if x <= 1 or y <= 1 or x + bw >= w - 1 or y + bh >= h - 1:      # cortado pela borda
            continue
        (_, _), (rw, rh), _ = cv2.minAreaRect(c)
        if min(rw, rh) <= 0:
            continue
        aspect = min(rw, rh) / max(rw, rh)
        extent = area / (rw * rh)
        solidity = area / max(cv2.contourArea(cv2.convexHull(c)), 1.0)
        if aspect < 0.45 or extent < 0.72 or solidity < 0.92:
            continue
        # Quadrado x círculo: bolhas PREENCHIDAS passam em aspecto/extensão (círculo ≈ 0,785),
        # mas têm circularidade ≈ 0,88–0,91; um quadrado (mesmo em perspectiva) fica em ≈ 0,72–0,80.
        perimeter = cv2.arcLength(c, True)
        circularity = 4 * np.pi * area / max(perimeter * perimeter, 1.0)
        if circularity > MAX_MARKER_CIRCULARITY:
            continue
        if len(cv2.approxPolyDP(c, 0.06 * perimeter, True)) != 4:
            continue
        # Preenchimento: rejeita formas ocas (ex.: os "olhos" do QR Code têm ~67% de tinta)
        mask = np.zeros((bh, bw), np.uint8)
        cv2.drawContours(mask, [c - np.array([x, y])], -1, 255, -1)
        solid = cv2.mean(binary[y:y + bh, x:x + bw], mask=mask)[0] / 255.0
        if solid < 0.9:
            continue
        m = cv2.moments(c)
        center = np.array([m["m10"] / m["m00"], m["m01"] / m["m00"]])
        out.append(_Candidate(center, area, aspect * extent * solidity * solid))
    return out


def _select_quad(cands: list[_Candidate]) -> np.ndarray | None:
    """Dentre os candidatos, escolhe os 4 de tamanho coerente que formam o maior quadrilátero convexo."""
    if len(cands) < 4:
        return None
    # Os marcadores são as maiores formas quadradas sólidas da folha: o pool privilegia área
    # (bolhas preenchidas são menores) mas mantém os de melhor forma.
    by_area = sorted(cands, key=lambda c: -c.area)[:10]
    by_score = sorted(cands, key=lambda c: -c.score)[:6]
    pool = list({id(c): c for c in by_area + by_score}.values())
    best, best_val = None, 0.0
    for combo in itertools.combinations(pool, 4):
        areas = [c.area for c in combo]
        if max(areas) / min(areas) > 2.5:           # marcadores têm o mesmo tamanho (± perspectiva)
            continue
        pts = np.array([c.center for c in combo], dtype=np.float32)
        hull = cv2.convexHull(pts)
        if len(hull) != 4:
            continue
        val = cv2.contourArea(hull) * float(np.mean([c.score for c in combo]))
        if val > best_val:
            best, best_val = pts, val
    return None if best is None else order_clockwise(best)


def detect_fiducials(bgr: np.ndarray) -> np.ndarray:
    """Retorna 4x2 float32 (TL,TR,BR,BL) em coordenadas da foto ORIGINAL."""
    scale = min(1.0, MAX_SIDE / max(bgr.shape[:2]))
    small = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else bgr
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    for name, binary in _binarizations(gray):
        quad = _select_quad(_marker_candidates(binary))
        if quad is not None:
            log.debug("fiduciais encontrados com a estratégia %s", name)
            return (quad / scale).astype(np.float32)

    report = assess_quality(bgr)
    raise MarkersNotFoundError(
        "Não foi possível localizar os 4 marcadores pretos dos cantos.",
        hint=report.hint or "Enquadre a folha inteira, com os 4 quadrados pretos visíveis e sem cortes.",
        issues=report.issues)


# ───────────────────────────── 2. Homografia ──────────────────────────────────
def warp_to_canonical(bgr: np.ndarray, ordered_corners: np.ndarray) -> np.ndarray:
    homography = cv2.getPerspectiveTransform(ordered_corners.astype(np.float32), fiducial_centers_px())
    return cv2.warpPerspective(bgr, homography, (CANVAS_W_PX, CANVAS_H_PX),
                               flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


# ───────────────────────────── 3. QR / orientação ─────────────────────────────
try:                                   # zxing-cpp: bem mais robusto em QR pequeno/borrado
    import zxingcpp as _zxing
except ImportError:                    # pragma: no cover
    _zxing = None


def _zxing_read(gray: np.ndarray) -> str | None:
    if _zxing is None:
        return None
    try:
        hits = _zxing.read_barcodes(gray, formats=_zxing.BarcodeFormat.QRCode)
    except Exception:                  # API antiga sem `formats`
        hits = _zxing.read_barcodes(gray)
    return next((h.text for h in hits if h.text), None)


def _qr_detectors() -> list:
    """O detector baseado em ArUco (OpenCV >= 4.8) é bem mais robusto que o clássico em fotos
    borradas/comprimidas (nos testes, o clássico falhava ~1% dos QR; o ArUco leu todos)."""
    dets = []
    if hasattr(cv2, "QRCodeDetectorAruco"):
        dets.append(cv2.QRCodeDetectorAruco())
    dets.append(cv2.QRCodeDetector())
    return dets


def read_qr(canonical: np.ndarray) -> str | None:
    """Lê o QR apenas dentro da zona reservada; várias variações de contraste/escala são tentadas."""
    x, y, w, h = QR_ZONE_MM
    crop = canonical[int(y * PPMM):int((y + h) * PPMM), int(x * PPMM):int((x + w) * PPMM)]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    flat = normalize_illumination(gray, feature_px=int(gray.shape[0] * 0.6))
    _, otsu = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants = [gray, otsu, flat,
                cv2.resize(flat, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC),
                cv2.resize(otsu, None, fx=0.75, fy=0.75, interpolation=cv2.INTER_AREA)]
    for v in (gray, flat, otsu):
        text = _zxing_read(cv2.copyMakeBorder(v, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255))
        if text:
            return text
    for detector in _qr_detectors():
        for v in variants:
            v = cv2.copyMakeBorder(v, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)
            text, _, _ = detector.detectAndDecode(v)
            if text:
                return text
    return None


def markers_look_right(canonical: np.ndarray) -> bool:
    """Depois da homografia, cada canto deve ser um quadrado escuro com papel claro ao lado
    (do lado de dentro da folha). Se não for, a escolha dos 4 marcadores estava errada —
    típico de foto com um canto cortado."""
    gray = cv2.cvtColor(canonical, cv2.COLOR_BGR2GRAY).astype(np.float32)
    r, gap, band = 3.0 * PPMM, 6.0 * PPMM, 2.0 * PPMM
    for cx, cy in fiducial_centers_px():
        core = gray[int(cy - r):int(cy + r), int(cx - r):int(cx + r)]
        sx = cx + gap if cx < CANVAS_W_PX / 2 else cx - gap - band       # faixa para dentro da folha
        side = gray[int(cy - r):int(cy + r), int(sx):int(sx + band)]
        if core.size == 0 or side.size == 0 or core.mean() > 0.6 * side.mean():
            return False
    return True


# ───────────────────────────── API pública ────────────────────────────────────
def align_sheet(bgr: np.ndarray) -> AlignedSheet:
    """
    Foto bruta → AlignedSheet. A rotação é resolvida testando os 4 giros possíveis dos cantos:
    o giro correto é aquele em que o QR aparece na sua zona fixa.
    """
    corners = detect_fiducials(bgr)
    for k in range(4):
        ordered = np.roll(corners, -k, axis=0)
        canonical = warp_to_canonical(bgr, ordered)
        text = read_qr(canonical)
        if text:
            rows, cols = roi_slices_px()
            return AlignedSheet(canonical, canonical[rows, cols].copy(), text, ordered, k)

    report = assess_quality(bgr)
    if not markers_look_right(warp_to_canonical(bgr, corners)):
        raise MarkersNotFoundError(
            "Os 4 marcadores pretos dos cantos não estão todos visíveis.",
            hint=report.hint or "Enquadre a folha inteira, com os 4 quadrados pretos visíveis e sem cortes.",
            issues=report.issues)
    raise QRNotFoundError(
        "Marcadores encontrados, mas o QR Code não pôde ser lido.",
        hint=report.hint or "Aproxime a câmera e evite reflexos sobre o QR Code.",
        issues=report.issues)
