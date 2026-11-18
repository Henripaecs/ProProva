"""
Gera as pastas android/ e ios/ do app e aplica as permissões necessárias. Rode UMA vez:

    cd mobile
    python setup_platforms.py

O que faz:
  1. flutter create --platforms=android,ios .   (não sobrescreve lib/ nem pubspec.yaml)
  2. Android: permissão de CÂMERA/INTERNET e HTTP liberado na rede local (desenvolvimento)
  3. iOS: textos de permissão da câmera e da rede local
  4. remove o test/widget_test.dart de exemplo (ele referencia um app que não existe)
É seguro rodar de novo: cada ajuste só é aplicado se ainda não estiver lá.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


APP_NAME = "ProProva"   # nome exibido embaixo do ícone (o pacote interno continua omr_scanner)


def patch_android_manifest(xml: str) -> str:
    xml = re.sub(r'android:label="[^"]*"', f'android:label="{APP_NAME}"', xml, count=1)
    for perm in ("android.permission.CAMERA", "android.permission.INTERNET"):
        if perm not in xml:
            xml = xml.replace("<application", f'<uses-permission android:name="{perm}"/>\n    <application', 1)
    if "usesCleartextTraffic" not in xml:
        # HTTP sem TLS só para falar com o computador na rede local durante o desenvolvimento.
        # Em produção use HTTPS e remova esta linha.
        xml = re.sub(r"<application(\s)", r'<application android:usesCleartextTraffic="true"\1', xml, count=1)
    return xml


IOS_KEYS = {
    "NSCameraUsageDescription": "A câmera é usada para fotografar os cartões-resposta das provas.",
    "NSLocalNetworkUsageDescription": "O app envia as fotos para o servidor da escola na rede local.",
    "NSPhotoLibraryUsageDescription": "Para anexar imagens às questões da prova.",
}


def patch_info_plist(plist: str) -> str:
    for key in ("CFBundleDisplayName", "CFBundleName"):
        plist = re.sub(rf"(<key>{key}</key>\s*<string>)[^<]*(</string>)", rf"\g<1>{APP_NAME}\g<2>", plist)
    add = "".join(f"\t<key>{k}</key>\n\t<string>{v}</string>\n" for k, v in IOS_KEYS.items() if k not in plist)
    if "NSAppTransportSecurity" not in plist:
        add += ("\t<key>NSAppTransportSecurity</key>\n\t<dict>\n"
                "\t\t<key>NSAllowsLocalNetworking</key>\n\t\t<true/>\n\t</dict>\n")
    if not add:
        return plist
    i = plist.rindex("</dict>")
    return plist[:i] + add + plist[i:]


CAMERAX_FIX_KTS = """
// ProProva: o plugin camera_android_camerax usa androidx.concurrent:concurrent-futures sem declarar;
// o javac do JDK 22+ exige essa classe ao ler as anotações do camera-core 1.5.x (erro
// "Cannot attach type annotations ... CallbackToFutureAdapter not found"). Funciona com qualquer JDK.
subprojects {
    if (name == "camera_android_camerax") {
        plugins.withId("com.android.library") {
            dependencies.add("implementation", "androidx.concurrent:concurrent-futures:1.2.0")
        }
    }
}
"""

CAMERAX_FIX_GROOVY = """
// ProProva: dependência que o camera_android_camerax usa sem declarar (erro com JDK 22+).
subprojects {
    if (it.name == "camera_android_camerax") {
        it.plugins.withId("com.android.library") {
            it.dependencies.add("implementation", "androidx.concurrent:concurrent-futures:1.2.0")
        }
    }
}
"""


def patch_root_gradle(text: str, kotlin: bool) -> str:
    if "concurrent-futures" in text:
        return text
    return text.rstrip() + "\n" + (CAMERAX_FIX_KTS if kotlin else CAMERAX_FIX_GROOVY)


def main() -> None:
    flutter = shutil.which("flutter")
    if not flutter:
        sys.exit("Flutter não encontrado no PATH. Instale: https://docs.flutter.dev/get-started/install")
    if not (ROOT / "android").exists() or not (ROOT / "ios").exists():
        subprocess.run([flutter, "create", "--platforms=android,ios", "--org", "br.escola.omr",
                        "--project-name", "omr_scanner", "."], cwd=ROOT, check=True, shell=sys.platform == "win32")
    (ROOT / "test" / "widget_test.dart").unlink(missing_ok=True)

    manifest = ROOT / "android/app/src/main/AndroidManifest.xml"
    manifest.write_text(patch_android_manifest(manifest.read_text(encoding="utf-8")), encoding="utf-8")
    for name, kotlin in (("build.gradle.kts", True), ("build.gradle", False)):
        root_gradle = ROOT / "android" / name
        if root_gradle.exists():
            root_gradle.write_text(patch_root_gradle(root_gradle.read_text(encoding="utf-8"), kotlin), encoding="utf-8")
    plist = ROOT / "ios/Runner/Info.plist"
    plist.write_text(patch_info_plist(plist.read_text(encoding="utf-8")), encoding="utf-8")
    print("Pronto. Agora:  flutter pub get  →  flutter test  →  flutter run")


if __name__ == "__main__":
    main()
