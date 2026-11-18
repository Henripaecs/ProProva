import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Erro amigável para mostrar na tela (o servidor manda `message` + `hint` nos erros de leitura).
class ApiException implements Exception {
  ApiException(this.message, {this.hint, this.code, this.status});
  final String message;
  final String? hint;
  final String? code;
  final int? status;

  bool get isAuth => status == 401;

  /// Foto ruim (marcadores/QR/desfoque): vale tentar de novo com outra foto.
  bool get isRetakeable => status == 422;

  @override
  String toString() => hint == null ? message : '$message\n$hint';
}

class ScanResult {
  ScanResult({required this.scanId, required this.points, required this.maxPoints, required this.correct,
      required this.wrong, required this.blank, required this.pending, required this.reviewNeeded});

  final String scanId;
  final double points;
  final double maxPoints;
  final int correct;
  final int wrong;
  final int blank;
  final int pending;
  final List<int> reviewNeeded;
  String? studentName;
  String? examTitle;

  factory ScanResult.fromJson(Map<String, dynamic> j) {
    final s = j['score'] as Map<String, dynamic>;
    return ScanResult(
      scanId: j['scan_id'] as String,
      points: (s['points'] as num).toDouble(),
      maxPoints: (s['max_points'] as num).toDouble(),
      correct: s['correct'] as int,
      wrong: s['wrong'] as int,
      blank: s['blank'] as int,
      pending: s['pending'] as int,
      reviewNeeded: (j['review_needed'] as List).cast<int>(),
    );
  }
}

/// Cliente da API FastAPI. Endereço e token ficam salvos no aparelho.
class Api {
  Api._(this._prefs);
  final SharedPreferences _prefs;

  static const _kBase = 'api.base';
  static const _kToken = 'api.token';
  static const _kEmail = 'api.email';

  static Future<Api> load() async => Api._(await SharedPreferences.getInstance());

  String get baseUrl => _prefs.getString(_kBase) ?? '';
  String? get token => _prefs.getString(_kToken);
  String get lastEmail => _prefs.getString(_kEmail) ?? '';
  bool get loggedIn => token != null && baseUrl.isNotEmpty;

  Future<void> logout() => _prefs.remove(_kToken);

  Uri _uri(String path) => Uri.parse('${baseUrl.replaceAll(RegExp(r'/+$'), '')}/v1$path');

  /// "192.168.0.10:8000" → http:// (rede local);  "proprova.tail1234.ts.net" → https:// (internet).
  static String normalizeBase(String raw) {
    var b = raw.trim();
    if (b.isEmpty) return b;
    if (!b.startsWith('http://') && !b.startsWith('https://')) {
      final host = b.split('/').first;
      final local = RegExp(r'^(\d{1,3}\.){3}\d{1,3}(:\d+)?$').hasMatch(host) || host.startsWith('localhost');
      b = '${local ? 'http' : 'https'}://$b';
    }
    // Fica só com "https://host[:porta]": quem cola o link do painel (…/provas) não quebra o app.
    final uri = Uri.tryParse(b);
    if (uri != null && uri.hasAuthority) {
      return '${uri.scheme}://${uri.host}${uri.hasPort ? ':${uri.port}' : ''}';
    }
    return b.replaceAll(RegExp(r'/+$'), '');
  }

  Future<void> login(String base, String email, String password) async {
    await _prefs.setString(_kBase, normalizeBase(base));
    final res = await _send(() => http.post(_uri('/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email.trim(), 'password': password})));
    await _prefs.setString(_kToken, (jsonDecode(res.body) as Map<String, dynamic>)['token'] as String);
    await _prefs.setString(_kEmail, email.trim());
  }

  Map<String, String> get _auth => {'Authorization': 'Bearer ${token ?? ''}'};

  /// Envia a foto do cartão. O QR Code diz de que prova/aluno ela é.
  Future<ScanResult> scan(File photo) async {
    final req = http.MultipartRequest('POST', _uri('/scan'))
      ..headers.addAll(_auth)
      ..files.add(await http.MultipartFile.fromPath('file', photo.path, filename: 'cartao.jpg'));
    final res = await _send(() async => http.Response.fromStream(await req.send()), timeout: 90);
    final result = ScanResult.fromJson(jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>);
    try {
      // nome do aluno e título da prova (só para exibir)
      final d = await _send(() => http.get(_uri('/scans/${result.scanId}'), headers: _auth));
      final j = jsonDecode(utf8.decode(d.bodyBytes)) as Map<String, dynamic>;
      result.studentName = j['student_name'] as String?;
      result.examTitle = j['exam_title'] as String?;
    } catch (_) {/* cosmético */}
    return result;
  }

  Future<http.Response> _send(Future<http.Response> Function() call, {int timeout = 20}) async {
    if (baseUrl.isEmpty) throw ApiException('Informe o endereço do servidor.');
    http.Response res;
    try {
      res = await call().timeout(Duration(seconds: timeout));
    } on TimeoutException {
      throw ApiException('O servidor demorou para responder.', hint: 'Confira a conexão e tente de novo.');
    } on SocketException {
      throw ApiException('Sem conexão com o servidor.',
          hint: 'Confira o Wi-Fi e o endereço ($baseUrl). Celular e computador precisam estar na mesma rede.');
    } on http.ClientException catch (e) {
      throw ApiException('Falha de conexão: ${e.message}');
    }
    if (res.statusCode >= 200 && res.statusCode < 300) return res;

    String message = 'Erro ${res.statusCode}';
    String? hint, code;
    try {
      final j = jsonDecode(utf8.decode(res.bodyBytes));
      if (j is Map<String, dynamic>) {
        if (j['message'] is String) message = j['message'] as String;
        if (j['hint'] is String) hint = j['hint'] as String;
        if (j['code'] is String) code = j['code'] as String;
        if (j['detail'] is String) message = j['detail'] as String;
      }
    } catch (_) {}
    if (res.statusCode == 401) {
      await logout();
      message = res.request?.url.path.endsWith('/auth/login') == true ? 'E-mail ou senha inválidos.' : 'Sessão expirada. Entre de novo.';
    }
    throw ApiException(message, hint: hint, code: code, status: res.statusCode);
  }
}
