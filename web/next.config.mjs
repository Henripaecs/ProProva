/** @type {import('next').NextConfig} */
const API_INTERNAL_URL = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  // "standalone" gera um servidor enxuto para o Docker (deploy/). No PC usa-se o `npm start` normal.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  images: { unoptimized: true },
  // Um endereço só: o painel repassa /v1/* e /health para a API (usado no PC + Tailscale).
  // Com NEXT_PUBLIC_API_URL="" no build, painel e app falam com a API pela mesma origem.
  async rewrites() {
    return [
      { source: "/v1/:path*", destination: `${API_INTERNAL_URL}/v1/:path*` },
      { source: "/health", destination: `${API_INTERNAL_URL}/health` },
    ];
  },
  experimental: {
    proxyTimeout: 300_000,               // PDF de turma grande pode levar mais que os 30 s padrão
    middlewareClientMaxBodySize: "20mb", // fotos do cartão passam pelo repasse /v1 (padrão: 10 MB, cortaria a foto)
  },
};
export default nextConfig;
