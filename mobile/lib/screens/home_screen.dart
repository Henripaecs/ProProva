import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

import '../api.dart';
import 'login_screen.dart';
import 'scan_screen.dart';

/// Tela principal: aba "Painel" (o mesmo painel da web, numa WebView) + aba "Corrigir" (câmera nativa).
/// O login é um só: o token do app é entregue ao painel por /app#t=<token>.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.api});
  final Api api;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final WebViewController _web;
  int _tab = 0;
  bool _loading = true;
  String? _webError;

  String get _base => widget.api.baseUrl;

  @override
  void initState() {
    super.initState();
    _web = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFFF7F5EF))
      ..addJavaScriptChannel('ProProva', onMessageReceived: (m) => _onWebMessage(m.message))
      ..setNavigationDelegate(NavigationDelegate(
        onPageStarted: (_) {
          if (mounted) setState(() => _loading = true);
        },
        onPageFinished: (_) {
          if (mounted) setState(() => _loading = false);
        },
        onWebResourceError: (e) {
          if (e.isForMainFrame == true && mounted) {
            setState(() => _webError = 'Não foi possível abrir o painel (${e.description}).');
          }
        },
        // Só navega dentro do próprio servidor; links externos ficam bloqueados.
        onNavigationRequest: (req) =>
            req.url.startsWith(_base) || req.url.startsWith('about:') || req.url.startsWith('data:')
                ? NavigationDecision.navigate
                : NavigationDecision.prevent,
      ));
    final platform = _web.platform;
    if (platform is AndroidWebViewController) {
      platform.setOnShowFileSelector(_pickFiles); // "Anexar imagem" do editor no Android
    }
    _web.loadRequest(_entryUri('/provas'));
  }

  Uri _entryUri(String path) {
    final token = Uri.encodeComponent(widget.api.token ?? '');
    return Uri.parse('$_base/app#t=$token&dest=${Uri.encodeComponent(path)}');
  }

  /// Abre uma página do painel (ex.: /correcoes/<id>) e mostra a aba Painel.
  void _openPanel(String path) {
    setState(() {
      _webError = null;
      _tab = 0;
    });
    _web.loadRequest(_entryUri(path));
  }

  Future<List<String>> _pickFiles(FileSelectorParams params) async {
    final picked = await ImagePicker().pickImage(source: ImageSource.gallery, maxWidth: 2400);
    if (picked == null) return <String>[];
    return <String>[Uri.file(picked.path).toString()];
  }

  Future<void> _onWebMessage(String raw) async {
    Map<String, dynamic> msg;
    try {
      msg = jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      return;
    }
    switch (msg['type']) {
      case 'scan':
        setState(() => _tab = 1);
      case 'logout':
        await widget.api.logout();
        if (!mounted) return;
        final expired = msg['expired'] == true;
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(
              builder: (_) => LoginScreen(api: widget.api, message: expired ? 'Sessão expirada. Entre de novo.' : null)),
          (_) => false,
        );
      case 'download':
        await _saveAndShare(msg['filename'] as String? ?? 'arquivo', msg['data'] as String? ?? '');
    }
  }

  /// PDF/ZIP/CSV do painel → arquivo temporário → menu de compartilhar (salvar, WhatsApp, imprimir…).
  Future<void> _saveAndShare(String filename, String dataUrl) async {
    final comma = dataUrl.indexOf(',');
    if (comma < 0) return;
    try {
      final bytes = base64Decode(dataUrl.substring(comma + 1));
      final safe = filename.replaceAll(RegExp(r'[^\w\-. ]'), '_');
      final file = File('${(await getTemporaryDirectory()).path}/$safe');
      await file.writeAsBytes(bytes, flush: true);
      await Share.shareXFiles([XFile(file.path)], subject: filename);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Não foi possível abrir o arquivo: $e')));
    }
  }

  Future<void> _onBack() async {
    if (_tab == 1) {
      setState(() => _tab = 0);
    } else if (await _web.canGoBack()) {
      await _web.goBack();
    } else {
      await SystemNavigator.pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _onBack();
      },
      child: Scaffold(
        body: IndexedStack(index: _tab, children: [
          SafeArea(
            child: Stack(children: [
              WebViewWidget(controller: _web),
              if (_loading) const LinearProgressIndicator(minHeight: 2),
              if (_webError != null)
                Container(
                  color: const Color(0xFFF7F5EF),
                  alignment: Alignment.center,
                  padding: const EdgeInsets.all(32),
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Text(_webError!, textAlign: TextAlign.center),
                    const SizedBox(height: 8),
                    const Text('O computador com o sistema está ligado?', style: TextStyle(color: Colors.black54)),
                    const SizedBox(height: 16),
                    FilledButton(onPressed: () => _openPanel('/provas'), child: const Text('Tentar de novo')),
                  ]),
                ),
            ]),
          ),
          // a câmera só existe enquanto a aba está aberta (libera a câmera e a bateria)
          _tab == 1
              ? ScanScreen(api: widget.api, onOpenPanel: _openPanel)
              : const SizedBox.shrink(),
        ]),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _tab,
          onDestinationSelected: (i) => setState(() => _tab = i),
          destinations: const [
            NavigationDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: 'Painel'),
            NavigationDestination(icon: Icon(Icons.photo_camera_outlined), selectedIcon: Icon(Icons.photo_camera), label: 'Corrigir'),
          ],
        ),
      ),
    );
  }
}
