// Ponte com o app ProProva (Flutter). Dentro do app, o painel roda numa WebView que injeta
// `window.ProProva.postMessage(texto)`. Fora do app, nada disto faz efeito.

type AppMessage =
  | { type: "scan" }                                           // abrir a câmera nativa
  | { type: "logout"; expired?: boolean }                      // voltar ao login do app
  | { type: "download"; filename: string; data: string };      // arquivo (data URL) para compartilhar/salvar

type Bridge = { postMessage: (msg: string) => void };

function bridge(): Bridge | null {
  if (typeof window === "undefined") return null;
  const b = (window as unknown as { ProProva?: Bridge }).ProProva;
  return b && typeof b.postMessage === "function" ? b : null;
}

export function isApp(): boolean {
  return bridge() !== null;
}

export function appPost(msg: AppMessage): boolean {
  const b = bridge();
  if (!b) return false;
  b.postMessage(JSON.stringify(msg));
  return true;
}

/** No app, entrega o arquivo para o celular (compartilhar/salvar/imprimir). */
export async function appDownload(blob: Blob, filename: string): Promise<boolean> {
  if (!isApp()) return false;
  const data = await new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
  return appPost({ type: "download", filename, data });
}
