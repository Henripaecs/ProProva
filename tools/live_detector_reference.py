"""Referência em Python do detector ao vivo do app (mobile/lib/marker_detector.dart), usada para calibrar
com fotos reais:  python tools/live_detector_reference.py fotos/*.jpeg"""
import sys
from collections import deque
import cv2, numpy as np

TARGET_LONG = 480


def integral(g):
    h, w = g.shape
    ii = np.zeros((h + 1, w + 1), np.int64)
    for y in range(h):
        row = 0
        for x in range(w):
            row += int(g[y, x])
            ii[y + 1, x + 1] = ii[y, x + 1] + row
    return ii


def box_sum(ii, x0, y0, x1, y1):  # [x0,x1) [y0,y1)
    return ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]


def detect(gray):
    H, W = gray.shape
    step = max(1, max(H, W) // TARGET_LONG)
    g = gray[::step, ::step].astype(np.int64)
    h, w = g.shape
    L = max(h, w)
    ii = np.zeros((h + 1, w + 1), np.int64); ii[1:, 1:] = g.cumsum(0).cumsum(1)
    r = max(4, L // 16)
    dark = np.zeros((h, w), bool)
    for y in range(h):
        y0, y1 = max(0, y - r), min(h, y + r + 1)
        for x in range(w):
            x0, x1 = max(0, x - r), min(w, x + r + 1)
            mean = box_sum(ii, x0, y0, x1, y1) / ((x1 - x0) * (y1 - y0))
            dark[y, x] = g[y, x] * 100 < mean * 62
    seen = np.zeros_like(dark)
    cands = []
    for yy in range(h):
        for xx in range(w):
            if not dark[yy, xx] or seen[yy, xx]:
                continue
            q = deque([(yy, xx)]); seen[yy, xx] = True
            area = sx = sy = sv = 0; mnx = mxx = xx; mny = mxy = yy; pix = []
            while q:
                a, b = q.popleft(); pix.append((a, b)); area += 1; sx += b; sy += a; sv += g[a, b]
                if b < mnx: mnx = b
                if b > mxx: mxx = b
                if a < mny: mny = a
                if a > mxy: mxy = a
                for na, nb in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
                    if 0 <= na < h and 0 <= nb < w and dark[na, nb] and not seen[na, nb]:
                        seen[na, nb] = True; q.append((na, nb))
            bw, bh = mxx - mnx + 1, mxy - mny + 1
            if mnx == 0 or mny == 0 or mxx == w - 1 or mxy == h - 1: continue
            if min(bw, bh) < max(4, 0.012 * L) or max(bw, bh) > 0.12 * L: continue
            if min(bw, bh) / max(bw, bh) < 0.5 or area / (bw * bh) < 0.55: continue
            cx_, cy_ = sx / area, sy / area
            far = max((b - cx_) ** 2 + (a - cy_) ** 2 for a, b in pix)
            side = area ** 0.5
            sq = far / (area * ((side - 1) / side) ** 2)   # quadrado = 0,50 · círculo = 0,32 (qualquer tamanho/giro)
            if not (0.42 <= sq <= 0.75): continue
            # anel ao redor: papel claro (marcador fica a 8 mm da borda da folha)
            t = max(2, max(bw, bh) // 2)
            ox0, oy0, ox1, oy1 = max(0, mnx - t), max(0, mny - t), min(w, mxx + 1 + t), min(h, mxy + 1 + t)
            outer = box_sum(ii, ox0, oy0, ox1, oy1); inner = box_sum(ii, mnx, mny, mxx + 1, mxy + 1)
            n_ring = (ox1 - ox0) * (oy1 - oy0) - bw * bh
            if n_ring <= 0: continue
            ring_mean = (outer - inner) / n_ring
            comp_mean = sv / area
            if ring_mean < 1.7 * comp_mean or ring_mean < 40: continue
            cands.append((area, sx / area, sy / area))
    cands.sort(key=lambda c: -c[0])
    pool = cands[:8]
    best, best_area = None, 0.0
    import itertools
    for combo in itertools.combinations(pool, 4):
        areas = [c[0] for c in combo]
        if max(areas) > 3 * min(areas): continue
        pts = sorted(combo, key=lambda c: np.arctan2(c[2] - sum(p[2] for p in combo) / 4, c[1] - sum(p[1] for p in combo) / 4))
        cross = []
        for i in range(4):
            a, b, c = pts[i], pts[(i + 1) % 4], pts[(i + 2) % 4]
            cross.append((b[1] - a[1]) * (c[2] - b[2]) - (b[2] - a[2]) * (c[1] - b[1]))
        if not (all(v > 0 for v in cross) or all(v < 0 for v in cross)): continue
        sides = [((pts[i][1] - pts[(i + 1) % 4][1]) ** 2 + (pts[i][2] - pts[(i + 1) % 4][2]) ** 2) ** 0.5 for i in range(4)]
        a_, b_ = (sides[0] + sides[2]) / 2, (sides[1] + sides[3]) / 2
        if not (1.15 <= max(a_, b_) / min(a_, b_) <= 2.1): continue        # A4: 271/184 = 1,47
        msize = (sum(c[0] for c in combo) / 4) ** 0.5 / min(a_, b_)
        if not (0.03 <= msize <= 0.085): continue                          # marcador 10 mm / 184 mm = 0,054
        poly = sum(pts[i][1] * pts[(i + 1) % 4][2] - pts[(i + 1) % 4][1] * pts[i][2] for i in range(4))
        if abs(poly) / 2 > best_area: best, best_area = pts, abs(poly) / 2
    return (best is not None), best_area / (w * h), len(cands)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        gray = cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2GRAY)
        found, frac, n = detect(gray)
        print(f"{p[-24:]:>26}  4 marcadores={found}  área da folha={frac:.0%}  candidatos={n}")
        gray2 = cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE)          # como o frame do sensor (paisagem)
        print(f"{'(girado 90°)':>26}  4 marcadores={detect(gray2)[0]}")
