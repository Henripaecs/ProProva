import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omr_scanner/marker_detector.dart';

/// Frame sintético 600×800: fundo escuro, folha A4 clara, 4 marcadores e bolhas preenchidas.
/// Mesmo caso verificado em Python (tools/live_detector_reference.py).
GrayImage frame({bool hideOneMarker = false, bool circlesInsteadOfSquares = false, double scale = 1}) {
  const w = 600, h = 800;
  final img = Uint8List(w * h)..fillRange(0, w * h, 70);
  final sw = (420 * scale).round(), sh = (594 * scale).round();
  final x0 = (w - sw) ~/ 2, y0 = (h - sh) ~/ 2;
  void fillRect(int x, int y, int rw, int rh, int v) {
    for (var yy = y; yy < y + rh; yy++) {
      for (var xx = x; xx < x + rw; xx++) {
        img[yy * w + xx] = v;
      }
    }
  }

  void fillCircle(int cx, int cy, int r, int v) {
    for (var yy = cy - r; yy <= cy + r; yy++) {
      for (var xx = cx - r; xx <= cx + r; xx++) {
        if ((xx - cx) * (xx - cx) + (yy - cy) * (yy - cy) <= r * r) img[yy * w + xx] = v;
      }
    }
  }

  fillRect(x0, y0, sw, sh, 230);
  final ppmm = sw / 210;
  final m = (10 * ppmm).round(), c = 13 * ppmm;
  final centers = [
    [x0 + c, y0 + c],
    [x0 + sw - c, y0 + c],
    [x0 + sw - c, y0 + sh - c],
    [x0 + c, y0 + sh - c],
  ];
  for (var i = 0; i < 4; i++) {
    if (hideOneMarker && i == 2) continue;
    final cx = centers[i][0].round(), cy = centers[i][1].round();
    if (circlesInsteadOfSquares) {
      fillCircle(cx, cy, m ~/ 2, 25);
    } else {
      fillRect(cx - m ~/ 2, cy - m ~/ 2, m, m, 25);
    }
  }
  for (var q = 0; q < 12; q++) {
    fillCircle(x0 + (60 * ppmm).round() + (q % 4) * (25 * ppmm).round(),
        y0 + (90 * ppmm).round() + (q ~/ 4) * (20 * ppmm).round(), (2.3 * ppmm).round(), 30);
  }
  return GrayImage(img, w, h);
}

void main() {
  test('acha os 4 marcadores numa folha bem enquadrada', () {
    final d = detectMarkers(frame());
    expect(d.found, isTrue);
    expect(d.ready, isTrue);
    expect(d.sheetFraction, greaterThan(0.3));
  });

  test('um marcador escondido → não está pronto', () {
    expect(detectMarkers(frame(hideOneMarker: true)).ready, isFalse);
  });

  test('círculos nos cantos não contam como marcadores', () {
    expect(detectMarkers(frame(circlesInsteadOfSquares: true)).found, isFalse);
  });

  test('folha pequena demais no quadro → pede para aproximar', () {
    final d = detectMarkers(frame(scale: 0.55));
    expect(d.found, isTrue);
    expect(d.tooFar, isTrue);
  });

  test('downsample do plano BGRA (iOS) usa o canal verde', () {
    final bgra = Uint8List.fromList([1, 2, 3, 4, 5, 6, 7, 8]);
    final g = downsample(bgra, 2, 1, rowStride: 8, pixelStride: 4, channelOffset: 1, targetLong: 480);
    expect(g.data, [2, 6]);
  });
}
