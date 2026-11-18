// Detector AO VIVO dos 4 marcadores do cartão — só para guiar o usuário antes da foto.
// (A leitura de verdade acontece no servidor, em alta resolução.)
//
// Dart puro, sem Flutter: roda num Isolate e pode ser testado com `flutter test`.
// Espelha linha a linha tools/live_detector_reference.py, calibrado com as fotos reais de fotos/.
//
// Ideia:
//  1. reduz o frame para ~480 px no lado maior (só a luminância);
//  2. "escuro" = pixel < 62% da média local (aguenta sombra e luz amarela);
//  3. componentes conexos; um marcador é um QUADRADO sólido com papel claro em volta.
//     Quadrado x bolha preenchida: (maior distância ao centro)² / área = 0,50 no quadrado e
//     0,32 no círculo, em qualquer giro ou tamanho;
//  4. escolhe 4 candidatos de tamanho parecido que formem um quadrilátero convexo com a
//     proporção do A4 e marcadores do tamanho certo em relação à folha.

import 'dart:math' as math;
import 'dart:typed_data';

class GrayImage {
  GrayImage(this.data, this.width, this.height);
  final Uint8List data;
  final int width;
  final int height;
}

class MarkerDetection {
  const MarkerDetection(this.found, this.sheetFraction, this.candidates);

  /// Quatro marcadores formando uma folha plausível.
  final bool found;

  /// Fração do frame ocupada pela folha (0–1). Pequena demais → QR ilegível.
  final double sheetFraction;
  final int candidates;

  static const double minSheetFraction = 0.15;

  bool get ready => found && sheetFraction >= minSheetFraction;
  bool get tooFar => found && sheetFraction < minSheetFraction;

  static const none = MarkerDetection(false, 0, 0);
}

const int _targetLong = 480;

/// Extrai a luminância reduzida de um plano de imagem.
/// Android (YUV420): plano Y, pixelStride 1. iOS (BGRA8888): pixelStride 4, channelOffset 1 (verde).
GrayImage downsample(Uint8List bytes, int width, int height,
    {required int rowStride, int pixelStride = 1, int channelOffset = 0, int targetLong = _targetLong}) {
  final step = math.max(1, math.max(width, height) ~/ targetLong);
  final w = (width + step - 1) ~/ step;
  final h = (height + step - 1) ~/ step;
  final out = Uint8List(w * h);
  for (var y = 0; y < h; y++) {
    final rowBase = y * step * rowStride + channelOffset;
    for (var x = 0; x < w; x++) {
      final i = rowBase + x * step * pixelStride;
      out[y * w + x] = i < bytes.length ? bytes[i] : 255;
    }
  }
  return GrayImage(out, w, h);
}

class _Cand {
  _Cand(this.area, this.cx, this.cy);
  final int area;
  final double cx;
  final double cy;
}

