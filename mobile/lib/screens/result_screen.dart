import 'package:flutter/material.dart';

import '../api.dart';

/// Nota do cartão recém-fotografado. Rasuras ficam pendentes e são decididas no painel web.
class ResultScreen extends StatelessWidget {
  const ResultScreen({super.key, required this.result, this.onOpenInPanel});
  final ScanResult result;

  /// Abre esta correção no painel (tela de revisão com o recorte das rasuras).
  final VoidCallback? onOpenInPanel;

  static String _fmt(double v) => v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1).replaceAll('.', ',');

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final pending = result.reviewNeeded.isNotEmpty;
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(result.examTitle ?? 'Prova', style: t.titleMedium?.copyWith(color: Colors.black54)),
            const SizedBox(height: 4),
            Text(result.studentName ?? 'Aluno', style: t.headlineMedium?.copyWith(fontFamily: 'serif', fontWeight: FontWeight.w700)),
            const SizedBox(height: 28),
            Text(pending ? 'Nota parcial' : 'Nota', style: t.labelLarge?.copyWith(color: Colors.black54)),
            Row(crossAxisAlignment: CrossAxisAlignment.baseline, textBaseline: TextBaseline.alphabetic, children: [
              Text(_fmt(result.points),
                  style: const TextStyle(fontSize: 64, fontWeight: FontWeight.w800, color: Color(0xFFB3261E), fontFamily: 'serif')),
              Text(' / ${_fmt(result.maxPoints)}', style: t.titleLarge?.copyWith(color: Colors.black54)),
            ]),
            const SizedBox(height: 16),
            Wrap(spacing: 10, runSpacing: 10, children: [
              _Chip('${result.correct} acertos', const Color(0xFFE3F3E9), const Color(0xFF1D7A46)),
              _Chip('${result.wrong} erros', const Color(0xFFFBE6E4), const Color(0xFFB3261E)),
              _Chip('${result.blank} em branco', const Color(0xFFEFECE3), Colors.black54),
            ]),
            if (pending) ...[
              const SizedBox(height: 22),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(color: const Color(0xFFFBEFDC), borderRadius: BorderRadius.circular(10)),
                child: Text(
                  'Questões ${result.reviewNeeded.join(', ')} com rasura ou marca fraca. '
                  'Elas ficaram pendentes: toque em "Revisar agora" para decidir.',
                  style: const TextStyle(color: Color(0xFF7A4608)),
                ),
              ),
            ],
            const Spacer(),
            if (onOpenInPanel != null) ...[
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: () {
                    Navigator.of(context).pop();
                    onOpenInPanel!();
                  },
                  icon: Icon(pending ? Icons.rule : Icons.visibility_outlined),
                  label: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    child: Text(pending ? 'Revisar agora' : 'Ver respostas no painel'),
                  ),
                ),
              ),
              const SizedBox(height: 10),
            ],
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(Icons.photo_camera),
                label: const Padding(padding: EdgeInsets.symmetric(vertical: 14), child: Text('Próximo cartão')),
              ),
            ),
          ]),
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip(this.text, this.bg, this.fg);
  final String text;
  final Color bg;
  final Color fg;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(20)),
        child: Text(text, style: TextStyle(color: fg, fontWeight: FontWeight.w600)),
      );
}
