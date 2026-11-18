import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ProProva — painel do professor",
  description: "Crie provas, imprima por turma e corrija por foto.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