MarkerDetection detectMarkers(GrayImage img) {
  final w = img.width, h = img.height, g = img.data;
  if (w < 32 || h < 32) return MarkerDetection.none;
  final L = math.max(w, h);

  // imagem integral (soma de 480×360×255 cabe com folga em 32 bits)
  final W1 = w + 1;
  final ii = Int32List(W1 * (h + 1));
  for (var y = 0; y < h; y++) {
    var row = 0;
    for (var x = 0; x < w; x++) {
      row += g[y * w + x];
      ii[(y + 1) * W1 + x + 1] = ii[y * W1 + x + 1] + row;
    }
  }
  int boxSum(int x0, int y0, int x1, int y1) =>
      ii[y1 * W1 + x1] - ii[y0 * W1 + x1] - ii[y1 * W1 + x0] + ii[y0 * W1 + x0];

  // 1) escuro relativo à média local
  final r = math.max(4, L ~/ 16);
  final dark = Uint8List(w * h);
  for (var y = 0; y < h; y++) {
    final y0 = math.max(0, y - r), y1 = math.min(h, y + r + 1);
    for (var x = 0; x < w; x++) {
      final x0 = math.max(0, x - r), x1 = math.min(w, x + r + 1);
      final count = (x1 - x0) * (y1 - y0);
      if (g[y * w + x] * 100 * count < boxSum(x0, y0, x1, y1) * 62) dark[y * w + x] = 1;
    }
  }

  // 2) componentes conexos (BFS; a fila guarda todos os pixels do componente)
  final seen = Uint8List(w * h);
  final queue = Int32List(w * h);
  final cands = <_Cand>[];
  final minSide = math.max(4.0, 0.012 * L), maxSide = 0.12 * L;

  for (var start = 0; start < w * h; start++) {
    if (dark[start] == 0 || seen[start] == 1) continue;
    var head = 0, tail = 0;
    queue[tail++] = start;
    seen[start] = 1;
    var sx = 0, sy = 0, sv = 0;
    var mnx = start % w, mxx = mnx, mny = start ~/ w, mxy = mny;
    while (head < tail) {
      final p = queue[head++];
      final px = p % w, py = p ~/ w;
      sx += px;
      sy += py;
      sv += g[p];
      if (px < mnx) mnx = px;
      if (px > mxx) mxx = px;
      if (py < mny) mny = py;
      if (py > mxy) mxy = py;
      if (py + 1 < h && dark[p + w] == 1 && seen[p + w] == 0) { seen[p + w] = 1; queue[tail++] = p + w; }
      if (py > 0 && dark[p - w] == 1 && seen[p - w] == 0) { seen[p - w] = 1; queue[tail++] = p - w; }
      if (px + 1 < w && dark[p + 1] == 1 && seen[p + 1] == 0) { seen[p + 1] = 1; queue[tail++] = p + 1; }
      if (px > 0 && dark[p - 1] == 1 && seen[p - 1] == 0) { seen[p - 1] = 1; queue[tail++] = p - 1; }
    }
    final area = tail;
    final bw = mxx - mnx + 1, bh = mxy - mny + 1;
    if (mnx == 0 || mny == 0 || mxx == w - 1 || mxy == h - 1) continue; // cortado pela borda
    final shortSide = math.min(bw, bh), longSide = math.max(bw, bh);
    if (shortSide < minSide || longSide > maxSide) continue;
    if (shortSide / longSide < 0.5 || area / (bw * bh) < 0.55) continue;

    // quadrado x círculo
    final cx = sx / area, cy = sy / area;
    var far = 0.0;
    for (var k = 0; k < tail; k++) {
      final dx = queue[k] % w - cx, dy = queue[k] ~/ w - cy;
      final d = dx * dx + dy * dy;
      if (d > far) far = d;
    }
    final side = math.sqrt(area);
    if (side <= 1) continue;
    final corr = (side - 1) / side;
    final sq = far / (area * corr * corr);
    if (sq < 0.42 || sq > 0.75) continue;

    // anel ao redor deve ser papel claro (o marcador fica a 8 mm da borda da folha)
    final t = math.max(2, longSide ~/ 2);
    final ox0 = math.max(0, mnx - t), oy0 = math.max(0, mny - t);
    final ox1 = math.min(w, mxx + 1 + t), oy1 = math.min(h, mxy + 1 + t);
    final nRing = (ox1 - ox0) * (oy1 - oy0) - bw * bh;
    if (nRing <= 0) continue;
    final ringMean = (boxSum(ox0, oy0, ox1, oy1) - boxSum(mnx, mny, mxx + 1, mxy + 1)) / nRing;
    final compMean = sv / area;
    if (ringMean < 1.7 * compMean || ringMean < 40) continue;

    cands.add(_Cand(area, cx, cy));
  }

  // 3) melhor quadrilátero entre os maiores candidatos
  cands.sort((a, b) => b.area.compareTo(a.area));
  final pool = cands.take(8).toList();
  var bestArea = 0.0;
  var found = false;
  for (var a = 0; a < pool.length; a++) {
    for (var b = a + 1; b < pool.length; b++) {
      for (var c = b + 1; c < pool.length; c++) {
        for (var d = c + 1; d < pool.length; d++) {
          final combo = [pool[a], pool[b], pool[c], pool[d]];
          final areas = combo.map((e) => e.area);
          if (areas.reduce(math.max) > 3 * areas.reduce(math.min)) continue;
          final mx = combo.fold<double>(0, (s, e) => s + e.cx) / 4;
          final my = combo.fold<double>(0, (s, e) => s + e.cy) / 4;
          combo.sort((p, q) => math.atan2(p.cy - my, p.cx - mx).compareTo(math.atan2(q.cy - my, q.cx - mx)));
          var pos = 0, neg = 0;
          for (var i = 0; i < 4; i++) {
            final p = combo[i], q = combo[(i + 1) % 4], s = combo[(i + 2) % 4];
            final cross = (q.cx - p.cx) * (s.cy - q.cy) - (q.cy - p.cy) * (s.cx - q.cx);
            if (cross > 0) pos++;
            if (cross < 0) neg++;
          }
          if (pos != 4 && neg != 4) continue; // não convexo
          final sides = List<double>.generate(4, (i) {
            final p = combo[i], q = combo[(i + 1) % 4];
            return math.sqrt((p.cx - q.cx) * (p.cx - q.cx) + (p.cy - q.cy) * (p.cy - q.cy));
          });
          final s1 = (sides[0] + sides[2]) / 2, s2 = (sides[1] + sides[3]) / 2;
          final ratio = math.max(s1, s2) / math.min(s1, s2);
          if (ratio < 1.15 || ratio > 2.1) continue; // A4: 271/184 = 1,47
          final meanArea = combo.fold<double>(0, (s, e) => s + e.area) / 4;
          final msize = math.sqrt(meanArea) / math.min(s1, s2);
          if (msize < 0.03 || msize > 0.085) continue; // marcador 10 mm / 184 mm = 0,054
          var poly = 0.0;
          for (var i = 0; i < 4; i++) {
            final p = combo[i], q = combo[(i + 1) % 4];
            poly += p.cx * q.cy - q.cx * p.cy;
          }
          final quadArea = poly.abs() / 2;
          if (quadArea > bestArea) {
            bestArea = quadArea;
            found = true;
          }
        }
      }
    }
  }
  return MarkerDetection(found, bestArea / (w * h), cands.length);
}
