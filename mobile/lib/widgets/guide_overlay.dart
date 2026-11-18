import 'package:flutter/material.dart';

enum GuideState { searching, tooFar, steady, ready, sending }

/// Moldura-guia no formato A4 com cantoneiras nos 4 marcadores.
/// Cinza = procurando; laranja = aproxime; azul = segure firme; verde = pronto.
class GuideOverlay extends StatelessWidget {
  const GuideOverlay({super.key, required this.state});
  final GuideState state;

  static Color colorFor(GuideState s) => switch (s) {
        GuideState.searching => Colors.white70,
        GuideState.tooFar => const Color(0xFFF2A33A),
        GuideState.steady => const Color(0xFF7FA7F0),
        GuideState.ready || GuideState.sending => const Color(0xFF3DDC84),
      };

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: CustomPaint(size: Size.infinite, painter: _GuidePainter(colorFor(state))),
    );
  }
}

class _GuidePainter extends CustomPainter {
  _GuidePainter(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    const aspect = 210 / 297;
    var w = size.width * 0.86;
    var h = w / aspect;
    if (h > size.height * 0.80) {
      h = size.height * 0.80;
      w = h * aspect;
    }
    final rect = Rect.fromCenter(center: size.center(Offset.zero), width: w, height: h);

    // escurece fora da moldura
    final shade = Path()
      ..addRect(Offset.zero & size)
      ..addRRect(RRect.fromRectAndRadius(rect, const Radius.circular(6)))
      ..fillType = PathFillType.evenOdd;
    canvas.drawPath(shade, Paint()..color = Colors.black.withValues(alpha: 0.38));

    final edge = Paint()
      ..color = color.withValues(alpha: 0.55)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2;
    canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(6)), edge);

    // cantoneiras + quadradinho onde fica cada marcador do cartão
    final corner = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;
    final len = w * 0.12;
    final marker = w * (10 / 210);
    final inset = w * (8 / 210);
    for (final (cx, cy, sx, sy) in [
      (rect.left, rect.top, 1.0, 1.0),
      (rect.right, rect.top, -1.0, 1.0),
      (rect.right, rect.bottom, -1.0, -1.0),
      (rect.left, rect.bottom, 1.0, -1.0),
    ]) {
      canvas.drawLine(Offset(cx, cy), Offset(cx + sx * len, cy), corner);
      canvas.drawLine(Offset(cx, cy), Offset(cx, cy + sy * len), corner);
      final m = Rect.fromLTWH(sx > 0 ? cx + inset : cx - inset - marker, sy > 0 ? cy + inset : cy - inset - marker, marker, marker);
      canvas.drawRect(m, Paint()
        ..color = color.withValues(alpha: 0.8)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5);
    }
  }

  @override
  bool shouldRepaint(_GuidePainter old) => old.color != color;
}
