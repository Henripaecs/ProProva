import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  final api = await Api.load();
  runApp(OmrApp(api: api));
}

class OmrApp extends StatelessWidget {
  const OmrApp({super.key, required this.api});
  final Api api;

  static const ink = Color(0xFF1B2430);
  static const pen = Color(0xFF1F4FA3);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ProProva',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: pen, surface: const Color(0xFFF7F5EF)),
        scaffoldBackgroundColor: const Color(0xFFF7F5EF),
        useMaterial3: true,
      ),
      home: api.loggedIn ? HomeScreen(api: api) : LoginScreen(api: api),
    );
  }
}
