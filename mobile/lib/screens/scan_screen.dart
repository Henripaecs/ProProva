import 'dart:async';
import 'dart:io';
import 'dart:isolate';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api.dart';
import '../marker_detector.dart';
import '../widgets/guide_overlay.dart';
import 'login_screen.dart';
import 'result_screen.dart';

/// Câmera com moldura-guia. Analisa ~4 frames/s procurando os 4 marcadores;
/// quando a folha está estável e grande o bastante, libera (ou dispara sozinho) a foto.
class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key, required this.api, this.onOpenPanel});
  final Api api;

  /// Abre uma página do painel (usado pelo botão "Revisar no painel" do resultado).
  final void Function(String path)? onOpenPanel;

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> with WidgetsBindingObserver {
  CameraController? _cam;
  String? _cameraError;
  bool _analyzing = false;
  DateTime _lastAnalysis = DateTime.fromMillisecondsSinceEpoch(0);
  int _readyStreak = 0;
  MarkerDetection _det = MarkerDetection.none;
  bool _sending = false;
  bool _autoShoot = true;
  bool _torch = false;
  int _sessionCount = 0;
  ScanResult? _last;

  static const _analysisEvery = Duration(milliseconds: 250);
  static const _streakToReady = 3; // ~0,75 s estável → pronto
  static const _streakToShoot = 5; // ~1,25 s estável → disparo automático

  GuideState get _state {
    if (_sending) return GuideState.sending;
    if (_det.tooFar) return GuideState.tooFar;
    if (!_det.ready) return GuideState.searching;
    return _readyStreak >= _streakToReady ? GuideState.ready : GuideState.steady;
  }

  String get _message => switch (_state) {
        GuideState.searching => 'Enquadre a folha inteira: os 4 quadrados pretos precisam aparecer',
        GuideState.tooFar => 'Aproxime o celular da folha',
        GuideState.steady => 'Segure firme…',
        GuideState.ready => _autoShoot ? 'Fotografando…' : 'Pronto! Toque no botão',
        GuideState.sending => 'Corrigindo…',
      };

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initCamera();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _cam?.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final cam = _cam;
    if (cam == null || !cam.value.isInitialized) return;
    if (state == AppLifecycleState.inactive) {
      cam.dispose();
      _cam = null;
    } else if (state == AppLifecycleState.resumed) {
      _initCamera();
    }
  }

  Future<void> _initCamera() async {
    try {
      final cams = await availableCameras();
      final back = cams.firstWhere((c) => c.lensDirection == CameraLensDirection.back, orElse: () => cams.first);
      final cam = CameraController(
        back,
        ResolutionPreset.veryHigh, // ~1080p: QR legível e upload leve
        enableAudio: false,
        imageFormatGroup: Platform.isIOS ? ImageFormatGroup.bgra8888 : ImageFormatGroup.yuv420,
      );
      await cam.initialize();
      await cam.setFlashMode(FlashMode.off);
      if (!mounted) return cam.dispose();
      setState(() {
        _cam = cam;
        _cameraError = null;
        _torch = false;
      });
      await _startStream();
    } on CameraException catch (e) {
      setState(() => _cameraError = e.code == 'CameraAccessDenied'
          ? 'Permita o acesso à câmera nas configurações do aparelho.'
          : 'Não foi possível abrir a câmera (${e.description ?? e.code}).');
    } catch (e) {
      setState(() => _cameraError = 'Nenhuma câmera disponível ($e).');
    }
  }

  Future<void> _startStream() async {
    final cam = _cam;
    if (cam == null || cam.value.isStreamingImages) return;
    _readyStreak = 0;
    await cam.startImageStream(_onFrame);
  }

  void _onFrame(CameraImage img) {
    final now = DateTime.now();
    if (_analyzing || _sending || now.difference(_lastAnalysis) < _analysisEvery) return;
    _analyzing = true;
    _lastAnalysis = now;
    // reduz aqui (barato) e só manda ~130 KB para o isolate
    final p = img.planes.first;
    final gray = downsample(p.bytes, img.width, img.height,
        rowStride: p.bytesPerRow,
        pixelStride: Platform.isIOS ? 4 : (p.bytesPerPixel ?? 1),
        channelOffset: Platform.isIOS ? 1 : 0);
    Isolate.run(() => detectMarkers(gray)).then((det) {
      if (!mounted) return;
      setState(() {
        _det = det;
        _readyStreak = det.ready ? _readyStreak + 1 : 0;
      });
      if (det.ready && _readyStreak == _streakToReady) HapticFeedback.selectionClick();
      if (_autoShoot && _readyStreak >= _streakToShoot) unawaited(_shoot());
    }).whenComplete(() {
      _analyzing = false;
    });
  }

  Future<void> _shoot() async {
    final cam = _cam;
    if (cam == null || _sending) return;
    setState(() => _sending = true);
    try {
      if (cam.value.isStreamingImages) await cam.stopImageStream();
      final shot = await cam.takePicture();
      final result = await widget.api.scan(File(shot.path));
      File(shot.path).delete().ignore(); // não guarda foto de aluno no aparelho
      HapticFeedback.mediumImpact();
      _sessionCount++;
      _last = result;
      if (!mounted) return;
      final openPanel = widget.onOpenPanel;
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => ResultScreen(
                result: result,
                onOpenInPanel: openPanel == null ? null : () => openPanel('/correcoes/${result.scanId}'),
              )));
    } on ApiException catch (e) {
      if (e.isAuth) return _goLogin(e.message);
      HapticFeedback.heavyImpact();
      if (mounted) await _showError(e);
    } on CameraException catch (e) {
      if (mounted) await _showError(ApiException('Falha ao fotografar: ${e.description ?? e.code}'));
    } finally {
      if (mounted) {
        setState(() {
          _sending = false;
          _det = MarkerDetection.none;
          _readyStreak = 0;
        });
        await _startStream();
      }
    }
  }

  Future<void> _showError(ApiException e) => showModalBottomSheet<void>(
        context: context,
        showDragHandle: true,
        builder: (ctx) => Padding(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 28),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(e.isRetakeable ? 'Tire a foto de novo' : 'Não deu certo',
                style: Theme.of(ctx).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            Text(e.message),
            if (e.hint != null) ...[
              const SizedBox(height: 8),
              Text(e.hint!, style: const TextStyle(fontWeight: FontWeight.w600)),
            ],
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Entendi')),
            ),
          ]),
        ),
      );

  Future<void> _goLogin(String message) async {
    await widget.api.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => LoginScreen(api: widget.api, message: message)), (_) => false);
  }

  Future<void> _toggleTorch() async {
    final cam = _cam;
    if (cam == null) return;
    try {
      await cam.setFlashMode(_torch ? FlashMode.off : FlashMode.torch);
      setState(() => _torch = !_torch);
    } on CameraException {/* aparelho sem lanterna */}
  }

  void _focusAt(TapDownDetails d, BoxConstraints c) {
    final cam = _cam;
    if (cam == null) return;
    final p = Offset(d.localPosition.dx / c.maxWidth, d.localPosition.dy / c.maxHeight);
    cam.setFocusPoint(p).catchError((_) {});
    cam.setExposurePoint(p).catchError((_) {});
  }

  @override
  Widget build(BuildContext context) {
    final cam = _cam;
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Stack(children: [
          if (_cameraError != null)
            Center(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text(_cameraError!, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white)),
                  const SizedBox(height: 16),
                  FilledButton(onPressed: _initCamera, child: const Text('Tentar de novo')),
                ]),
              ),
            )
          else if (cam == null || !cam.value.isInitialized)
            const Center(child: CircularProgressIndicator())
          else
            Center(
              child: AspectRatio(
                aspectRatio: 1 / cam.value.aspectRatio, // retrato
                child: LayoutBuilder(
                  builder: (_, c) => GestureDetector(
                    onTapDown: (d) => _focusAt(d, c),
                    child: Stack(fit: StackFit.expand, children: [
                      CameraPreview(cam),
                      GuideOverlay(state: _state),
                    ]),
                  ),
                ),
              ),
            ),
          // barra superior
          Positioned(
            left: 8,
            right: 8,
            top: 8,
            child: Row(children: [
              IconButton(
                tooltip: 'Sair',
                color: Colors.white,
                icon: const Icon(Icons.logout),
                onPressed: () => _goLogin('Você saiu.'),
              ),
              const Spacer(),
              if (_sessionCount > 0)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(20)),
                  child: Text('$_sessionCount corrigido(s)', style: const TextStyle(color: Colors.white)),
                ),
              const Spacer(),
              IconButton(
                tooltip: 'Lanterna',
                color: Colors.white,
                icon: Icon(_torch ? Icons.flashlight_on : Icons.flashlight_off),
                onPressed: _toggleTorch,
              ),
            ]),
          ),
          // mensagem + botões
          Positioned(
            left: 16,
            right: 16,
            bottom: 20,
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              if (_last != null && !_sending)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Text(
                    'Último: ${_last!.studentName ?? '—'} · ${_fmt(_last!.points)}/${_fmt(_last!.maxPoints)}'
                    '${_last!.reviewNeeded.isEmpty ? '' : ' · revisar no painel'}',
                    style: const TextStyle(color: Colors.white70),
                  ),
                ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(color: Colors.black.withValues(alpha: 0.6), borderRadius: BorderRadius.circular(10)),
                child: Text(_message,
                    textAlign: TextAlign.center,
                    style: TextStyle(color: GuideOverlay.colorFor(_state), fontWeight: FontWeight.w600, fontSize: 15)),
              ),
              const SizedBox(height: 14),
              Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                SizedBox(
                  width: 110,
                  child: Row(children: [
                    Switch(value: _autoShoot, onChanged: (v) => setState(() => _autoShoot = v)),
                    const Flexible(child: Text('Automático', style: TextStyle(color: Colors.white, fontSize: 12))),
                  ]),
                ),
                _ShutterButton(
                  enabled: !_sending && cam != null,
                  highlighted: _state == GuideState.ready,
                  busy: _sending,
                  onTap: _shoot,
                ),
                const SizedBox(width: 110),
              ]),
            ]),
          ),
        ]),
      ),
    );
  }

  static String _fmt(double v) => v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1).replaceAll('.', ',');
}

class _ShutterButton extends StatelessWidget {
  const _ShutterButton({required this.enabled, required this.highlighted, required this.busy, required this.onTap});
  final bool enabled;
  final bool highlighted;
  final bool busy;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = highlighted ? const Color(0xFF3DDC84) : Colors.white;
    return GestureDetector(
      onTap: enabled ? onTap : null,
      child: Container(
        width: 76,
        height: 76,
        decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: color, width: 5)),
        padding: const EdgeInsets.all(5),
        child: busy
            ? const CircularProgressIndicator(color: Colors.white, strokeWidth: 3)
            : DecoratedBox(decoration: BoxDecoration(shape: BoxShape.circle, color: enabled ? color : Colors.white24)),
      ),
    );
  }
}
