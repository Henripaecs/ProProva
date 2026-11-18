# ProProva — app de correção (Flutter)

O app tem duas abas, com um login só:
- **Painel:** o mesmo painel da web (provas, turmas, alunos, impressão, notas, revisão de rasuras), dentro do app.
  Tudo que for adicionado ao painel aparece no app sem precisar montar um app novo. PDFs e CSVs abrem o
  menu de compartilhar do celular (salvar, WhatsApp, imprimir).
- **Corrigir:** câmera com moldura-guia que detecta os 4 quadrados pretos ao vivo e fotografa (sozinha
  ou no botão). A foto vai para `POST /v1/scan`, e o app mostra a nota. Com rasura, o botão
  **Revisar agora** abre a tela de revisão no painel.

```
lib/
  main.dart                  abre no login ou direto nas abas
  screens/home_screen.dart   abas Painel (WebView do painel) e Corrigir (câmera); ponte JS "ProProva"
  api.dart                   login, envio da foto, mensagens de erro com dica
  marker_detector.dart       detector ao vivo (Dart puro, roda num Isolate)
  screens/login_screen.dart  servidor + e-mail + senha
  screens/scan_screen.dart   câmera, moldura, disparo automático, lanterna, toque para focar
  screens/result_screen.dart nota, acertos/erros, questões pendentes
  widgets/guide_overlay.dart moldura A4 com cantoneiras (cinza/laranja/azul/verde)
test/marker_detector_test.dart
setup_platforms.py           cria android/ e ios/ e aplica as permissões
```

## Primeira vez
Requer Flutter 3.27 ou mais novo.
```powershell
cd mobile
python setup_platforms.py      # flutter create + permissões de câmera e rede local
flutter pub get
flutter test                   # testes do detector de marcadores
flutter run                    # com o celular conectado por USB
```

## Usando
1. No computador, rode a API escutando na rede (não só em 127.0.0.1):
   `python -m uvicorn main:app --host 0.0.0.0 --port 8000`
2. Descubra o IP do computador (`ipconfig` no Windows) e, no app, informe em **Servidor**,
   por exemplo `192.168.0.10:8000`. Celular e computador na mesma rede Wi-Fi.
   Se o Windows perguntar, libere o Python no Firewall para redes privadas.
3. Entre com a mesma conta do painel.
4. Aponte para o cartão: a moldura fica **laranja** se estiver longe, **azul** enquanto estabiliza
   e **verde** quando está pronto. No modo automático a foto sai sozinha após ~1 s estável.

## Como o detector ao vivo funciona
Ele só serve para guiar a foto; a leitura de verdade é feita no servidor, em alta resolução.
A cada 250 ms o frame é reduzido para ~480 px. Escuro é tudo abaixo de 62% da média local, o que
aguenta sombra e luz amarela. Em seguida o detector procura **quadrados** sólidos cercados de papel
claro. O teste (maior distância ao centro)² ÷ área dá 0,50 para quadrado e 0,32 para círculo, então
bolhas preenchidas não enganam. Por fim, escolhe 4 quadrados que formem um quadrilátero com a proporção
do A4. A folha precisa ocupar pelo menos 15% do quadro, senão o app pede para aproximar.

O mesmo algoritmo existe em Python em `tools/live_detector_reference.py`. Use-o para calibrar com
fotos reais (`python tools/live_detector_reference.py fotos/*.jpeg`). Nas fotos de teste do projeto
ele aceitou as 5 boas e recusou a que tem um canto cortado; em 16 fotos sintéticas, aceitou todas e
recusou todas com um canto tapado.

## Privacidade
A foto é apagada do celular logo depois do envio. O app guarda só o endereço do servidor, o
e-mail e o token de acesso (que expira em 12 h).

## Com o servidor na internet
Com o sistema publicado (veja `servidor-pc/LEIA-ME.md`), digite em **Servidor** só o endereço, por exemplo
`proprova.tail1234.ts.net`. O app usa HTTPS automaticamente para nomes e HTTP para `IP:porta` da rede
local. Depois disso, o app funciona no 4G, de qualquer lugar.
